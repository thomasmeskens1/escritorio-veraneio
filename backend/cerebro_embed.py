"""Cérebro: embeddings locais pelo Ollama (custo zero). Se o Ollama estiver fora, devolve None
e a busca segue só com o BM25; após uma falha, espera um pouco antes de tentar de novo."""

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
# O qwen3-embedding rende mais com a instrução na pergunta (os documentos vão sem instrução).
INSTRUCAO = "Instruct: Given a question about a company, retrieve passages that answer it\nQuery: "

_trava = threading.Lock()  # protege o cache das perguntas
_cache: dict[str, np.ndarray] = {}  # pergunta -> vetor (agentes repetem perguntas)
CACHE_MAX = 512
_ultima_falha = 0.0
_ok: bool | None = None  # None: ainda não testado


def ollama_ok() -> bool | None:
    return _ok


def _marcar(ok: bool) -> None:
    global _ok, _ultima_falha
    _ok = ok
    if not ok:
        _ultima_falha = time.monotonic()


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
        resposta = httpx.post(f"{config.OLLAMA_BASE_URL}/api/embed",
                              json={"model": config.MODELO_EMBEDDING, "input": entradas, "truncate": True},
                              timeout=TIMEOUT_CONSULTA if consulta else TIMEOUT_LOTE)
        resposta.raise_for_status()
        matriz = np.asarray(resposta.json()["embeddings"], dtype=np.float32)
        if matriz.shape[0] != len(textos):
            raise ValueError("quantidade de embeddings diferente da de textos")
    except Exception as erro:
        if _ok is not False:
            log.warning("Cérebro: embeddings indisponíveis (%s); usando a busca lexical.", str(erro)[:200])
        _marcar(False)
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
