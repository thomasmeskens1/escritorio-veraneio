"""Projetos do Gestor em livro-razão (.md): plano, etapas e passagem salvos em disco.

Cada etapa roda separada e é gravada assim que termina. Se o modelo trocar no meio do caminho,
o próximo lê o plano e a passagem e continua da primeira etapa pendente: nada se perde nem é refeito.
"""

import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import config
from agents.perfis import ESTILO_CHAT
from estado import ANDARES

PASTA_PROJETOS = config.ARQUIVO_BANCO.parent / "projetos"
MAX_ETAPAS = 8  # micro-tarefas: cada especialista com uma entrega focada
TRECHO_ETAPA = 1500   # caracteres de cada etapa anterior enviados à próxima
TRECHO_FINAL = 2500   # caracteres de cada etapa enviados à consolidação
PALAVRAS_ETAPA = 400  # limite pedido a cada etapa (tempo e tokens)
PALAVRAS_FINAL = 800
MAX_PARALELAS = 4      # etapas da mesma fase rodando ao mesmo tempo (limite dos modelos gratuitos)


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


def equipe() -> dict[str, str]:
    """Especialistas do andar do Gestor (id -> nome), incluindo os criados pelo Construtor."""
    return {i: a.nome for i, a in ANDARES["marketing"].items() if a.tipo == "ia" and i != "gestor"}


def _nome(agente_id: str) -> str:
    return equipe().get(agente_id, agente_id)


def _extrair_plano(texto: str) -> tuple[list[dict], str]:
    """(etapas, título curto do projeto). Etapas: agente, instrução e fase (mesma fase = rodam juntas)."""
    bloco = re.search(r"\[.*\]", texto, re.DOTALL)
    if not bloco:
        raise ValueError("O Gestor não devolveu um plano em JSON.")
    # Aceita o id ("gestor_trafego") ou o nome ("Gestor de Tráfego"), sem diferenciar maiúsculas/acentos.
    time = equipe()
    ids_por_chave = {**{_chave(i): i for i in time}, **{_chave(n): i for i, n in time.items()}}
    plano = []
    for passo in json.loads(bloco.group(0)):
        agente = ids_por_chave.get(_chave(passo.get("agente", ""))) if isinstance(passo, dict) else None
        if agente:
            fase = passo.get("fase")
            plano.append({"agente": agente, "instrucao": str(passo.get("instrucao", "")),
                          "fase": int(fase) if str(fase).isdigit() and int(fase) > 0 else len(plano) + 1})
    if not plano:
        raise ValueError("Plano sem etapas válidas.")
    titulo = re.search(r'"titulo"\s*:\s*"([^"]{3,80})"', texto)
    return plano[:MAX_ETAPAS], (titulo.group(1).strip() if titulo else "")


def titulo_do_projeto(tarefa_id: int) -> str:
    """Título curto que o Gestor deu ao projeto (nome da pasta de entrega); "" se não houver."""
    arquivo = PASTA_PROJETOS / str(tarefa_id) / "titulo.txt"
    return arquivo.read_text(encoding="utf-8").strip() if arquivo.exists() else ""


def _plano(pasta: Path, pedido: str, contexto: str, executar: Executar) -> list[dict]:
    arquivo = pasta / "plano.json"
    if not arquivo.exists():
        equipe_txt = ", ".join(f"{i} ({nome})" for i, nome in equipe().items())
        descricao = (
            f"{contexto}\n\nPedido do usuário: {pedido}\n\n"
            f"Divida o trabalho em até {MAX_ETAPAS} etapas para a sua equipe: {equipe_txt}. "
            "Prefira micro-tarefas: cada etapa é uma entrega focada de um único especialista "
            "(ex.: post de Lodge = Copywriter escreve o texto da arte e a legenda com os dados do Cérebro, "
            "Criador de Imagens escolhe as fotos reais do acervo, Designer define o layout e o editável; "
            "reels = Moviemaker faz o roteiro, Copywriter os textos de tela, Editor de Vídeo a montagem). "
            "Acione só quem for necessário. "
            "Organize as etapas em FASES para ganhar tempo: etapas que não dependem umas das outras ficam na "
            "mesma fase e rodam ao mesmo tempo (ex.: Copywriter e Criador de Imagens juntos na fase 1); quem "
            "precisa do resultado de outra etapa vai para uma fase seguinte (ex.: Designer na fase 2). Cada etapa "
            "recebe só os resultados das fases anteriores. "
            "Dê também um título curto ao projeto (até 6 palavras, sem data, ex.: \"Post Réveillon Lodge 1\"). "
            'Responda SOMENTE com um JSON: {"titulo": "<título>", "etapas": '
            '[{"agente": "<id>", "instrucao": "<o que entregar>", "fase": <número>}]}.'
        )
        plano, titulo = _extrair_plano(executar("gestor", descricao, "JSON com o título e as etapas.", "gestor"))
        if titulo:
            _gravar(pasta / "titulo.txt", titulo)
        _gravar(arquivo, json.dumps(plano, ensure_ascii=False, indent=2))
        linhas = [f"{n}. **{_nome(p['agente'])}** (fase {p['fase']}): {p['instrucao']}" for n, p in enumerate(plano, 1)]
        _gravar(pasta / "plano.md", f"# Plano\n\nPedido: {pedido}\n\n" + "\n".join(linhas) + "\n")
    return json.loads(arquivo.read_text(encoding="utf-8"))


def agentes_de_producao(tarefa_id: int) -> list[str]:
    """Agentes do plano que entregam arquivo (PNG/MP4) e, por isso, seguem para a produção no Max."""
    from estado import AGENTES_PRODUCAO

    arquivo = PASTA_PROJETOS / str(tarefa_id) / "plano.json"
    if not arquivo.exists():
        return []
    ids = [p["agente"] for p in json.loads(arquivo.read_text(encoding="utf-8"))]
    return [i for i in dict.fromkeys(ids) if i in AGENTES_PRODUCAO]


def _arquivo_etapa(pasta: Path, numero: int, agente: str) -> Path:
    return pasta / "etapas" / f"{numero:02d}-{agente}.md"


def _passagem(pasta: Path, plano: list[dict]) -> str:
    """Resumo curto do andamento: o que já foi feito e o que falta."""
    linhas = []
    for n, passo in enumerate(plano, 1):
        arquivo = _arquivo_etapa(pasta, n, passo["agente"])
        if arquivo.exists():
            inicio = arquivo.read_text(encoding="utf-8")[:300].replace("\n", " ")
            linhas.append(f"- [x] {n}. {_nome(passo['agente'])}: {inicio}...")
        else:
            linhas.append(f"- [ ] {n}. {_nome(passo['agente'])}: {passo['instrucao']}")
    texto = "# Passagem\n\n" + "\n".join(linhas) + "\n"
    (pasta / "passagem.md").write_text(texto, encoding="utf-8")
    return texto


def _sem_aviso(tipo: str, agente: str, detalhe: str) -> None:
    pass


def executar_projeto(tarefa_id: int, pedido: str, contexto: str, executar: Executar,
                     cancelar: threading.Event, avisar: Callable[[str, str, str], None] = _sem_aviso) -> str:
    """`avisar(tipo, agente, detalhe)` recebe etapa_iniciada/etapa_salva (registro e animação do setor)."""
    pasta = PASTA_PROJETOS / str(tarefa_id)
    (pasta / "etapas").mkdir(parents=True, exist_ok=True)
    plano = _plano(pasta, pedido, contexto, executar)
    fase = lambda n, p: p.get("fase", n)  # plano antigo (sem fases): uma etapa por vez

    def rodar_etapa(n: int, passo: dict) -> None:
        if cancelar.is_set():
            raise Cancelado
        anteriores = "\n\n".join(
            f"## Etapa {i} ({_nome(p['agente'])})\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_ETAPA]}"
            for i, p in enumerate(plano, 1) if fase(i, p) < fase(n, passo)
        )
        descricao = (
            f"{contexto}\n\nProjeto: {pedido}\n\n{_passagem(pasta, plano)}\n"
            f"Resultados das etapas anteriores:\n{anteriores or '(nenhuma)'}\n\n"
            f"Sua etapa ({n}): {passo['instrucao']}\n\n"
            f"Seja objetivo: até ~{PALAVRAS_ETAPA} palavras, só o essencial para as próximas etapas."
        )
        detalhe = f"Etapa {n}: {passo['instrucao'][:160]}"
        avisar("etapa_iniciada", passo["agente"], detalhe)
        try:
            _gravar(_arquivo_etapa(pasta, n, passo["agente"]),
                    executar(passo["agente"], descricao, "Entrega completa desta etapa.", "equipe"))
        finally:
            avisar("etapa_encerrada", passo["agente"], detalhe)
        avisar("etapa_salva", passo["agente"], detalhe)

    # Fase a fase; dentro da fase, as etapas rodam ao mesmo tempo (o que já foi feito numa tentativa anterior é pulado).
    for numero_fase in sorted({fase(n, p) for n, p in enumerate(plano, 1)}):
        pendentes = [(n, p) for n, p in enumerate(plano, 1)
                     if fase(n, p) == numero_fase and not _arquivo_etapa(pasta, n, p["agente"]).exists()]
        if pendentes:
            with ThreadPoolExecutor(min(len(pendentes), MAX_PARALELAS)) as pool:
                for futuro in [pool.submit(rodar_etapa, n, p) for n, p in pendentes]:
                    futuro.result()  # repassa erro ou Cancelado (as demais da fase terminam antes)
            _passagem(pasta, plano)

    final = pasta / "final.md"
    if not final.exists():
        if cancelar.is_set():
            raise Cancelado
        entregas = "\n\n".join(
            f"## {_nome(p['agente'])}\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_FINAL]}"
            for i, p in enumerate(plano, 1)
        )
        descricao = (f"{contexto}\n\nPedido do usuário: {pedido}\n\nEntregas da equipe:\n{entregas}\n\n"
                     f"Revise e consolide tudo numa entrega final coerente para o usuário (até ~{PALAVRAS_FINAL} palavras). "
                     f"{ESTILO_CHAT}")
        _gravar(final, executar("gestor", descricao, "Entrega final consolidada e revisada.", "gestor"))
    return final.read_text(encoding="utf-8")
