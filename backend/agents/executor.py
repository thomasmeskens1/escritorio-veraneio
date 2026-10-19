"""Executa uma tarefa num modelo específico, com tempo limite e medição de tokens e custo."""

import asyncio
import threading
from dataclasses import dataclass

import crewai.llms.retry
from crewai import LLM, Agent, Crew, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import atividade
import config
import diretora
import tarefas
from agents import projeto
from agents.perfis import PERFIS, contexto, descricao_tarefa
from estado import andar_do_agente
from roteamento import Etapa

# O CrewAI repete chamadas com erro 429 (3x, sem opção de configurar). Desligado para não
# gastar cota repetindo o mesmo modelo: o roteamento já passa ao próximo. Revisar ao atualizar o crewai.
crewai.llms.retry._LLM_RATE_LIMIT_MAX_ATTEMPTS = 1

MAX_ITERACOES = 8  # limita voltas de raciocínio (e tokens) por agente
MAX_TOKENS_SAIDA_CLAUDE = 2000


class LocalOcupado(Exception):
    """O modelo local já está processando outra tarefa (o Ollama atende uma por vez)."""


@dataclass
class Resultado:
    texto: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0


class _Pergunta(BaseModel):
    pergunta: str = Field(description="O que você precisa saber sobre a empresa")


class ConsultarDiretora(BaseTool):
    name: str = "consultar_diretora"
    description: str = ("Consulta a Diretora, que guarda os documentos da Casa Veraneio (marca, produtos, preços, "
                        "regras e políticas). Use antes de afirmar qualquer fato sobre a empresa.")
    args_schema: type[BaseModel] = _Pergunta
    andar: str
    agente: str
    tarefa_id: int

    def _run(self, pergunta: str) -> str:
        return diretora.consultar(pergunta, self.andar, self.agente, self.tarefa_id)


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


def _rodar(agente_id: str, descricao: str, esperado: str, modelo: str, limite_s: int, total: Resultado,
          tarefa_id: int) -> str:
    """Roda um agente (Crew de uma tarefa) e acumula tokens e custo no `total`."""
    ferramentas = []
    if diretora.tem_documentos():  # sem documentos, a ferramenta só gastaria chamadas
        ferramentas.append(ConsultarDiretora(andar=andar_do_agente(agente_id) or "", agente=agente_id, tarefa_id=tarefa_id))
    agente = Agent(**PERFIS[agente_id], llm=_llm(modelo, limite_s), tools=ferramentas,
                   max_iter=MAX_ITERACOES, max_retry_limit=0, verbose=False)
    saida = Crew(agents=[agente], tasks=[Task(description=descricao, expected_output=esperado, agent=agente)]).kickoff()

    uso = saida.token_usage
    total.tokens_entrada += uso.prompt_tokens
    total.tokens_saida += uso.completion_tokens
    total.custo_usd += tarefas.custo_estimado(modelo, uso.prompt_tokens, uso.completion_tokens)
    return saida.raw


def _executar_sincrono(tarefa_id: int, agente_id: str, texto: str, etapa: Etapa, historico: list,
                       cancelar: threading.Event) -> Resultado:
    total = Resultado(texto="")
    if agente_id == "gestor":
        # Com o Claude, só o Gestor (plano e revisão) usa o modelo forte; a equipe usa o padrão, bem mais barato.
        equipe = config.MODELO_FILA_PADRAO if etapa.modelo == config.MODELO_FILA_COMPLEXO else etapa.modelo

        def executar(agente: str, descricao: str, esperado: str, papel: str) -> str:
            return _rodar(agente, descricao, esperado, etapa.modelo if papel == "gestor" else equipe,
                          etapa.limite_s, total, tarefa_id)

        def avisar(tipo: str, agente: str, detalhe: str) -> None:
            atividade.etapa_em_thread(tarefa_id, tipo, agente, detalhe)

        total.texto = projeto.executar_projeto(tarefa_id, texto, contexto("gestor", historico), executar,
                                               cancelar, avisar)
    else:
        esperado = "JSON com a especificação do novo agente." if agente_id == "construtor" else "Resposta completa ao pedido."
        total.texto = _rodar(agente_id, descricao_tarefa(agente_id, texto, historico), esperado,
                             etapa.modelo, etapa.limite_s, total, tarefa_id)
    return total


def _descartar_erro(futuro: asyncio.Future) -> None:
    if not futuro.cancelled():
        futuro.exception()  # evita aviso de exceção não lida após o tempo limite


async def executar(agente_id: str, texto: str, etapa: Etapa, historico: list = (), tarefa_id: int = 0) -> Resultado:
    """Roda numa thread. Estourando o limite, levanta TimeoutError e sinaliza cancelamento: a thread
    termina sozinha (limitada pelo timeout do LLM), e só então libera o modelo local."""
    local = etapa.modelo.startswith("ollama/")
    if local and _trava_local.locked():
        raise LocalOcupado
    if local:
        await _trava_local.acquire()

    cancelar = threading.Event()
    execucao = asyncio.ensure_future(asyncio.to_thread(
        _executar_sincrono, tarefa_id, agente_id, texto, etapa, historico, cancelar))
    execucao.add_done_callback(_descartar_erro)
    if local:
        execucao.add_done_callback(lambda _: _trava_local.release())
    try:
        return await asyncio.wait_for(asyncio.shield(execucao), etapa.limite_s)
    except asyncio.TimeoutError:
        cancelar.set()  # projetos param na próxima etapa; o próximo modelo retoma do livro-razão
        raise
