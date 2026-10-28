"""Link da pasta de entrega no Google Drive (botão "Visualizar" do chat), a partir do Drive para desktop.

O Drive para desktop guarda o ID de nuvem de cada item no banco local (metadata_sqlite_db, só LEITURA aqui). A pasta
é achada pelo nome e conferida pela cadeia de pastas-mãe (ex.: ESCRITÓRIO VERANEIO > MARKETING > pasta), para não
confundir pastas homônimas. Pasta recém-criada ainda sem ID de nuvem: espera a sincronização por alguns segundos.
"""

import glob
import os
import sqlite3
import time
from pathlib import Path

ESPERA_S = 90       # tempo máximo esperando a pasta nova ganhar ID de nuvem
INTERVALO_S = 10


def _banco() -> str | None:
    achados = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS", "*", "metadata_sqlite_db"))
    return achados[0] if achados else None


def _id_da_pasta(partes: list[str]) -> str | None:
    """ID de nuvem da última pasta de `partes` (nomes do topo até ela), conferindo as pastas-mãe."""
    caminho = _banco()
    if not caminho:
        return None
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=5)
    conexao.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        candidatos = conexao.execute("SELECT stable_id, id FROM items WHERE is_folder = 1 AND trashed = 0 AND "
                                     "local_title = ?", (partes[-1],)).fetchall()
        for stable_id, nuvem in candidatos:
            atual, confere = stable_id, True
            for esperado in reversed(partes[:-1]):
                pai = conexao.execute("SELECT parent_stable_id FROM stable_parents WHERE item_stable_id = ?",
                                      (atual,)).fetchone()
                titulo = pai and conexao.execute("SELECT local_title FROM items WHERE stable_id = ?",
                                                 (pai[0],)).fetchone()
                if not titulo or titulo[0] != esperado:
                    confere = False
                    break
                atual = pai[0]
            if confere and nuvem and not nuvem.startswith("local"):
                return nuvem
    finally:
        conexao.close()
    return None


def link_da_pasta(pasta: Path, raiz: Path) -> str:
    """URL da pasta no Drive ("" se não achar). `raiz` = pasta do Escritório; a conferência sobe até ela."""
    try:
        partes = [raiz.name, *pasta.relative_to(raiz).parts]
    except ValueError:
        return ""
    fim = time.monotonic() + ESPERA_S
    while True:
        try:
            if (nuvem := _id_da_pasta(partes)):
                return f"https://drive.google.com/drive/folders/{nuvem}"
        except sqlite3.Error:
            pass  # banco ocupado pelo Drive: tenta de novo
        if time.monotonic() >= fim:
            return ""
        time.sleep(INTERVALO_S)
