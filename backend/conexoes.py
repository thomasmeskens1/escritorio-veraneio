"""Gerenciador de conexões WebSocket com múltiplos clientes."""

import logging
from typing import Callable

from fastapi import WebSocket

log = logging.getLogger(__name__)


class GerenciadorConexoes:
    def __init__(self) -> None:
        self.ativas: dict[WebSocket, dict] = {}  # websocket -> payload do token

    def conectar(self, ws: WebSocket, usuario: dict) -> None:
        self.ativas[ws] = usuario

    def desconectar(self, ws: WebSocket) -> None:
        self.ativas.pop(ws, None)

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
