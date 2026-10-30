"""Banco perdido volta da cópia e a cópia boa nunca é trocada por um banco vazio (revisão de 30/10/2026, item 1.5).
Tudo em pastas temporárias: o banco dos testes (tests/conftest.py) e o de produção não são tocados.
"""

import sqlite3

import pytest

import config
import saude
import tarefas


def _banco(arquivo, tarefas_n: int) -> None:
    conexao = sqlite3.connect(arquivo)
    conexao.execute("CREATE TABLE tarefas (id INTEGER PRIMARY KEY, texto TEXT)")
    conexao.executemany("INSERT INTO tarefas (texto) VALUES (?)", [(f"t{n}",) for n in range(tarefas_n)])
    conexao.commit()
    conexao.close()


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    volume, dados = tmp_path / "volume", tmp_path / "dados"
    volume.mkdir()
    dados.mkdir()
    monkeypatch.setattr(config, "ARQUIVO_BANCO", volume / "escritorio.db")
    monkeypatch.setattr(config, "DADOS_DIR", dados)
    monkeypatch.setattr(config, "ARQUIVO_COPIA_BANCO", dados / "escritorio.copia.db")
    return volume, dados


def test_volume_perdido_volta_da_copia(pastas):
    volume, dados = pastas
    _banco(dados / "escritorio.copia.db", 126)
    tarefas._restaurar_da_copia()
    conexao = sqlite3.connect(volume / "escritorio.db")
    assert conexao.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 126
    conexao.close()


def test_copia_estragada_recusa_subir_vazio(pastas):
    _volume, dados = pastas
    (dados / "escritorio.copia.db").write_bytes(b"isto nao e um banco sqlite" * 100)
    with pytest.raises(tarefas.BancoAusente):
        tarefas._restaurar_da_copia()


def test_primeira_instalacao_sobe_vazio(pastas):
    tarefas._restaurar_da_copia()  # sem cópia nenhuma: nada a restaurar, sem erro
    assert not (pastas[0] / "escritorio.db").exists()


def test_copia_boa_nao_e_trocada_por_banco_menor(pastas, monkeypatch):
    volume, dados = pastas
    _banco(dados / "escritorio.copia.db", 126)
    _banco(volume / "escritorio.db", 0)  # banco recriado vazio
    vazio = sqlite3.connect(volume / "escritorio.db")
    monkeypatch.setattr(tarefas, "_db", lambda: vazio)
    with pytest.raises(RuntimeError, match="menos tarefas"):
        tarefas.copiar_para_backup()
    vazio.close()
    conexao = sqlite3.connect(dados / "escritorio.copia.db")
    assert conexao.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 126
    conexao.close()


def test_copia_nova_guarda_a_anterior(pastas, monkeypatch):
    volume, dados = pastas
    _banco(dados / "escritorio.copia.db", 3)
    _banco(volume / "escritorio.db", 5)
    banco = sqlite3.connect(volume / "escritorio.db")
    monkeypatch.setattr(tarefas, "_db", lambda: banco)
    tarefas.copiar_para_backup()
    banco.close()
    assert (dados / "escritorio.copia.db.anterior").exists()
    conexao = sqlite3.connect(dados / "escritorio.copia.db")
    assert conexao.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 5
    conexao.close()


def test_aviso_de_backup_atrasado(tmp_path, monkeypatch):
    log = tmp_path / "backup.log"
    monkeypatch.setattr(config, "ARQUIVO_LOG_BACKUP", log)
    assert "não encontrado" in saude.aviso_backup()
    log.write_text("[2026-10-01 02:30:03] Backup ok: x.zip (100 KB)\n[2026-10-02 02:30:03] Backup FALHOU: erro\n",
                   encoding="utf-8")
    aviso = saude.aviso_backup()
    assert "01/10" in aviso and "1 tentativa" in aviso
    from datetime import datetime

    log.write_text(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Backup ok: x.zip (100 KB)\n", encoding="utf-8")
    assert saude.aviso_backup() is None


def test_avisos_da_operacao(monkeypatch, tmp_path):
    import max_texto

    monkeypatch.setattr(config, "ARQUIVO_LOG_BACKUP", tmp_path / "backup.log")
    monkeypatch.setattr(max_texto, "ARQUIVO_CONTATO", tmp_path / "max.contato")  # trabalhador nunca respondeu
    monkeypatch.setattr(saude, "ollama_ok", lambda: False)
    monkeypatch.setattr(config, "MODELOS_GRATUITOS", ["openrouter/a:free"])
    avisos = " | ".join(saude.avisos_da_operacao())
    assert "Trabalhador do Max nunca respondeu" in avisos and "Ollama fora do ar" in avisos
    assert "backup" in avisos.lower() and "gratuito" in avisos
    assert saude.banco_ok()


def test_lista_de_gratuitos_muda_sem_reiniciar(tmp_path, monkeypatch):
    arquivo = tmp_path / "modelos_gratuitos.json"
    monkeypatch.setattr(config, "ARQUIVO_MODELOS_GRATUITOS", arquivo)
    assert config.modelos_gratuitos() == config.MODELOS_GRATUITOS  # sem arquivo: a lista do código
    arquivo.write_text('["groq/novo", "openrouter/outro:free"]', encoding="utf-8")
    assert config.modelos_gratuitos() == ["groq/novo", "openrouter/outro:free"]
    arquivo.write_text("isto não é json", encoding="utf-8")
    import os
    os.utime(arquivo, (1, 1))  # força a releitura
    assert config.modelos_gratuitos() == config.MODELOS_GRATUITOS  # arquivo quebrado: volta para a do código
