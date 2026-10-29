"""API do Escritório Veraneio: login, WebSocket em tempo real, painel de tarefas e frontend estático."""

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import acesso
import agendamentos
import andamento
import anexos
import agentes_dinamicos
import aprendizado
import atividade
import config
import correcoes
import empresas
import encaminhamento
import espera
import estudos
import modelos_uso
import monday
import cerebro
import cerebro_mapa
import comercial
import entrevista
import historico
import orquestrador
import parar
import producao
import relatorios
import tarefas
import usuarios_admin
from api_painel import rotas as rotas_painel
from auth import autenticar, criar_token, e_master, validar_token
from conexoes import gerenciador
from estado import AGENTES_PRODUCAO, Status, buscar_agente, snapshot

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veraneio")

# 8 mil caracteres (~2 mil tokens): cabem nos modelos gratuitos; o Groq pula sozinho pedido grande (executor.py).
TAMANHO_MAX_TEXTO = 8000
# Só o Gestor recebe pedidos gigantes (briefings de até 30 mil): ele os transforma numa ficha de requisitos antes de
# distribuir à equipe (agents/projeto.py), para ninguém se perder no texto. Thomas, 28/10/2026.
TAMANHO_MAX_GESTOR = 30000
# Comandos reservados do dono, pelo hash (sha256) do texto: nenhum nome no código público nem na interface.
COMANDOS_RESERVADOS = {"ddf7839cb8fca09abdd9e9b0b2f498885f382f5bf9fec65d95db793bd0f11832": "chat",
                       "7416b21e82400f2b73863b1c65dafc0581d462baae82802358ea2c84fd389f7f": "todos"}
# Comercial: o setor já diz a empresa (o Estrategista olha as três; estudos.empresa_do_estudo).
EMPRESA_DO_AGENTE = {"prospectador": "cv_corporativo", "estrategista": empresas.COMUM}
VISAO_DO_GRUPO = {"analista_metricas"}  # podem trabalhar com as três empresas juntas (opção "Todas" do seletor)
EXIGEM_EMPRESA = {"marketing"}  # andares que trabalham para uma empresa (o Cérebro também, ver tratar_mensagem)
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
    from agents.diretrizes import verificar  # manuais por função: nenhum agente pode ficar sem regra obrigatória
    for agente_id, situacao in verificar().items():
        if situacao["faltando"]:
            log.warning("Diretrizes de %s sem %s: confira o mapa SECOES.", agente_id, situacao["faltando"])
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
app.include_router(cerebro_mapa.rotas)
app.include_router(entrevista.rotas)
app.include_router(anexos.rotas)
app.include_router(monday.rotas)
app.include_router(andamento.rotas)
app.include_router(modelos_uso.rotas)
app.include_router(correcoes.rotas)
app.include_router(relatorios.rotas)
app.include_router(usuarios_admin.rotas)
app.include_router(parar.rotas)


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
    return {"token": criar_token(usuario), "usuario": usuario["nome"], "role": usuario["role"],
            "master": e_master(usuario["login"])}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    usuario = await autenticar_ws(ws)
    if not usuario:
        await ws.close(code=4401, reason="Token inválido")
        return

    gerenciador.conectar(ws, usuario)
    await gerenciador.enviar(ws, snapshot(usuario))
    await orquestrador.entregar_pendentes(usuario["sub"])
    try:
        while True:
            await tratar_mensagem(ws, usuario, await ws.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        tinha_chat = ws in gerenciador.chats
        gerenciador.desconectar(ws)
        if tinha_chat:
            await atividade.transmitir_estado()


async def autenticar_ws(ws: WebSocket) -> dict | None:
    """A primeira mensagem precisa ser {"tipo": "auth", "token": "..."} (evita token na URL/logs)."""
    try:
        msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("tipo") != "auth":
        return None
    return validar_token(str(msg.get("token", "")))


async def ensinar_cerebro(ws: WebSocket, usuario: dict, andar: str, agente, texto: str, empresa: str) -> None:
    """Grava o ensinamento (da empresa da conversa, ou comum às três) e registra como tarefa concluída."""
    alvo = {"andar": andar, "agente": agente.id}
    try:
        resposta = await cerebro.ensinar(usuario["sub"], texto, empresa)
    except (PermissionError, ValueError) as e:
        return await gerenciador.enviar(ws, {"tipo": "erro", "texto": str(e), **alvo})
    tarefa_id = tarefas.criar(usuario["sub"], andar, agente.id, texto, "simples",
                              empresa if empresas.valida(empresa) else empresas.PADRAO)
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
    if isinstance(msg, dict) and msg.get("tipo") == "presenca":  # status ativo/ausente e chat aberto
        chat = msg.get("chat")
        if gerenciador.registrar_presenca(ws, bool(msg.get("interagiu")), str(chat) if chat is not None else None):
            await atividade.transmitir_estado()  # "Em uso: ..." aparece/some para os outros na hora
        return
    if not isinstance(msg, dict) or msg.get("tipo") != "mensagem":
        return await erro("Tipo de mensagem desconhecido.")
    gerenciador.registrar_presenca(ws, True)  # enviar um pedido é interação

    andar, agente_id = str(msg.get("andar", "")), str(msg.get("agente", ""))
    texto = str(msg.get("texto", "")).strip()
    # Comandos reservados do dono (limpeza visual do chat). Sem nome no código (o repositório é público): compara o
    # hash do texto. Para qualquer outra conta, ou texto que não seja comando, segue como mensagem comum.
    if usuario["sub"] == config.DONO_MAX and (comando := COMANDOS_RESERVADOS.get(
            hashlib.sha256(texto.lower().encode()).hexdigest())):
        historico.limpar(usuario["sub"], *((andar, agente_id) if comando == "chat" else ()))
        return await gerenciador.enviar(ws, {"tipo": "limpar_chat", "andar": andar, "agente": agente_id,
                                             "todos": comando == "todos"})
    anexos_ids = [str(i) for i in msg.get("anexos") or [] if isinstance(i, str)][:4]
    alvo = {"andar": andar, "agente": agente_id}

    if not acesso.pode_ver_andar(usuario, andar):
        return await erro("Acesso negado.", **alvo)
    agente = buscar_agente(andar, agente_id)
    if not agente:
        return await erro("Agente não encontrado.", **alvo)
    if agente.tipo != "ia":
        return await erro(f"{agente.nome} não recebe tarefas pelo chat.", **alvo)
    if not acesso.pode_usar(usuario, andar, agente.id):  # o master decide quem usa cada agente
        return await erro(f"Você ainda não tem acesso ao {agente.nome}. Fale com o Thomas para liberar.", **alvo)
    if agente.id in AGENTES_PRODUCAO and not config.usa_max(usuario["sub"]):
        return await erro("A produção de imagens e vídeos é exclusiva da conta do Thomas. "
                          "Fale com ele para solicitar.", **alvo)
    limite = TAMANHO_MAX_GESTOR if agente.id == encaminhamento.GESTOR else TAMANHO_MAX_TEXTO
    if not texto or len(texto) > limite:
        extra = "" if limite == TAMANHO_MAX_GESTOR else (
            f" Pedidos maiores (até {TAMANHO_MAX_GESTOR // 1000} mil caracteres) vão direto ao Gestor, que divide o "
            "trabalho com a equipe.")
        return await erro(f"A tarefa deve ter entre 1 e {limite} caracteres.{extra}", **alvo)
    # Marketing e Cérebro trabalham sempre para UMA empresa, escolhida no seletor da conversa (nada é assumido).
    # No Cérebro, "Aprenda:" também aceita "todas" (regra comum às três).
    empresa = str(msg.get("empresa", ""))
    ensino = agente.id == cerebro.ID and cerebro.e_ensino(texto)
    # Ajuste de uma peça já produzida: a empresa é a da peça, nunca a do seletor (nem é preciso escolher).
    # Teste real (27/10/2026): "Ajuste na peça #63" pedia a empresa, que já está na peça.
    base_ajuste = producao.base_do_ajuste(usuario["sub"], agente.id, texto) if agente.id in AGENTES_PRODUCAO else None
    if base_ajuste and (peca := tarefas.obter(base_ajuste)) and empresas.valida(peca["empresa"]):
        empresa = peca["empresa"]
    # Resposta a um formulário: continua a tarefa que perguntou, na empresa dela. Teste real (#84/#85, 28/10/2026):
    # a resposta foi com a empresa do seletor, o histórico perdeu o carrossel e o Gestor retomou o Reels anterior.
    elif (responde_a := msg.get("responde_a")) and isinstance(responde_a, int) \
            and (anterior := tarefas.obter(responde_a)) and anterior["usuario"] == usuario["sub"] \
            and empresas.valida(anterior["empresa"]):
        empresa = anterior["empresa"]
    # A empresa dita no pedido vale mais que o seletor ("A empresa é a Casa Veraneio" com o seletor em Casa Vero).
    elif (dita := empresas.citada(texto)) and empresas.valida(empresa) and dita != empresa \
            and (andar in EXIGEM_EMPRESA or agente.id == cerebro.ID) and not cerebro.e_ensino(texto):
        await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "titulo": "Empresa",
                                      "texto": f"Segui com a {empresas.nome(dita)}, citada no pedido (o seletor da "
                                               f"conversa estava em {empresas.nome(empresa)})."})
        empresa = dita
    if andar in EXIGEM_EMPRESA or agente.id == cerebro.ID:
        todas = empresa == empresas.COMUM and (ensino or agente.id in VISAO_DO_GRUPO)
        if not (empresas.valida(empresa) or todas):
            return await erro("Escolha a empresa desta conversa (Casa Veraneio, Corporativo ou Casa Vero) no "
                              "seletor do topo do chat antes de enviar.", **alvo)
    elif agente.id in EMPRESA_DO_AGENTE:  # Comercial: o setor já diz a empresa (sem seletor)
        empresa = EMPRESA_DO_AGENTE[agente.id]
    else:
        empresa = empresas.PADRAO
    if ensino:  # "Aprenda: ..." (só o dono)
        return await ensinar_cerebro(ws, usuario, andar, agente, texto, empresa)
    # Produção em espera neste chat (o Gestor fez uma pergunta): esta mensagem é a resposta.
    # Correção do Thomas a uma resposta recente vira observação para a revisão semanal (o pedido segue normal).
    orquestrador._em_segundo_plano(asyncio.to_thread(  # correção ou elogio: em segundo plano, sem atrasar a resposta
        correcoes.registrar_se_correcao, usuario["sub"], andar, agente.id, texto))
    if (pendente := espera.no_chat(usuario["sub"], andar, agente.id)):
        texto_aviso = await orquestrador.retomar_producao(pendente, texto)
        return await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "titulo": "Produção", "liberar": True,
                                             "texto": texto_aviso})
    # Estudo com pesquisa na web (Analista de Tendências, Estrategista): no Max, só na conta do Thomas. Para as
    # outras contas, ou pergunta simples ("o que é a Matriz BCG?"), o agente responde pelos modelos gratuitos.
    if config.usa_max(usuario["sub"]) and estudos.e_estudo(agente.id, texto):
        await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "liberar": True, "titulo": "Estudo iniciado",
                                      "texto": "Vou pesquisar na web (notícias, dados de mercado e concorrentes) e "
                                               "trazer o estudo aqui, com as fontes. Leva alguns minutos."})
        await estudos.iniciar(usuario["sub"], andar, agente, texto,
                              estudos.empresa_do_estudo(agente.id, texto, empresa))
        return
    # A resposta final sempre volta ao chat onde o usuário pediu (origem_id), mesmo rodando em outro agente.
    origem_id = None
    aviso = None  # "encaminhei/mandei para...": só sai depois de o pedido passar nas validações abaixo
    # "Ajuste na peça #33" no chat de origem: vai para quem produziu a peça, e a nova versão volta para cá.
    if (produtor := producao.agente_da_peca(usuario["sub"], texto)) and produtor != agente.id:
        origem_id, agente = agente.id, buscar_agente(andar, produtor) or agente
        aviso = {"titulo": "Ajuste enviado",
                 "texto": f"Mandei o ajuste para o {agente.nome}. A nova versão chega aqui quando ficar pronta."}
    # Ajuste de uma peça deste mesmo agente de produção: vai direto para a produção (nova versão da peça), sem
    # perguntar "planejamento ou peça final" e sem passar pelo Gestor. Teste real (27/10/2026): "Ajuste na peça #63:
    # ajuste todos os slides..." foi tratado como peça nova.
    elif base_ajuste:
        pass
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
    # Produção: quem produz é o especialista do formato (vídeo = Editor de Vídeo; imagem = Criador de Imagens), mesmo
    # que o pedido tenha sido feito ao outro. No ajuste, conta também o que a peça original era (#63: carrossel em
    # vídeo feito pelo Criador de Imagens). A entrega volta ao chat onde o usuário pediu.
    base_producao = None
    if agente.id in AGENTES_PRODUCAO:
        base_producao = base_ajuste or producao.base_do_ajuste(usuario["sub"], agente.id, texto)
        peca_base = tarefas.obter(base_producao) if base_producao else None
        original = peca_base["texto"] if peca_base else ""
        alvo_produtor = producao.produtor_da_peca(f"{texto}\n{original}")
        if alvo_produtor != agente.id and (especialista := buscar_agente(andar, alvo_produtor)):
            origem_id = origem_id or agente.id
            aviso = {"titulo": "Com o especialista",
                     "texto": f"{'Este ajuste' if base_producao else 'Esta peça'} é de "
                              f"{'vídeo' if alvo_produtor == 'editor_video' else 'imagem'}, então quem produz é o "
                              f"{especialista.nome}. A entrega chega aqui quando ficar pronta."}
            agente = especialista
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
    # Todos leem e escrevem no Monday pelo chat, com as credenciais universais da empresa (Thomas, 29/10/2026).
    contexto, item_citado = (await asyncio.to_thread(monday.contexto_citado, texto)
                             if monday.CITACAO.search(texto) else ("", None))

    def ao_criar(tarefa_id: int) -> None:
        if origem_id:
            encaminhamento.registrar(tarefa_id, andar, origem_id)
        if item_citado:
            monday.vincular(tarefa_id, item_citado, origem="chat")

    # Prospecção (pesquisa na web pelo Max + leads no Monday) ou persona. Liberada para quem usa o Max (todos desde
    # 29/10/2026); quem pode usar o Prospectador se controla no painel de usuários. O resto é conversa.
    if agente.id == comercial.AGENTE and comercial.e_pedido_de_trabalho(texto):
        if not config.usa_max(usuario["sub"]):
            return await erro("A prospecção (pesquisa na web e leads no Monday) é exclusiva da conta do Thomas. "
                              "Aqui você pode tirar dúvidas sobre a persona e a estratégia.", **alvo)
        if not (comercial.PEDE_CRIACAO.search(texto) or comercial.PEDE_PERSONA.search(texto)):
            await gerenciador.enviar(ws, {"tipo": "aviso", **alvo, "liberar": True, "titulo": "Prospecção iniciada",
                                          "texto": "Vou pesquisar as empresas na web e trazer uma prévia aqui, sem "
                                                   "criar nada no Monday. Leva alguns minutos."})
        await comercial.iniciar(usuario["sub"], agente, texto)
        return
    if agente.id in AGENTES_PRODUCAO:  # só chega aqui o dono do plano Max (checado acima)
        # "Ajuste na peça #20: ..." ou "troque o título...": nova versão da peça anterior, na mesma pasta.
        await producao.enfileirar(usuario["sub"], andar, agente, f"{texto}\n\n{contexto}".strip(), empresa=empresa,
                                  anexos=anexos.caminhos(anexos_ids, usuario["sub"]),
                                  base=base_producao, ao_criar=ao_criar)
    else:
        await orquestrador.nova_tarefa(usuario["sub"], andar, agente, texto, anexos_ids, contexto=contexto, empresa=empresa,
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
