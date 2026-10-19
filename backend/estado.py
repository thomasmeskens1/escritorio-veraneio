"""Estado dos agentes, dividido por andar (em memória)."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Status(str, Enum):
    dormindo = "dormindo"
    disponivel = "disponivel"
    trabalhando = "trabalhando"


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
    tipo: Literal["ia", "sistema", "conhecimento"] = "ia"  # sistema: painel; conhecimento: sem interação
    status: Status = Status.disponivel
    visitando: dict | None = None  # {"andar", "agente"} enquanto a Diretora atende em outro andar


def _ap(pele, cabelo, cor_cabelo, roupa, cor_roupa, calca, acessorio) -> Aparencia:
    return Aparencia(pele=pele, cabelo=Cabelo(estilo=cabelo, cor=cor_cabelo),
                     roupa=Roupa(estilo=roupa, cor=cor_roupa), calca=calca, acessorio=acessorio)


def _andar(*agentes: Agente) -> dict[str, Agente]:
    return {a.id: a for a in agentes}


ANDARES: dict[str, dict[str, Agente]] = {
    "porao": _andar(
        Agente(id="construtor", nome="Construtor", funcao="Cria novos agentes para o escritório",
               aparencia=_ap("#c68642", "curto", "#2b1d0e", "macacao", "#f4a261", "#3d405b", "capacete")),
        Agente(id="despachante", nome="Despachante", funcao="Classifica tarefas e opera a fila do Claude",
               tipo="sistema", aparencia=_ap("#8d5524", "careca", "#000000", "camisa", "#457b9d", "#1d3557", "fone")),
    ),
    "terreo": _andar(
        Agente(id="recepcionista", nome="Recepcionista", funcao="Boas-vindas e visão geral do escritório",
               aparencia=_ap("#ffdbac", "longo", "#b5651d", "blazer", "#2a9d8f", "#264653", "cracha")),
        Agente(id="professor", nome="Professor", funcao="Ensina a pedir tarefas e escrever bons briefings",
               aparencia=_ap("#e0ac69", "curto", "#9e9e9e", "camisa", "#6d597a", "#355070", "oculos")),
        Agente(id="diretora", nome="Diretora", funcao="Conhecimento da empresa (consultada pelos agentes)",
               tipo="conhecimento", aparencia=_ap("#e0ac69", "coque", "#3b2f2f", "blazer", "#7b2d26", "#1b1b1b", "oculos")),
    ),
    "marketing": _andar(
        Agente(id="designer", nome="Designer", funcao="Design gráfico e identidade visual",
               aparencia=_ap("#f1c27d", "cacheado", "#7b2cbf", "camiseta", "#e76f51", "#22223b", "oculos")),
        Agente(id="moviemaker", nome="Moviemaker", funcao="Roteiro, captação e edição de vídeos",
               aparencia=_ap("#c68642", "curto", "#3b2f2f", "moletom", "#1d3557", "#14213d", "camera")),
        Agente(id="gestor_trafego", nome="Gestor de Tráfego", funcao="Mídia paga e performance",
               aparencia=_ap("#ffdbac", "moicano", "#d62828", "camiseta", "#2a9d8f", "#264653", "fone")),
        Agente(id="gestor", nome="Gestor", funcao="Coordena, delega e revisa o time",
               aparencia=_ap("#8d5524", "curto", "#1b1b1b", "blazer", "#343a40", "#212529", "gravata")),
    ),
    "cobertura": {},
}

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
    """Mensagem de estado; andares restritos vão vazios para quem não tem acesso."""
    return {
        "tipo": "estado",
        "andares": {
            andar: {i: a.model_dump(mode="json") for i, a in agentes.items()} if pode_acessar(role, andar) else {}
            for andar, agentes in ANDARES.items()
        },
    }
