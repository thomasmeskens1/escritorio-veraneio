"""Orquestra as tarefas: execução imediata (gratuito → local), fila adiada do Claude e entrega das respostas."""

import asyncio
import logging
import time

import tarefas
from conexoes import gerenciador
from estado import Agente, Status, buscar_agente, snapshot
from roteamento import Dificuldade, Etapa, classificar, etapa_fila, etapas_imediatas

log = logging.getLogger(__name__)

INTERVALO_FILA = 5          # segundos entre verificações da fila
ESPERA_ORCAMENTO = 10 * 60  # orçamento do dia esgotado: tenta de novo mais tarde

_em_andamento: set[asyncio.Task] = set()  # referência forte às tarefas em segundo plano


async def atualizar_status(agente: Agente, status: Status) -> None:
    agente.status = status
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


def ha_modelo_disponivel() -> bool:
    return any(etapas_imediatas(d) or etapa_fila(d) for d in Dificuldade)


async def nova_tarefa(login: str, andar: str, agente: Agente, texto: str) -> None:
    dificuldade = classificar(agente.id, texto)
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, dificuldade.value)
    await atualizar_status(agente, Status.trabalhando)
    execucao = asyncio.create_task(_executar_imediata(tarefa_id, agente, dificuldade))
    _em_andamento.add(execucao)
    execucao.add_done_callback(_em_andamento.discard)


async def _tentar(tarefa_id: int, agente: Agente, texto: str, etapa: Etapa):
    """Uma tentativa num modelo. Devolve (resultado ou None, descrição do erro)."""
    from agents.executor import LocalOcupado, executar  # import tardio: CrewAI é pesado

    inicio = time.monotonic()
    try:
        return await executar(agente.id, texto, etapa), ""
    except LocalOcupado:
        return None, "modelo local ocupado"
    except asyncio.TimeoutError:
        erro = f"excedeu {etapa.limite_s // 60} min"
    except Exception as e:
        erro = str(e)
    finally:
        tarefas.registrar_tentativa(tarefa_id, time.monotonic() - inicio)
    log.warning("Tarefa %s: %s falhou (%s).", tarefa_id, etapa.modelo, erro[:200])
    return None, erro


async def _executar_imediata(tarefa_id: int, agente: Agente, dificuldade: Dificuldade) -> None:
    tarefa = tarefas.obter(tarefa_id)
    try:
        for etapa in etapas_imediatas(dificuldade):
            resultado, _ = await _tentar(tarefa_id, agente, tarefa["texto"], etapa)
            if resultado:
                return await _concluir(tarefa_id, etapa.modelo, resultado)

        motivo = "Os modelos gratuitos e o local não concluíram a tarefa a tempo."
        if etapa_fila(dificuldade):
            tarefas.atualizar(tarefa_id, status="adiada", motivo=motivo)
            await gerenciador.enviar_para_usuario(tarefa["usuario"], {
                "tipo": "tarefa_adiada", "andar": tarefa["andar"], "agente": agente.id, "tarefa_id": tarefa_id,
                "texto": f"{motivo} Ela foi para a fila do Claude; a resposta chega assim que for processada.",
            })
        else:
            tarefas.atualizar(tarefa_id, status="falhou", motivo=motivo)
            await _entregar(tarefas.obter(tarefa_id))
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


# --- Fila adiada (Claude) ---------------------------------------------------------------

async def processar_fila() -> None:
    while True:
        try:
            espera = await _processar_proxima()
        except Exception:
            log.exception("Erro ao processar a fila.")
            espera = INTERVALO_FILA
        await asyncio.sleep(espera)


async def _processar_proxima() -> int:
    """Processa uma tarefa adiada; devolve quantos segundos esperar antes da próxima."""
    if tarefas.orcamento_pausado():
        return ESPERA_ORCAMENTO

    for linha in tarefas.proximas_adiadas():
        agente = buscar_agente(linha["andar"], linha["agente"])
        etapa = etapa_fila(Dificuldade(linha["dificuldade"]))
        if not agente or not etapa:
            tarefas.atualizar(linha["id"], status="falhou", motivo="Agente ou modelo do Claude indisponível.")
            await _entregar(tarefas.obter(linha["id"]))
            continue
        if agente.status == Status.trabalhando:
            continue  # tenta outra; esta volta na próxima rodada

        tarefas.atualizar(linha["id"], status="executando")
        await atualizar_status(agente, Status.trabalhando)
        try:
            resultado, erro = await _tentar(linha["id"], agente, linha["texto"], etapa)
        finally:
            await atualizar_status(agente, Status.disponivel)

        if resultado:
            await _concluir(linha["id"], etapa.modelo, resultado)
            return 0
        if "credit balance" in erro.lower():  # crédito do mês acabou: mantém na fila
            tarefas.atualizar(linha["id"], status="adiada")
            return ESPERA_ORCAMENTO
        tarefas.atualizar(linha["id"], status="falhou", motivo="O Claude também não concluiu a tarefa.")
        await _entregar(tarefas.obter(linha["id"]))
        return 0

    return INTERVALO_FILA
