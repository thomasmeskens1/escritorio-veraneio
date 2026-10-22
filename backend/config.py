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
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Execução imediata: gratuitos em ordem e depois o local (sem custo). Ordem definida por benchmark
# (velocidade, resposta em pt-BR e chamada de ferramentas); o Gemma vai por último por falhar em ferramentas.
MODELOS_GRATUITOS = _lista(
    "MODELOS_GRATUITOS",
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free,"
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free,"
    "openrouter/minimax/minimax-m3.1-flash:free,"
    "openrouter/dots-studio/dots-3-note-preview:free,"
    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,"
    "openrouter/google/gemma-4-31b-it:free",
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
_CHAVES = {"anthropic/": ANTHROPIC_API_KEY, "openrouter/": OPENROUTER_API_KEY}

# Única conta que pode acionar a produção de PNG/MP4 pelo Claude Code (plano Max pessoal).
# Sem padrão no código (o repositório é público): o login do dono vem só do .env.
DONO_MAX = os.getenv("DONO_MAX", "").strip().lower()
if not DONO_MAX:
    raise RuntimeError("Defina DONO_MAX no .env (login do dono do plano Max; veja .env.example).")

# Dados do sistema (tokens, anexos, manuais, projetos): pasta compartilhada com o PC (trabalhador Max, backup).
DADOS_DIR = Path(__file__).resolve().parent / "dados"
# O banco fica num volume do Docker (ARQUIVO_BANCO no compose): na pasta compartilhada do Windows cada leitura e
# escrita custava 10 a 40 vezes mais. Sem a variável, fica em dados/ (rodando fora do Docker).
ARQUIVO_BANCO = Path(os.getenv("ARQUIVO_BANCO", DADOS_DIR / "escritorio.db"))
# Cópia consistente do banco em dados/ (a cada 6 h) para o backup diário do Windows, que não enxerga o volume.
ARQUIVO_COPIA_BANCO = DADOS_DIR / "escritorio.copia.db"
# Documentos oficiais e diretrizes dos agentes (fora do git: o repositório é público).
PASTA_CONHECIMENTO = Path(__file__).resolve().parent / "dados" / "conhecimento"
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend"))


def modelo_disponivel(modelo: str) -> bool:
    return bool(modelo) and all(chave for prefixo, chave in _CHAVES.items() if modelo.startswith(prefixo))
