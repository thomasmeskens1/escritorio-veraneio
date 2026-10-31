"""Lacunas do Cérebro e "Perguntas da semana" (cerebro-02): cada "não sei" vira pergunta para o Thomas ensinar.

Quando falta informação, o agente escreve PENDENTE, "não registrado" ou "só enxergo parte", e a coisa parava aí; as
mesmas perguntas voltavam semana após semana. Agora cada busca vazia ou fraca e cada resposta com essas marcas grava
uma lacuna (pergunta curta, empresa, agente, quantas vezes); perguntas parecidas se juntam pelas palavras em comum.

Toda segunda, de dia (10:00; a madrugada depende da decisão 4), as 5 a 10 lacunas mais repetidas vão para a ficha do
Cérebro como "❓ Pergunta da semana", na lista "Correções e elogios". Só o Thomas responde (decisão 16: ele aprova os
fatos de cada empresa): a resposta vira "ensinado" na empresa certa. Sem IA e sem Max.

Fora da lista: preço, faturamento, clientes e CRM (sigilosos) e o que não tem resposta por natureza (disponibilidade
futura, números de mercado), marcado "fora do alcance".
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import cerebro_base as base
import empresas
import tarefas
from cerebro_texto import termos

log = logging.getLogger(__name__)

NOTA_FRACA = 0.2          # melhor trecho da busca abaixo disso: o Cérebro não soube de verdade
PARECIDA = 0.6            # termos em comum (Jaccard) para juntar duas perguntas na mesma lacuna
MIN_SEMANA, MAX_SEMANA = 5, 10
JANELA_DIAS = 30          # só entram lacunas que voltaram nos últimos 30 dias
HORA_SEMANAL = 10         # segunda, 10:00 (de dia)
# Marcas de "não sei" nas respostas (históricos de email_marketing, estrategista, social_media e cerebro).
NAO_SEI = re.compile(r"\bPENDENTE\b|n[ãa]o (?:est[áa] )?registrad[oa]|n[ãa]o encontrei|s[óo] enxergo|"
                     r"SEM FICHA|n[ãa]o confirmad[oa] na fonte|n[ãa]o tenho (?:essa|esse|a) informa", re.I)
SIGILOSA = re.compile(r"faturamento|receita|lucro|margem|\bCRM\b|clientes?\b|carteira|leads?\b|investimento|"
                      r"pre[çc]os?|valor(?:es)?|di[áa]rias?|R\$|comiss", re.I)
FORA_DO_ALCANCE = re.compile(r"disponibilidade|dispon[íi]ve(?:l|is) (?:em|para|no|na)|vagas? (?:em|para)|"
                             r"tamanho do mercado|market share|previs[ãa]o d[eo]|vai (?:chover|lotar)", re.I)
MAX_PERGUNTA = 200

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS lacunas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, empresa TEXT NOT NULL, pergunta TEXT NOT NULL, termos TEXT NOT NULL,
    agentes TEXT NOT NULL DEFAULT '[]', vezes INTEGER NOT NULL DEFAULT 1, origem TEXT NOT NULL,
    primeira_em TEXT NOT NULL, ultima_em TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberta',   -- aberta | fora_do_alcance | enviada | respondida | descartada
    observacao_id INTEGER, resposta TEXT, respondida_em TEXT);
CREATE INDEX IF NOT EXISTS idx_lacunas_status ON lacunas(status, empresa);
CREATE TABLE IF NOT EXISTS lacunas_semanas (semana TEXT PRIMARY KEY, em TEXT NOT NULL, itens INTEGER NOT NULL);
"""
_pronto = False


def _db():
    global _pronto
    conexao = tarefas._db()
    if not _pronto:
        with base._trava:
            conexao.executescript(_ESQUEMA)
        _pronto = True
    return conexao


def _limpa(texto: str) -> str:
    import cerebro  # import tardio: o Cérebro importa este módulo

    texto = cerebro.sem_contatos(" ".join((texto or "").split()))
    return texto[:MAX_PERGUNTA].rstrip() + ("…" if len(texto) > MAX_PERGUNTA else "")


def registrar(pergunta: str, empresa: str, agente: str, origem: str = "busca") -> int | None:
    """Grava (ou soma +1 numa parecida) a lacuna. Sigilosa não entra; sem resposta por natureza entra como
    "fora do alcance" (não vai para a lista). Devolve o id, ou None."""
    pergunta = _limpa(pergunta)
    chave = {t for t in termos(pergunta) if not t.isdigit() or len(t) > 2}
    if len(chave) < 2 or SIGILOSA.search(pergunta):
        return None
    empresa = empresa if empresas.valida(empresa) else empresas.COMUM
    agora = base.agora()
    with base._trava, _db() as conexao:
        abertas = conexao.execute("SELECT id, termos, agentes FROM lacunas WHERE empresa = ? AND status IN "
                                  "('aberta', 'enviada', 'fora_do_alcance') ORDER BY id DESC LIMIT 500",
                                  (empresa,)).fetchall()
        for l in abertas:
            outra = set(json.loads(l["termos"]))
            if outra and len(chave & outra) / len(chave | outra) >= PARECIDA:
                agentes = sorted(set(json.loads(l["agentes"])) | {agente})
                conexao.execute("UPDATE lacunas SET vezes = vezes + 1, ultima_em = ?, agentes = ? WHERE id = ?",
                                (agora, json.dumps(agentes), l["id"]))
                return l["id"]
        status = "fora_do_alcance" if FORA_DO_ALCANCE.search(pergunta) else "aberta"
        return conexao.execute(
            "INSERT INTO lacunas (empresa, pergunta, termos, agentes, origem, primeira_em, ultima_em, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (empresa, pergunta, json.dumps(sorted(chave)), json.dumps([agente]),
                                               origem, agora, agora, status)).lastrowid


def da_busca(pergunta: str, trechos: list[dict], empresa: str, agente: str) -> None:
    """Busca vazia ou só com trechos fracos: o Cérebro não soube."""
    try:
        if not trechos or max(t.get("nota", 0) for t in trechos) < NOTA_FRACA:
            registrar(pergunta, empresa, agente, "busca")
    except Exception:
        log.exception("Lacunas: falha ao registrar a busca.")


def da_resposta(linha) -> int:
    """Resposta concluída com PENDENTE, "não registrado", "só enxergo"...: cada linha marcada vira lacuna (o pedido,
    se a linha não diz nada sozinha). Devolve quantas."""
    try:
        if not linha or not linha["resposta"] or linha["agente"] == "prospectador":  # leads e contatos: fora
            return 0
        total = 0
        for frase in [l.strip(" -*•#\t") for l in linha["resposta"].splitlines() if NAO_SEI.search(l)][:5]:
            texto = frase if len(termos(NAO_SEI.sub(" ", frase))) >= 3 else linha["texto"]
            total += registrar(texto, linha["empresa"] or empresas.PADRAO, linha["agente"], "resposta") is not None
        return total
    except Exception:
        log.exception("Lacunas: falha ao ler a resposta da tarefa.")
        return 0


# --- Perguntas da semana -------------------------------------------------------------------------

def _semana(quando: datetime | None = None) -> str:
    quando = quando or datetime.now(timezone.utc)
    return f"{quando.isocalendar().year}-S{quando.isocalendar().week:02d}"


def _nome_agente(agente: str) -> str:
    from estado import andar_do_agente, buscar_agente

    andar = andar_do_agente(agente)
    achado = buscar_agente(andar, agente) if andar else None
    return achado.nome if achado else agente


def escolher(limite: int = MAX_SEMANA) -> list:
    """As lacunas abertas mais repetidas dos últimos 30 dias (mais vezes primeiro)."""
    desde = base.agora(-timedelta(days=JANELA_DIAS))
    with base._trava:
        return _db().execute("SELECT * FROM lacunas WHERE status = 'aberta' AND ultima_em >= ? "
                             "ORDER BY vezes DESC, ultima_em DESC LIMIT ?", (desde, limite)).fetchall()


def perguntas_da_semana(forcar: bool = False) -> dict:
    """Manda as lacunas da semana para a Diretoria (uma vez por semana). Repetidas (2+) primeiro; se forem menos de
    5, completa com as de uma vez só até 5."""
    import correcoes

    semana = _semana()
    if not forcar and _db().execute("SELECT 1 FROM lacunas_semanas WHERE semana = ?", (semana,)).fetchone():
        return {"ok": False, "itens": 0, "mensagem": "As perguntas desta semana já foram enviadas."}
    candidatas = escolher(MAX_SEMANA * 3)
    repetidas = [l for l in candidatas if l["vezes"] >= 2][:MAX_SEMANA]
    itens = repetidas + [l for l in candidatas if l["vezes"] < 2][:max(0, MIN_SEMANA - len(repetidas))]
    correcoes._db()  # garante a tabela de observações
    with base._trava, _db() as conexao:
        for l in itens:
            quem = ", ".join(_nome_agente(a) for a in json.loads(l["agentes"])[:4])
            texto = (f"O Cérebro não soube {l['vezes']} {'vezes' if l['vezes'] > 1 else 'vez'}: {l['pergunta']} "
                     f"({empresas.nome(l['empresa'])})")
            evidencia = (f"Quem perguntou: {quem}. Primeira vez em {l['primeira_em'][8:10]}/{l['primeira_em'][5:7]}, "
                         f"última em {l['ultima_em'][8:10]}/{l['ultima_em'][5:7]}. A resposta vira conhecimento "
                         f"ensinado da {empresas.nome(l['empresa'])}.")
            obs = conexao.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, "
                                  "resposta_anterior, tipo) VALUES (?, 'cerebro', 'cobertura', 'cerebro', NULL, ?, ?, "
                                  "'pergunta')", (tarefas._agora(), texto[:1000], evidencia[:400])).lastrowid
            conexao.execute("UPDATE lacunas SET status = 'enviada', observacao_id = ? WHERE id = ?", (obs, l["id"]))
        conexao.execute("INSERT OR REPLACE INTO lacunas_semanas VALUES (?, ?, ?)", (semana, tarefas._agora(), len(itens)))
    if itens:
        import atividade

        atividade._no_loop(correcoes.avisar_diretoria("pergunta"))
    log.info("Perguntas da semana %s: %d para a Diretoria.", semana, len(itens))
    return {"ok": True, "itens": len(itens), "mensagem": f"{len(itens)} pergunta(s) da semana esperando o Thomas."}


async def rodar_agendada() -> None:
    import asyncio

    try:
        await asyncio.to_thread(perguntas_da_semana)
    except Exception:
        log.exception("Perguntas da semana falharam.")


def agendar(agendador) -> None:
    """Segunda, 10:00 (São Paulo), no agendador das rotinas. Com o PC fora nesse horário, roda quando voltar, mas só
    de dia (até 18:00 de segunda; na subida, de segunda a sexta entre 08:00 e 20:00)."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger

    agendador.add_job(rodar_agendada, CronTrigger(day_of_week="mon", hour=HORA_SEMANAL, minute=0,
                                                  timezone=agendador.timezone),
                      id="perguntas_da_semana", replace_existing=True, misfire_grace_time=8 * 3600, coalesce=True)
    agora = datetime.now(agendador.timezone)
    ja_foi = _db().execute("SELECT 1 FROM lacunas_semanas WHERE semana = ?", (_semana(),)).fetchone()
    passou = agora.weekday() > 0 or agora.hour >= HORA_SEMANAL
    if not ja_foi and passou and agora.weekday() < 5 and 8 <= agora.hour < 20:
        agendador.add_job(rodar_agendada, DateTrigger(agora + timedelta(minutes=7)), id="perguntas_atrasadas",
                          replace_existing=True)


# --- Resposta do Thomas ----------------------------------------------------------------------------

rotas = APIRouter()


class Resposta(BaseModel):
    resposta: str = Field("", max_length=2000)
    fora_do_alcance: bool = False


@rotas.post("/lacunas/{observacao_id}/responder")
async def responder(observacao_id: int, dados: Resposta, authorization: str = Header("")):
    """Só o Thomas responde (decisão 16); "fora do alcance" tira a pergunta da lista sem ensinar nada."""
    import cerebro
    import config
    import correcoes

    usuario = correcoes._dono(authorization)
    lacuna = _db().execute("SELECT * FROM lacunas WHERE observacao_id = ? AND status = 'enviada'",
                           (observacao_id,)).fetchone()
    if not lacuna:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada ou já respondida.")
    if dados.fora_do_alcance:
        status, decisao = "fora_do_alcance", "descartada"
    else:
        if str(usuario.get("sub", "")).lower() != config.DONO_MAX:
            raise HTTPException(status_code=403, detail="Só o Thomas ensina fatos ao Cérebro. Você pode marcar "
                                                        "\"fora do alcance\" ou descartar.")
        if len(dados.resposta.strip()) < 3:
            raise HTTPException(status_code=422, detail="Escreva a resposta que o Cérebro deve aprender.")
        await cerebro.ensinar(config.DONO_MAX, f"Aprenda: Pergunta frequente: {lacuna['pergunta']}\nResposta: "
                                               f"{dados.resposta.strip()}", lacuna["empresa"])
        status, decisao = "respondida", "aprovada"
    with base._trava, _db() as conexao:
        conexao.execute("UPDATE lacunas SET status = ?, resposta = ?, respondida_em = ? WHERE id = ?",
                        (status, dados.resposta.strip()[:2000] or None, base.agora(), lacuna["id"]))
        conexao.execute("UPDATE observacoes SET status = ?, regra = ?, decidido_em = ? WHERE id = ?",
                        (decisao, dados.resposta.strip()[:500] or None, tarefas._agora(), observacao_id))
    return {"ok": True}
