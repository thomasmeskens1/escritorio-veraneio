"""Orquestra as tarefas: execução imediata (gratuito → local), fila adiada e entrega das respostas.

A fila nunca trava: tenta o Claude (Haiku/Sonnet) e, se ele estiver indisponível (crédito do mês
esgotado ou ritmo diário atingido), segue em contingência com os gratuitos e o modelo local.
"""

import asyncio
import logging
import time

import saude
import tarefas
from conexoes import gerenciador
from estado import Agente, Status, buscar_agente, snapshot
from roteamento import Dificuldade, Etapa, classificar, etapa_fila, etapas_contingencia, etapas_imediatas

log = logging.getLogger(__name__)

INTERVALO_FILA = 5  # segundos entre verificações da fila

_em_andamento: set[asyncio.Task] = set()  # referência forte às tarefas em segundo plano


async def atualizar_status(agente: Agente, status: Status) -> None:
    agente.status = status
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


def ha_modelo_disponivel() -> bool:
    return bool(etapas_contingencia() or etapa_fila(Dificuldade.simples))


async def nova_tarefa(login: str, andar: str, agente: Agente, texto: str) -> None:
    dificuldade = classificar(agente.id, texto)
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, dificuldade.value)
    await atualizar_status(agente, Status.trabalhando)
    execucao = asyncio.create_task(_executar_imediata(tarefa_id, agente, dificuldade))
    _em_andamento.add(execucao)
    execucao.add_done_callback(_em_andamento.discard)


async def _tentar(tarefa, agente: Agente, etapa: Etapa):
    """Uma tentativa num modelo, com o histórico da conversa. Devolve (resultado ou None, erro)."""
    from agents.executor import LocalOcupado, executar  # import tardio: CrewAI é pesado

    historico = tarefas.historico(tarefa["usuario"], tarefa["andar"], tarefa["agente"], tarefa["id"])
    inicio = time.monotonic()
    try:
        return await executar(agente.id, tarefa["texto"], etapa, historico), ""
    except LocalOcupado:
        return None, "modelo local ocupado"
    except asyncio.TimeoutError:
        erro = f"excedeu {etapa.limite_s // 60} min"
    except Exception as e:
        erro = str(e)
        saude.registrar_falha(etapa.modelo, erro)  # estourou? sai da rota até a cota voltar
    finally:
        tarefas.registrar_tentativa(tarefa["id"], time.monotonic() - inicio)
    log.warning("Tarefa %s: %s falhou (%s).", tarefa["id"], etapa.modelo, erro[:200])
    return None, erro


async def _executar_etapas(tarefa, agente: Agente, etapas: list[Etapa]) -> bool:
    """Troca de modelo a cada falha, até um concluir."""
    for etapa in etapas:
        resultado, _ = await _tentar(tarefa, agente, etapa)
        if resultado:
            await _concluir(tarefa["id"], etapa.modelo, resultado)
            return True
    return False


async def _executar_imediata(tarefa_id: int, agente: Agente, dificuldade: Dificuldade) -> None:
    tarefa = tarefas.obter(tarefa_id)
    try:
        if await _executar_etapas(tarefa, agente, etapas_imediatas(dificuldade, agente.id)):
            return
        destino = "fila do Claude" if etapa_fila(dificuldade) else "fila de contingência (gratuitos e local)"
        tarefas.atualizar(tarefa_id, status="adiada", motivo="Os modelos imediatos não concluíram a tarefa a tempo.")
        await gerenciador.enviar_para_usuario(tarefa["usuario"], {
            "tipo": "tarefa_adiada", "andar": tarefa["andar"], "agente": agente.id, "tarefa_id": tarefa_id,
            "texto": f"Os modelos imediatos não concluíram a tarefa a tempo. Ela foi para a {destino}; "
                     "a resposta chega assim que for processada.",
        })
    finally:
        await atualizar_status(agente, Status.disponivel)


async def _concluir(tarefa_id: int, modelo: str, resultado) -> None:
    custo = tarefas.custo_estimado(modelo, resultado.tokens_entrada, resultado.tokens_saida)
    tarefas.atualizar(tarefa_id, status="concluida", modelo=modelo, resposta=resultado.texto,
                      tokens_entrada=resultado.tokens_entrada, tokens_saida=resultado.tokens_saida, custo_usd=custo)
    await _entregar(tarefas.obter(tarefa_id))


def _mensagem(linha) -> dict:
    alvo = {"andar": linha["andar"], "agente": linha["agente"], "tarefa_id": linha["id"]}
    if linha["status"] == "falhou":
        return {"tipo": "erro", "texto": linha["motivo"] or "Falha ao executar a tarefa.", **alvo}
    return {"tipo": "resposta_agente", **alvo, "texto": linha["resposta"], "modelo": linha["modelo"],
            "dificuldade": linha["dificuldade"], "tempo_segundos": round(linha["tempo_segundos"], 1),
            "adiada": linha["motivo"] is not None}


async def _entregar(linha) -> None:
    if await gerenciador.enviar_para_usuario(linha["usuario"], _mensagem(linha)):
        tarefas.atualizar(linha["id"], entregue=1)


async def entregar_pendentes(login: str) -> None:
    """Respostas que ficaram prontas enquanto o usuário estava fora."""
    for linha in tarefas.nao_entregues(login):
        await _entregar(linha)


# --- Fila adiada -------------------------------------------------------------------------

async def processar_fila() -> None:
    while True:
        try:
            espera = await _processar_proxima()
        except Exception:
            log.exception("Erro ao processar a fila.")
            espera = INTERVALO_FILA
        await asyncio.sleep(espera)


def _etapas_fila(dificuldade: Dificuldade) -> list[Etapa]:
    """Claude primeiro (se houver crédito e ritmo diário); depois a contingência."""
    claude = etapa_fila(dificuldade) if not tarefas.orcamento_pausado() else None
    return ([claude] if claude else []) + etapas_contingencia()


async def _processar_proxima() -> int:
    """Processa uma tarefa adiada; devolve quantos segundos esperar antes da próxima."""
    for linha in tarefas.proximas_adiadas():
        agente = buscar_agente(linha["andar"], linha["agente"])
        if not agente:
            tarefas.atualizar(linha["id"], status="falhou", motivo="Agente não existe mais.")
            await _entregar(tarefas.obter(linha["id"]))
            continue
        etapas = _etapas_fila(Dificuldade(linha["dificuldade"]))
        if agente.status == Status.trabalhando or not etapas:
            continue  # agente ocupado ou nenhum modelo no ar agora: fica para a próxima rodada

        tarefas.atualizar(linha["id"], status="executando")
        await atualizar_status(agente, Status.trabalhando)
        try:
            concluiu = await _executar_etapas(linha, agente, etapas)
        finally:
            await atualizar_status(agente, Status.disponivel)

        if not concluiu and not tarefas.reagendar(linha["id"]):
            tarefas.atualizar(linha["id"], status="falhou",
                              motivo="Nenhum modelo conseguiu concluir a tarefa após várias tentativas.")
            await _entregar(tarefas.obter(linha["id"]))
        return 0

    return INTERVALO_FILA
