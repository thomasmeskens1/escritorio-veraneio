"""Projetos do Gestor em livro-razão (.md): plano, etapas e passagem salvos em disco.

Cada etapa roda separada e é gravada assim que termina. Se o modelo trocar no meio do caminho,
o próximo lê o plano e a passagem e continua da primeira etapa pendente: nada se perde nem é refeito.
"""

import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Callable

import config

PASTA_PROJETOS = config.ARQUIVO_BANCO.parent / "projetos"
EQUIPE = {"designer": "Designer", "moviemaker": "Moviemaker", "gestor_trafego": "Gestor de Tráfego"}
MAX_ETAPAS = 6
TRECHO_ETAPA = 1500   # caracteres de cada etapa anterior enviados à próxima
TRECHO_FINAL = 2500   # caracteres de cada etapa enviados à consolidação
PALAVRAS_ETAPA = 400  # limite pedido a cada etapa (tempo e tokens)
PALAVRAS_FINAL = 800


class Cancelado(Exception):
    """A tentativa estourou o tempo; o próximo modelo retoma do livro-razão."""


# Executa um agente: (agente_id, descrição da tarefa, saída esperada, papel "gestor"|"equipe") -> texto
Executar = Callable[[str, str, str, str], str]


def _gravar(arquivo: Path, texto: str) -> None:
    """Gravação atômica; se outra tentativa já gravou, mantém a primeira."""
    if arquivo.exists():
        return
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(texto, encoding="utf-8")
    temporario.replace(arquivo)


def _chave(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", sem_acento.lower())


# Aceita o id ("gestor_trafego") ou o nome ("Gestor de Tráfego"), sem diferenciar maiúsculas/acentos.
_IDS_POR_CHAVE = {**{_chave(i): i for i in EQUIPE}, **{_chave(n): i for i, n in EQUIPE.items()}}


def _extrair_plano(texto: str) -> list[dict]:
    bloco = re.search(r"\[.*\]", texto, re.DOTALL)
    if not bloco:
        raise ValueError("O Gestor não devolveu um plano em JSON.")
    plano = []
    for passo in json.loads(bloco.group(0)):
        agente = _IDS_POR_CHAVE.get(_chave(passo.get("agente", ""))) if isinstance(passo, dict) else None
        if agente:
            plano.append({"agente": agente, "instrucao": str(passo.get("instrucao", ""))})
    if not plano:
        raise ValueError("Plano sem etapas válidas.")
    return plano[:MAX_ETAPAS]


def _plano(pasta: Path, pedido: str, contexto: str, executar: Executar) -> list[dict]:
    arquivo = pasta / "plano.json"
    if not arquivo.exists():
        equipe = ", ".join(f"{i} ({nome})" for i, nome in EQUIPE.items())
        descricao = (
            f"{contexto}\n\nPedido do usuário: {pedido}\n\n"
            f"Divida o trabalho em até {MAX_ETAPAS} etapas para a sua equipe: {equipe}. "
            "Ordene as etapas de forma que cada uma possa usar o resultado das anteriores. "
            'Responda SOMENTE com um JSON: [{"agente": "<id>", "instrucao": "<o que entregar>"}].'
        )
        plano = _extrair_plano(executar("gestor", descricao, "JSON com a lista de etapas.", "gestor"))
        _gravar(arquivo, json.dumps(plano, ensure_ascii=False, indent=2))
        linhas = [f"{n}. **{EQUIPE[p['agente']]}**: {p['instrucao']}" for n, p in enumerate(plano, 1)]
        _gravar(pasta / "plano.md", f"# Plano\n\nPedido: {pedido}\n\n" + "\n".join(linhas) + "\n")
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _arquivo_etapa(pasta: Path, numero: int, agente: str) -> Path:
    return pasta / "etapas" / f"{numero:02d}-{agente}.md"


def _passagem(pasta: Path, plano: list[dict]) -> str:
    """Resumo curto do andamento: o que já foi feito e o que falta."""
    linhas = []
    for n, passo in enumerate(plano, 1):
        arquivo = _arquivo_etapa(pasta, n, passo["agente"])
        if arquivo.exists():
            inicio = arquivo.read_text(encoding="utf-8")[:300].replace("\n", " ")
            linhas.append(f"- [x] {n}. {EQUIPE[passo['agente']]}: {inicio}...")
        else:
            linhas.append(f"- [ ] {n}. {EQUIPE[passo['agente']]}: {passo['instrucao']}")
    texto = "# Passagem\n\n" + "\n".join(linhas) + "\n"
    (pasta / "passagem.md").write_text(texto, encoding="utf-8")
    return texto


def executar_projeto(tarefa_id: int, pedido: str, contexto: str, executar: Executar,
                     cancelar: threading.Event) -> str:
    pasta = PASTA_PROJETOS / str(tarefa_id)
    (pasta / "etapas").mkdir(parents=True, exist_ok=True)
    plano = _plano(pasta, pedido, contexto, executar)

    for n, passo in enumerate(plano, 1):
        arquivo = _arquivo_etapa(pasta, n, passo["agente"])
        if arquivo.exists():
            continue  # feita por uma tentativa anterior (talvez outro modelo)
        if cancelar.is_set():
            raise Cancelado
        anteriores = "\n\n".join(
            f"## Etapa {i} ({EQUIPE[p['agente']]})\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_ETAPA]}"
            for i, p in enumerate(plano[:n - 1], 1)
        )
        descricao = (
            f"{contexto}\n\nProjeto: {pedido}\n\n{_passagem(pasta, plano)}\n"
            f"Resultados das etapas anteriores:\n{anteriores or '(nenhuma)'}\n\n"
            f"Sua etapa ({n}): {passo['instrucao']}\n\n"
            f"Seja objetivo: até ~{PALAVRAS_ETAPA} palavras, só o essencial para as próximas etapas."
        )
        _gravar(arquivo, executar(passo["agente"], descricao, "Entrega completa desta etapa.", "equipe"))
        _passagem(pasta, plano)

    final = pasta / "final.md"
    if not final.exists():
        if cancelar.is_set():
            raise Cancelado
        entregas = "\n\n".join(
            f"## {EQUIPE[p['agente']]}\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_FINAL]}"
            for i, p in enumerate(plano, 1)
        )
        descricao = (f"{contexto}\n\nPedido do usuário: {pedido}\n\nEntregas da equipe:\n{entregas}\n\n"
                     f"Revise e consolide tudo numa entrega final coerente para o usuário (até ~{PALAVRAS_FINAL} palavras).")
        _gravar(final, executar("gestor", descricao, "Entrega final consolidada e revisada.", "gestor"))
    return final.read_text(encoding="utf-8")
