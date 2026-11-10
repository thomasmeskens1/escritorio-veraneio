"""Ocupação que vazou (caso real de 06–10/11/2026): o Gestor ficou em "trabalhando" sem nenhuma tarefa e recusava todo
pedido. Sem tarefa ativa no banco, o agente é liberado; com tarefa ativa, segue ocupado. Banco temporário
(tests/conftest.py)."""

import asyncio

import atividade
import tarefas
from estado import Status, buscar_agente

tarefas.iniciar()


def test_agente_preso_sem_tarefa_e_liberado(monkeypatch):
    gestor = buscar_agente("marketing", "gestor")
    asyncio.run(atividade.ocupar("gestor"))
    assert gestor.status == Status.trabalhando
    monkeypatch.setattr(atividade, "_tem_tarefa_ativa", lambda _agente: False)
    assert asyncio.run(atividade.destravar_se_ocioso("gestor"))
    assert gestor.status == Status.disponivel and atividade._ocupacao["gestor"] == 0


def test_agente_com_tarefa_ativa_segue_ocupado():
    tarefa_id = tarefas.criar("ana-ocupacao", "marketing", "copywriter", "Legenda", "simples")  # nasce "executando"
    copy = buscar_agente("marketing", "copywriter")
    asyncio.run(atividade.ocupar("copywriter"))
    assert atividade._tem_tarefa_ativa("copywriter")
    assert not asyncio.run(atividade.destravar_se_ocioso("copywriter"))
    assert copy.status == Status.trabalhando
    tarefas.atualizar(tarefa_id, status="concluida")
    asyncio.run(atividade.liberar("copywriter"))
