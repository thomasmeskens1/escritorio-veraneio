"""Atividade em tempo real: ocupação dos agentes (status) e eventos do registro.

Os agentes rodam em threads (CrewAI); as funções `*_em_thread` levam as mudanças para o loop principal.
A ocupação é um contador: um agente pode estar numa tarefa própria e numa etapa de projeto ao mesmo tempo.
"""

import asyncio
from collections import Counter

import tarefas
from conexoes import gerenciador
from estado import Agente, Status, andar_do_agente, buscar_agente, snapshot

_loop: asyncio.AbstractEventLoop | None = None
_ocupacao: Counter = Counter()


def vincular_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


async def transmitir_estado() -> None:
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


def _agente(agente_id: str) -> Agente | None:
    andar = andar_do_agente(agente_id)
    return buscar_agente(andar, agente_id) if andar else None


async def ocupar(agente_id: str) -> None:
    agente = _agente(agente_id)
    if agente:
        _ocupacao[agente_id] += 1
        agente.status = Status.trabalhando
        await transmitir_estado()


async def liberar(agente_id: str) -> None:
    agente = _agente(agente_id)
    if agente:
        _ocupacao[agente_id] = max(0, _ocupacao[agente_id] - 1)
        if not _ocupacao[agente_id]:
            agente.status = Status.disponivel
        await transmitir_estado()


def _no_loop(corrotina) -> None:
    if _loop:
        asyncio.run_coroutine_threadsafe(corrotina, _loop)
    else:
        corrotina.close()


async def _gravar_evento(*args) -> None:
    tarefas.registrar_evento(*args)


def evento_em_thread(tarefa_id: int, tipo: str, agente: str | None = None, modelo: str | None = None,
                     detalhe: str | None = None) -> None:
    _no_loop(_gravar_evento(tarefa_id, tipo, agente, modelo, detalhe))


def etapa_em_thread(tarefa_id: int, tipo: str, agente: str, detalhe: str) -> None:
    """Etapa de projeto do Gestor: acende o setor do especialista e registra no log."""
    if tipo == "etapa_iniciada":
        _no_loop(ocupar(agente))
    elif tipo == "etapa_encerrada":
        _no_loop(liberar(agente))
        return
    evento_em_thread(tarefa_id, tipo, agente, None, detalhe)
