"""Alarme no celular pelo Telegram (brainstorm de 31/10/2026, despachante-16; decisão 18a do Thomas: só o Telegram).

A cada 5 min confere os avisos de operação do painel da Diretoria (saude.avisos_da_operacao: trabalhador do Max
parado, Ollama fora, backup atrasado, caixa de areia, rota de gratuitos encolhida...) e manda ao Telegram só o que
é novo, repetindo a cada 6 h enquanto continuar e avisando quando resolver. Limite conhecido: se o PC inteiro cair,
a própria API cai junto e nada é enviado (o Healthchecks.io cobriria esse caso; ficou de fora por decisão).

Configuração no .env do projeto: TELEGRAM_BOT_TOKEN (do @BotFather) e TELEGRAM_CHAT_ID. Sem os dois, não faz nada.
Descobrir o chat: mande /start ao robô e rode no contêiner `python alarme_telegram.py --descobrir-chat`.
Teste: `python alarme_telegram.py --teste`.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.request

import segredos

log = logging.getLogger(__name__)

INTERVALO_S = 5 * 60
REPETIR_S = 6 * 3600
LIMITE_TEXTO = 3500  # o Telegram aceita 4096 caracteres por mensagem


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def ativo() -> bool:
    return bool(_token() and _chat())


def _api(metodo: str, dados: dict | None = None) -> dict:
    requisicao = urllib.request.Request(
        f"https://api.telegram.org/bot{_token()}/{metodo}", data=json.dumps(dados or {}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requisicao, timeout=20) as resposta:
        return json.load(resposta)


def enviar(texto: str) -> None:
    _api("sendMessage", {"chat_id": _chat(), "text": segredos.limpar(texto)[:LIMITE_TEXTO],
                         "disable_web_page_preview": True})


def _chave(aviso: str) -> str:
    """O mesmo problema com números diferentes ("há 12 min", "há 17 min") é um aviso só."""
    return re.sub(r"\d+", "#", aviso)[:120]


class Alarme:
    def __init__(self, enviar_fn=enviar):
        self._enviar = enviar_fn
        self._abertos: dict[str, tuple[str, float]] = {}  # chave -> (texto, quando avisou)

    def conferir(self, avisos: list[str], agora: float | None = None) -> list[str]:
        """Manda o que é novo ou repetido e o que resolveu; devolve as mensagens enviadas."""
        agora = time.time() if agora is None else agora
        atuais = {_chave(a): a for a in avisos}
        novos = [a for k, a in atuais.items() if k not in self._abertos or agora - self._abertos[k][1] >= REPETIR_S]
        resolvidos = [texto for k, (texto, _) in self._abertos.items() if k not in atuais]
        mensagens = []
        if novos:
            mensagens.append("⚠️ Escritório Veraneio\n\n" + "\n\n".join(f"• {a}" for a in novos))
        if resolvidos:
            mensagens.append("✅ Resolvido\n\n" + "\n\n".join(f"• {a[:200]}" for a in resolvidos))
        for mensagem in mensagens:
            self._enviar(mensagem)
        for k, a in atuais.items():
            if a in novos:
                self._abertos[k] = (a, agora)
        for k in [k for k in self._abertos if k not in atuais]:
            del self._abertos[k]
        return mensagens


async def vigiar() -> None:
    """Laço da API (main.ciclo_de_vida). Falha no Telegram ou no painel nunca derruba nada."""
    import saude

    if not ativo():
        log.info("Alarme do Telegram desligado (falta TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID).")
        return
    alarme = Alarme()
    await asyncio.sleep(120)  # deixa a subida terminar (Ollama e trabalhador do Max voltam a responder)
    while True:
        try:
            avisos = await asyncio.to_thread(saude.avisos_da_operacao)
            await asyncio.to_thread(alarme.conferir, avisos)
        except Exception:
            log.exception("Alarme do Telegram: falha ao conferir ou enviar.")
        await asyncio.sleep(INTERVALO_S)


if __name__ == "__main__":
    if not _token():
        sys.exit("Falta TELEGRAM_BOT_TOKEN no .env.")
    if "--descobrir-chat" in sys.argv:
        for atualizacao in _api("getUpdates").get("result", []):
            chat = (atualizacao.get("message") or {}).get("chat") or {}
            print(chat.get("id"), chat.get("first_name") or chat.get("title") or "")
    elif "--teste" in sys.argv:
        enviar("✅ Teste do alarme do Escritório Veraneio: está funcionando.")
        print("Mensagem de teste enviada.")
