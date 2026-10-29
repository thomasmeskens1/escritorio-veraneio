"""Parar uma solicitação (Thomas, 29/10/2026): pelo botão "Parar" do chat (dado errado, falta de informação) ou
fechando o pop-up de formulário sem responder.

- Tarefa em andamento (executando, na fila, produzindo no Max): vira "falhou" com o motivo MOTIVO_PARADA. Nada muda
  mais o status dela (tarefas.atualizar): a resposta que chegar depois é descartada e não é entregue.
- Tarefa concluída esperando formulário ou decisão de produção: o formulário fica ENCERRADO (some o "!" e o botão
  "Responder formulário") e a produção em espera é cancelada.
"""

from fastapi import APIRouter, Header, HTTPException

import atividade
import encaminhamento
import espera
import tarefas
from auth import validar_token
from conexoes import gerenciador

rotas = APIRouter(prefix="/api")

EM_ANDAMENTO = ("executando", "adiada", "producao", "produzindo")
_ESQUEMA = ("CREATE TABLE IF NOT EXISTS formularios_encerrados (tarefa_id INTEGER PRIMARY KEY, em TEXT NOT NULL, "
            "usuario TEXT NOT NULL)")
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def formulario_encerrado(tarefa_id: int) -> bool:
    return bool(_db().execute("SELECT 1 FROM formularios_encerrados WHERE tarefa_id = ?", (tarefa_id,)).fetchone())


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


async def parar(linha, usuario: dict) -> str:
    """Para a tarefa (ou encerra o formulário dela) e avisa nos chats; devolve o que foi feito."""
    quem = usuario.get("nome") or usuario["sub"]
    if linha["status"] in EM_ANDAMENTO:
        tarefas.atualizar(linha["id"], status="falhou", motivo=f"{tarefas.MOTIVO_PARADA} por {quem}.")
        tarefas.registrar_evento(linha["id"], "parada", linha["agente"], detalhe=f"Parada por {quem}")
        if linha["status"] == "produzindo":  # o Max já tinha ocupado o agente; a entrega não vai acontecer
            await atividade.liberar(linha["agente"])
        feito = "Solicitação parada. O que o agente produzir depois disso é descartado."
    else:
        with _db() as db:
            db.execute("INSERT OR IGNORE INTO formularios_encerrados VALUES (?, ?, ?)",
                       (linha["id"], tarefas._agora(), usuario["sub"]))
        tarefas.registrar_evento(linha["id"], "parada", linha["agente"], detalhe=f"Formulário encerrado por {quem}")
        feito = "Solicitação encerrada: o formulário foi fechado sem resposta."
    espera.remover(linha["id"])  # produção esperando decisão: cancelada
    chats = {(linha["andar"], linha["agente"])}
    if (origem := encaminhamento.origem(linha["id"])):
        chats.add(origem)
    for andar, agente in chats:
        await gerenciador.enviar_para_usuario(linha["usuario"], {
            "tipo": "aviso", "andar": andar, "agente": agente, "titulo": "Solicitação parada", "liberar": True,
            "texto": feito, "tarefa_id": linha["id"]})
    return feito


@rotas.post("/tarefas/{tarefa_id}/parar")
async def parar_tarefa(tarefa_id: int, authorization: str = Header("")):
    usuario = _usuario(authorization)
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return {"ok": True, "texto": await parar(linha, usuario)}


@rotas.post("/chats/{andar}/{agente_id}/parar")
async def parar_do_chat(andar: str, agente_id: str, authorization: str = Header("")):
    """Botão "Parar" do chat: o pedido em andamento mais recente do usuário neste chat (inclusive o que nasceu aqui
    e roda em outro agente, como o Gestor ou a produção)."""
    usuario = _usuario(authorization)
    vindas = list(encaminhamento.tarefas_do_chat(andar, agente_id))
    marcadores = ",".join("?" * len(vindas)) or "NULL"
    linha = tarefas._db().execute(
        f"SELECT * FROM tarefas WHERE usuario = ? AND ((andar = ? AND agente = ?) OR id IN ({marcadores})) "
        f"AND status IN ({','.join('?' * len(EM_ANDAMENTO))}) ORDER BY id DESC LIMIT 1",
        (usuario["sub"], andar, agente_id, *vindas, *EM_ANDAMENTO)).fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Nenhuma solicitação em andamento neste chat.")
    return {"ok": True, "texto": await parar(linha, usuario)}
