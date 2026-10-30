"""Configurações lidas das variáveis de ambiente."""

import os
from pathlib import Path

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITMO = "HS256"
JWT_VALIDADE_HORAS = 8

if len(JWT_SECRET) < 32:  # segredo curto permite adivinhar e forjar tokens
    raise RuntimeError("Defina JWT_SECRET no .env com pelo menos 32 caracteres (veja .env.example).")


def _lista(nome: str, padrao: str) -> list[str]:
    return [item.strip() for item in os.getenv(nome, padrao).split(",") if item.strip()]


# Provedores de LLM. Modelos usam o formato "<provedor>/<modelo>".
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # créditos inclusos no plano Max
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _chave(nome: str) -> str:
    """Chave do .env; o texto de exemplo ("sua_chave_...") conta como ausente."""
    valor = os.getenv(nome, "").strip()
    return "" if valor.lower().startswith("sua_chave") else valor


# Planos gratuitos oficiais (sem cartão): Groq e Mistral. Sem chave válida, os modelos deles ficam fora da rota.
GROQ_API_KEY = _chave("GROQ_API_KEY")
MISTRAL_API_KEY = _chave("MISTRAL_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Execução imediata: gratuitos em ordem e depois o local (sem custo). Ordem definida por benchmark
# (velocidade, resposta em pt-BR e chamada de ferramentas); o Gemma vai por último por falhar em ferramentas.
MODELOS_GRATUITOS = _lista(
    "MODELOS_GRATUITOS",
    # Groq (plano gratuito, 2-3 s por resposta; 8 mil tokens/min: usa os manuais compactos, e no limite sai da
    # rota por 2 min); Mistral entra quando houver chave válida; Nemotron Super por último (afastado no teste).
    # Fora desde 28/10/2026 (teste de estresse): MiniMax M3.1 Flash (fim do período gratuito em 22/10) e Nemotron
    # Nano Omni Reasoning (devolvia o raciocínio em inglês no lugar da resposta).
    "groq/openai/gpt-oss-120b,"
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free,"
    "mistral/mistral-medium-latest,"
    "groq/qwen/qwen3.8-27b,"
    "openrouter/dots-studio/dots-3-note-preview:free,"
    "openrouter/google/gemma-4-31b-it:free,"
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
)
MODELO_LOCAL = os.getenv("MODELO_LOCAL", "ollama/qwen3:4b").strip()
# Embeddings do Cérebro (RAG), locais pelo Ollama: custo zero.
MODELO_EMBEDDING = os.getenv("MODELO_EMBEDDING", "qwen3-embedding:0.6b").strip()

# Fila adiada: créditos do Max. Haiku para simples/médias, Sonnet para complexas.
MODELO_FILA_PADRAO = os.getenv("MODELO_FILA_PADRAO", "anthropic/claude-haiku-5-5").strip()
MODELO_FILA_COMPLEXO = os.getenv("MODELO_FILA_COMPLEXO", "anthropic/claude-sonnet-5-5").strip()

# Orçamento Anthropic: crédito mensal do Max 5x, liberado em ritmo diário dentro do mês.
CREDITO_MENSAL_ANTHROPIC_USD = float(os.getenv("CREDITO_MENSAL_ANTHROPIC_USD", "100"))
FRACAO_UTILIZAVEL = 0.95  # reserva de 5% contra erro de estimativa
FRACAO_CHAT_RAPIDO = 0.10  # teto do crédito para tarefas simples atendidas pelo Haiku antes do local
# Agentes que dependem da API (usam ferramentas do sistema, então não vão para o Max): têm uma reserva do
# crédito que os demais não podem usar. Quanto mais longe a renovação, maior a reserva.
AGENTES_API_PRIORITARIOS = {"social_media", "construtor"}
RESERVA_PRIORITARIOS = ((21, 0.40), (11, 0.25), (6, 0.15), (0, 0.05))  # (dias até renovar ≥, fração reservada)
# US$ por milhão de tokens (entrada, saída). Conferir em platform.claude.com/docs/en/about-claude/pricing
PRECOS_ANTHROPIC = {
    "anthropic/claude-haiku-5-5": (0.10, 0.50),
    "anthropic/claude-sonnet-5-5": (2.00, 10.00),
}

# Provedor -> chave exigida (modelos sem chave configurada são ignorados).
_CHAVES = {"anthropic/": ANTHROPIC_API_KEY, "openrouter/": OPENROUTER_API_KEY, "groq/": GROQ_API_KEY,
           "mistral/": MISTRAL_API_KEY}

# Única conta que pode acionar a produção de PNG/MP4 pelo Claude Code (plano Max pessoal).
# Sem padrão no código (o repositório é público): o login do dono vem só do .env.
DONO_MAX = os.getenv("DONO_MAX", "").strip().lower()
if not DONO_MAX:
    raise RuntimeError("Defina DONO_MAX no .env (login do dono do plano Max; veja .env.example).")
# Chave do Max para todos os usuários (produção de arquivos, estudos e prospecção na web, anexos, respostas).
# LIGADA por decisão do Thomas em 29/10/2026, depois de avisado de que a assinatura Max é individual e de que os termos
# da Anthropic não permitem atender pedidos de outras pessoas por ela (risco à conta; decisão anterior: 19/10/2026).
# O que não é do Max continua do dono de qualquer forma (Monday, faturamento, Cérebro). Para desligar, False.
MAX_PARA_TODOS = True


def usa_max(login: str) -> bool:
    return MAX_PARA_TODOS or (login or "").strip().lower() == DONO_MAX

# Dados do sistema (tokens, anexos, manuais, projetos): pasta compartilhada com o PC (trabalhador Max, backup).
DADOS_DIR = Path(__file__).resolve().parent / "dados"
# O banco fica num volume do Docker (ARQUIVO_BANCO no compose): na pasta compartilhada do Windows cada leitura e
# escrita custava 10 a 40 vezes mais. Sem a variável, fica em dados/ (rodando fora do Docker).
ARQUIVO_BANCO = Path(os.getenv("ARQUIVO_BANCO", DADOS_DIR / "escritorio.db"))
# Cópia consistente do banco em dados/ (a cada 1 h e ao desligar) para o backup diário do Windows, que não enxerga o
# volume. Se o volume se perder, o banco é restaurado dela na subida (tarefas._restaurar_da_copia).
ARQUIVO_COPIA_BANCO = Path(os.getenv("ARQUIVO_COPIA_BANCO", DADOS_DIR / "escritorio.copia.db"))
ARQUIVO_LOG_BACKUP = DADOS_DIR / "backup.log"  # escrito pelo backup diário do Windows (scripts/backup_dados.py)
# Documentos oficiais e diretrizes dos agentes (fora do git: o repositório é público).
PASTA_CONHECIMENTO = Path(__file__).resolve().parent / "dados" / "conhecimento"
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend"))


def modelo_disponivel(modelo: str) -> bool:
    return bool(modelo) and all(chave for prefixo, chave in _CHAVES.items() if modelo.startswith(prefixo))
