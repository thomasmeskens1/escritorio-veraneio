"""Estagiários do Cérebro: levam o conhecimento até o andar de quem consultou (só animação).

Pool de 4: cada consulta pega um estagiário livre, que "visita" o agente por pelo menos ~6 s e volta.
Com os 4 ocupados, a consulta é respondida na hora, sem visita: nunca bloqueia os agentes.
Chamado das threads dos agentes; o estado vai ao frontend pelo loop principal (atividade._loop).
"""

import asyncio
import threading
import time

import atividade
from estado import Status, andar_do_agente, buscar_agente

IDS = ["estagiario_1", "estagiario_2", "estagiario_3", "estagiario_4"]
DURACAO_MINIMA_VISITA = 6.0  # segundos, para a caminhada aparecer na tela

_trava = threading.Lock()
_visitas: dict[str, dict] = {}  # estagiário -> {"andar", "agente", "fim"}


def _aplicar(estagiario_id: str, visita: dict | None) -> None:
    """Muda o avatar e transmite o estado (no loop principal, se houver)."""
    agente = buscar_agente("cobertura", estagiario_id)
    if not agente:
        return
    agente.visitando = {"andar": visita["andar"], "agente": visita["agente"]} if visita else None
    agente.status = Status.trabalhando if visita else Status.disponivel
    loop = atividade._loop
    if loop and not loop.is_closed():
        asyncio.run_coroutine_threadsafe(atividade.transmitir_estado(), loop)


def _encerrar(estagiario_id: str, fim: float) -> None:
    with _trava:
        visita = _visitas.get(estagiario_id)
        if not visita or visita["fim"] != fim:
            return  # a visita foi estendida por outra consulta do mesmo agente
        del _visitas[estagiario_id]
    _aplicar(estagiario_id, None)


def _agendar_fim(estagiario_id: str, fim: float) -> None:
    espera = max(0.0, fim - time.monotonic())
    temporizador = threading.Timer(espera, _encerrar, args=(estagiario_id, fim))
    temporizador.daemon = True
    temporizador.start()


def iniciar_visita(agente_id: str) -> str | None:
    """Despacha um estagiário livre ao andar do agente. Devolve o id dele, ou None (todos ocupados)."""
    andar = andar_do_agente(agente_id)
    if not andar:
        return None
    fim = time.monotonic() + DURACAO_MINIMA_VISITA
    with _trava:
        # O mesmo agente consultando de novo: o estagiário que já está lá fica mais um pouco.
        atual = next((e for e, v in _visitas.items() if v["agente"] == agente_id), None)
        if atual:
            _visitas[atual]["fim"] = fim
            _agendar_fim(atual, fim)
            return atual
        livre = next((e for e in IDS if e not in _visitas and buscar_agente("cobertura", e)), None)
        if not livre:
            return None
        visita = _visitas[livre] = {"andar": andar, "agente": agente_id, "fim": fim}
    _aplicar(livre, visita)
    _agendar_fim(livre, fim)
    return livre


def concluir_visita(estagiario_id: str, folga: float = 2.0) -> None:
    """Busca terminou: se ela passou dos ~6 s, o estagiário ainda fica `folga` segundos e volta."""
    with _trava:
        visita = _visitas.get(estagiario_id)
        if not visita or visita["fim"] >= time.monotonic() + folga:
            return
        visita["fim"] = time.monotonic() + folga
        fim = visita["fim"]
    _agendar_fim(estagiario_id, fim)


def visitas() -> dict[str, dict]:
    with _trava:
        return {e: {"andar": v["andar"], "agente": v["agente"]} for e, v in _visitas.items()}
