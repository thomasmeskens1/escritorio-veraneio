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
        Agente(id="recepcionista", nome="Recepcionista", funcao="Boas-vindas e visão geral do escritório",
               setor="escola", descricao="Explica como o escritório funciona: andares, agentes, status, fila e limites.",
               exemplo="Sou novo aqui. Por onde começo?",
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
               exemplo="Monte a arte do post de lançamento da suíte master.",
               aparencia=_ap("#f1c27d", "moicano", "#2a9d8f", "camiseta", "#ffb703", "#023047", "lapis")),
        Agente(id="copywriter", nome="Copywriter", funcao="Textos, legendas e chamadas", setor="conteudo",
               descricao="Escreve legendas, títulos e chamadas no tom de voz da marca.",
               exemplo="Escreva 3 legendas para o post do café da manhã.",
               aparencia=_ap("#c68642", "longo", "#1b1b1b", "camisa", "#e5989b", "#6d6875", "oculos")),
        Agente(id="social_media", nome="Social Media", funcao="Calendário e publicação", setor="conteudo",
               descricao="Organiza o calendário editorial, formatos, horários e a rotina de publicação.",
               exemplo="Monte o calendário de posts da próxima semana.",
               aparencia=_ap("#ffdbac", "coque", "#d4a373", "moletom", "#ff006e", "#3a0ca3", "fone")),
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
    "cobertura": _andar(
        Agente(id="cerebro", nome="Cérebro", funcao="Conhecimento central da Casa Veraneio", setor="laboratorio",
               visual="cerebro",
               descricao="Guarda e aprende o conhecimento da empresa: lodges, serviços do Hotel Privativo, marca, "
                         "regras e o trabalho do time. Responde citando a fonte; os agentes o consultam sempre.",
               exemplo="Quais serviços exclusivos estão incluídos na estadia dos lodges?",
               aparencia=_ap("#d9d9d9", "careca", "#9e9e9e", "avental", "#ffffff", "#5c677d", "oculos")),
        *(Agente(id=f"estagiario_{n}", nome=f"Estagiário {n}", funcao="Repassa o conhecimento do Cérebro aos agentes",
                 setor="estagiarios", tipo="estagiario",
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

# Andar -> role exigida para acessá-lo.
ANDARES_RESTRITOS = {"cobertura": "diretoria"}


def pode_acessar(role: str, andar: str) -> bool:
    exigida = ANDARES_RESTRITOS.get(andar)
    return exigida is None or role == exigida


def buscar_agente(andar: str, agente_id: str) -> Agente | None:
    return ANDARES.get(andar, {}).get(agente_id)


def andar_do_agente(agente_id: str) -> str | None:
    return next((andar for andar, agentes in ANDARES.items() if agente_id in agentes), None)


def snapshot(role: str) -> dict:
    """Mensagem de estado. Andar restrito, para quem não tem acesso, leva só os estagiários
    (para as visitas deles aparecerem nos outros andares)."""
    return {
        "tipo": "estado",
        "andares": {
            andar: {i: a.model_dump(mode="json", exclude=_SO_NO_DETALHE) for i, a in agentes.items()
                    if pode_acessar(role, andar) or a.tipo == "estagiario"}
            for andar, agentes in ANDARES.items()
        },
    }
