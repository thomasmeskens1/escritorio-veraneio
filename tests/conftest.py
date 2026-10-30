"""Todos os testes usam um banco temporário, nunca o de produção.

O pytest carrega este arquivo antes de qualquer teste. Antes dele, o primeiro teste a importar `config` fixava o
caminho do banco do contêiner (volume de produção) e os testes seguintes gravavam lá (30/10/2026: tarefas, trechos
do Cérebro e observações de teste apareceram na produção e foram removidos).
"""

import os
import sys
import tempfile
from pathlib import Path

assert "config" not in sys.modules, "config importado antes do conftest: o banco de teste não seria isolado"

_PASTA = Path(tempfile.mkdtemp(prefix="escritorio-testes-"))
(_PASTA / "teste.db").touch()  # já existe: o banco antigo de dados/ nunca é migrado para cá
os.environ["ARQUIVO_BANCO"] = str(_PASTA / "teste.db")

import config  # noqa: E402

assert config.ARQUIVO_BANCO == _PASTA / "teste.db", config.ARQUIVO_BANCO
