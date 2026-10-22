"""Última barreira contra vazamento: texto que volta do Claude Code (Max) passa por aqui antes de ir ao chat ou ao
Monday. Valores de chaves/tokens/senhas do servidor e formatos conhecidos de chave viram "[removido]".

O Max roda Python no PC do dono; um briefing malicioso (ex.: comentário no Monday) poderia pedir para ler o .env
e devolver no resumo. O isolamento do trabalhador evita isso; esta limpeza garante que nada saia mesmo assim.
"""

import os
import re

import config

REMOVIDO = "[removido]"
_NOME_SEGREDO = re.compile(r"KEY|TOKEN|SECRET|SENHA|PASSWORD|CREDENTIAL|JWT", re.IGNORECASE)
_FORMATOS = re.compile(
    r"sk-(?:ant|or)-[\w-]{10,}"                               # Anthropic / OpenRouter
    r"|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"                 # JWT
    r"|\b\d{8,10}:AA[\w-]{30,}"                               # token de bot do Telegram
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")


def _valores() -> list[str]:
    valores = [v for k, v in os.environ.items() if _NOME_SEGREDO.search(k) and len(v or "") >= 12]
    token = config.ARQUIVO_BANCO.parent / "operador.token"
    if token.exists():
        valores.append(token.read_text(encoding="utf-8").strip())
    return sorted({v for v in valores if v}, key=len, reverse=True)


def limpar(texto: str) -> str:
    if not texto:
        return texto
    for valor in _valores():
        texto = texto.replace(valor, REMOVIDO)
    return _FORMATOS.sub(REMOVIDO, texto)
