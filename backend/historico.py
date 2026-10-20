"""Memória do chat: conversa de cada usuário com um agente, reconstruída a partir das tarefas salvas."""

import json

from fastapi import APIRouter, Header, HTTPException

import auth
import tarefas
from estado import buscar_agente, pode_acessar

rotas = APIRouter(prefix="/api")

LIMITE_MAXIMO = 100

# Status ainda sem resposta -> aviso curto mostrado no lugar dela.
AVISOS_ANDAMENTO = {
    "executando": "Tarefa em andamento…",
    "adiada": "Na fila…",
    "producao": "Em produção pelo Claude Code (Max)…",
    "produzindo": "Em produção pelo Claude Code (Max)…",
}


def _anexos(linha) -> list[dict]:
    """Metadados dos anexos da tarefa, para as miniaturas no chat."""
    ids = json.loads(linha["anexos"]) if linha["anexos"] else []
    if not ids:
        return []
    marcadores = ",".join("?" * len(ids))
    linhas = tarefas._db().execute(
        f"SELECT id, nome_original, mime, tamanho FROM anexos WHERE id IN ({marcadores})", ids).fetchall()
    return [{"id": a["id"], "nome": a["nome_original"], "mime": a["mime"], "tamanho": a["tamanho"]} for a in linhas]


def _mensagens_da_tarefa(linha) -> list[dict]:
    tarefa_id = linha["id"]
    mensagens = [{"autor": "voce", "texto": linha["texto"], "em": linha["criada_em"], "tarefa_id": tarefa_id,
                  "anexos": _anexos(linha)}]
    status = linha["status"]
    if status == "concluida":
        mensagens.append({
            "autor": "agente", "texto": linha["resposta"] or "", "em": linha["concluida_em"], "tarefa_id": tarefa_id,
            "meta": {"modelo": linha["modelo"], "dificuldade": linha["dificuldade"],
                     "tempo_segundos": round(linha["tempo_segundos"], 1), "adiada": linha["motivo"] is not None},
        })
    elif status == "falhou":
        mensagens.append({"autor": "sistema", "texto": linha["motivo"] or "Falha ao executar a tarefa.",
                          "em": linha["concluida_em"] or linha["criada_em"], "tarefa_id": tarefa_id})
    elif status in AVISOS_ANDAMENTO:
        mensagens.append({"autor": "sistema", "texto": AVISOS_ANDAMENTO[status], "em": linha["criada_em"],
                          "tarefa_id": tarefa_id})
    return mensagens


@rotas.get("/historico/{andar}/{agente_id}")
def historico_do_chat(andar: str, agente_id: str, limite: int = 30, authorization: str = Header("")):
    """Últimas `limite` tarefas do próprio usuário com o agente, em ordem cronológica."""
    usuario = auth.validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if not buscar_agente(andar, agente_id) or not pode_acessar(usuario["role"], andar):
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    limite = min(max(limite, 1), LIMITE_MAXIMO)
    linhas = tarefas._db().execute(
        "SELECT * FROM tarefas WHERE usuario = ? AND andar = ? AND agente = ? ORDER BY id DESC LIMIT ?",
        (usuario["sub"], andar, agente_id, limite),
    ).fetchall()

    mensagens, pendentes = [], []
    for linha in reversed(linhas):
        mensagens.extend(_mensagens_da_tarefa(linha))
        if linha["status"] in AVISOS_ANDAMENTO:
            pendentes.append(linha["id"])
    return {"mensagens": mensagens, "pendentes": pendentes}
