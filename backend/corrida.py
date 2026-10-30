"""Modelos em corrida, com aprendizado (Thomas, 30/10/2026).

Antes: os modelos gratuitos eram tentados em ordem fixa, cada um com até 4 min; um modelo travado custava 4 min
antes de o próximo começar (tarefa 133 da Francielle). Agora, aprendendo com o histórico de cada modelo (eventos
"tentativa" → "concluida"/"falha_modelo" dos últimos 14 dias):

1. Ordem: o modelo com menor tempo esperado vai primeiro (tempo típico + chance de falhar × limite).
2. Tempo de espera adaptativo: o limite de cada gratuito vira ~1,5× o tempo em que ele costuma responder (p90),
   nunca acima do limite fixo de hoje.
3. Corrida ("hedge"): se o primeiro passa do tempo em que costuma responder, o segundo começa em paralelo e fica
   valendo a primeira resposta boa. Só para agentes sem efeito externo: Gestor (projeto com livro-razão), Social
   Media e Prospectador (Monday), E-mail Marketing (Brevo) e Construtor ficam fora, para nada ser feito duas vezes.

Modelo com menos de MINIMO_AMOSTRAS tentativas segue com os valores de hoje (sem dados, sem palpite).
"""

import asyncio
import logging
import statistics
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import tarefas

log = logging.getLogger(__name__)

JANELA_DIAS = 14
MINIMO_AMOSTRAS = 5
CACHE_S = 600
LIMITE_MINIMO_S = 60
ATRASO_PADRAO_S = 45                     # sem dados: a corrida começa depois de 45 s
ATRASO_MIN_S, ATRASO_MAX_S = 20, 120
SEM_CORRIDA = {"gestor", "social_media", "prospectador", "email_marketing", "construtor"}
_FIXOS = ("claude-code/", "ollama/", "anthropic/")  # Max, local e Claude pago: ordem e limites de hoje

_cache: dict = {}
_cache_em = 0.0


def _segundos(inicio: str, fim: str) -> float:
    formato = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.strptime(fim, formato) - datetime.strptime(inicio, formato)).total_seconds()


def perfis() -> dict[str, dict]:
    """modelo -> {tentativas, sucessos, taxa, p50, p90} aprendidos com o histórico (cache de 10 min)."""
    global _cache, _cache_em
    if time.time() - _cache_em < CACHE_S:
        return _cache
    desde = (datetime.now(timezone.utc) - timedelta(days=JANELA_DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = tarefas._db().execute(
        "SELECT tarefa_id, tipo, modelo, em FROM eventos WHERE em >= ? AND modelo IS NOT NULL "
        "AND tipo IN ('tentativa', 'concluida', 'falha_modelo') ORDER BY tarefa_id, id", (desde,)).fetchall()
    abertas: dict[tuple[int, str], str] = {}
    dados: dict[str, dict] = {}
    for l in linhas:
        chave = (l["tarefa_id"], l["modelo"])
        d = dados.setdefault(l["modelo"], {"tentativas": 0, "sucessos": 0, "tempos": []})
        if l["tipo"] == "tentativa":
            abertas[chave] = l["em"]
        elif (inicio := abertas.pop(chave, None)):  # tentativa pulada (ex.: grande demais para o Groq) não conta
            d["tentativas"] += 1
            if l["tipo"] == "concluida":
                d["sucessos"] += 1
                d["tempos"].append(max(_segundos(inicio, l["em"]), 1.0))
    resultado = {}
    for modelo, d in dados.items():
        tempos = sorted(d["tempos"])
        resultado[modelo] = {
            "tentativas": d["tentativas"], "sucessos": d["sucessos"],
            "taxa": d["sucessos"] / d["tentativas"] if d["tentativas"] else 0.0,
            "p50": statistics.median(tempos) if tempos else None,
            "p90": tempos[min(len(tempos) - 1, int(len(tempos) * 0.9))] if tempos else None,
        }
    _cache, _cache_em = resultado, time.time()
    return resultado


def _conhecido(modelo: str) -> dict | None:
    p = perfis().get(modelo)
    return p if p and p["tentativas"] >= MINIMO_AMOSTRAS else None


def _custo(p: dict, limite_s: int) -> float:
    """Tempo esperado até uma resposta: o típico dele (ou o limite, se nunca respondeu) + chance de falhar × limite."""
    return (p["p50"] if p["p50"] is not None else limite_s) + (1 - p["taxa"]) * limite_s


def _gratuito(modelo: str) -> bool:
    return not modelo.startswith(_FIXOS)


def ajustar(etapas: list) -> list:
    """Reordena os gratuitos pelo tempo esperado e ajusta o limite de cada um; os demais ficam onde estão."""
    posicoes = [i for i, e in enumerate(etapas) if _gratuito(e.modelo)]
    gratuitos = [etapas[i] for i in posicoes]

    def esperado(etapa) -> float:
        p = _conhecido(etapa.modelo)
        if not p:  # sem histórico: no meio da fila (nem primeiro, nem descartado)
            conhecidos = [q for g in gratuitos if (q := _conhecido(g.modelo))]
            return statistics.median([_custo(q, etapa.limite_s) for q in conhecidos]) if conhecidos else 0.0
        return _custo(p, etapa.limite_s)

    ordenados = sorted(gratuitos, key=esperado)  # sort estável: empates mantêm a ordem configurada
    novas = list(etapas)
    for i, etapa in zip(posicoes, ordenados):
        p = _conhecido(etapa.modelo)
        limite = etapa.limite_s if not p or not p["p90"] else \
            int(max(LIMITE_MINIMO_S, min(etapa.limite_s, p["p90"] * 1.5 + 15)))
        novas[i] = replace(etapa, limite_s=limite)
    return novas


def atraso_da_corrida(modelo: str) -> float:
    """Quanto esperar o primeiro modelo antes de largar o segundo: ~o tempo em que ele costuma responder."""
    p = _conhecido(modelo)
    return ATRASO_PADRAO_S if not p or p["p50"] is None else max(ATRASO_MIN_S, min(ATRASO_MAX_S, p["p50"] * 1.3))


def pode_correr(agente_id: str, primeira, segunda) -> bool:
    return (agente_id not in SEM_CORRIDA and segunda is not None
            and _gratuito(primeira.modelo) and _gratuito(segunda.modelo))


async def correr(tentar, primeira, segunda):
    """Roda `tentar(primeira)`; se não terminar no atraso aprendido, larga `tentar(segunda)` junto. Devolve
    (etapa, resultado, segunda_largou): a etapa da primeira resposta boa (ou None) e se a segunda chegou a rodar."""
    t1 = asyncio.ensure_future(tentar(primeira))
    try:
        resultado, _ = await asyncio.wait_for(asyncio.shield(t1), atraso_da_corrida(primeira.modelo))
        return (primeira, resultado, False) if resultado else (None, None, False)
    except asyncio.TimeoutError:
        pass
    log.info("Corrida: %s passou de %.0f s; largando %s em paralelo.", primeira.modelo,
             atraso_da_corrida(primeira.modelo), segunda.modelo)
    t2 = asyncio.ensure_future(tentar(segunda))
    pendentes = {t1: primeira, t2: segunda}
    while pendentes:
        prontas, _ = await asyncio.wait(pendentes, return_when=asyncio.FIRST_COMPLETED)
        for t in prontas:
            etapa = pendentes.pop(t)
            resultado, _ = t.result()
            if resultado:
                for perdedora in pendentes:  # a outra termina sozinha; o resultado dela é ignorado
                    perdedora.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
                return etapa, resultado, True
    return None, None, True


def resumo() -> list[dict]:
    """Para o relatório do "Treinar agora": o que foi aprendido de cada modelo."""
    return sorted(({"modelo": m, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in p.items()}}
                   for m, p in perfis().items() if p["tentativas"]), key=lambda x: -x["tentativas"])
