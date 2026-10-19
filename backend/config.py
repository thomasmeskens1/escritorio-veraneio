"""Configurações lidas das variáveis de ambiente."""

import os
from pathlib import Path

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITMO = "HS256"
JWT_VALIDADE_HORAS = 8

if not JWT_SECRET:
    raise RuntimeError("Defina JWT_SECRET no .env (veja .env.example).")


def _lista(nome: str, padrao: str) -> list[str]:
    return [item.strip() for item in os.getenv(nome, padrao).split(",") if item.strip()]


# Provedores de LLM. Modelos usam o formato "<provedor>/<modelo>".
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # créditos inclusos no plano Max
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Cadeia de fallback sem custo extra: gratuitos primeiro, créditos do Max por último.
MODELOS = _lista(
    "MODELOS",
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free,"
    "openrouter/google/gemma-4-31b-it:free,"
    "ollama/qwen3:4b,"
    "anthropic/claude-haiku-5-5",
)
# Modelo mais forte; vem primeiro para os agentes complexos. Vazio = nunca usado.
MODELO_PREMIUM = os.getenv("MODELO_PREMIUM", "anthropic/claude-sonnet-5-5").strip()
AGENTES_COMPLEXOS = set(_lista("AGENTES_COMPLEXOS", "gestor"))

# Provedor -> chave exigida (modelos sem chave configurada saem da cadeia).
_CHAVES = {"anthropic/": ANTHROPIC_API_KEY, "openrouter/": OPENROUTER_API_KEY}

TEMPO_LIMITE_TAREFA = int(os.getenv("TEMPO_LIMITE_TAREFA", "600"))  # segundos

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend"))


def cadeia_modelos(agente_id: str) -> list[str]:
    """Ordem de tentativa para o agente; ignora modelos de provedores sem chave configurada."""
    premium = [MODELO_PREMIUM] if MODELO_PREMIUM else []
    cadeia = premium + MODELOS if agente_id in AGENTES_COMPLEXOS else MODELOS + premium
    return [m for m in cadeia if all(chave for prefixo, chave in _CHAVES.items() if m.startswith(prefixo))]
