"""Tela "Modelos de IA" (diretoria): uso das LLMs no período — chamadas, sucessos, falhas, tempo, custo, status de
cada modelo, uso por agente, falhas recentes, plano Max e chamadas por dia.

Fontes: eventos das tarefas (tentativa, falha_modelo, concluida), tarefas (tempo), gastos_api (custo) e a saúde dos
modelos (pausas e afastamentos).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

import config
import saude
import tarefas
from api_painel import _nome_do_agente, _usuario
from estado import AGENTES_PRODUCAO

rotas = APIRouter(prefix="/api")

MODELO_MAX = "claude-code/max"
FALHA_REAL = "e.tipo = 'falha_modelo' AND COALESCE(e.detalhe, '') NOT LIKE 'Max ocupado%'"  # Max ocupado não é falha
TIPOS_LEGIVEIS = {"credito": "crédito do mês esgotado", "cota": "cota diária esgotada", "limite": "limite temporário",
                  "lento": "lento demais (estourou o tempo)", "indisponivel": "fora do ar no provedor",
                  "erro": "erro do modelo"}


def _iso(dias: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _motivo(detalhe: str | None) -> str:
    texto = detalhe or ""
    if texto.startswith("Max ocupado"):
        return "Max ocupado (seguiu para a API)"
    return TIPOS_LEGIVEIS.get(saude._classificar(texto)[0], "erro do modelo")


def _por_modelo(db, desde: str) -> list[dict]:
    linhas = db.execute(
        f"SELECT e.modelo, SUM(e.tipo = 'tentativa') AS tentativas, SUM(e.tipo = 'concluida') AS sucessos, "
        f"SUM({FALHA_REAL}) AS falhas FROM eventos e WHERE e.em >= ? AND e.modelo IS NOT NULL "
        "AND e.modelo != 'cerebro/ensino' GROUP BY e.modelo", (desde,)).fetchall()
    tempos = {l["modelo"]: l["media"] for l in db.execute(
        "SELECT modelo, AVG(tempo_segundos) AS media FROM tarefas WHERE status = 'concluida' AND concluida_em >= ? "
        "AND tempo_segundos > 0 GROUP BY modelo", (desde,))}
    custos = {l["modelo"]: l["custo"] for l in db.execute(
        "SELECT modelo, SUM(custo_usd) AS custo FROM gastos_api WHERE em >= ? GROUP BY modelo", (desde,))}
    fora = {m["modelo"]: m for m in saude.resumo()}
    resultado = []
    for l in linhas:
        tentativas = l["tentativas"] or 0
        situacao = fora.get(l["modelo"])
        resultado.append({
            "modelo": l["modelo"], "tentativas": tentativas, "sucessos": l["sucessos"] or 0, "falhas": l["falhas"] or 0,
            "taxa_falha": round((l["falhas"] or 0) / tentativas, 2) if tentativas else 0,
            "tempo_medio_s": round(tempos[l["modelo"]], 1) if tempos.get(l["modelo"]) else None,
            "custo_usd": round(custos.get(l["modelo"]) or 0, 4),
            "status": ("afastado" if situacao and situacao["afastado"] else "pausa" if situacao else "ativo"),
            "motivo": situacao["motivo"] if situacao else "", "volta_em": situacao["volta_em"] if situacao else None,
        })
    return sorted(resultado, key=lambda m: m["tentativas"], reverse=True)


def _por_agente(db, desde: str) -> list[dict]:
    linhas = db.execute(
        f"SELECT e.agente, e.modelo, SUM(e.tipo = 'tentativa') AS tentativas, SUM({FALHA_REAL}) AS falhas "
        "FROM eventos e WHERE e.em >= ? AND e.agente IS NOT NULL AND e.modelo IS NOT NULL "
        "AND e.modelo != 'cerebro/ensino' GROUP BY e.agente, e.modelo", (desde,)).fetchall()
    custos = {l["agente"]: l["custo"] for l in db.execute(
        "SELECT agente, SUM(custo_usd) AS custo FROM gastos_api WHERE em >= ? GROUP BY agente", (desde,))}
    agentes: dict[str, dict] = {}
    for l in linhas:
        a = agentes.setdefault(l["agente"], {"agente": l["agente"], "nome": _nome_do_agente(l["agente"]),
                                             "tentativas": 0, "falhas": 0, "modelos": []})
        a["tentativas"] += l["tentativas"] or 0
        a["falhas"] += l["falhas"] or 0
        a["modelos"].append({"modelo": l["modelo"], "tentativas": l["tentativas"] or 0, "falhas": l["falhas"] or 0})
    for a in agentes.values():
        a["modelos"].sort(key=lambda m: m["tentativas"], reverse=True)
        a["custo_usd"] = round(custos.get(a["agente"]) or 0, 4)
    return sorted(agentes.values(), key=lambda a: a["tentativas"], reverse=True)


def _falhas_recentes(db, desde: str) -> list[dict]:
    return [{"em": l["em"], "modelo": l["modelo"], "agente": _nome_do_agente(l["agente"] or ""),
             "motivo": _motivo(l["detalhe"]), "detalhe": (l["detalhe"] or "")[:160]}
            for l in db.execute("SELECT em, modelo, agente, detalhe FROM eventos e WHERE e.tipo = 'falha_modelo' "
                                "AND e.em >= ? ORDER BY e.id DESC LIMIT 30", (desde,))]


def _max(db, desde: str) -> dict:
    """Plano Max: textos (tarefas de agentes no lugar da API) e produções (PNG/MP4)."""
    marcadores = ",".join("?" * len(AGENTES_PRODUCAO))
    def bloco(condicao: str) -> dict:
        linha = db.execute(
            f"SELECT COUNT(*) AS n, AVG(tempo_segundos) AS media, SUM(status = 'falhou') AS falhas FROM tarefas "
            f"WHERE modelo = ? AND criada_em >= ? AND status IN ('concluida', 'falhou') AND {condicao}",
            (MODELO_MAX, desde, *AGENTES_PRODUCAO)).fetchone()
        return {"total": linha["n"] or 0, "falhas": linha["falhas"] or 0,
                "tempo_medio_s": round(linha["media"], 1) if linha["media"] else None}
    return {"textos": bloco(f"agente NOT IN ({marcadores})"), "producoes": bloco(f"agente IN ({marcadores})")}


def _por_dia(db, dias: int) -> list[dict]:
    desde = _iso(dias)
    linhas = {l["dia"]: l for l in db.execute(
        f"SELECT substr(e.em, 1, 10) AS dia, SUM(e.tipo = 'concluida' AND e.modelo IS NOT NULL) AS sucessos, "
        f"SUM({FALHA_REAL}) AS falhas FROM eventos e WHERE e.em >= ? GROUP BY dia", (desde,))}
    hoje = datetime.now(timezone.utc).date()
    serie = []
    for n in range(dias - 1, -1, -1):
        dia = (hoje - timedelta(days=n)).isoformat()
        l = linhas.get(dia)
        serie.append({"dia": dia, "sucessos": (l["sucessos"] or 0) if l else 0, "falhas": (l["falhas"] or 0) if l else 0})
    return serie


@rotas.get("/modelos/uso")
def uso_dos_modelos(dias: int = 7, authorization: str = Header("")):
    if _usuario(authorization)["role"] != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria vê o uso dos modelos.")
    dias = min(max(dias, 1), 90)
    db = tarefas._db()
    desde = _iso(dias)
    por_modelo = _por_modelo(db, desde)
    chamadas = sum(m["tentativas"] for m in por_modelo)
    sucessos = sum(m["sucessos"] for m in por_modelo)
    falhas = sum(m["falhas"] for m in por_modelo)
    custo_periodo = db.execute("SELECT COALESCE(SUM(custo_usd), 0) FROM gastos_api WHERE em >= ?", (desde,)).fetchone()[0]
    return {
        "dias": dias,
        "resumo": {"chamadas": chamadas, "sucessos": sucessos, "falhas": falhas,
                   "taxa_sucesso": round(sucessos / chamadas, 2) if chamadas else None,
                   "custo_periodo_usd": round(custo_periodo, 4), "custo_mes_usd": round(tarefas.gasto_mes_usd(), 4),
                   "credito_utilizavel_usd": round(config.CREDITO_MENSAL_ANTHROPIC_USD * config.FRACAO_UTILIZAVEL, 2)},
        "modelos": por_modelo,
        "agentes": _por_agente(db, desde),
        "falhas_recentes": _falhas_recentes(db, desde),
        "max": _max(db, desde),
        "por_dia": _por_dia(db, min(dias, 30) if dias > 1 else 7),
    }
