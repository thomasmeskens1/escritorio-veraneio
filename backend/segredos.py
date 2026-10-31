"""Última barreira contra vazamento: texto que volta do Claude Code (Max) passa por aqui antes de ir ao chat ou ao
Monday. Valores de chaves/tokens/senhas do servidor e formatos conhecidos de chave viram "[removido]".

O Max roda Python no PC do dono; um briefing malicioso (ex.: comentário no Monday) poderia pedir para ler o .env
e devolver no resumo. O isolamento do trabalhador evita isso; esta limpeza garante que nada saia mesmo assim.
Formatos com prefixo e tamanho mínimo (31/10/2026: Groq, Brevo, Google, GitHub, Meta, Slack, AWS), com borda de
palavra onde o prefixo é curto, para não cortar texto comum. Tokens OAuth dos *.token.json de dados/ também saem.
"""

import json
import os
import re

import config

REMOVIDO = "[removido]"
_NOME_SEGREDO = re.compile(r"KEY|TOKEN|SECRET|SENHA|PASSWORD|CREDENTIAL|JWT", re.IGNORECASE)
_FORMATOS = re.compile(
    r"sk-(?:ant|or|proj)-[\w-]{10,}"                          # Anthropic / OpenRouter / OpenAI
    r"|\bgsk_[A-Za-z0-9]{20,}"                                # Groq
    r"|\bx(?:key|smtp)sib-[\w-]{20,}"                         # Brevo (API e SMTP)
    r"|\bAIza[\w-]{30,}"                                      # chave de API do Google
    r"|\bGOCSPX-[\w-]{20,}"                                   # segredo de cliente OAuth do Google
    r"|\bya29\.[\w-]{20,}"                                    # token de acesso OAuth do Google
    r"|(?<![\w/])1//0[\w-]{30,}"                              # refresh token do Google
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_\w{40,}"     # GitHub
    r"|\bEAA[A-Za-z0-9]{40,}"                                 # token da Meta (Facebook/Instagram)
    r"|\bxox[abprs]-[\w-]{10,}"                               # Slack
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"                         # AWS
    r"|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"                 # JWT
    r"|\b\d{8,10}:AA[\w-]{30,}"                               # token de bot do Telegram
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")
_CAMPOS_TOKEN = ("access_token", "refresh_token", "token", "client_secret", "id_token")


def _valores_tokens() -> list[str]:
    """Valores dos arquivos de token OAuth em dados/ (ex.: youtube_legendas.token.json)."""
    valores = []
    for arquivo in config.DADOS_DIR.glob("*.token.json"):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict):
            valores += [str(dados[c]) for c in _CAMPOS_TOKEN if isinstance(dados.get(c), str) and len(dados[c]) >= 12]
    return valores


def _valores() -> list[str]:
    valores = [v for k, v in os.environ.items() if _NOME_SEGREDO.search(k) and len(v or "") >= 12]
    token = config.DADOS_DIR / "operador.token"
    if token.exists():
        valores.append(token.read_text(encoding="utf-8").strip())
    valores += _valores_tokens()
    return sorted({v for v in valores if v}, key=len, reverse=True)


def limpar(texto: str) -> str:
    if not texto:
        return texto
    for valor in _valores():
        texto = texto.replace(valor, REMOVIDO)
    return _FORMATOS.sub(REMOVIDO, texto)
