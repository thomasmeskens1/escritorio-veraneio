"""Consolidação semanal do Cérebro (Thomas, 29/10/2026): toda segunda às 07:00 o Max lê a semana e propõe o que
aprendemos.

Junta, por empresa e por agente, as tarefas da semana (concluídas, falhas, tempo), os 👍/👎 com comentário e os
elogios e correções. O Max (Claude Code, pela fila do trabalhador) devolve até 6 aprendizados curtos, que entram na
lista "Correções e elogios" como "🧠 Aprendizado da semana": a Diretoria aprova (vira regra para o agente ou para
todos), edita ou descarta. Nada vira regra sozinho. Na mesma rodada, a rede neural do Cérebro é retreinada.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

import correcoes
import empresas
import tarefas
from auth import validar_token
from estado import ANDARES

log = logging.getLogger(__name__)
rotas = APIRouter(prefix="/api/cerebro")

MAX_APRENDIZADOS = 6
MAX_EXEMPLOS_POR_AGENTE = 4
_rodando = False


def _semana() -> str:
    hoje = datetime.now(timezone.utc)
    return f"{hoje.isocalendar().year}-S{hoje.isocalendar().week:02d}"


def _nomes() -> dict[str, str]:
    return {a.id: a.nome for agentes in ANDARES.values() for a in agentes.values()}


def coletar(dias: int = 7) -> dict:
    """Resumo da semana por empresa e agente (sem dados de clientes: só pedidos curtos, notas e comentários)."""
    db = correcoes._db()
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        votos = {l["tarefa_id"]: (l["valor"], l["comentario"]) for l in db.execute(
            "SELECT tarefa_id, valor, comentario FROM avaliacoes WHERE em >= ?", (desde,))}
    except Exception:
        votos = {}
    grupos: dict = defaultdict(lambda: {"concluidas": 0, "falhas": 0, "tempo_total": 0.0, "positivos": 0,
                                        "negativos": 0, "exemplos": []})
    for t in db.execute("SELECT id, agente, empresa, status, texto, tempo_segundos FROM tarefas WHERE criada_em >= ? "
                        "AND status IN ('concluida', 'falhou')", (desde,)):
        g = grupos[(empresas.nome(t["empresa"]), t["agente"])]
        g["concluidas" if t["status"] == "concluida" else "falhas"] += 1
        g["tempo_total"] += t["tempo_segundos"] or 0
        valor, comentario = votos.get(t["id"], (0, None))
        if valor:
            g["positivos" if valor > 0 else "negativos"] += 1
        if valor < 0 and len(g["exemplos"]) < MAX_EXEMPLOS_POR_AGENTE:
            g["exemplos"].append({"pedido": t["texto"][:200], "nota": "👎", "comentario": comentario or ""})
    for o in db.execute("SELECT o.agente, o.tipo, o.correcao, t.empresa FROM observacoes o LEFT JOIN tarefas t "
                        "ON t.id = o.tarefa_anterior WHERE o.em >= ? AND o.tipo IN ('elogio', 'correcao')", (desde,)):
        g = grupos[(empresas.nome(o["empresa"]) if o["empresa"] else "—", o["agente"])]
        if len(g["exemplos"]) < MAX_EXEMPLOS_POR_AGENTE:
            g["exemplos"].append({"tipo": o["tipo"], "texto": o["correcao"][:300]})
    nomes = _nomes()
    return {"desde": desde, "grupos": [
        {"empresa": empresa, "agente": agente, "agente_nome": nomes.get(agente, agente),
         "concluidas": g["concluidas"], "falhas": g["falhas"], "positivos": g["positivos"], "negativos": g["negativos"],
         "tempo_medio_s": round(g["tempo_total"] / max(g["concluidas"] + g["falhas"], 1)), "exemplos": g["exemplos"]}
        for (empresa, agente), g in sorted(grupos.items(), key=lambda x: (str(x[0][0]), x[0][1]))]}


def _prompt(dados: dict) -> str:
    agentes = ", ".join(f"{i} ({n})" for i, n in sorted(_nomes().items()))
    return (
        "Você é o Cérebro do Escritório Veraneio e faz a consolidação semanal do que a equipe aprendeu. Não pesquise "
        "na web: trabalhe só com os dados abaixo (tarefas da semana por empresa e agente, notas 👍/👎, elogios e "
        "correções da equipe). As três empresas (Casa Veraneio, Corporativo, Casa Vero) são separadas: um aprendizado "
        "de uma não vale para outra, a menos que seja claramente geral.\n\n"
        f"Proponha no máximo {MAX_APRENDIZADOS} aprendizados práticos, cada um uma regra curta e acionável (até 300 "
        "caracteres) que o agente deve seguir daqui em diante, apoiada nos dados (cite a evidência em `porque`). "
        "Prefira padrões repetidos a casos isolados. Se não houver nada sólido, devolva lista vazia.\n\n"
        f"Agentes válidos (use o id; \"*\" = todos os agentes): {agentes}\n\n"
        f"Dados da semana:\n{json.dumps(dados, ensure_ascii=False)[:20000]}\n\n"
        "Responda SOMENTE com este bloco:\n<<APRENDIZADOS>>\n"
        '[{"agente": "<id ou *>", "empresa": "<nome ou Todas>", "aprendizado": "...", "porque": "..."}]\n<<FIM>>')


def consolidar(forcar: bool = False) -> dict:
    """Roda a consolidação (em thread: espera o Max). Uma vez por semana, a não ser que `forcar`."""
    global _rodando
    import comercial
    import reranker

    if _rodando:
        return {"ok": False, "mensagem": "A consolidação já está rodando."}
    db = correcoes._db()
    db.execute("CREATE TABLE IF NOT EXISTS consolidacoes (semana TEXT PRIMARY KEY, em TEXT NOT NULL, itens INTEGER)")
    semana = _semana()
    if not forcar and db.execute("SELECT 1 FROM consolidacoes WHERE semana = ?", (semana,)).fetchone():
        return {"ok": False, "mensagem": "Esta semana já foi consolidada."}
    _rodando = True
    try:
        rede = reranker.treinar()
        dados = coletar()
        if not dados["grupos"]:
            return {"ok": True, "itens": 0, "rede": rede, "mensagem": "Nenhuma tarefa na semana."}
        bruto = json.loads(comercial._bloco(comercial.pedir_ao_max(_prompt(dados)), "APRENDIZADOS"))
        validos = set(_nomes()) | {"*"}
        itens = [a for a in bruto if isinstance(a, dict) and str(a.get("aprendizado", "")).strip()][:MAX_APRENDIZADOS]
        with db:
            for a in itens:
                empresa = str(a.get("empresa") or "").strip()
                texto = str(a["aprendizado"]).strip()[:300]
                if empresa and empresa.lower() not in ("todas", "todos", "geral"):
                    texto = f"[{empresa}] {texto}"
                db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, "
                           "resposta_anterior, tipo) VALUES (?, 'cerebro', 'cobertura', ?, NULL, ?, ?, 'aprendizado')",
                           (tarefas._agora(), a.get("agente") if a.get("agente") in validos else "*", texto,
                            f"Por quê: {str(a.get('porque') or '')[:390]}"))
            db.execute("INSERT OR REPLACE INTO consolidacoes VALUES (?, ?, ?)", (semana, tarefas._agora(), len(itens)))
        if itens:
            import atividade

            atividade._no_loop(correcoes.avisar_diretoria("aprendizado"))
        log.info("Consolidação semanal %s: %d aprendizado(s) para a Diretoria.", semana, len(itens))
        return {"ok": True, "itens": len(itens), "rede": rede,
                "mensagem": f"{len(itens)} aprendizado(s) da semana esperando a Diretoria."}
    except Exception as erro:
        log.exception("Consolidação semanal falhou.")
        return {"ok": False, "mensagem": f"A consolidação falhou: {erro}"}
    finally:
        _rodando = False


async def rodar_agendada() -> None:
    await asyncio.to_thread(consolidar)


def agendar(agendador) -> None:
    """Segunda-feira, 07:00 (São Paulo), no agendador das rotinas (agendamentos.iniciar)."""
    from apscheduler.triggers.cron import CronTrigger

    from apscheduler.triggers.date import DateTrigger

    # Revisão de 30/10/2026 (2.20): a tolerância era de 1 s; com o PC ou o Docker fora às 07:00, a semana se perdia.
    agendador.add_job(rodar_agendada, CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=agendador.timezone),
                      id="consolidacao_semanal", replace_existing=True, misfire_grace_time=24 * 3600, coalesce=True)
    agora = datetime.now(agendador.timezone)
    if not (agora.weekday() == 0 and agora.hour < 7):  # já passou das 07:00 de segunda: confere a semana na subida
        agendador.add_job(rodar_agendada, DateTrigger(agora + timedelta(minutes=5)), id="consolidacao_atrasada",
                          replace_existing=True)


@rotas.post("/consolidar")
async def consolidar_agora(authorization: str = Header("")):
    """Botão do master: roda a consolidação agora (em segundo plano; o ratinho avisa quando houver itens)."""
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario or not usuario.get("master"):
        raise HTTPException(status_code=403, detail="Só o master pode rodar a consolidação.")
    if _rodando:
        return {"ok": False, "mensagem": "A consolidação já está rodando."}
    import orquestrador

    orquestrador._em_segundo_plano(asyncio.to_thread(consolidar, True))
    return {"ok": True, "mensagem": "Consolidação iniciada: o Max lê a semana e os itens chegam para aprovação."}
