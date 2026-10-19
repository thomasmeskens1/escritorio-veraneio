"""Executa uma tarefa num modelo específico, com tempo limite e medição de tokens."""

import asyncio
from dataclasses import dataclass

import crewai.llms.retry
from crewai import LLM, Agent, Crew, Process, Task

import config
from agents.perfis import PERFIS, descricao_tarefa
from roteamento import Etapa

# O CrewAI repete chamadas com erro 429 (3x, sem opção de configurar). Desligado para não
# gastar cota repetindo o mesmo modelo: o roteamento já passa ao próximo. Revisar ao atualizar o crewai.
crewai.llms.retry._LLM_RATE_LIMIT_MAX_ATTEMPTS = 1

EQUIPE_DO_GESTOR = ("designer", "moviemaker", "gestor_trafego")
MAX_ITERACOES = 8  # limita voltas de raciocínio (e tokens) por agente
MAX_TOKENS_SAIDA_CLAUDE = 2000


class LocalOcupado(Exception):
    """O modelo local já está processando outra tarefa (o Ollama atende uma por vez)."""


@dataclass
class Resultado:
    texto: str
    tokens_entrada: int
    tokens_saida: int


_trava_local = asyncio.Lock()


def _llm(modelo: str, limite_s: int) -> LLM:
    # Sem novas tentativas no mesmo modelo: em caso de falha, o roteamento decide o próximo passo.
    if modelo.startswith("anthropic/"):
        return LLM(model=modelo, api_key=config.ANTHROPIC_API_KEY, timeout=min(limite_s, 120),
                   max_retries=0, max_tokens=MAX_TOKENS_SAIDA_CLAUDE)
    if modelo.startswith("openrouter/"):
        return LLM(model=modelo, base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY,
                   timeout=90, max_retries=0)
    if modelo.startswith("ollama/"):
        return LLM(model=modelo, base_url=config.OLLAMA_BASE_URL, timeout=limite_s, max_retries=0)
    return LLM(model=modelo, timeout=90, max_retries=0)


def _agente(agente_id: str, llm: LLM, delegar: bool = False) -> Agent:
    return Agent(**PERFIS[agente_id], llm=llm, allow_delegation=delegar, max_iter=MAX_ITERACOES,
                 max_retry_limit=0, verbose=False)


def _montar_crew(agente_id: str, texto: str, etapa: Etapa, historico: list) -> Crew:
    llm = _llm(etapa.modelo, etapa.limite_s)
    descricao = descricao_tarefa(agente_id, texto, historico)

    if agente_id == "gestor":
        # Com o Claude, só o Gestor usa o modelo forte; a equipe usa o padrão, bem mais barato.
        complexo = etapa.modelo == config.MODELO_FILA_COMPLEXO
        llm_equipe = _llm(config.MODELO_FILA_PADRAO, etapa.limite_s) if complexo else llm
        equipe = [_agente(i, llm_equipe) for i in EQUIPE_DO_GESTOR]
        tarefa = Task(description=descricao, expected_output="Entrega final consolidada e revisada pelo Gestor.")
        return Crew(agents=equipe, tasks=[tarefa], process=Process.hierarchical,
                    manager_agent=_agente("gestor", llm, delegar=True))

    agente = _agente(agente_id, llm)
    esperado = "JSON com a especificação do novo agente." if agente_id == "construtor" else "Resposta completa ao pedido."
    return Crew(agents=[agente], tasks=[Task(description=descricao, expected_output=esperado, agent=agente)])


def _descartar_erro(futuro: asyncio.Future) -> None:
    if not futuro.cancelled():
        futuro.exception()  # evita aviso de exceção não lida após o tempo limite


async def executar(agente_id: str, texto: str, etapa: Etapa, historico: list = ()) -> Resultado:
    """Roda a Crew numa thread. Estourando o limite, levanta TimeoutError (a thread termina sozinha,
    limitada pelo timeout do LLM, e só então libera o modelo local)."""
    local = etapa.modelo.startswith("ollama/")
    if local and _trava_local.locked():
        raise LocalOcupado
    crew = _montar_crew(agente_id, texto, etapa, historico)

    if local:
        await _trava_local.acquire()
    execucao = asyncio.ensure_future(asyncio.to_thread(crew.kickoff))
    execucao.add_done_callback(_descartar_erro)
    if local:
        execucao.add_done_callback(lambda _: _trava_local.release())

    saida = await asyncio.wait_for(asyncio.shield(execucao), etapa.limite_s)
    uso = saida.token_usage
    return Resultado(saida.raw, uso.prompt_tokens, uso.completion_tokens)
