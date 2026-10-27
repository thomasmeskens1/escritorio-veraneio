"""Memória do chat: conversa de cada usuário com um agente, reconstruída a partir das tarefas salvas."""

import json

from fastapi import APIRouter, Header, HTTPException

import auth
import encaminhamento
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


def _mensagens_da_tarefa(linha, encaminhada: bool | None = None) -> list[dict]:
    """`encaminhada`: None = tarefa deste chat; True/False = nasceu aqui e rodou em outro agente (com/sem o
    pedido do usuário no texto). A resposta vem assinada por quem respondeu."""
    tarefa_id = linha["id"]
    mensagens = []
    if encaminhada is not False:
        texto = encaminhamento.pedido_original(linha["texto"]) if encaminhada else linha["texto"]
        mensagens.append({"autor": "voce", "texto": texto, "em": linha["criada_em"], "tarefa_id": tarefa_id,
                          "anexos": _anexos(linha)})
    status = linha["status"]
    if status == "concluida":
        quem = buscar_agente(linha["andar"], linha["agente"]) if encaminhada is not None else None
        mensagens.append({
            "autor": "agente", "texto": linha["resposta"] or "", "em": linha["concluida_em"], "tarefa_id": tarefa_id,
            "meta": {"modelo": linha["modelo"], "dificuldade": linha["dificuldade"],
                     "tempo_segundos": round(linha["tempo_segundos"], 1), "adiada": linha["motivo"] is not None,
                     **({"por": quem.nome} if quem else {})},
        })
    elif status == "falhou":
        mensagens.append({"autor": "sistema", "texto": linha["motivo"] or "Falha ao executar a tarefa.",
                          "em": linha["concluida_em"] or linha["criada_em"], "tarefa_id": tarefa_id})
    elif status in AVISOS_ANDAMENTO:
        mensagens.append({"autor": "sistema", "texto": AVISOS_ANDAMENTO[status], "em": linha["criada_em"],
                          "tarefa_id": tarefa_id})
    return mensagens


# Limpeza VISUAL do chat (recurso reservado do dono): a conversa passa a ser mostrada só a partir de certa tarefa.
# Não apaga nada: as tarefas e a memória dos agentes (tarefas.historico) continuam intactas.
_ESQUEMA_LIMPEZA = ("CREATE TABLE IF NOT EXISTS chat_limpo (usuario TEXT NOT NULL, chave TEXT NOT NULL, "
                    "ate_id INTEGER NOT NULL, PRIMARY KEY (usuario, chave))")
TODOS = "*"


def limpar(usuario: str, andar: str = "", agente_id: str = "") -> None:
    """Esconde da tela do usuário as tarefas já terminadas: deste chat, ou de todos (sem andar/agente)."""
    banco = tarefas._db()
    with banco:
        banco.execute(_ESQUEMA_LIMPEZA)
        ate = banco.execute("SELECT COALESCE(MAX(id), 0) FROM tarefas WHERE usuario = ? AND status IN "
                            "('concluida', 'falhou')", (usuario,)).fetchone()[0]
        banco.execute("INSERT OR REPLACE INTO chat_limpo (usuario, chave, ate_id) VALUES (?, ?, ?)",
                      (usuario, f"{andar}/{agente_id}" if andar else TODOS, ate))


def _limpo_ate(usuario: str, andar: str, agente_id: str) -> int:
    banco = tarefas._db()
    banco.execute(_ESQUEMA_LIMPEZA)
    linha = banco.execute("SELECT MAX(ate_id) FROM chat_limpo WHERE usuario = ? AND chave IN (?, ?)",
                          (usuario, f"{andar}/{agente_id}", TODOS)).fetchone()
    return linha[0] or 0


@rotas.get("/historico/{andar}/{agente_id}")
def historico_do_chat(andar: str, agente_id: str, limite: int = 30, authorization: str = Header("")):
    """Últimas `limite` tarefas do próprio usuário com o agente, em ordem cronológica."""
    usuario = auth.validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if not buscar_agente(andar, agente_id) or not pode_acessar(usuario["role"], andar):
        raise HTTPException(status_code=404, detail="Agente não encontrado")

    limite = min(max(limite, 1), LIMITE_MAXIMO)
    # Tarefas do chat + as que nasceram aqui e rodaram em outro agente (Gestor, produção).
    vindas = encaminhamento.tarefas_do_chat(andar, agente_id)
    marcadores = ",".join("?" * len(vindas)) or "NULL"
    linhas = tarefas._db().execute(
        f"SELECT * FROM tarefas WHERE usuario = ? AND ((andar = ? AND agente = ?) OR id IN ({marcadores})) "
        "AND id > ? ORDER BY id DESC LIMIT ?",
        (usuario["sub"], andar, agente_id, *vindas, _limpo_ate(usuario["sub"], andar, agente_id), limite),
    ).fetchall()

    mensagens, pendentes = [], []
    for linha in reversed(linhas):
        de_outro = linha["id"] in vindas and (linha["andar"], linha["agente"]) != (andar, agente_id)
        mensagens.extend(_mensagens_da_tarefa(linha, vindas[linha["id"]] if de_outro else None))
        if linha["status"] in AVISOS_ANDAMENTO:
            pendentes.append(linha["id"])
    return {"mensagens": mensagens, "pendentes": pendentes}
