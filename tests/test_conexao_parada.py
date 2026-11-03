"""Conexão que parou de ler não trava quem envia (tarefa 239, 03/11/2026: o Gestor ficou "trabalhando" para sempre)."""

import asyncio

import conexoes


class _ParadaNoEnvio:
    def __init__(self):
        self.fechada = False

    async def send_json(self, _mensagem):
        await asyncio.sleep(3600)  # navegador em segundo plano: o envio nunca termina

    async def close(self):
        self.fechada = True


def test_envio_parado_desiste_e_fecha_a_conexao(monkeypatch):
    monkeypatch.setattr(conexoes, "ENVIO_LIMITE_S", 0.05)
    gerenciador = conexoes.GerenciadorConexoes()
    ws = _ParadaNoEnvio()
    gerenciador.conectar(ws, {"sub": "usuario.teste"})

    async def rodar():
        entregue = await gerenciador.enviar_para_usuario("usuario.teste", {"tipo": "aviso"})
        await asyncio.sleep(0.1)  # o fechamento roda em segundo plano
        return entregue

    assert asyncio.run(rodar()) is False
    assert ws not in gerenciador.ativas and ws.fechada
