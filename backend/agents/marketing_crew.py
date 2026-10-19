"""Time de Marketing (CrewAI) com cadeia de modelos (Claude, OpenRouter e Ollama local)."""

import asyncio
import logging

import crewai.llms.retry
from crewai import LLM, Agent, Crew, Process, Task

import config

log = logging.getLogger(__name__)

# O CrewAI repete chamadas com erro 429 (3x, sem opção de configurar). Desligado para não
# gastar a cota repetindo o mesmo modelo: a cadeia já passa ao próximo. Revisar ao atualizar o crewai.
crewai.llms.retry._LLM_RATE_LIMIT_MAX_ATTEMPTS = 1

PERFIS = {
    "designer": {
        "role": "Designer",
        "goal": "Criar conceitos visuais, direção de arte e especificações de peças gráficas coerentes com a marca.",
        "backstory": "Designer sênior com anos de agência; traduz objetivos de negócio em layouts, paletas e tipografia.",
    },
    "moviemaker": {
        "role": "Moviemaker",
        "goal": "Planejar vídeos: roteiro, storyboard, captação e edição para redes sociais e peças institucionais.",
        "backstory": "Diretor e editor de vídeo especializado em formatos curtos que prendem a atenção nos primeiros segundos.",
    },
    "gestor_trafego": {
        "role": "Gestor de Tráfego",
        "goal": "Planejar campanhas de mídia paga com público, orçamento, canais e métricas de sucesso claras.",
        "backstory": "Especialista em Meta Ads e Google Ads, guiado por dados e obcecado por custo por resultado.",
    },
    "gestor": {
        "role": "Gestor de Marketing",
        "goal": "Entender o pedido, delegar cada parte ao especialista certo e revisar a entrega final antes de devolvê-la.",
        "backstory": "Líder do time de marketing; conhece os pontos fortes de cada membro e garante qualidade e coerência.",
    },
    "carpinteiro": {
        "role": "Carpinteiro",
        "goal": "Transformar o briefing do usuário na especificação de um novo agente: nome, role, goal e backstory.",
        "backstory": "Arquiteto do escritório; constrói novos membros do time sob medida para cada necessidade.",
    },
}

INSTRUCOES = "Responda em português do Brasil, de forma objetiva e acionável."


def _llm(modelo: str) -> LLM:
    # Sem novas tentativas no mesmo modelo: em caso de limite, a cadeia passa ao próximo.
    if modelo.startswith("anthropic/"):
        return LLM(model=modelo, api_key=config.ANTHROPIC_API_KEY, timeout=90, max_retries=0)
    if modelo.startswith("openrouter/"):
        return LLM(model=modelo, base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY,
                   timeout=90, max_retries=0)
    if modelo.startswith("ollama/"):
        return LLM(model=modelo, base_url=config.OLLAMA_BASE_URL, timeout=config.TEMPO_LIMITE_TAREFA, max_retries=0)
    return LLM(model=modelo, timeout=90, max_retries=0)  # demais provedores leem a chave do ambiente


def _agente(agente_id: str, llm: LLM, delegar: bool = False) -> Agent:
    return Agent(**PERFIS[agente_id], llm=llm, allow_delegation=delegar, max_retry_limit=0, verbose=False)


def _montar_crew(agente_id: str, texto: str, modelo: str) -> Crew:
    llm = _llm(modelo)
    descricao = f"Pedido do usuário: {texto}\n\n{INSTRUCOES}"

    if agente_id == "gestor":
        # O Gestor coordena: delega aos especialistas e revisa o resultado.
        equipe = [_agente(i, llm) for i in PERFIS if i != "gestor"]
        tarefa = Task(description=descricao, expected_output="Entrega final consolidada e revisada pelo Gestor.")
        return Crew(agents=equipe, tasks=[tarefa], process=Process.hierarchical, manager_agent=_agente("gestor", llm, delegar=True))

    agente = _agente(agente_id, llm)
    tarefa = Task(description=descricao, expected_output="Resposta completa ao pedido.", agent=agente)
    return Crew(agents=[agente], tasks=[tarefa])


async def executar(agente_id: str, texto: str) -> tuple[str, str]:
    """Executa a tarefa (em thread) percorrendo a cadeia de modelos. Devolve (resposta, modelo)."""
    ultimo_erro: Exception | None = None
    for modelo in config.cadeia_modelos(agente_id):
        crew = _montar_crew(agente_id, texto, modelo)
        try:
            resultado = await asyncio.to_thread(crew.kickoff)
            return resultado.raw, modelo
        except Exception as erro:
            log.warning("Modelo %s falhou (%s); tentando o próximo.", modelo, erro)
            ultimo_erro = erro
    raise RuntimeError("Todos os modelos falharam.") from ultimo_erro
