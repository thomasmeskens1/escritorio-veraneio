"""Restaura o banco do escritório a partir de um backup (revisão de 30/10/2026, item 1.5: não havia como voltar).

Uso (no PC, na pasta do projeto):
  python scripts/restaurar_banco.py                       # só confere o backup mais recente do Drive (nada muda)
  python scripts/restaurar_banco.py caminho/backup.zip    # confere esse backup (zip do Drive ou arquivo .db)
  python scripts/restaurar_banco.py [backup] --confirmar  # restaura: para a API, troca o banco e sobe de novo

Como funciona a restauração: o banco escolhido vira backend/dados/escritorio.copia.db (a atual fica como
.substituida), o banco do volume do Docker é apagado e a API sobe; na subida ela restaura sozinha da cópia
(tarefas._restaurar_da_copia). Tudo o que entrou no sistema depois do backup se perde.
"""

import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "backend" / "dados"
COPIA = DADOS / "escritorio.copia.db"
BACKUPS = Path(r"G:\Meu Drive\Backups Escritório Veraneio")
BANCO_NO_VOLUME = "/var/lib/escritorio/escritorio.db"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def conferir(banco: Path) -> int:
    """Total de tarefas do banco; levanta erro se ele estiver estragado ou vazio."""
    conexao = sqlite3.connect(f"{banco.resolve().as_uri()}?mode=ro", uri=True)
    try:
        if conexao.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"{banco.name} está estragado (integrity_check)")
        total = conexao.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]
    finally:
        conexao.close()
    if not total:
        raise RuntimeError(f"{banco.name} não tem nenhuma tarefa")
    return total


def extrair(origem: Path, pasta: Path) -> Path:
    if origem.suffix.lower() == ".db":
        return origem
    with zipfile.ZipFile(origem) as pacote:
        pacote.extract("escritorio.db", pasta)
    return pasta / "escritorio.db"


def docker(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=RAIZ, check=True, creationflags=SEM_JANELA)


def main() -> None:
    argumentos = [a for a in sys.argv[1:] if a != "--confirmar"]
    if argumentos:
        origem = Path(argumentos[0])
    else:
        zips = sorted(BACKUPS.glob("escritorio-dados-*.zip"))
        if not zips:
            sys.exit(f"Nenhum backup em {BACKUPS}.")
        origem = zips[-1]
    with tempfile.TemporaryDirectory() as temporaria:
        banco = extrair(origem, Path(temporaria))
        total = conferir(banco)
        print(f"Backup {origem.name}: íntegro, {total} tarefas.")
        if "--confirmar" not in sys.argv:
            print("Nada foi alterado. Para restaurar, rode de novo com --confirmar.")
            return
        docker("stop", "api")
        if COPIA.exists():
            COPIA.replace(COPIA.with_suffix(".db.substituida"))
        shutil.copy2(banco, COPIA)
        docker("run", "--rm", "--no-deps", "-T", "--entrypoint", "sh", "api", "-c",
               f"rm -f {BANCO_NO_VOLUME} {BANCO_NO_VOLUME}-wal {BANCO_NO_VOLUME}-shm")
        docker("start", "api")
    print("Restaurado: a API subiu e trouxe o banco da cópia. Confira o escritório no navegador.")


if __name__ == "__main__":
    main()
