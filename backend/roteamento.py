"""Classificação de dificuldade (sem custo de tokens) e plano de execução por dificuldade."""

from dataclasses import dataclass
from enum import Enum

import aprendizado
import config
import saude
import tarefas


class Dificuldade(str, Enum):
    simples = "simples"
    media = "media"
    complexa = "complexa"


_ORDEM = list(Dificuldade)

# Dificuldade mínima por agente: quem delega ou gera saída estruturada nunca é "simples".
PISO_DIFICULDADE = {"gestor": Dificuldade.media, "construtor": Dificuldade.media}
# Agentes que o modelo local (4B) não atende bem: delegação com ferramentas e JSON estruturado.
AGENTES_SEM_LOCAL = {"gestor", "construtor"}

TERMOS_COMPLEXOS = (
    "estratégia", "estrategia", "planejamento", "plano de", "análise", "analise", "relatório", "relatorio",
    "pesquisa", "cronograma", "orçamento", "orcamento", "comparativo", "funil", "campanha completa", "passo a passo",
)

# Limites em segundos. Base: qwen3:4b nesta máquina leva ~3 min numa tarefa simples (benchmark).
LIMITE_GRATUITO = 240  # o MiniMax leva ~3 min nas respostas que dão certo; menos que isso descarta respostas boas
MAX_GRATUITOS_IMEDIATOS = 3  # caminho imediato: até 3 gratuitos antes do Max/Haiku/local
LIMITE_LOCAL = {Dificuldade.simples: 6 * 60, Dificuldade.media: 15 * 60}  # complexa não usa o local de imediato
LIMITE_LOCAL_CONTINGENCIA = 30 * 60  # na fila, sem ninguém esperando, o local pode ir mais longe
LIMITE_FILA = 5 * 60


@dataclass(frozen=True)
class Etapa:
    modelo: str
    limite_s: int


def classificar(agente_id: str, texto: str) -> Dificuldade:
    termos = sum(t in texto.lower() for t in TERMOS_COMPLEXOS)
    if len(texto) > 800 or termos >= 2:
        dificuldade = Dificuldade.complexa
    elif len(texto) > 250 or termos == 1:
        dificuldade = Dificuldade.media
    else:
        dificuldade = Dificuldade.simples
    dificuldade = Dificuldade(aprendizado.ajustar(agente_id, dificuldade.value, texto))  # aprende com o histórico
    piso = PISO_DIFICULDADE.get(agente_id, Dificuldade.simples)
    return max(dificuldade, piso, key=_ORDEM.index)


def _utilizaveis(etapas: list[Etapa]) -> list[Etapa]:
    return [e for e in etapas if config.modelo_disponivel(e.modelo) and saude.disponivel(e.modelo)]


def _gratuitos(maximo: int | None = None) -> list[Etapa]:
    """Gratuitos na ordem da lista; os fora da rota (saude) saem antes de contar o máximo."""
    disponiveis = [m for m in config.modelos_gratuitos() if config.modelo_disponivel(m) and saude.disponivel(m)]
    return [Etapa(m, LIMITE_GRATUITO) for m in disponiveis[:maximo]]


def etapas_imediatas(dificuldade: Dificuldade, agente_id: str) -> list[Etapa]:
    """Gratuitos primeiro. Simples: Haiku antes do local (rápido e barato, com teto próprio).
    O local só para simples/médias de agentes que ele atende bem."""
    etapas = _gratuitos(MAX_GRATUITOS_IMEDIATOS)  # alguém esperando: no pior caso 3 x 4 min, não 6 x 4 min
    if dificuldade == Dificuldade.simples and tarefas.chat_rapido_liberado(agente_id):
        etapas.append(Etapa(config.MODELO_FILA_PADRAO, LIMITE_FILA))
    if dificuldade in LIMITE_LOCAL and agente_id not in AGENTES_SEM_LOCAL and config.MODELO_LOCAL:
        etapas.append(Etapa(config.MODELO_LOCAL, LIMITE_LOCAL[dificuldade]))
    return _utilizaveis(etapas)


def etapa_fila(dificuldade: Dificuldade) -> Etapa | None:
    """Claude: Haiku para simples/médias, Sonnet só para complexas."""
    modelo = config.MODELO_FILA_COMPLEXO if dificuldade == Dificuldade.complexa else config.MODELO_FILA_PADRAO
    etapas = _utilizaveis([Etapa(modelo, LIMITE_FILA)])
    return etapas[0] if etapas else None


def etapas_contingencia() -> list[Etapa]:
    """Quando o Claude não está disponível: gratuitos (a cota pode ter voltado) e o local, sem pressa."""
    etapas = _gratuitos()
    if config.MODELO_LOCAL:
        etapas.append(Etapa(config.MODELO_LOCAL, LIMITE_LOCAL_CONTINGENCIA))
    return _utilizaveis(etapas)
