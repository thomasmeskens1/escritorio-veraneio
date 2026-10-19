"""Diretora: conhecimento da empresa em documentos .md, consultado pelos agentes (nunca pelo usuário).

A busca é local (sem LLM e sem custo de tokens): os documentos são divididos por seção e pontuados
pelas palavras da pergunta (TF-IDF simples). Durante a consulta, a Diretora "visita" o andar do agente.
"""

import asyncio
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

import atividade
from conexoes import gerenciador
from estado import Status, buscar_agente, snapshot

PASTA_CONHECIMENTO = Path(__file__).resolve().parent / "conhecimento"
MAX_TRECHOS = 3
MAX_CARACTERES = 1500
DURACAO_MINIMA_VISITA = 6  # segundos, para a caminhada aparecer na tela

_PALAVRAS_VAZIAS = set("""a o as os de da do das dos e em no na nos nas um uma uns umas para por com sem que qual
quais como se ao aos ou mais menos muito sobre entre ser ter sua seu suas seus nosso nossa isso este esta""".split())

_loop: asyncio.AbstractEventLoop | None = None
_visitas: list[dict] = []  # consultas em andamento, a mais recente por último


def vincular_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Os agentes rodam em threads; a visita precisa do loop principal para avisar o frontend."""
    global _loop
    _loop = loop


# --- Busca --------------------------------------------------------------------------------

def _termos(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return [p for p in re.findall(r"[a-z0-9]{3,}", sem_acento) if p not in _PALAVRAS_VAZIAS]


def _trechos() -> list[tuple[str, str]]:
    """(título, conteúdo) de cada seção de cada documento."""
    trechos = []
    for arquivo in sorted(PASTA_CONHECIMENTO.glob("*.md")):
        titulo_doc = arquivo.stem.replace("_", " ").capitalize()
        for secao in re.split(r"\n(?=#{1,3} )", arquivo.read_text(encoding="utf-8")):
            if secao.strip():
                titulo = secao.strip().splitlines()[0].lstrip("# ").strip()
                trechos.append((f"{titulo_doc} › {titulo}", secao.strip()))
    return trechos


def tem_documentos() -> bool:
    return any(PASTA_CONHECIMENTO.glob("*.md"))


def buscar(pergunta: str) -> str:
    trechos = _trechos()
    if not trechos:
        return "A base de conhecimento da empresa ainda não tem documentos."
    termos_pergunta = set(_termos(pergunta))
    contagens = [Counter(_termos(conteudo)) for _, conteudo in trechos]
    total = len(trechos)

    def pontuacao(contagem: Counter) -> float:
        return sum(contagem[t] * math.log(1 + total / (1 + sum(1 for c in contagens if t in c)))
                   for t in termos_pergunta)

    ranking = sorted(zip(trechos, contagens), key=lambda par: pontuacao(par[1]), reverse=True)
    melhores = [(titulo, conteudo) for (titulo, conteudo), contagem in ranking[:MAX_TRECHOS] if pontuacao(contagem) > 0]
    if not melhores:
        return "Não encontrei nada sobre isso nos documentos da empresa."
    resposta = "\n\n".join(f"[{titulo}]\n{conteudo}" for titulo, conteudo in melhores)
    return resposta[:MAX_CARACTERES]


# --- Visitas ------------------------------------------------------------------------------

async def _atualizar_visita() -> None:
    diretora = buscar_agente("terreo", "diretora")
    atual = _visitas[-1] if _visitas else None
    diretora.visitando = {"andar": atual["andar"], "agente": atual["agente"]} if atual else None
    diretora.status = Status.trabalhando if atual else Status.disponivel
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


async def _iniciar(andar: str, agente: str) -> None:
    if not any(v["agente"] == agente for v in _visitas):
        _visitas.append({"andar": andar, "agente": agente, "inicio": asyncio.get_running_loop().time()})
        await _atualizar_visita()


async def encerrar_consulta(agente: str) -> None:
    """Chamado quando a tentativa do agente termina; garante uma visita mínima visível."""
    visita = next((v for v in _visitas if v["agente"] == agente), None)
    if not visita:
        return
    restante = DURACAO_MINIMA_VISITA - (asyncio.get_running_loop().time() - visita["inicio"])
    if restante > 0:
        await asyncio.sleep(restante)
    _visitas.remove(visita)
    await _atualizar_visita()


def consultar(pergunta: str, andar: str, agente: str, tarefa_id: int = 0) -> str:
    """Chamado pela ferramenta do agente (em thread): marca a visita e devolve os trechos relevantes."""
    if _loop:
        asyncio.run_coroutine_threadsafe(_iniciar(andar, agente), _loop)
    if tarefa_id:
        atividade.evento_em_thread(tarefa_id, "consulta_diretora", agente, detalhe=pergunta)
    return buscar(pergunta)


def documentos() -> list[dict]:
    """Para o popup da Diretora."""
    return [{"nome": a.name, "tamanho_kb": round(a.stat().st_size / 1024, 1)}
            for a in sorted(PASTA_CONHECIMENTO.glob("*.md"))]
