"""Cérebro: embeddings locais pelo Ollama (custo zero). Se o Ollama estiver fora, devolve None
e a busca segue só com o BM25; após uma falha, aquece o modelo em segundo plano e espera um pouco antes de
tentar de novo."""

import logging
import threading
import time

import httpx
import numpy as np

import config

log = logging.getLogger(__name__)

PAUSA_APOS_FALHA = 60  # segundos sem tentar depois de uma falha (não atrasa as consultas)
TIMEOUT_CONSULTA = 8
TIMEOUT_LOTE = 120
# Primeira busca depois de uma pausa (levantamento de 31/10/2026, cerebro-17): o Ollama descarrega o modelo após 5 min
# parado, a recarga estourava os 8 s e a busca caía só nas palavras (pior) por 60 s. Escolha pela memória do PC:
# - nada de modelo fixo na memória (keep_alive -1): ele fica carregado 30 min depois do último uso, o que cobre o
#   ritmo do expediente, e sai sozinho à noite e nas pausas longas, liberando a memória para o qwen3:4b;
# - com o modelo provavelmente frio (sem uso há mais que isso), a consulta espera a recarga (TIMEOUT_FRIO) em vez de
#   cair na busca pior;
# - falhou mesmo assim: aquece em segundo plano (sob demanda), e a próxima consulta já o encontra carregado.
MANTER_CARREGADO = "30m"
MANTER_CARREGADO_S = 30 * 60
TIMEOUT_FRIO = 30
# O qwen3-embedding rende mais com a instrução na pergunta (os documentos vão sem instrução).
INSTRUCAO = "Instruct: Given a question about a company, retrieve passages that answer it\nQuery: "

_trava = threading.Lock()  # protege o cache das perguntas
_cache: dict[str, np.ndarray] = {}  # pergunta -> vetor (agentes repetem perguntas)
CACHE_MAX = 512
_ultima_falha = 0.0
_ultimo_uso = 0.0  # último embed que deu certo (o modelo segue carregado por MANTER_CARREGADO)
_ok: bool | None = None  # None: ainda não testado
_aquecendo = threading.Event()


def ollama_ok() -> bool | None:
    return _ok


def _marcar(ok: bool) -> None:
    global _ok, _ultima_falha, _ultimo_uso
    _ok = ok
    if ok:
        _ultimo_uso = time.monotonic()
    else:
        _ultima_falha = time.monotonic()


def frio() -> bool:
    """O modelo provavelmente já saiu da memória do Ollama (sem uso há mais de MANTER_CARREGADO)."""
    return time.monotonic() - _ultimo_uso > MANTER_CARREGADO_S


def _pedir(entradas: list[str], timeout: float) -> list:
    resposta = httpx.post(f"{config.OLLAMA_BASE_URL}/api/embed",
                          json={"model": config.MODELO_EMBEDDING, "input": entradas, "truncate": True,
                                "keep_alive": MANTER_CARREGADO}, timeout=timeout)
    resposta.raise_for_status()
    return resposta.json()["embeddings"]


def aquecer() -> None:
    """Carrega o modelo em segundo plano (uma vez por vez), sem segurar a consulta de ninguém."""
    if _aquecendo.is_set():
        return
    _aquecendo.set()

    def carregar() -> None:
        try:
            _pedir(["aquecimento"], TIMEOUT_LOTE)
            _marcar(True)
        except Exception as erro:
            log.info("Cérebro: aquecimento do modelo de busca falhou (%s).", str(erro)[:120])
        finally:
            _aquecendo.clear()

    threading.Thread(target=carregar, name="cerebro-aquecer", daemon=True).start()


def gerar(textos: list[str], consulta: bool = False) -> np.ndarray | None:
    """Matriz (n, d) float32 normalizada, ou None se o Ollama não respondeu."""
    if not textos:
        return np.zeros((0, 0), dtype=np.float32)
    if _ok is False and time.monotonic() - _ultima_falha < PAUSA_APOS_FALHA:
        return None
    if consulta and len(textos) == 1:
        with _trava:
            if textos[0] in _cache:
                return _cache[textos[0]][None, :]
    entradas = [INSTRUCAO + t if consulta else t for t in textos]
    try:
        # Sem trava: o Ollama enfileira/paraleliza sozinho e uma consulta não espera a outra aqui.
        # Ollama já fora (_ok False): sem a espera longa; o aquecimento em segundo plano é que tenta de novo.
        espera = (TIMEOUT_FRIO if frio() and _ok is not False else TIMEOUT_CONSULTA) if consulta else TIMEOUT_LOTE
        matriz = np.asarray(_pedir(entradas, espera), dtype=np.float32)
        if matriz.shape[0] != len(textos):
            raise ValueError("quantidade de embeddings diferente da de textos")
    except Exception as erro:
        if _ok is not False:
            log.warning("Cérebro: embeddings indisponíveis (%s); usando a busca lexical.", str(erro)[:200])
        _marcar(False)
        if consulta:
            aquecer()  # a próxima consulta já encontra o modelo carregado
        return None
    _marcar(True)
    normas = np.linalg.norm(matriz, axis=1, keepdims=True)
    matriz = matriz / np.where(normas == 0, 1, normas)
    if consulta and len(textos) == 1:
        with _trava:
            if len(_cache) >= CACHE_MAX:
                _cache.pop(next(iter(_cache)))
            _cache[textos[0]] = matriz[0]
    return matriz


def para_blob(vetor: np.ndarray) -> bytes:
    return np.asarray(vetor, dtype=np.float32).tobytes()


def de_blob(blob: bytes | None) -> np.ndarray | None:
    return np.frombuffer(blob, dtype=np.float32) if blob else None
