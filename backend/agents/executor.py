"""Executa uma tarefa num modelo específico, com tempo limite e medição de tokens e custo."""

import asyncio
import json
import re
import threading
import time
from dataclasses import dataclass

import crewai.llms.retry
from crewai import LLM, Agent, Crew, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import agentes_dinamicos
import atividade
import config
import encaminhamento
import cerebro
import max_texto
import saude
import tarefas
from agents import diretrizes, ferramentas_brevo, ferramentas_monday, projeto
from agents.perfis import PERFIS, contexto, descricao_tarefa
from roteamento import Etapa, etapas_contingencia

# O CrewAI repete chamadas com erro 429 (3x, sem opção de configurar). Desligado para não
# gastar cota repetindo o mesmo modelo: o roteamento já passa ao próximo. Revisar ao atualizar o crewai.
crewai.llms.retry._LLM_RATE_LIMIT_MAX_ATTEMPTS = 1

MAX_ITERACOES = 8  # limita voltas de raciocínio (e tokens) por agente
MAX_ITERACOES_MONDAY = 14  # Social Media com o Monday: consultas + leitura do board + criação + resposta
# Chamada de ferramenta escrita como texto (alguns modelos gratuitos não usam a chamada nativa), ex.:
# <tool_call><function=criar_item_monday><parameter=nome>...</parameter>...</function></tool_call>
CHAMADA_EM_TEXTO = re.compile(r"(?:<tool_call>\s*)?<function=([\w-]+)>(.*?)(?:</function>\s*(?:</tool_call>)?|$)", re.S)
PARAMETRO_EM_TEXTO = re.compile(r"<parameter=([\w-]+)>\s*(.*?)\s*(?:</parameter>|(?=<parameter=)|$)", re.S)
MAX_TOKENS_SAIDA_CLAUDE = 2000
_trava_total = threading.Lock()  # soma de tokens/custo de etapas paralelas


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


class ConsultarCerebro(BaseTool):
    name: str = "consultar_cerebro"
    description: str = ("Consulta o Cérebro, o conhecimento central da Casa Veraneio (lodges de alto padrão para "
                        "temporada, serviços do Hotel Privativo, marca, preços, regras e trabalhos anteriores do time). "
                        "Use antes de afirmar qualquer fato sobre a empresa e cite a fonte que ele devolver.")
    args_schema: type[BaseModel] = _Pergunta
    agente: str
    tarefa_id: int

    def _run(self, pergunta: str) -> str:
        return cerebro.consultar(pergunta, self.agente, self.tarefa_id)


class _Especificacao(BaseModel):
    nome: str = Field(description="Nome curto do agente, ex.: Vendedor")
    andar: str = Field(description="porao | marketing")
    setor: str = Field(description="Setor válido do andar (veja a lista nas instruções)")
    funcao: str = Field(description="Função em uma linha")
    descricao: str = Field(description="O que ele faz, em 1-2 frases")
    exemplo: str = Field(description="Pedido curto de exemplo que o usuário faria a ele")
    role: str = Field(description="Papel (persona) do agente")
    goal: str = Field(description="Objetivo do agente")
    backstory: str = Field(description="História/experiência do agente")
    aparencia: dict = Field(description="Objeto com pele, cabelo {estilo, cor}, roupa {estilo, cor}, calca e acessorio")


class CriarAgente(BaseTool):
    name: str = "criar_agente"
    description: str = ("Cria de verdade um novo agente no escritório a partir da especificação completa. "
                        "Devolve a confirmação ou o erro de validação a corrigir.")
    args_schema: type[BaseModel] = _Especificacao
    tarefa_id: int

    def _run(self, **spec) -> str:
        tarefa = tarefas.obter(self.tarefa_id) if self.tarefa_id else None
        return agentes_dinamicos.criar_em_thread(spec, tarefa["usuario"] if tarefa else "", self.tarefa_id or None)


_trava_local = asyncio.Lock()


def _llm(modelo: str, limite_s: int) -> LLM:
    # Sem novas tentativas no mesmo modelo: em caso de falha, o roteamento decide o próximo passo.
    if modelo.startswith("anthropic/"):
        return LLM(model=modelo, api_key=config.ANTHROPIC_API_KEY, timeout=min(limite_s, 120),
                   max_retries=0, max_tokens=MAX_TOKENS_SAIDA_CLAUDE)
    if modelo.startswith("openrouter/"):
        return LLM(model=modelo, base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY,
                   timeout=90, max_retries=0)
    # Groq e Mistral seguem a API da OpenAI: conector nativo "openai/" apontando para o endereço deles
    # (o CrewAI não tem conector próprio para eles sem instalar o LiteLLM).
    if modelo.startswith("groq/"):
        return LLM(model=f"openai/{modelo.removeprefix('groq/')}", base_url=config.GROQ_BASE_URL,
                   api_key=config.GROQ_API_KEY, timeout=90, max_retries=0)
    if modelo.startswith("mistral/"):
        return LLM(model=f"openai/{modelo.removeprefix('mistral/')}", base_url=config.MISTRAL_BASE_URL,
                   api_key=config.MISTRAL_API_KEY, timeout=90, max_retries=0)
    if modelo.startswith("ollama/"):
        return LLM(model=modelo, base_url=config.OLLAMA_BASE_URL, timeout=limite_s, max_retries=0)
    return LLM(model=modelo, timeout=90, max_retries=0)


class MaxOcupado(Exception):
    """O Claude Code (Max) está fazendo outra coisa: a tarefa segue para a API (em paralelo)."""


def _rodar_no_max(agente_id: str, descricao: str, esperado: str, limite_s: int, tarefa_id: int) -> str:
    """Tarefa de texto pelo plano Max (custo zero). Levanta MaxOcupado se ele não estiver livre agora."""
    trabalho = max_texto.reservar()
    if trabalho is None:
        raise MaxOcupado
    etapa = re.search(r"Sua etapa \(\d+\): (.+)", descricao)  # projeto do Gestor: a pergunta é a etapa
    consulta = (etapa.group(1) if etapa else descricao)[:500]
    contexto_cerebro = cerebro.consultar(consulta, agente_id, tarefa_id) if agente_id != cerebro.ID else ""
    prompt = max_texto.montar_prompt(PERFIS[agente_id],
                                     diretrizes.para(agente_id, empresa=cerebro.empresa_da_tarefa(tarefa_id)),
                                     contexto_cerebro, descricao, esperado)
    return max_texto.executar(trabalho, prompt, limite_s)


def _modelo_reserva(agente_id: str) -> str | None:
    """Max ocupado numa etapa de projeto: a API (se o orçamento do dia permitir) ou um gratuito."""
    api = config.MODELO_FILA_PADRAO
    if config.modelo_disponivel(api) and saude.disponivel(api) and not tarefas.orcamento_pausado(agente_id):
        return api
    gratuitos = etapas_contingencia()
    return gratuitos[0].modelo if gratuitos else None


def _rodar_max_ou_api(agente_id: str, descricao: str, esperado: str, limite_s: int, total: "Resultado",
                      tarefa_id: int) -> str:
    """Etapa de projeto com o Max na rota: Max se livre; senão a API em paralelo; sem API, espera o Max."""
    fim = time.monotonic() + limite_s
    while True:
        if agente_id not in max_texto.AGENTES_COM_FERRAMENTAS:
            try:
                return _rodar_no_max(agente_id, descricao, esperado, max(60, int(fim - time.monotonic())), tarefa_id)
            except MaxOcupado:
                pass
        if (reserva := _modelo_reserva(agente_id)) or time.monotonic() >= fim:
            if not reserva:
                raise TimeoutError("Nem o Max nem a API ficaram disponíveis a tempo.")
            return _rodar(agente_id, descricao, esperado, reserva, limite_s, total, tarefa_id)
        time.sleep(5)


def _rodar(agente_id: str, descricao: str, esperado: str, modelo: str, limite_s: int, total: Resultado,
          tarefa_id: int) -> str:
    """Roda um agente (Crew de uma tarefa) e acumula tokens e custo no `total`."""
    if modelo == max_texto.MODELO:  # plano Max: sem tokens nem custo de API
        return _rodar_no_max(agente_id, descricao, esperado, limite_s, tarefa_id)
    # Todos os agentes de IA consultam o Cérebro (ele mesmo recebe os trechos já na descrição).
    ferramentas = [] if agente_id == cerebro.ID else [ConsultarCerebro(agente=agente_id, tarefa_id=tarefa_id)]
    if agente_id == "construtor":
        ferramentas.append(CriarAgente(tarefa_id=tarefa_id))
    # Social Media: ver/criar itens no board. Só em tarefas da conta do Thomas (usa o token do sistema) e fora
    # de projeto do Gestor (a etapa não cria itens no Monday).
    tarefa = tarefas.obter(tarefa_id) if tarefa_id else None
    if "Sua etapa (" not in descricao and tarefa and tarefa["usuario"] == config.DONO_MAX:
        ferramentas += ferramentas_monday.para(agente_id, tarefa_id)
        ferramentas += ferramentas_brevo.para(agente_id, cerebro.empresa_da_tarefa(tarefa_id), tarefa_id)
    perfil = dict(PERFIS[agente_id])
    # Diretrizes da Casa Veraneio (regras, marca e manual da função); versão curta no modelo local.
    if (extras := diretrizes.para(agente_id, compacto=modelo.startswith(("ollama/", "groq/")),
                                  empresa=cerebro.empresa_da_tarefa(tarefa_id))):
        perfil["backstory"] = f"{perfil['backstory']}\n\n{extras}"
    monday_ativo = any(f.name.startswith("criar_ite") for f in ferramentas)
    agente = Agent(**perfil, llm=_llm(modelo, limite_s), tools=ferramentas,
                   max_iter=MAX_ITERACOES_MONDAY if monday_ativo else MAX_ITERACOES, max_retry_limit=0, verbose=False)
    saida = Crew(agents=[agente], tasks=[Task(description=descricao, expected_output=esperado, agent=agente)]).kickoff()

    uso = saida.token_usage
    custo = tarefas.custo_estimado(modelo, uso.prompt_tokens, uso.completion_tokens)
    tarefas.registrar_gasto(tarefa_id, agente_id, modelo, custo)  # na hora: vale mesmo se a tentativa for descartada
    with _trava_total:  # etapas do Gestor podem rodar em paralelo
        total.tokens_entrada += uso.prompt_tokens
        total.tokens_saida += uso.completion_tokens
        total.custo_usd += custo
    return _chamadas_em_texto(saida.raw, ferramentas)


def _chamadas_em_texto(texto: str, ferramentas: list[BaseTool]) -> str:
    """Executa as chamadas de ferramenta que o modelo escreveu como texto na resposta (em vez de chamar) e troca
    cada uma pelo resultado; o usuário nunca vê o código. Teste real: o 6º item do Monday veio como texto."""
    if "<function=" not in texto:
        return texto
    por_nome = {f.name: f for f in ferramentas}

    def executar(achado: re.Match) -> str:
        ferramenta = por_nome.get(achado.group(1))
        if not ferramenta:
            return ""
        argumentos = {}
        for nome, valor in PARAMETRO_EM_TEXTO.findall(achado.group(2)):
            try:  # listas e objetos (ex.: itens do criar_itens_monday) vêm em JSON
                argumentos[nome] = json.loads(valor) if valor[:1] in "[{" else valor
            except ValueError:
                argumentos[nome] = valor
        try:
            return f"\n{ferramenta.run(**argumentos)}\n"
        except Exception as erro:
            return f"\n(Não foi possível executar {ferramenta.name}: {erro})\n"

    return re.sub(r"</?tool_call>", "", CHAMADA_EM_TEXTO.sub(executar, texto)).strip()


def _executar_sincrono(tarefa_id: int, agente_id: str, texto: str, etapa: Etapa, historico: list,
                       cancelar: threading.Event) -> Resultado:
    total = Resultado(texto="")
    if agente_id == "gestor" and not encaminhamento.pergunta_simples(texto):
        # Com o Claude, só o Gestor (plano e revisão) usa o modelo forte; a equipe usa o padrão, bem mais barato.
        equipe = config.MODELO_FILA_PADRAO if etapa.modelo == config.MODELO_FILA_COMPLEXO else etapa.modelo

        def executar(agente: str, descricao: str, esperado: str, papel: str) -> str:
            if etapa.modelo == max_texto.MODELO:  # cada etapa: Max se livre, senão a API em paralelo
                return _rodar_max_ou_api(agente, descricao, esperado, etapa.limite_s, total, tarefa_id)
            return _rodar(agente, descricao, esperado, etapa.modelo if papel == "gestor" else equipe,
                          etapa.limite_s, total, tarefa_id)

        def avisar(tipo: str, agente: str, detalhe: str) -> None:
            atividade.etapa_em_thread(tarefa_id, tipo, agente, detalhe)

        total.texto = projeto.executar_projeto(tarefa_id, texto, contexto("gestor", historico, texto, cerebro.empresa_da_tarefa(tarefa_id)), executar,
                                               cancelar, avisar)
    else:
        esperado = ("Confirmação amigável, em texto (sem JSON), do agente criado: nome, andar, setor e função."
                    if agente_id == "construtor" else "Resposta completa ao pedido.")
        total.texto = _rodar(agente_id, descricao_tarefa(agente_id, texto, historico, tarefa_id), esperado,
                             etapa.modelo, etapa.limite_s, total, tarefa_id)
    total.texto = _garantir_formulario(total.texto)
    return total


# Rede de segurança: o agente pede "responda o formulário" e esquece o bloco (teste real, Social Media,
# 23/10/2026). Sem o bloco o usuário não tem onde responder: entra um campo aberto de resposta.
PEDE_FORMULARIO = re.compile(r"\b(?:formul[aá]rio abaixo|responda (?:com |n?o |pelo )?(?:o |ao |um )?formul[aá]rio|"
                             r"preencha o formul[aá]rio)", re.I)
FORMULARIO_ABERTO = ('<<FORMULARIO>>{"titulo": "Sua resposta", "campos": [{"nome": "resposta", "rotulo": '
                     '"Responda aqui o que foi pedido acima", "tipo": "texto_longo", "obrigatorio": true}]}'
                     '<<FIM DO FORMULARIO>>')


def _garantir_formulario(texto: str) -> str:
    if "<<FORMULARIO>>" in texto or not PEDE_FORMULARIO.search(texto):
        return texto
    return f"{texto}\n\n{FORMULARIO_ABERTO}"


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
