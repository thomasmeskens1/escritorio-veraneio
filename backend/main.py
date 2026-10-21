"""API do Escritório Veraneio: login, WebSocket em tempo real, painel de tarefas e frontend estático."""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agendamentos
import anexos
import agentes_dinamicos
import aprendizado
import atividade
import config
import encaminhamento
import cerebro
import historico
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
MAX_FALHAS_LOGIN = 5          # senhas erradas seguidas por usuário/IP antes do bloqueio
BLOQUEIO_LOGIN_S = 15 * 60

_falhas_login: dict[tuple[str, str], list[float]] = {}  # (usuário, IP) -> horários das falhas


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    tarefas.iniciar()
    producao.iniciar()
    agentes_dinamicos.carregar()  # agentes criados pelo Construtor voltam ao prédio
    aprendizado.carregar()
    atividade.vincular_loop(asyncio.get_running_loop())
    cerebro.iniciar()  # conhecimento: tabelas, indexação inicial e consolidação diária
    fila = asyncio.create_task(orquestrador.processar_fila())
    agendamentos.iniciar()  # rotinas agendadas (recarrega as ativas do banco)
    yield
    agendamentos.parar()
    fila.cancel()


# Sem /docs, /redoc e /openapi.json: não expõe o mapa da API.
app = FastAPI(title="Escritório Veraneio", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(rotas_painel)
app.include_router(producao.rotas)
app.include_router(historico.rotas)
app.include_router(agentes_dinamicos.rotas)
app.include_router(agendamentos.rotas)
app.include_router(cerebro.rotas)
app.include_router(anexos.rotas)


class Credenciais(BaseModel):
    usuario: str
    senha: str


@app.post("/api/login")
def login(credenciais: Credenciais, request: Request):
    chave = (credenciais.usuario.strip().lower(), request.client.host if request.client else "")
    agora = time.monotonic()
    falhas = [t for t in _falhas_login.get(chave, []) if agora - t < BLOQUEIO_LOGIN_S]
    if len(falhas) >= MAX_FALHAS_LOGIN:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente de novo em alguns minutos.")
    usuario = autenticar(credenciais.usuario, credenciais.senha)
    if not usuario:
        _falhas_login[chave] = [*falhas, agora]
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    _falhas_login.pop(chave, None)
    return {"token": criar_token(usuario), "usuario": usuario["nome"], "role": usuario["role"]}


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


async def ensinar_cerebro(ws: WebSocket, usuario: dict, andar: str, agente, texto: str) -> None:
    """Grava o ensinamento e registra como tarefa concluída (aparece no histórico e no registro)."""
    alvo = {"andar": andar, "agente": agente.id}
    try:
        resposta = await cerebro.ensinar(usuario["sub"], texto)
    except (PermissionError, ValueError) as e:
        return await gerenciador.enviar(ws, {"tipo": "erro", "texto": str(e), **alvo})
    tarefa_id = tarefas.criar(usuario["sub"], andar, agente.id, texto, "simples")
    tarefas.atualizar(tarefa_id, status="concluida", modelo="cerebro/ensino", resposta=resposta)
    tarefas.registrar_evento(tarefa_id, "concluida", agente.id, "cerebro/ensino", "Conhecimento ensinado pelo dono")
    await orquestrador.entregar(tarefas.obter(tarefa_id))


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
    anexos_ids = [str(i) for i in msg.get("anexos") or [] if isinstance(i, str)][:4]
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
    if agente.id == cerebro.ID and cerebro.e_ensino(texto):  # "Aprenda: ..." (só o dono)
        return await ensinar_cerebro(ws, usuario, andar, agente, texto)
    # "...todos os dias às 8h" vira rotina agendada (vale mesmo com o agente ocupado agora).
    if agendamentos.e_agendamento(texto) and await agendamentos.criar(usuario["sub"], andar, agente.id, texto):
        return
    # Peça completa pedida a um especialista do Marketing: o Gestor coordena a equipe.
    if encaminhamento.para_o_gestor(andar, agente.id, texto):
        gestor = buscar_agente(andar, encaminhamento.GESTOR)
        await gerenciador.enviar(ws, {
            "tipo": "aviso", **alvo, "titulo": "Encaminhado ao Gestor", "liberar": True,
            "texto": f"Isso é uma peça completa, então encaminhei ao Gestor: ele monta o plano e aciona "
                     f"{agente.nome}, Designer, Criador de Imagens e quem mais precisar. "
                     "A resposta chega na conversa do Gestor."})
        agente, texto, alvo = gestor, f"[Pedido feito ao {agente.nome}] {texto}", {"andar": andar, "agente": gestor.id}
    if agente.status == Status.trabalhando:
        return await erro(f"{agente.nome} já está trabalhando em outra tarefa.", **alvo)
    if not orquestrador.ha_modelo_disponivel():
        return await erro("Nenhum modelo de IA configurado no servidor.", **alvo)

    if agente.id in AGENTES_PRODUCAO:  # só chega aqui o dono do plano Max (checado acima)
        await producao.enfileirar(usuario["sub"], andar, agente, texto, anexos=anexos.caminhos(anexos_ids))
    else:
        await orquestrador.nova_tarefa(usuario["sub"], andar, agente, texto, anexos_ids)


class FrontendSemCacheVelho(StaticFiles):
    """Obriga o navegador a revalidar (ETag → 304), para nunca usar JS/HTML desatualizado."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


# Frontend servido na mesma origem (montado por último para não sombrear as rotas acima).
if config.FRONTEND_DIR.is_dir():
    app.mount("/", FrontendSemCacheVelho(directory=config.FRONTEND_DIR, html=True), name="frontend")
