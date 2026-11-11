"""Atividade em tempo real: ocupação dos agentes (status) e eventos do registro.

Os agentes rodam em threads (CrewAI); as funções `*_em_thread` levam as mudanças para o loop principal.
A ocupação é um contador: um agente pode estar numa tarefa própria e numa etapa de projeto ao mesmo tempo.
"""

import asyncio
import logging
from collections import Counter

import tarefas
from conexoes import gerenciador
from estado import Agente, Status, andar_do_agente, buscar_agente, snapshot

log = logging.getLogger(__name__)
_loop: asyncio.AbstractEventLoop | None = None
_ocupacao: Counter = Counter()


def vincular_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


async def transmitir_estado() -> None:
    await gerenciador.transmitir(lambda usuario: snapshot(usuario))


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


_etapas_abertas: Counter = Counter()  # agente -> etapas de projeto do Gestor rodando agora (vivas na memória)


def _tem_tarefa_ativa(agente_id: str) -> bool:
    """Brainstorm de 11/11/2026 (despachante-02): tarefa adiada ou peça na fila do Max ("producao") esperam a vez e não
    ocupam o agente; antes, uma adiada própria presa nunca deixava destravar. O projeto do Gestor só ocupa quem está
    numa etapa aberta agora (antes, qualquer tarefa do Gestor segurava o escritório inteiro)."""
    if _etapas_abertas[agente_id] > 0:
        return True
    return tarefas._db().execute(
        "SELECT 1 FROM tarefas WHERE status IN ('executando', 'produzindo') AND agente = ? LIMIT 1",
        (agente_id,)).fetchone() is not None


async def destravar_se_ocioso(agente_id: str) -> bool:
    """Agente "trabalhando" sem nenhuma tarefa ativa no banco (nem etapa de projeto aberta) é ocupação que vazou: zera
    e libera. Caso real (06–10/11/2026): o Gestor ficou preso em "trabalhando" por 4 dias e recusava todo pedido com
    "já está trabalhando em outra tarefa"."""
    agente = _agente(agente_id)
    if not agente or _tem_tarefa_ativa(agente_id):
        return False
    _ocupacao[agente_id] = 0
    agente.status = Status.disponivel
    await transmitir_estado()
    return True


INTERVALO_VIGIA_S = 5 * 60


async def destravar_todos() -> list[str]:
    """Uma volta do vigia: libera todo agente "trabalhando" sem tarefa ativa. Devolve quem foi liberado."""
    from estado import ANDARES

    liberados = []
    for agentes in ANDARES.values():
        for agente in list(agentes.values()):
            if agente.status == Status.trabalhando and await destravar_se_ocioso(agente.id):
                liberados.append(agente.id)
    return liberados


async def vigiar() -> None:
    """Vigia da ocupação (main.ciclo_de_vida): a cada 5 min, sem esperar alguém escrever no chat ou o Monday chamar
    (o conserto de 10/11 só destravava nesses dois casos). Erro aqui nunca derruba nada."""
    while True:
        await asyncio.sleep(INTERVALO_VIGIA_S)
        try:
            if (liberados := await destravar_todos()):
                log.warning("Vigia da ocupação: %s estava(m) em \"trabalhando\" sem tarefa ativa; liberado(s).",
                            ", ".join(liberados))
        except Exception:
            log.exception("Vigia da ocupação: falha ao conferir os agentes.")


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


async def _abrir_etapa(agente_id: str) -> None:
    _etapas_abertas[agente_id] += 1
    await ocupar(agente_id)


async def _fechar_etapa(agente_id: str) -> None:
    _etapas_abertas[agente_id] = max(0, _etapas_abertas[agente_id] - 1)
    await liberar(agente_id)


def etapa_em_thread(tarefa_id: int, tipo: str, agente: str, detalhe: str) -> None:
    """Etapa de projeto do Gestor: acende o setor do especialista e registra no log. O próprio Gestor já está ocupado
    pela tarefa dele: o aviso "Plano refeito" (etapa_iniciada do Gestor, sem etapa_encerrada) somava uma ocupação que
    nunca era liberada e o deixava preso em "trabalhando" (brainstorm de 11/11/2026, despachante-02)."""
    if tipo == "etapa_iniciada" and agente != "gestor":
        _no_loop(_abrir_etapa(agente))
    elif tipo == "etapa_encerrada":
        if agente != "gestor":
            _no_loop(_fechar_etapa(agente))
        return
    evento_em_thread(tarefa_id, tipo, agente, None, detalhe)
