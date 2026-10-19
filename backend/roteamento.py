"""Classificação de dificuldade (sem custo de tokens) e plano de execução por dificuldade."""

from dataclasses import dataclass
from enum import Enum

import config


class Dificuldade(str, Enum):
    simples = "simples"
    media = "media"
    complexa = "complexa"


# Agentes que sempre trabalham em modo complexo (delegação ou saída estruturada).
AGENTES_COMPLEXOS = {"gestor", "construtor"}

TERMOS_COMPLEXOS = (
    "estratégia", "estrategia", "planejamento", "plano de", "análise", "analise", "relatório", "relatorio",
    "pesquisa", "cronograma", "orçamento", "orcamento", "comparativo", "funil", "campanha completa", "passo a passo",
)

# Limites em segundos. Base: qwen3:4b nesta máquina leva ~3 min numa tarefa simples (benchmark).
LIMITE_GRATUITO = 240
LIMITE_LOCAL = {Dificuldade.simples: 6 * 60, Dificuldade.media: 15 * 60}  # complexa não usa o local
LIMITE_FILA = 5 * 60


@dataclass(frozen=True)
class Etapa:
    modelo: str
    limite_s: int


def classificar(agente_id: str, texto: str) -> Dificuldade:
    if agente_id in AGENTES_COMPLEXOS:
        return Dificuldade.complexa
    termos = sum(t in texto.lower() for t in TERMOS_COMPLEXOS)
    if len(texto) > 800 or termos >= 2:
        return Dificuldade.complexa
    if len(texto) > 250 or termos == 1:
        return Dificuldade.media
    return Dificuldade.simples


def etapas_imediatas(dificuldade: Dificuldade) -> list[Etapa]:
    """Gratuitos primeiro; o local só para simples/médias (o 4B não dá conta de complexas)."""
    etapas = [Etapa(m, LIMITE_GRATUITO) for m in config.MODELOS_GRATUITOS]
    if dificuldade in LIMITE_LOCAL and config.MODELO_LOCAL:
        etapas.append(Etapa(config.MODELO_LOCAL, LIMITE_LOCAL[dificuldade]))
    return [e for e in etapas if config.modelo_disponivel(e.modelo)]


def etapa_fila(dificuldade: Dificuldade) -> Etapa | None:
    modelo = config.MODELO_FILA_COMPLEXO if dificuldade == Dificuldade.complexa else config.MODELO_FILA_PADRAO
    return Etapa(modelo, LIMITE_FILA) if config.modelo_disponivel(modelo) else None
