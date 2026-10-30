"""👍/👎 nas respostas dos agentes (Thomas, 29/10/2026): o sinal de qualidade que ensina o Cérebro.

Um voto por tarefa (do dono do pedido; o master também pode votar). O voto:
- ajusta a pontuação dos trechos do Cérebro usados naquela resposta (👍 sobe, 👎 desce; trocar o voto desfaz o
  anterior), para que as próximas buscas priorizem o que ajudou;
- vira rótulo da rede neural do Cérebro (reranker.py), que aprende quais sinais indicam um trecho útil;
- com comentário, vira observação para a Diretoria aprovar: 👎 = correção, 👍 = elogio (mesma lista do ratinho).
"""

import json

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import atividade
import cerebro_base as base
import correcoes
import tarefas
from auth import validar_token

rotas = APIRouter(prefix="/api")

_ESQUEMA = ("CREATE TABLE IF NOT EXISTS avaliacoes (tarefa_id INTEGER PRIMARY KEY, usuario TEXT NOT NULL, "
            "valor INTEGER NOT NULL, comentario TEXT, em TEXT NOT NULL)")
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def de(tarefa_id: int) -> int:
    """Voto da tarefa: 1, -1 ou 0 (sem voto). Vai no histórico do chat para o botão aparecer marcado."""
    linha = _db().execute("SELECT valor FROM avaliacoes WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return linha["valor"] if linha else 0


def _passo(valor: int) -> float:
    return base.PASSO_SUCESSO if valor > 0 else -base.PASSO_FALHA if valor < 0 else 0.0


def _trechos_usados(tarefa_id: int) -> list[int]:
    linhas = base.db().execute("SELECT ids_conhecimento FROM consultas_cerebro WHERE tarefa_id = ?",
                               (tarefa_id,)).fetchall()
    return sorted({i for l in linhas for i in json.loads(l["ids_conhecimento"] or "[]")})


def avaliar(linha, usuario: str, valor: int, comentario: str = "") -> int:
    """Registra (ou troca, ou retira com 0) o voto; devolve quantos trechos do Cérebro foram ajustados."""
    anterior = de(linha["id"])
    with _db() as db:
        if valor:
            db.execute("INSERT INTO avaliacoes VALUES (?, ?, ?, ?, ?) ON CONFLICT(tarefa_id) DO UPDATE SET "
                       "usuario = excluded.usuario, valor = excluded.valor, comentario = excluded.comentario, "
                       "em = excluded.em", (linha["id"], usuario, valor, comentario or None, tarefas._agora()))
        else:
            db.execute("DELETE FROM avaliacoes WHERE tarefa_id = ?", (linha["id"],))
    if (valor == -1) != (anterior == -1):  # resposta ruim não fica como conhecimento (revisão de 30/10, 2.15)
        base.ativar_trecho_da_tarefa(linha["id"], valor != -1)
    ids = _trechos_usados(linha["id"])
    if ids and valor != anterior:
        base.ajustar_pontuacao(ids, _passo(valor) - _passo(anterior))
    if valor and comentario:
        with correcoes._db() as db:
            db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, "
                       "resposta_anterior, tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (tarefas._agora(), usuario, linha["andar"], linha["agente"], linha["id"], comentario[:1000],
                        (linha["resposta"] or "")[:400], "elogio" if valor > 0 else "correcao"))
        atividade._no_loop(correcoes.avisar_diretoria("elogio" if valor > 0 else "correcao"))
    return len(ids) if valor != anterior else 0


class Avaliacao(BaseModel):
    valor: int = Field(ge=-1, le=1)
    comentario: str = Field("", max_length=1000)


@rotas.post("/tarefas/{tarefa_id}/avaliar")
def avaliar_rota(tarefa_id: int, dados: Avaliacao, authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if linha["status"] != "concluida":
        raise HTTPException(status_code=409, detail="Só respostas concluídas podem ser avaliadas.")
    ajustados = avaliar(linha, usuario["sub"], dados.valor, dados.comentario.strip())
    return {"ok": True, "valor": dados.valor, "trechos_ajustados": ajustados}
