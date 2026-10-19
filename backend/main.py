"""API do Escritório Veraneio: login, WebSocket em tempo real e frontend estático."""

import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from auth import autenticar, criar_token, validar_token
from conexoes import GerenciadorConexoes
from estado import Agente, Status, buscar_agente, pode_acessar, snapshot

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veraneio")

TAMANHO_MAX_TEXTO = 4000

app = FastAPI(title="Escritório Veraneio")
gerenciador = GerenciadorConexoes()
tarefas: set[asyncio.Task] = set()  # referência forte às tarefas em execução


class Credenciais(BaseModel):
    usuario: str
    senha: str


async def atualizar_status(agente: Agente, status: Status) -> None:
    agente.status = status
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


@app.post("/api/login")
def login(credenciais: Credenciais):
    usuario = autenticar(credenciais.usuario, credenciais.senha)
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    return {"token": criar_token(usuario), "usuario": usuario["nome"], "role": usuario["role"]}


@app.get("/test/{andar}/{agente_id}/{status}")
async def testar_status(andar: str, agente_id: str, status: Status):
    """Rota de desenvolvimento: muda o status de um agente e transmite o novo estado."""
    agente = buscar_agente(andar, agente_id)
    if not agente:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    await atualizar_status(agente, status)
    return agente


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    usuario = await autenticar_ws(ws)
    if not usuario:
        await ws.close(code=4401, reason="Token inválido")
        return

    gerenciador.conectar(ws, usuario)
    await gerenciador.enviar(ws, snapshot(usuario["role"]))
    try:
        while True:
            await tratar_mensagem(ws, usuario, await ws.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        gerenciador.desconectar(ws)


async def autenticar_ws(ws: WebSocket) -> dict | None:
    """A primeira mensagem precisa ser {"tipo": "auth", "token": "..."} (evita token na URL/logs)."""
    try:
        msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("tipo") != "auth":
        return None
    return validar_token(str(msg.get("token", "")))


async def tratar_mensagem(ws: WebSocket, usuario: dict, bruto: str) -> None:
    async def erro(texto: str, **extra) -> None:
        await gerenciador.enviar(ws, {"tipo": "erro", "texto": texto, **extra})

    try:
        msg = json.loads(bruto)
    except ValueError:
        return await erro("JSON inválido.")
    if not isinstance(msg, dict) or msg.get("tipo") != "mensagem":
        return await erro("Tipo de mensagem desconhecido.")

    andar, agente_id = str(msg.get("andar", "")), str(msg.get("agente", ""))
    texto = str(msg.get("texto", "")).strip()
    alvo = {"andar": andar, "agente": agente_id}

    if not pode_acessar(usuario["role"], andar):
        return await erro("Acesso negado.", **alvo)
    agente = buscar_agente(andar, agente_id)
    if not agente:
        return await erro("Agente não encontrado.", **alvo)
    if not texto or len(texto) > TAMANHO_MAX_TEXTO:
        return await erro(f"A tarefa deve ter entre 1 e {TAMANHO_MAX_TEXTO} caracteres.", **alvo)
    if agente.status == Status.trabalhando:
        return await erro(f"{agente.nome} já está trabalhando em outra tarefa.", **alvo)
    if not config.cadeia_modelos(agente.id):
        return await erro("Nenhum modelo de IA configurado no servidor.", **alvo)

    await atualizar_status(agente, Status.trabalhando)
    tarefa = asyncio.create_task(executar_tarefa(ws, andar, agente, texto))
    tarefas.add(tarefa)
    tarefa.add_done_callback(tarefas.discard)


async def executar_tarefa(ws: WebSocket, andar: str, agente: Agente, texto: str) -> None:
    """Roda a Crew fora do loop de eventos e devolve a resposta ao chat."""
    alvo = {"andar": andar, "agente": agente.id}
    try:
        from agents.marketing_crew import executar  # import tardio: CrewAI é pesado

        resposta, modelo = await asyncio.wait_for(executar(agente.id, texto), timeout=config.TEMPO_LIMITE_TAREFA)
        await gerenciador.enviar(ws, {"tipo": "resposta_agente", **alvo, "texto": resposta, "modelo": modelo})
    except asyncio.TimeoutError:
        await gerenciador.enviar(ws, {"tipo": "erro", "texto": "A tarefa excedeu o tempo limite.", **alvo})
    except Exception:
        log.exception("Falha ao executar tarefa de %s", agente.id)
        await gerenciador.enviar(ws, {"tipo": "erro", "texto": "Falha ao executar a tarefa.", **alvo})
    finally:
        await atualizar_status(agente, Status.disponivel)


# Frontend servido na mesma origem (montado por último para não sombrear as rotas acima).
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
