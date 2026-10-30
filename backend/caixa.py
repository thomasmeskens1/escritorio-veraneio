"""Caixa de entrada (Thomas, 30/10/2026; ideia do pizza-bot): duas filas por pessoa, num ícone do topo.

- "Para aprovar": o que espera uma decisão do usuário (formulário sem resposta, produção esperando "produzir?"),
  as mesmas pendências do "!" vermelho dos agentes (historico.pendencias).
- "Concluídos": pedidos que terminaram (ou falharam) nos últimos 7 dias e que o usuário ainda não abriu.

Clicar num item abre o chat onde o pedido nasceu e marca como lido.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import encaminhamento
import historico
import tarefas
from auth import validar_token
from estado import andar_do_agente, buscar_agente

rotas = APIRouter(prefix="/api/caixa")

DIAS = 7
LIMITE = 30
MOTIVOS = {"formulario": "Responder o formulário do agente", "producao": "Decidir sobre a produção da peça"}
_ESQUEMA = ("CREATE TABLE IF NOT EXISTS caixa_lidos (usuario TEXT NOT NULL, tarefa_id INTEGER NOT NULL, "
            "em TEXT NOT NULL, PRIMARY KEY (usuario, tarefa_id))")
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def _nome(andar: str, agente_id: str) -> str:
    agente = buscar_agente(andar, agente_id)
    return agente.nome if agente else agente_id


def _chat(linha) -> tuple[str, str]:
    """Chat onde o pedido nasceu (a resposta aparece lá)."""
    return encaminhamento.origem(linha["id"]) or (linha["andar"], linha["agente"])


def caixa(usuario: str) -> dict:
    aprovar = []
    for p in historico.pendencias(usuario):
        linha = tarefas.obter(p["tarefa_id"])
        aprovar.append({"tarefa_id": p["tarefa_id"], "andar": p["andar"], "agente": p["agente"],
                        "agente_nome": _nome(p["andar"], p["agente"]), "motivo": MOTIVOS.get(p["motivo"], p["motivo"]),
                        "resumo": encaminhamento.pedido_original(linha["texto"])[:140] if linha else "",
                        "em": (linha["concluida_em"] or linha["criada_em"]) if linha else ""})
    desde = (datetime.now(timezone.utc) - timedelta(days=DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pendentes = {a["tarefa_id"] for a in aprovar}
    linhas = _db().execute(
        "SELECT t.* FROM tarefas t LEFT JOIN caixa_lidos l ON l.usuario = t.usuario AND l.tarefa_id = t.id "
        "WHERE t.usuario = ? AND t.status IN ('concluida', 'falhou') AND t.concluida_em >= ? AND l.tarefa_id IS NULL "
        "ORDER BY t.id DESC LIMIT ?", (usuario, desde, LIMITE)).fetchall()
    concluidos = []
    for linha in linhas:
        if linha["id"] in pendentes:
            continue
        andar, agente = _chat(linha)
        quem = linha["agente"] if linha["agente"] != agente else None
        concluidos.append({"tarefa_id": linha["id"], "andar": andar, "agente": agente,
                           "agente_nome": _nome(andar, agente),
                           "por": _nome(andar_do_agente(quem) or andar, quem) if quem else None,
                           "status": linha["status"], "resumo": encaminhamento.pedido_original(linha["texto"])[:140],
                           "em": linha["concluida_em"]})
    return {"aprovar": aprovar, "concluidos": concluidos}


def marcar_lidos(usuario: str, ids: list[int]) -> int:
    with _db() as db:
        return db.executemany("INSERT OR IGNORE INTO caixa_lidos VALUES (?, ?, ?)",
                              [(usuario, i, tarefas._agora()) for i in ids]).rowcount


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


class Lidos(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    todos: bool = False


@rotas.get("")
def ver_caixa(authorization: str = Header("")):
    return caixa(_usuario(authorization)["sub"])


@rotas.post("/lidos")
def lidos(dados: Lidos, authorization: str = Header("")):
    usuario = _usuario(authorization)["sub"]
    ids = [c["tarefa_id"] for c in caixa(usuario)["concluidos"]] if dados.todos else dados.ids
    return {"ok": True, "marcados": marcar_lidos(usuario, ids)}
