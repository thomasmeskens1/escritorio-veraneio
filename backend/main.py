"""API do Escritório Veraneio: login, WebSocket em tempo real, painel de tarefas e frontend estático."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import aprendizado
import atividade
import config
import diretora
import orquestrador
import producao
import tarefas
from api_painel import rotas as rotas_painel
from auth import autenticar, criar_token, validar_token
from conexoes import gerenciador
from estado import AGENTES_PRODUCAO, Status, buscar_agente, pode_acessar, snapshot

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veraneio")

TAMANHO_MAX_TEXTO = 4000


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    tarefas.iniciar()
    producao.iniciar()
    aprendizado.carregar()
    diretora.vincular_loop(asyncio.get_running_loop())
    atividade.vincular_loop(asyncio.get_running_loop())
    fila = asyncio.create_task(orquestrador.processar_fila())
    yield
    fila.cancel()


app = FastAPI(title="Escritório Veraneio", lifespan=ciclo_de_vida)
app.include_router(rotas_painel)
app.include_router(producao.rotas)


class Credenciais(BaseModel):
    usuario: str
    senha: str


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
    await orquestrador.atualizar_status(agente, status)
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
    await orquestrador.entregar_pendentes(usuario["sub"])
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
    if agente.tipo != "ia":
        return await erro(f"{agente.nome} não recebe tarefas pelo chat.", **alvo)
    if agente.id in AGENTES_PRODUCAO and usuario["sub"] != config.DONO_MAX:
        return await erro("A produção de imagens e vídeos é exclusiva da conta do Thomas. "
                          "Fale com ele para solicitar.", **alvo)
    if not texto or len(texto) > TAMANHO_MAX_TEXTO:
        return await erro(f"A tarefa deve ter entre 1 e {TAMANHO_MAX_TEXTO} caracteres.", **alvo)
    if agente.status == Status.trabalhando:
        return await erro(f"{agente.nome} já está trabalhando em outra tarefa.", **alvo)
    if not orquestrador.ha_modelo_disponivel():
        return await erro("Nenhum modelo de IA configurado no servidor.", **alvo)

    if agente.id in AGENTES_PRODUCAO:  # só chega aqui o dono do plano Max (checado acima)
        await producao.enfileirar(usuario["sub"], andar, agente, texto)
    else:
        await orquestrador.nova_tarefa(usuario["sub"], andar, agente, texto)


class FrontendSemCacheVelho(StaticFiles):
    """Obriga o navegador a revalidar (ETag → 304), para nunca usar JS/HTML desatualizado."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


# Frontend servido na mesma origem (montado por último para não sombrear as rotas acima).
if config.FRONTEND_DIR.is_dir():
    app.mount("/", FrontendSemCacheVelho(directory=config.FRONTEND_DIR, html=True), name="frontend")
