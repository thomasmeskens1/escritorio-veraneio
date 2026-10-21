"""Backup diário de backend/dados (banco, usuários, manuais, Cérebro, projetos, anexos) num .zip no Drive pessoal.

O banco SQLite é copiado pela API de backup do próprio SQLite (cópia consistente mesmo com o sistema rodando).
Fica de fora o token do operador e os logs. Mantém os últimos 7 backups.

Uso: pythonw scripts/backup_dados.py   (tarefa agendada do Windows, todo dia às 02:30)
"""

import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

DADOS = Path(__file__).resolve().parents[1] / "backend" / "dados"
DESTINO = Path(os.getenv("ESCRITORIO_BACKUP", r"G:\Meu Drive\Backups Escritório Veraneio"))
MANTER = 7
FORA = {"operador.token"}
EXTENSOES_FORA = {".log", ".1", ".pyc"}
LOG = DADOS / "backup.log"


def registrar(texto: str) -> None:
    with LOG.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {texto}\n")


def fazer_backup() -> Path:
    DESTINO.mkdir(parents=True, exist_ok=True)
    final = DESTINO / f"escritorio-dados-{datetime.now():%Y-%m-%d}.zip"
    parcial = final.with_suffix(".zip.parcial")  # o Drive só sincroniza o arquivo pronto
    with tempfile.TemporaryDirectory() as temporaria:
        copia_banco = Path(temporaria) / "escritorio.db"
        origem, destino = sqlite3.connect(DADOS / "escritorio.db"), sqlite3.connect(copia_banco)
        try:
            origem.backup(destino)
        finally:  # `with` não fecha a conexão; no Windows o arquivo ficaria preso
            origem.close()
            destino.close()
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as pacote:
            pacote.write(copia_banco, "escritorio.db")
            for arquivo in sorted(DADOS.rglob("*")):
                relativo = arquivo.relative_to(DADOS)
                if (not arquivo.is_file() or arquivo.name in FORA or arquivo.suffix in EXTENSOES_FORA
                        or relativo.parts[0] == "__pycache__" or arquivo.name.startswith("escritorio.db")):
                    continue
                pacote.write(arquivo, relativo.as_posix())
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
