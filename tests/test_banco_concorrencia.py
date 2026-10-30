"""Conexão SQLite compartilhada entre threads (Francielle, 30/10/2026: tarefas 133 e 134).

Antes: "cannot start a transaction within a transaction" e o rollback de uma thread desfazia o INSERT de outra
("Trabalho do Max não encontrado"). Banco temporário (tests/conftest.py).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_banco_concorrencia.py
"""

import threading
import time

import tarefas  # banco temporário: tests/conftest.py

THREADS, VOLTAS = 8, 60


def test_transacoes_paralelas_nao_se_atrapalham():
    db = tarefas._db()
    db.execute("CREATE TABLE IF NOT EXISTS teste_concorrencia (id INTEGER PRIMARY KEY, quem TEXT, tipo TEXT)")
    erros: list[Exception] = []

    def trabalhar(n: int):
        for i in range(VOLTAS):
            try:
                with db:  # bloco que dá certo
                    db.execute("INSERT INTO teste_concorrencia (quem, tipo) VALUES (?, 'bloco')", (f"{n}-{i}",))
                    time.sleep(0.0005)  # outra thread entra no meio, como no sistema real
                db.execute("INSERT INTO teste_concorrencia (quem, tipo) VALUES (?, 'avulso')", (f"{n}-{i}",))  # sem bloco
                try:
                    with db:  # bloco que falha: só ele é desfeito
                        db.execute("INSERT INTO teste_concorrencia (quem, tipo) VALUES (?, 'desfeito')", (f"{n}-{i}",))
                        time.sleep(0.0005)
                        raise ValueError("falha proposital")
                except ValueError:
                    pass
            except Exception as erro:  # noqa: BLE001
                erros.append(erro)

    linhas = [threading.Thread(target=trabalhar, args=(n,)) for n in range(THREADS)]
    for t in linhas:
        t.start()
    for t in linhas:
        t.join()

    assert not erros, erros[:3]
    contagem = dict(db.execute("SELECT tipo, COUNT(*) FROM teste_concorrencia GROUP BY tipo").fetchall())
    assert contagem.get("bloco") == THREADS * VOLTAS
    assert contagem.get("avulso") == THREADS * VOLTAS  # nenhum INSERT de outra thread foi desfeito
    assert "desfeito" not in contagem
    assert not db.in_transaction  # escrita avulsa grava na hora
