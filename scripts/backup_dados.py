"""Backup diário de backend/dados (banco, usuários, manuais, Cérebro, projetos, anexos) num .zip no Drive pessoal.

O banco SQLite é copiado pela API de backup do próprio SQLite (cópia consistente mesmo com o sistema rodando).
Senhas, tokens e o .env não entram abertos: vão criptografados em segredos.cripto (scripts/segredos_backup.py),
quando a chave pública já foi gerada. Ficam de fora os logs. Mantém os últimos 7 backups.

Uso: pythonw scripts/backup_dados.py   (tarefa agendada do Windows, todo dia às 02:30)
"""

import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import segredos_backup

DADOS = Path(__file__).resolve().parents[1] / "backend" / "dados"
DESTINO = Path(os.getenv("ESCRITORIO_BACKUP", r"G:\Meu Drive\Backups Escritório Veraneio"))
MANTER = 7
# Segredos não vão para o Drive pessoal sem criptografia (revisão de 30/10/2026, 2.32): tokens de login (YouTube,
# Monday) e as senhas dos usuários. Entram só criptografados (segredos.cripto), com o .env do projeto.
FORA = {"operador.token", "usuarios.json"}
FORA_SE_NOME_TEM = ("token", "segredo", "secret", "credential", ".env")
EXTENSOES_FORA = {".log", ".1", ".pyc"}
LOG = DADOS / "backup.log"
ENV_PROJETO = DADOS.parents[1] / ".env"


def registrar(texto: str) -> None:
    with LOG.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {texto}\n")


def fazer_backup() -> Path:
    DESTINO.mkdir(parents=True, exist_ok=True)
    final = DESTINO / f"escritorio-dados-{datetime.now():%Y-%m-%d}.zip"
    parcial = final.with_suffix(".zip.parcial")  # o Drive só sincroniza o arquivo pronto
    with tempfile.TemporaryDirectory() as temporaria:
        copia_banco = Path(temporaria) / "escritorio.db"
        # O banco vive num volume do Docker; a API deixa uma cópia consistente em dados/ a cada 6 h.
        fonte = DADOS / "escritorio.copia.db"
        if not fonte.exists():  # sistema antigo (banco ainda em dados/)
            fonte = DADOS / "escritorio.db"
        if not fonte.exists():  # antes, o sqlite criava um banco vazio aqui e o backup registrava "ok"
            raise FileNotFoundError(f"Cópia do banco não encontrada em {DADOS}")
        # Só leitura: o backup nunca altera nem cria a fonte.
        origem, destino = sqlite3.connect(f"{fonte.as_uri()}?mode=ro", uri=True), sqlite3.connect(copia_banco)
        try:
            origem.backup(destino)
            if destino.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("cópia do banco estragada (integrity_check)")
            if not destino.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]:
                raise RuntimeError("cópia do banco sem nenhuma tarefa (banco recriado vazio?)")
        finally:  # `with` não fecha a conexão; no Windows o arquivo ficaria preso
            origem.close()
            destino.close()
        segredos = {}
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as pacote:
            pacote.write(copia_banco, "escritorio.db")
            for arquivo in sorted(DADOS.rglob("*")):
                relativo = arquivo.relative_to(DADOS)
                if (not arquivo.is_file() or arquivo.suffix in EXTENSOES_FORA or arquivo.name.startswith("escritorio.")
                        or relativo.parts[0] in ("__pycache__", "segredos_restaurados")):
                    continue
                if arquivo.name in FORA or any(p in arquivo.name.lower() for p in FORA_SE_NOME_TEM):
                    segredos[f"backend/dados/{relativo.as_posix()}"] = arquivo.read_bytes()
                    continue
                pacote.write(arquivo, relativo.as_posix())
            if ENV_PROJETO.exists():
                segredos[".env"] = ENV_PROJETO.read_bytes()
            if segredos_backup.CHAVE_PUBLICA.exists():
                pacote.writestr(segredos_backup.ARQUIVO_NO_ZIP,
                                segredos_backup.trancar(segredos, segredos_backup.CHAVE_PUBLICA.read_bytes()))
            else:
                registrar("Segredos fora deste backup: falta gerar a chave (python scripts/segredos_backup.py "
                          "gerar-chave).")
    parcial.replace(final)
    for antigo in sorted(DESTINO.glob("escritorio-dados-*.zip"))[:-MANTER]:
        antigo.unlink()
    return final


if __name__ == "__main__":
    try:
        caminho = fazer_backup()
        registrar(f"Backup ok: {caminho} ({caminho.stat().st_size // 1024} KB)")
    except Exception as erro:
        registrar(f"Backup FALHOU: {erro!r}")
        raise
