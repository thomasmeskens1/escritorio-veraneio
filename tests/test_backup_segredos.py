"""Segredos do backup diário: trancados com a chave pública, abertos só com a privada e a frase (30/10/2026).
Roda quando scripts/ está montado em /repo/scripts (ver tests/test_max_resiliencia.py)."""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path("/repo/scripts")
pytestmark = pytest.mark.skipif(not (SCRIPTS / "segredos_backup.py").exists(), reason="scripts/ não montado")


@pytest.fixture(scope="module")
def cofre():
    sys.path.insert(0, str(SCRIPTS))
    import segredos_backup

    return segredos_backup


def test_tranca_e_abre_com_a_frase(cofre):
    publica, privada = cofre.gerar_chaves("quatro palavras soltas aqui")
    arquivos = {"backend/dados/usuarios.json": b'{"a": 1}', ".env": b"CHAVE=x\n"}
    trancado = cofre.trancar(arquivos, publica)
    assert b"CHAVE=x" not in trancado and b"usuarios" not in trancado
    assert cofre.abrir(trancado, privada, "quatro palavras soltas aqui") == arquivos


def test_frase_errada_nao_abre(cofre):
    publica, privada = cofre.gerar_chaves("quatro palavras soltas aqui")
    trancado = cofre.trancar({"x": b"y"}, publica)
    with pytest.raises(ValueError):
        cofre.abrir(trancado, privada, "outra frase qualquer longa")


def test_arquivo_alterado_nao_abre(cofre):
    from cryptography.exceptions import InvalidTag

    publica, privada = cofre.gerar_chaves("quatro palavras soltas aqui")
    trancado = bytearray(cofre.trancar({"x": b"y"}, publica))
    trancado[-1] ^= 1
    with pytest.raises((ValueError, InvalidTag)):
        cofre.abrir(bytes(trancado), privada, "quatro palavras soltas aqui")
