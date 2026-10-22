"""API do Escritório Veraneio: login, WebSocket em tempo real, painel de tarefas e frontend estático."""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agendamentos
import andamento
import anexos
import agentes_dinamicos
import aprendizado
import atividade
import config
import encaminhamento
import espera
import modelos_uso
import monday
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
MAX_FALHAS_IP = 20            # senhas erradas de um IP (qualquer usuário) antes do bloqueio
BLOQUEIO_LOGIN_S = 15 * 60
INTERVALO_COPIA_BANCO_S = 6 * 3600

_falhas_login: dict[tuple[str, str], list[float]] = {}  # (usuário, IP) -> horários das falhas
_falhas_ip: dict[str, list[float]] = {}                 # IP -> horários das falhas (usuários aleatórios)


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
    copias = asyncio.create_task(copiar_banco_periodicamente())
    yield
    agendamentos.parar()
    fila.cancel()
    copias.cancel()


async def copiar_banco_periodicamente() -> None:
    """O banco vive num volume do Docker: a cada 6 h uma cópia consistente vai para dados/ (backup diário)."""
    while True:
        try:
            await asyncio.to_thread(tarefas.copiar_para_backup)
        except Exception:
            log.exception("Não foi possível copiar o banco para o backup.")
        await asyncio.sleep(INTERVALO_COPIA_BANCO_S)


# Sem /docs, /redoc e /openapi.json: não expõe o mapa da API.
app = FastAPI(title="Escritório Veraneio", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)

# Cabeçalhos de segurança: a página só roda scripts do próprio sistema (o Phaser também é servido daqui) e só
# conversa com a própria origem (inclusive o WebSocket).
CABECALHOS_SEGURANCA = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; font-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, chamar_proximo):
    resposta = await chamar_proximo(request)
    for nome, valor in CABECALHOS_SEGURANCA.items():
        resposta.headers.setdefault(nome, valor)
    return resposta


@app.get("/api/saude")
def saude_do_sistema():
    """Para o monitoramento externo (UptimeRobot): só diz se o sistema está no ar."""
    return {"ok": True}


app.include_router(rotas_painel)
app.include_router(producao.rotas)
app.include_router(historico.rotas)
app.include_router(agentes_dinamicos.rotas)
app.include_router(agendamentos.rotas)
app.include_router(cerebro.rotas)
app.include_router(anexos.rotas)
app.include_router(monday.rotas)
app.include_router(andamento.rotas)
app.include_router(modelos_uso.rotas)


class Credenciais(BaseModel):
    usuario: str = Field(max_length=120)
    senha: str = Field(max_length=200)  # o hash custa caro: senha gigante não chega a ser calculada


def _podar_falhas(agora: float) -> None:
    """Esquece falhas antigas: os registros não crescem sem limite."""
    if len(_falhas_login) + len(_falhas_ip) < 500:
        return
    for registro in (_falhas_login, _falhas_ip):
        for chave in [c for c, ts in registro.items() if not ts or agora - ts[-1] >= BLOQUEIO_LOGIN_S]:
            del registro[chave]


@app.post("/api/login")
def login(credenciais: Credenciais, request: Request):
    ip = request.client.host if request.client else ""
    chave = (credenciais.usuario.strip().lower(), ip)
    agora = time.monotonic()
    _podar_falhas(agora)
    falhas = [t for t in _falhas_login.get(chave, []) if agora - t < BLOQUEIO_LOGIN_S]
    falhas_ip = [t for t in _falhas_ip.get(ip, []) if agora - t < BLOQUEIO_LOGIN_S]
    # Antes do hash (caro): tentativas com usuários aleatórios do mesmo IP também esbarram no limite.
    if len(falhas) >= MAX_FALHAS_LOGIN or len(falhas_ip) >= MAX_FALHAS_IP:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente de novo em alguns minutos.")
    usuario = autenticar(credenciais.usuario, credenciais.senha)
    if not usuario:
        _falhas_login[chave] = [*falhas, agora]
        _falhas_ip[ip] = [*falhas_ip, agora]
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
    # Produção em espera neste chat (o Gestor fez uma pergunta): esta mensagem é a resposta.
    if (pendente := espera.no_chat(usuario["sub"], andar, agente.id)):
        texto_aviso = await orquestrador.retomar_producao(pendente, texto)
        return await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "titulo": "Produção", "liberar": True,
                                             "texto": texto_aviso})
    # A resposta final sempre volta ao chat onde o usuário pediu (origem_id), mesmo rodando em outro agente.
    origem_id = None
    aviso = None  # "encaminhei/mandei para...": só sai depois de o pedido passar nas validações abaixo
    # "Ajuste na peça #33" no chat de origem: vai para quem produziu a peça, e a nova versão volta para cá.
    if (produtor := producao.agente_da_peca(usuario["sub"], texto)) and produtor != agente.id:
        origem_id, agente = agente.id, buscar_agente(andar, produtor) or agente
        aviso = {"titulo": "Ajuste enviado",
                 "texto": f"Mandei o ajuste para o {agente.nome}. A nova versão chega aqui quando ficar pronta."}
    # Peça pedida sem dizer se quer o planejamento ou o arquivo pronto: pergunta antes (botões no chat).
    elif encaminhamento.precisa_escolher(andar, agente.id, texto):
        return await gerenciador.enviar(ws, {
            "tipo": "aviso", **alvo, "titulo": "Planejamento ou peça final?", "liberar": True,
            "texto": "Antes de acionar a equipe: você quer só o planejamento (ideias, textos e roteiro, sem produzir "
                     "arquivos) ou a peça final pronta (artes e vídeos produzidos no Max)?",
            "opcoes": [{"rotulo": "Só o planejamento", "texto": f"Planejamento: {texto}"},
                       {"rotulo": "Peça final", "texto": f"Peça final: {texto}"}]})
    # Peça completa pedida a um especialista do Marketing: o Gestor coordena a equipe.
    elif encaminhamento.para_o_gestor(andar, agente.id, texto):
        origem_id = agente.id
        gestor = buscar_agente(andar, encaminhamento.GESTOR)
        aviso = {"titulo": "Encaminhado ao Gestor",
                 "texto": f"Isso é uma peça completa, então encaminhei ao Gestor: ele monta o plano e aciona "
                          f"{agente.nome}, Designer, Criador de Imagens e quem mais precisar. "
                          "A resposta final chega aqui, nesta conversa, quando a equipe terminar."}
        agente, texto = gestor, f"[Pedido feito ao {agente.nome}] {texto}"
        # Pedido de peça pelo chat: o formato pedido (STORIES, POST...) vai explícito, como nos itens do Monday.
        # Teste real: "4 stories" foi respondido depois como REELS.
        if (formato := monday.linha_de_formato(texto)):
            texto = f"{texto}\n\n{formato}"
    # Erros e avisos imediatos ficam no chat onde o usuário escreveu (alvo não muda).
    # Produção (Criador de Imagens, Editor de Vídeo) tem fila: ocupado não impede pedir outra peça ou ajuste.
    if agente.status == Status.trabalhando and agente.id not in AGENTES_PRODUCAO:
        return await erro(f"{agente.nome} já está trabalhando em outra tarefa.", **alvo)
    if not orquestrador.ha_modelo_disponivel():
        return await erro("Nenhum modelo de IA configurado no servidor.", **alvo)
    if aviso:
        await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "liberar": True, **aviso})

    # 'Faça uma legenda para o item "FEED | ..."': os dados do item do Monday entram no pedido.
    # O resultado também vai para o item (comentário e legenda), sem mudar o status dele.
    # Só a conta do Thomas lê e escreve no Monday pelo chat (usa o token do sistema).
    contexto, item_citado = (await asyncio.to_thread(monday.contexto_citado, texto)
                             if usuario["sub"] == config.DONO_MAX and monday.CITACAO.search(texto) else ("", None))

    def ao_criar(tarefa_id: int) -> None:
        if origem_id:
            encaminhamento.registrar(tarefa_id, andar, origem_id)
        if item_citado:
            monday.vincular(tarefa_id, item_citado, origem="chat")

    if agente.id in AGENTES_PRODUCAO:  # só chega aqui o dono do plano Max (checado acima)
        # "Ajuste na peça #20: ..." ou "troque o título...": nova versão da peça anterior, na mesma pasta.
        await producao.enfileirar(usuario["sub"], andar, agente, f"{texto}\n\n{contexto}".strip(),
                                  anexos=anexos.caminhos(anexos_ids, usuario["sub"]),
                                  base=producao.base_do_ajuste(usuario["sub"], agente.id, texto), ao_criar=ao_criar)
    else:
        await orquestrador.nova_tarefa(usuario["sub"], andar, agente, texto, anexos_ids, contexto=contexto,
                                       ao_criar=ao_criar)


class FrontendSemCacheVelho(StaticFiles):
    """Obriga o navegador a revalidar (ETag → 304), para nunca usar JS/HTML desatualizado."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


# Frontend servido na mesma origem (montado por último para não sombrear as rotas acima).
if config.FRONTEND_DIR.is_dir():
    app.mount("/", FrontendSemCacheVelho(directory=config.FRONTEND_DIR, html=True), name="frontend")
