"""Estado dos agentes, dividido por andar (em memória)."""

from enum import Enum

from pydantic import BaseModel


class Status(str, Enum):
    dormindo = "dormindo"
    disponivel = "disponivel"
    trabalhando = "trabalhando"


class Agente(BaseModel):
    id: str
    nome: str
    funcao: str
    status: Status = Status.disponivel


def _andar(*agentes: Agente) -> dict[str, Agente]:
    return {a.id: a for a in agentes}


ANDARES: dict[str, dict[str, Agente]] = {
    "porao": {},
    "terreo": {},
    "marketing": _andar(
        Agente(id="designer", nome="Designer", funcao="Design gráfico e identidade visual"),
        Agente(id="moviemaker", nome="Moviemaker", funcao="Roteiro, captação e edição de vídeos"),
        Agente(id="gestor_trafego", nome="Gestor de Tráfego", funcao="Mídia paga e performance"),
        Agente(id="gestor", nome="Gestor", funcao="Coordena, delega e revisa o time"),
        Agente(id="carpinteiro", nome="Carpinteiro", funcao="Cria novos agentes para o escritório"),
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


def snapshot(role: str) -> dict:
    """Mensagem de estado; andares restritos vão vazios para quem não tem acesso."""
    return {
        "tipo": "estado",
        "andares": {
            andar: {i: a.model_dump(mode="json") for i, a in agentes.items()} if pode_acessar(role, andar) else {}
            for andar, agentes in ANDARES.items()
        },
    }
