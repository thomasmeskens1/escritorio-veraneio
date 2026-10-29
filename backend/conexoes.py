"""Gerenciador de conexões WebSocket com múltiplos clientes."""

import logging
import time
from typing import Callable

from fastapi import WebSocket

log = logging.getLogger(__name__)

# Presença (painel de usuários do master): o navegador avisa a cada minuto se a pessoa interagiu nos últimos 5 min
# com a aba visível. Ativo = alguma conexão nessa situação; ausente = conectado sem interação; offline = sem conexão.
AUSENTE_APOS_S = 5 * 60


class GerenciadorConexoes:
    def __init__(self) -> None:
        self.ativas: dict[WebSocket, dict] = {}  # websocket -> payload do token
        self.interacao: dict[WebSocket, float] = {}  # websocket -> última interação do usuário (time.time())
        self.chats: dict[WebSocket, str] = {}  # websocket -> "andar/agente" do chat aberto (quem está usando quem)

    def conectar(self, ws: WebSocket, usuario: dict) -> None:
        self.ativas[ws] = usuario
        self.interacao[ws] = time.time()

    def desconectar(self, ws: WebSocket) -> None:
        self.ativas.pop(ws, None)
        self.interacao.pop(ws, None)
        self.chats.pop(ws, None)

    def registrar_presenca(self, ws: WebSocket, interagiu: bool, chat: str | None = None) -> bool:
        """Aviso do navegador (ou um pedido enviado): `interagiu` = mexeu no escritório com a aba visível; `chat` =
        "andar/agente" aberto ("" = nenhum; None = não informado). Devolve True se o chat aberto mudou."""
        if ws not in self.ativas:
            return False
        if interagiu:
            self.interacao[ws] = time.time()
        if chat is None or self.chats.get(ws, "") == chat:
            return False
        if chat:
            self.chats[ws] = chat
        else:
            self.chats.pop(ws, None)
        return True

    def conversando(self) -> dict[str, set[str]]:
        """"andar/agente" -> logins com o chat dele aberto."""
        quem: dict[str, set[str]] = {}
        for ws, chat in self.chats.items():
            if ws in self.ativas:
                quem.setdefault(chat, set()).add(self.ativas[ws]["sub"])
        return quem

    def status_de(self, login: str) -> str:
        """"ativo", "ausente" ou "offline"."""
        ultimas = [self.interacao.get(ws, 0) for ws, usuario in self.ativas.items() if usuario["sub"] == login]
        if not ultimas:
            return "offline"
        return "ativo" if time.time() - max(ultimas) < AUSENTE_APOS_S else "ausente"

    async def enviar(self, ws: WebSocket, mensagem: dict) -> bool:
        try:
            await ws.send_json(mensagem)
            return True
        except Exception:
            log.info("Conexão perdida ao enviar; removendo cliente.")
            self.desconectar(ws)
            return False

    async def enviar_para_usuario(self, login: str, mensagem: dict) -> bool:
        """Envia a todas as conexões do usuário; True se ao menos uma recebeu."""
        entregue = False
        for ws, usuario in list(self.ativas.items()):
            if usuario["sub"] == login:
                entregue = await self.enviar(ws, mensagem) or entregue
        return entregue

    async def transmitir(self, montar: Callable[[dict], dict]) -> None:
        """Envia a todos; `montar` recebe o usuário e devolve a mensagem dele."""
        for ws, usuario in list(self.ativas.items()):
            await self.enviar(ws, montar(usuario))


gerenciador = GerenciadorConexoes()
