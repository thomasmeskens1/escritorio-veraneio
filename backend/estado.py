"""Estado dos agentes, dividido por andar (em memória)."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Status(str, Enum):
    dormindo = "dormindo"
    disponivel = "disponivel"
    trabalhando = "trabalhando"
    construindo = "construindo"  # agente sendo criado pelo Construtor


class Cabelo(BaseModel):
    estilo: Literal["curto", "longo", "coque", "careca", "cacheado", "moicano"]
    cor: str


class Roupa(BaseModel):
    estilo: Literal["camiseta", "camisa", "blazer", "moletom", "macacao", "avental"]
    cor: str


class Aparencia(BaseModel):
    """Visual do avatar; o Construtor gera aparências novas neste mesmo formato."""

    pele: str
    cabelo: Cabelo
    roupa: Roupa
    calca: str
    acessorio: Literal["nenhum", "oculos", "fone", "bone", "capacete", "cracha", "gravata", "camera", "lapis"]


class Agente(BaseModel):
    id: str
    nome: str
    funcao: str
    aparencia: Aparencia
    setor: str
    descricao: str = ""
    exemplo: str = ""  # pedido curto de exemplo (aparece no popup do agente)
    tipo: Literal["ia", "sistema", "estagiario"] = "ia"  # sistema: painel; estagiario: sem interação
    visual: Literal["humano", "cerebro"] = "humano"  # "cerebro": o frontend desenha o rato do laboratório
    status: Status = Status.disponivel
    visitando: dict | None = None  # {"andar", "agente"} enquanto um estagiário atende em outro andar


# Campos que não vão no `estado` transmitido a cada mudança (o popup busca em /api/agentes).
_SO_NO_DETALHE = {"descricao", "exemplo"}


def _ap(pele, cabelo, cor_cabelo, roupa, cor_roupa, calca, acessorio) -> Aparencia:
    return Aparencia(pele=pele, cabelo=Cabelo(estilo=cabelo, cor=cor_cabelo),
                     roupa=Roupa(estilo=roupa, cor=cor_roupa), calca=calca, acessorio=acessorio)


def _andar(*agentes: Agente) -> dict[str, Agente]:
    return {a.id: a for a in agentes}


ANDARES: dict[str, dict[str, Agente]] = {
    "porao": _andar(
        Agente(id="construtor", nome="Construtor", funcao="Cria novos agentes para o escritório", setor="oficina",
               descricao="Transforma um briefing na especificação completa de um novo agente, com visual exclusivo.",
               exemplo="Crie um agente de Vendas para atender leads de hóspedes.",
               aparencia=_ap("#c68642", "curto", "#2b1d0e", "macacao", "#f4a261", "#3d405b", "capacete")),
        Agente(id="despachante", nome="Despachante", funcao="Classifica tarefas e opera a fila do Claude",
               setor="operacoes", tipo="sistema",
               descricao="Classifica a dificuldade de cada tarefa, escolhe os modelos e opera a fila adiada.",
               aparencia=_ap("#8d5524", "careca", "#000000", "camisa", "#457b9d", "#1d3557", "fone")),
    ),
    "terreo": _andar(
        Agente(id="recepcionista", nome="Recepcionista", funcao="Especialista em onboarding",
               setor="escola", descricao="Apresenta o sistema num tour guiado (botão “Iniciar Onboarding”) e tira "
                                         "dúvidas sobre o uso do escritório no chat.",
               exemplo="Como acompanho o andamento de uma tarefa?",
               aparencia=_ap("#ffdbac", "longo", "#b5651d", "blazer", "#2a9d8f", "#264653", "cracha")),
        Agente(id="professor", nome="Professor", funcao="Ensina a pedir tarefas e escrever bons briefings",
               setor="escola", descricao="Ajuda a transformar pedidos vagos em briefings claros, com exemplos.",
               exemplo="Como peço um post para o Instagram do jeito certo?",
               aparencia=_ap("#e0ac69", "curto", "#9e9e9e", "camisa", "#6d597a", "#355070", "oculos")),
    ),
    "marketing": _andar(
        Agente(id="gestor", nome="Gestor", funcao="Coordena, delega e revisa o time", setor="gestao",
               descricao="Divide pedidos grandes em etapas, aciona os especialistas certos e revisa a entrega final.",
               exemplo="Monte o plano de outubro das redes sociais da Casa Veraneio.",
               aparencia=_ap("#8d5524", "curto", "#1b1b1b", "blazer", "#343a40", "#212529", "gravata")),
        Agente(id="designer", nome="Designer", funcao="Direção de arte e identidade visual", setor="criacao",
               descricao="Define conceito visual, paleta, tipografia e o layout das peças.",
               exemplo="Defina o conceito visual da campanha de verão.",
               aparencia=_ap("#f1c27d", "cacheado", "#7b2cbf", "camiseta", "#e76f51", "#22223b", "oculos")),
        Agente(id="criador_imagens", nome="Criador de Imagens", funcao="Monta as imagens dos posts (PNG)",
               setor="criacao", descricao="Especifica e monta as artes finais dos posts com as fotos reais dos produtos.",
               exemplo="Monte a arte do post do Lodge 239 para o Réveillon.",
               aparencia=_ap("#f1c27d", "moicano", "#2a9d8f", "camiseta", "#ffb703", "#023047", "lapis")),
        Agente(id="copywriter", nome="Copywriter", funcao="Textos, legendas e chamadas", setor="conteudo",
               descricao="Escreve legendas, títulos e chamadas no tom de voz da marca.",
               exemplo="Escreva 3 legendas para o carrossel do Lodge 239 no Réveillon.",
               aparencia=_ap("#c68642", "longo", "#1b1b1b", "camisa", "#e5989b", "#6d6875", "oculos")),
        Agente(id="social_media", nome="Social Media", funcao="Calendário e publicação", setor="conteudo",
               descricao="Organiza o calendário editorial, formatos, horários e a rotina de publicação.",
               exemplo="Monte o calendário de posts da próxima semana.",
               aparencia=_ap("#ffdbac", "coque", "#d4a373", "moletom", "#ff006e", "#3a0ca3", "fone")),
        Agente(id="email_marketing", nome="E-mail Marketing", funcao="Campanhas de e-mail (Brevo)", setor="conteudo",
               descricao="Escreve as campanhas de e-mail (assunto, pré-header, blocos e botões) no padrão dos e-mails "
                         "que já funcionaram e deixa o rascunho pronto no Brevo para revisão.",
               exemplo="Escreva o e-mail do feriado de 15/11 com 3 Lodges no litoral.",
               aparencia=_ap("#e0ac69", "longo", "#3b2f2f", "camisa", "#f4a261", "#2b2d42", "oculos")),
        Agente(id="analista_tendencias", nome="Analista de Tendências", funcao="Tendências, datas e previsões",
               setor="reuniao",
               descricao="Antecipa os momentos que importam (Carnaval, Natal, Réveillon, feriadões, grandes eventos) "
                         "com as datas calculadas e propõe com antecedência os temas e ganchos para a produção.",
               exemplo="Quais momentos dos próximos 3 meses devemos preparar desde já para a Casa Veraneio?",
               aparencia=_ap("#8d5524", "coque", "#1b1b1b", "blazer", "#5e548e", "#2b2d42", "oculos")),
        Agente(id="moviemaker", nome="Moviemaker", funcao="Roteiro e storyboard de vídeos", setor="video",
               descricao="Cria roteiros, storyboards e o plano de captação dos vídeos.",
               exemplo="Escreva o roteiro de um reels de 30 s sobre a piscina.",
               aparencia=_ap("#c68642", "curto", "#3b2f2f", "moletom", "#1d3557", "#14213d", "camera")),
        Agente(id="editor_video", nome="Editor de Vídeo", funcao="Edição e montagem dos vídeos (MP4)", setor="video",
               descricao="Monta os vídeos finais com as fotos e clipes reais, textos e transições.",
               exemplo="Monte o reels do roteiro de verão com os vídeos da pasta da piscina.",
               aparencia=_ap("#8d5524", "cacheado", "#1b1b1b", "moletom", "#264653", "#111111", "bone")),
        Agente(id="gestor_trafego", nome="Gestor de Tráfego", funcao="Mídia paga e campanhas", setor="performance",
               descricao="Planeja campanhas pagas: público, orçamento, canais e metas.",
               exemplo="Planeje uma campanha de R$ 2.000 para o feriado.",
               aparencia=_ap("#ffdbac", "moicano", "#d62828", "camiseta", "#2a9d8f", "#264653", "fone")),
        Agente(id="analista_metricas", nome="Analista de Métricas", funcao="Indicadores e relatórios",
               setor="performance", descricao="Define indicadores, analisa resultados e sugere otimizações.",
               exemplo="Quais métricas devo acompanhar na campanha de verão?",
               aparencia=_ap("#e0ac69", "curto", "#6f4e37", "camisa", "#90be6d", "#22333b", "cracha")),
    ),
    # Comercial: Hospedagem (Casa Veraneio; começa só com a mesa vaga) e Corporativo (Casa Veraneio Corporativo).
    "comercial": _andar(
        Agente(id="prospectador", nome="Prospectador", funcao="Prospecção ativa de empresas (Corporativo)",
               setor="corporativo",
               descricao="Conhece os clientes corporativos do CRM, mantém a persona do cliente ideal e prospecta "
                         "empresas na web: coleta nome, e-mail e telefone da empresa e mostra uma prévia; com a "
                         "sua aprovação, cria os leads no grupo [Corp] Prospecção Ativa do Monday.",
               exemplo="Prospecte 10 indústrias da região de Campinas com mais de 300 funcionários.",
               aparencia=_ap("#c68642", "curto", "#2b1d0e", "blazer", "#7f5347", "#1b263b", "cracha")),
        Agente(id="estrategista", nome="Estrategista", funcao="Estratégia e posicionamento das três empresas",
               setor="reuniao",
               descricao="Posiciona as empresas do grupo na Matriz BCG e na GE-McKinsey, faz SWOT, 5 Forças, Ansoff e "
                         "a conta de custo de aquisição x valor do cliente, com os números do painel e do CRM e "
                         "pesquisa de mercado na web, sempre com a fonte e o grau de confiança de cada ponto.",
               exemplo="Onde estamos na Matriz BCG e para onde devemos crescer?",
               aparencia=_ap("#f1c27d", "curto", "#9a9a9a", "blazer", "#22333b", "#111111", "oculos")),
    ),
    "cobertura": _andar(
        Agente(id="cerebro", nome="Cérebro", funcao="Conhecimento central do grupo (cada empresa separada)", setor="laboratorio",
               visual="cerebro",
               descricao="Guarda e aprende o conhecimento de cada empresa do grupo, separado: imóveis, serviços, "
                         "marca, regras e o trabalho do time. Responde citando a fonte; os agentes o consultam sempre.",
               exemplo="Quais serviços do Hotel Privativo podemos oferecer e como eles são cobrados?",
               aparencia=_ap("#d9d9d9", "careca", "#9e9e9e", "avental", "#ffffff", "#5c677d", "oculos")),
        *(Agente(id=f"estagiario_{n}", nome=f"Estagiário {n}", funcao="Repassa o conhecimento do Cérebro aos agentes",
                 setor="reuniao", tipo="estagiario",
                 descricao="Leva as respostas do Cérebro até a mesa de quem consultou e volta à Cobertura.",
                 aparencia=aparencia)
          for n, aparencia in enumerate([
              _ap("#f1c27d", "cacheado", "#6f4e37", "camiseta", "#06d6a0", "#2b2d42", "cracha"),
              _ap("#8d5524", "curto", "#1b1b1b", "moletom", "#ffd166", "#3d405b", "cracha"),
              _ap("#ffdbac", "longo", "#e9c46a", "camisa", "#118ab2", "#264653", "cracha"),
              _ap("#c68642", "moicano", "#ef476f", "camiseta", "#8338ec", "#1d3557", "cracha"),
          ], start=1)),
    ),
}

# Agentes que produzem arquivos (PNG/MP4) pelo Claude Code do dono do plano Max.
AGENTES_PRODUCAO = {"criador_imagens", "editor_video"}

def buscar_agente(andar: str, agente_id: str) -> Agente | None:
    return ANDARES.get(andar, {}).get(agente_id)


def andar_do_agente(agente_id: str) -> str | None:
    return next((andar for andar, agentes in ANDARES.items() if agente_id in agentes), None)


def _em_uso(login: str) -> dict[str, list[dict]]:
    """Quem MAIS está usando cada agente (Thomas, 29/10/2026): com o chat aberto ou com um pedido rodando.
    "andar/agente" -> [{"nome", "acao": "trabalhando" | "conversando"}], sem o próprio usuário."""
    import tarefas
    from auth import carregar_usuarios
    from conexoes import gerenciador

    usuarios = carregar_usuarios()
    nome = lambda l: usuarios.get(l, {}).get("nome", l.split("@")[0])  # noqa: E731
    uso: dict[str, dict[str, str]] = {}
    for linha in tarefas._db().execute("SELECT DISTINCT andar, agente, usuario FROM tarefas WHERE status IN "
                                       "('executando', 'producao', 'produzindo')"):
        if linha["usuario"] != login:
            uso.setdefault(f"{linha['andar']}/{linha['agente']}", {})[linha["usuario"]] = "trabalhando"
    for chat, logins in gerenciador.conversando().items():
        for outro in logins - {login}:
            uso.setdefault(chat, {}).setdefault(outro, "conversando")
    return {chat: [{"nome": nome(l), "acao": acao} for l, acao in sorted(quem.items())] for chat, quem in uso.items()}


def snapshot(usuario: dict) -> dict:
    """Mensagem de estado. Andar sem nenhum agente liberado para o usuário leva só os estagiários (para as visitas
    deles aparecerem nos outros andares). Agente não liberado vai com "bloqueado" (aparece apagado, sem chat)."""
    import acesso  # import tardio: acesso depende do estado

    em_uso = _em_uso(usuario.get("sub", ""))
    return {
        "tipo": "estado",
        "andares": {
            andar: {i: {**a.model_dump(mode="json", exclude=_SO_NO_DETALHE),
                        "bloqueado": a.tipo != "estagiario" and not acesso.pode_usar(usuario, andar, i),
                        "em_uso": em_uso.get(f"{andar}/{i}", [])}
                    for i, a in agentes.items()
                    if acesso.pode_ver_andar(usuario, andar) or a.tipo == "estagiario"}
            for andar, agentes in ANDARES.items()
        },
    }
