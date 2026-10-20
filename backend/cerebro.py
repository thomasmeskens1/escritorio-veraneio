"""Cérebro: o conhecimento central (RAG) da Casa Veraneio.

Substitui a Diretora. Os agentes consultam pela ferramenta consultar_cerebro (um estagiário leva a resposta
até o andar deles); a diretoria conversa direto com o Cérebro, e só a conta do dono pode ensiná-lo.
Base, busca e aprendizado: cerebro_base.py; estagiários: cerebro_estagiarios.py.
"""

import asyncio
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import atividade
import cerebro_base as base
import cerebro_embed as embed
import cerebro_estagiarios as estagiarios
import config
import tarefas
from auth import validar_token
from estado import AGENTES_PRODUCAO, andar_do_agente, buscar_agente

log = logging.getLogger(__name__)

ID = "cerebro"
PASTA_CONHECIMENTO = config.PASTA_CONHECIMENTO
FUSO = ZoneInfo("America/Sao_Paulo")
HORA_CONSOLIDACAO = 3
MAX_CARACTERES_FERRAMENTA = 3000  # resposta da ferramenta (tokens dos agentes)
MAX_CARACTERES_CONTEXTO = 6000    # trechos na tarefa do próprio Cérebro
INTERVALO_REVISAO = 600           # o trabalhador de embeddings revisa os pendentes a cada 10 min
ROTULOS_FONTE = {"oficial": "documento oficial", "ensinado": "ensinado pela diretoria", "site": "site",
                 "drive": "Drive", "tarefa": "trabalho anterior da equipe"}

_ENSINO = re.compile(r"^\s*(aprenda|anote|memorize|lembre(?:-se)?|ensinar|registre)\b\s*(?:-\s*se\b)?\s*:?\s*",
                     re.IGNORECASE)

_acordar = threading.Event()
_trabalhador: threading.Thread | None = None
_tarefas_fundo: set[asyncio.Task] = set()


# --- Ensino ---------------------------------------------------------------------------------------

def e_ensino(texto: str) -> bool:
    """Mensagens que começam com Aprenda/Anote/Memorize/Lembre(-se)/Ensinar/Registre."""
    return bool(_ENSINO.match(texto or ""))


async def ensinar(login: str, texto: str) -> str:
    """Grava o ensinamento (só a conta do dono). PermissionError/ValueError trazem a mensagem ao usuário."""
    if (login or "").strip().lower() != config.DONO_MAX:
        raise PermissionError("Só a conta do Thomas pode ensinar o Cérebro. Você pode fazer perguntas normalmente.")
    conteudo = _ENSINO.sub("", texto or "", count=1).strip()
    if len(conteudo) < 3:
        raise ValueError("Escreva o que o Cérebro deve aprender, ex.: \"Aprenda: o check-in é às 14h.\"")
    titulo = conteudo.splitlines()[0][:80]
    ref = f"chat:{base.agora()}:{uuid.uuid4().hex[:8]}"  # único: ensinamentos não são o "mesmo documento"
    ids, substituidos = await asyncio.to_thread(base.adicionar, "ensinado", ref, titulo, conteudo)
    _acordar.set()  # se o Ollama estava fora, o trabalhador tenta de novo
    resposta = "Anotado! Guardei isso no conhecimento da Casa Veraneio"
    resposta += f" ({len(ids)} trechos)." if len(ids) > 1 else "."
    if substituidos:
        resposta += f" Substituí {substituidos} informação(ões) antiga(s) sobre o mesmo assunto (o histórico fica guardado)."
    return resposta


# --- Consulta (ferramenta dos agentes) -----------------------------------------------------------------

def _formatar(trechos: list[dict], limite: int) -> str:
    por_trecho = max(300, limite // max(len(trechos), 1) - 120)
    blocos = []
    for n, t in enumerate(trechos, 1):
        ref = f" ({t['fonte_ref']})" if t["fonte_ref"] and t["fonte_tipo"] in ("oficial", "site", "drive") else ""
        conteudo = t["conteudo"] if len(t["conteudo"]) <= por_trecho else t["conteudo"][:por_trecho].rstrip() + "…"
        blocos.append(f"[{n}] {t['titulo']} — fonte: {ROTULOS_FONTE.get(t['fonte_tipo'], t['fonte_tipo'])}{ref}, "
                      f"{t['data']}\n{conteudo}")
    return "\n\n".join(blocos)[:limite]


def consultar(pergunta: str, agente: str, tarefa_id: int = 0) -> str:
    """Chamado pela ferramenta do agente (em thread). Nunca bloqueia: sem estagiário livre, responde sem visita."""
    estagiario = estagiarios.iniciar_visita(agente) if agente != ID else None
    try:
        if tarefa_id:
            atividade.evento_em_thread(tarefa_id, "consulta_cerebro", agente, detalhe=pergunta)
        trechos = base.buscar(pergunta)
        base.registrar_consulta(tarefa_id, agente, pergunta, [t["id"] for t in trechos])
    except Exception:
        log.exception("Cérebro: falha na consulta.")
        return "O Cérebro está indisponível agora. Não invente fatos sobre a empresa; avise o usuário se faltar algo."
    finally:
        if estagiario:
            estagiarios.concluir_visita(estagiario)
    if not trechos:
        return ("O Cérebro não tem nada registrado sobre isso. Não invente: diga que essa informação não está "
                "na base da Casa Veraneio ou pergunte ao usuário.")
    return ("Conhecimento do Cérebro (cite a fonte ao usar; prefira o mais recente se houver conflito):\n\n"
            + _formatar(trechos, MAX_CARACTERES_FERRAMENTA))


def descricao_tarefa(texto: str, historico: list = (), tarefa_id: int = 0) -> str:
    """Pergunta feita direto ao Cérebro: os trechos recuperados já vão na descrição (sem ferramenta)."""
    from agents.perfis import contexto  # import tardio: perfis depende do estado

    try:
        trechos = base.buscar(texto, k=6)
        base.registrar_consulta(tarefa_id, ID, texto, [t["id"] for t in trechos])
    except Exception:
        log.exception("Cérebro: falha ao recuperar trechos.")
        trechos = []
    conhecimento = (_formatar(trechos, MAX_CARACTERES_CONTEXTO) if trechos
                    else "(nenhum trecho relevante encontrado na base)")
    return (f"Pergunta do usuário: {texto}\n\n{contexto(ID, historico)}\n\n"
            f"Conhecimento recuperado da base da Casa Veraneio:\n{conhecimento}\n\n"
            "Responda usando SOMENTE o conhecimento acima. Cite a fonte de cada informação no formato [n] "
            "(título e fonte). Se houver versões conflitantes, use a mais recente e diga isso. Se a resposta não "
            "estiver nos trechos, diga claramente que não sabe e que essa informação ainda não foi registrada "
            "(o Thomas pode ensinar começando a mensagem com \"Aprenda:\"). Nunca invente.")


# --- Aprendizado com o trabalho da empresa --------------------------------------------------------------

def registrar_resultado(tarefa_id: int, sucesso: bool) -> int:
    """Fim da tarefa (concluída/falhou): ajusta a pontuação dos trechos que ela usou."""
    try:
        return base.registrar_resultado(tarefa_id, sucesso)
    except Exception:
        log.exception("Cérebro: falha ao registrar o resultado da tarefa %s.", tarefa_id)
        return 0


def aprender_tarefa(tarefa_id: int) -> int | None:
    """Tarefa concluída vira um trecho "tarefa" (pedido + resposta resumida). O embedding vem em segundo plano."""
    try:
        linha = tarefas.obter(tarefa_id)
        if (not linha or linha["status"] != "concluida" or not linha["resposta"]
                or linha["agente"] == ID or linha["agente"] in AGENTES_PRODUCAO):
            return None
        andar = andar_do_agente(linha["agente"])
        agente = buscar_agente(andar, linha["agente"]) if andar else None
        nome = agente.nome if agente else linha["agente"]
        resposta = linha["resposta"].strip()
        conteudo = (f"Pedido: {linha['texto'].strip()[:300]}\n\nResposta de {nome}: "
                    f"{resposta[:800]}{'…' if len(resposta) > 800 else ''}")
        trecho_id = base._inserir("tarefa", f"tarefa:{tarefa_id}", f"{nome}: {linha['texto'].strip()[:70]}", conteudo)
        _acordar.set()
        return trecho_id
    except Exception:
        log.exception("Cérebro: falha ao aprender com a tarefa %s.", tarefa_id)
        return None


# --- Subida, trabalhador de embeddings e consolidação ----------------------------------------------------

def indexar_oficiais() -> int:
    """Indexa os .md de backend/dados/conhecimento/ como "oficial" (só os que mudaram). Devolve o nº de trechos."""
    total, refs = 0, set()
    for arquivo in sorted(PASTA_CONHECIMENTO.glob("*.md")):
        refs.add(arquivo.name)
        titulo = arquivo.stem.replace("_", " ").capitalize()
        total += base.substituir_ref("oficial", arquivo.name, titulo, arquivo.read_text(encoding="utf-8"))
    with base._trava:  # documento apagado da pasta: seus trechos saem da busca
        sumidos = [l["id"] for l in base.db().execute(
            "SELECT id, fonte_ref FROM conhecimento WHERE fonte_tipo = 'oficial' AND ativo = 1") if l["fonte_ref"] not in refs]
    base._desativar(sumidos, None)
    return total


def _trabalhar() -> None:
    """Thread: indexa os oficiais e gera os embeddings pendentes (sem travar a subida nem o loop)."""
    try:
        indexar_oficiais()
    except Exception:
        log.exception("Cérebro: falha ao indexar os documentos oficiais.")
    while True:
        try:
            faltam = base.pendentes()
            if faltam:
                base.gerar_embeddings(faltam)
        except Exception:
            log.exception("Cérebro: falha ao gerar embeddings.")
        _acordar.wait(INTERVALO_REVISAO if embed.ollama_ok() is not False else embed.PAUSA_APOS_FALHA * 2)
        _acordar.clear()


def _segundos_ate_consolidacao() -> float:
    agora = datetime.now(FUSO)
    alvo = agora.replace(hour=HORA_CONSOLIDACAO, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def _laco_consolidacao() -> None:
    while True:
        await asyncio.sleep(_segundos_ate_consolidacao())
        try:
            await asyncio.to_thread(base.consolidar)
        except Exception:
            log.exception("Cérebro: falha na consolidação diária.")


def iniciar() -> None:
    """Na subida: tabelas, indexação inicial e embeddings em segundo plano, consolidação diária às 03:00."""
    global _trabalhador
    base.db()
    base.restaurar_documentos_distintos()
    if _trabalhador is None or not _trabalhador.is_alive():
        _trabalhador = threading.Thread(target=_trabalhar, name="cerebro-embeddings", daemon=True)
        _trabalhador.start()
    try:
        tarefa = asyncio.get_running_loop().create_task(_laco_consolidacao())
        _tarefas_fundo.add(tarefa)
        tarefa.add_done_callback(_tarefas_fundo.discard)
    except RuntimeError:
        log.warning("Cérebro: sem loop asyncio; a consolidação diária não foi agendada.")


# --- API ---------------------------------------------------------------------------------------------

rotas = APIRouter(prefix="/api/cerebro")


@rotas.get("/estatisticas")
def estatisticas(authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if usuario.get("role") != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria vê o Cérebro.")
    inicio_hoje = (datetime.now(FUSO).replace(hour=0, minute=0, second=0, microsecond=0)
                   .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return {**base.estatisticas(inicio_hoje),
            "pode_ensinar": str(usuario.get("sub", "")).lower() == config.DONO_MAX,
            "embeddings": {"modelo": config.MODELO_EMBEDDING, "pendentes": len(base.pendentes()),
                           "ollama_ok": embed.ollama_ok()}}


class Documento(BaseModel):
    fonte_tipo: Literal["site", "drive", "oficial"]
    fonte_ref: str = Field(min_length=1, max_length=500)
    titulo: str = Field("", max_length=200)
    conteudo: str = Field(min_length=1, max_length=200_000)


class Remocao(BaseModel):
    fonte_tipo: Literal["site", "drive", "oficial"]
    fonte_ref: str = Field(min_length=1, max_length=500)


class Ingestao(BaseModel):
    documentos: list[Documento] = Field([], max_length=500)
    remover: list[Remocao] = Field([], max_length=500)  # documentos que deixaram de existir na fonte


def _ingerir(ingestao: Ingestao) -> tuple[int, int]:
    trechos = sum(base.substituir_ref(d.fonte_tipo, d.fonte_ref.strip(), d.titulo.strip() or d.fonte_ref.strip(),
                                      d.conteudo) for d in ingestao.documentos)
    removidos = sum(base.remover_ref(r.fonte_tipo, r.fonte_ref.strip()) for r in ingestao.remover)
    return trechos, removidos


@rotas.post("/ingerir")
async def ingerir(ingestao: Ingestao, authorization: str = Header("")):
    """Trabalhador do Max (site casaveraneio.com, catálogo de fotos): mesmo fonte_ref substitui o anterior;
    `remover` desativa os documentos que sumiram da fonte."""
    from producao import _exigir_operador  # import tardio: produção depende do orquestrador na entrega

    _exigir_operador(authorization)
    trechos, removidos = await asyncio.to_thread(_ingerir, ingestao)
    _acordar.set()
    return {"trechos": trechos, "removidos": removidos}
