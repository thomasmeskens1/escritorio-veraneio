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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Cadeia de fallback: gratuitos → barato → local. Se um falhar, passa para o próximo.
MODELOS = _lista(
    "MODELOS",
    "openrouter/google/gemma-4-31b-it:free,"
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free,"
    "openrouter/qwen/qwen3.7-flash,"
    "ollama/qwen3:4b",
)
# Opcional e pago (ex.: openrouter/anthropic/claude-sonnet-5.5). Vazio = nunca usado.
MODELO_PREMIUM = os.getenv("MODELO_PREMIUM", "").strip()
# Agentes cujas tarefas começam pelo modelo premium.
AGENTES_COMPLEXOS = set(_lista("AGENTES_COMPLEXOS", "gestor"))

TEMPO_LIMITE_TAREFA = int(os.getenv("TEMPO_LIMITE_TAREFA", "600"))  # segundos

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend"))


def cadeia_modelos(agente_id: str) -> list[str]:
    """Ordem de tentativa para o agente; ignora modelos do OpenRouter sem chave configurada."""
    premium = [MODELO_PREMIUM] if MODELO_PREMIUM else []
    cadeia = premium + MODELOS if agente_id in AGENTES_COMPLEXOS else MODELOS + premium
    return [m for m in cadeia if OPENROUTER_API_KEY or not m.startswith("openrouter/")]
