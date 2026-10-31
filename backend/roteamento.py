"""Classificação de dificuldade (sem custo de tokens) e plano de execução por dificuldade."""

import logging
import re
from dataclasses import dataclass
from enum import Enum

import aprendizado
import config
import saude
import tarefas

log = logging.getLogger(__name__)


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


# --- Rota sigilosa (decisão 12, padrão; despachante-24) -------------------------------------------------------
# CRM, carteira de clientes e financeiro nunca vão a modelo gratuito de fora (alguns provedores guardam o texto e
# treinam com ele): só Max, modelo local (Ollama) ou a API do Claude, se estiver ligada. Sem IA na decisão.
AGENTES_SIGILOSOS = frozenset({"prospectador", "estrategista"})  # trabalham sobre a carteira e os números
_NAO_EXTERNOS = ("claude-code/", "ollama/", "anthropic/")
TEXTO_SIGILOSO = re.compile(
    r"R\$\s?\d|\b(crm|faturamento|faturou|faturamos|carteira de clientes|lista de clientes|contas (?:corporativas|"
    r"ativas)|roas|roi|ticket m[eé]dio|lucro|receitas? (?:da|do|de|por|mensal|anual|total)|vendas (?:do|no|deste|"
    r"por) (?:m[eê]s|ano|trimestre|semestre|per[ií]odo|empresa|canal))\b", re.I)


def externo_gratuito(modelo: str) -> bool:
    """Modelo gratuito de fora (OpenRouter :free, Groq, Mistral...): não recebe tarefa sigilosa."""
    return not modelo.startswith(_NAO_EXTERNOS)


def sigilosa(agente_id: str, pedido: str = "", contexto: str = "", tarefa_id: int = 0,
             financeiro: bool = False) -> bool:
    """A tarefa leva CRM, carteira ou financeiro? Agente da carteira, ferramenta financeira (`financeiro`), pedido
    com valores ou termos do CRM, trecho financeiro do Cérebro já consultado ou nome de cliente no `contexto`."""
    if agente_id in AGENTES_SIGILOSOS or financeiro or TEXTO_SIGILOSO.search(pedido or ""):
        return True
    try:
        if tarefa_id:
            import cerebro  # import tardio: o Cérebro carrega o índice

            if cerebro._consultou_financeiro(tarefa_id):
                return True
        if contexto:
            import carteira

            return carteira.tem_nomes(contexto)
    except Exception:
        log.exception("Rota sigilosa: não consegui conferir o contexto; segue como sigilosa.")
        return True
    return False


def _utilizaveis(etapas: list[Etapa]) -> list[Etapa]:
    return [e for e in etapas if config.modelo_disponivel(e.modelo) and saude.disponivel(e.modelo)]


def _gratuitos(maximo: int | None = None) -> list[Etapa]:
    """Gratuitos na ordem da lista; os fora da rota (saude) saem antes de contar o máximo."""
    disponiveis = [m for m in config.modelos_gratuitos() if config.modelo_disponivel(m) and saude.disponivel(m)]
    return [Etapa(m, LIMITE_GRATUITO) for m in disponiveis[:maximo]]


def etapas_imediatas(dificuldade: Dificuldade, agente_id: str) -> list[Etapa]:
    """Gratuitos primeiro. Simples: Haiku antes do local (rápido e barato, com teto próprio).
    O local só para simples/médias de agentes que ele atende bem. Agente da carteira (rota sigilosa): sem gratuitos
    de fora, e o local entra em qualquer dificuldade (o Max, quando pode, entra antes dele no orquestrador)."""
    sigiloso = agente_id in AGENTES_SIGILOSOS
    etapas = [] if sigiloso else _gratuitos(MAX_GRATUITOS_IMEDIATOS)  # alguém esperando: no pior caso 3 x 4 min
    if dificuldade == Dificuldade.simples and tarefas.chat_rapido_liberado(agente_id):
        etapas.append(Etapa(config.MODELO_FILA_PADRAO, LIMITE_FILA))
    if (dificuldade in LIMITE_LOCAL or sigiloso) and agente_id not in AGENTES_SEM_LOCAL and config.MODELO_LOCAL:
        etapas.append(Etapa(config.MODELO_LOCAL, LIMITE_LOCAL.get(dificuldade, LIMITE_LOCAL[Dificuldade.media])))
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
