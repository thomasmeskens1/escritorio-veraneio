"""Catálogo do acervo de fotos e vídeos dos lodges (Drive, SOMENTE LEITURA) para o Cérebro.

Percorre só as pastas "Lodges N-M" do acervo; dentro delas, uma pasta por lodge. Para cada lodge gera um
documento (contagem de fotos/vídeos, extensões, até 40 nomes de arquivo) e envia ao Cérebro apenas o que
mudou desde o último envio (hash local em backend/dados/). Grava o índice em CÉREBRO/catalogo_lodges.md.
Nunca grava nada no acervo.

Uso avulso: python scripts/max/catalogo_lodges.py
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

import comum
from comum import log

PADRAO_FAIXA = re.compile(r"^\s*lodges\s*(\d+)\s*-\s*(\d+)\s*$", re.IGNORECASE)
PADRAO_NUMERO = re.compile(r"lodge\s*(\d+)", re.IGNORECASE)
FOTOS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp", ".dng",
         ".raw", ".cr2", ".cr3", ".nef", ".arw"}
VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".mts", ".m2ts", ".3gp", ".webm"}
IGNORAR = {"desktop.ini", "thumbs.db", ".ds_store"}
MAX_NOMES = 40
ARQUIVO_HASHES = comum.DADOS / "catalogo_lodges.hashes.json"
INDICE = comum.CEREBRO / "catalogo_lodges.md"


def pastas_de_faixa(acervo: Path) -> list[tuple[Path, int, int]]:
    """Só as subpastas "Lodges N-M" (ignora CV COLLECTION, planilhas soltas etc.), em ordem numérica."""
    faixas = []
    for item in acervo.iterdir():
        if item.is_dir() and (casamento := PADRAO_FAIXA.match(item.name)):
            faixas.append((item, int(casamento.group(1)), int(casamento.group(2))))
    return sorted(faixas, key=lambda f: (f[1], f[2]))


def catalogar_lodge(pasta: Path, faixa: Path) -> dict:
    """Só leitura: os.walk + nomes/extensões, sem abrir os arquivos."""
    fotos = videos = outros = 0
    extensoes: dict[str, int] = {}
    nomes: list[str] = []
    for raiz, dirs, arquivos in os.walk(pasta, onerror=lambda _: None):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for nome in sorted(arquivos):
            if nome.lower() in IGNORAR or nome.startswith(("~$", ".")):
                continue
            extensao = Path(nome).suffix.lower() or "(sem extensão)"
            extensoes[extensao] = extensoes.get(extensao, 0) + 1
            if extensao in FOTOS:
                fotos += 1
            elif extensao in VIDEOS:
                videos += 1
            else:
                outros += 1
            if len(nomes) < MAX_NOMES:
                nomes.append(Path(raiz, nome).relative_to(pasta).as_posix())
    numero = PADRAO_NUMERO.search(pasta.name)
    return {
        "lodge": pasta.name.strip(), "numero": int(numero.group(1)) if numero else None,
        "faixa": faixa.name.strip(), "caminho": str(pasta), "fotos": fotos, "videos": videos, "outros": outros,
        "extensoes": dict(sorted(extensoes.items(), key=lambda e: (-e[1], e[0]))),
        "subpastas": sorted(d.name for d in pasta.iterdir() if d.is_dir()), "arquivos": nomes,
    }


def catalogar(acervo: Path) -> list[dict]:
    entradas = []
    for faixa, _, _ in pastas_de_faixa(acervo):
        for pasta in sorted((p for p in faixa.iterdir() if p.is_dir()), key=_ordem_lodge):
            entradas.append(catalogar_lodge(pasta, faixa))
    return entradas


def _ordem_lodge(pasta: Path):
    numero = PADRAO_NUMERO.search(pasta.name)
    return (int(numero.group(1)) if numero else 10**6, pasta.name.lower())


def documento(entrada: dict) -> dict:
    extensoes = ", ".join(f"{e} ({n})" for e, n in entrada["extensoes"].items()) or "nenhuma"
    linhas = [
        f"# {entrada['lodge']} — acervo de fotos e vídeos",
        f"Faixa: {entrada['faixa']}" + (f" | Número do lodge: {entrada['numero']}" if entrada["numero"] else ""),
        f"Caminho no Drive (somente leitura): {entrada['caminho']}",
        f"Fotos: {entrada['fotos']} | Vídeos: {entrada['videos']} | Outros arquivos: {entrada['outros']}",
        f"Extensões: {extensoes}",
        f"Subpastas: {', '.join(entrada['subpastas']) or 'nenhuma'}",
        f"Arquivos (até {MAX_NOMES}):",
        *(f"- {nome}" for nome in entrada["arquivos"]),
    ]
    return {"fonte_tipo": "drive", "fonte_ref": f"drive/lodges/{entrada['faixa']}/{entrada['lodge']}",
            "titulo": f"Acervo de fotos e vídeos — {entrada['lodge']}", "conteudo": "\n".join(linhas)}


def indice(entradas: list[dict]) -> str:
    linhas = ["# Catálogo do acervo de fotos e vídeos dos lodges", "",
              f"Fonte (somente leitura): {comum.ACERVO}", f"Lodges catalogados: {len(entradas)}", "",
              "| Faixa | Lodge | Fotos | Vídeos | Outros | Caminho |", "|---|---|---:|---:|---:|---|"]
    linhas += [f"| {e['faixa']} | {e['lodge']} | {e['fotos']} | {e['videos']} | {e['outros']} | {e['caminho']} |"
               for e in entradas]
    return "\n".join(linhas) + "\n"


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sincronizar(acervo: Path = comum.ACERVO, arquivo_indice: Path = INDICE,
                arquivo_hashes: Path = ARQUIVO_HASHES, enviar=comum.enviar_ao_cerebro) -> dict:
    """Cataloga, grava o índice (se mudou) e envia ao Cérebro só os lodges novos/alterados."""
    if not acervo.is_dir():
        raise RuntimeError(f"Acervo não encontrado: {acervo}")
    entradas = catalogar(acervo)
    try:
        hashes = json.loads(arquivo_hashes.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hashes = {}

    corpo = indice(entradas)
    indice_gravado = False
    if hashes.get("__indice__") != _hash(corpo) or not arquivo_indice.exists():
        arquivo_indice.parent.mkdir(parents=True, exist_ok=True)
        arquivo_indice.write_text(corpo + f"\n_Atualizado em {datetime.now():%Y-%m-%d %H:%M}._\n", encoding="utf-8")
        hashes["__indice__"] = _hash(corpo)
        indice_gravado = True

    documentos = [documento(e) for e in entradas]
    mudados = [d for d in documentos if hashes.get(d["fonte_ref"]) != _hash(d["conteudo"])]
    enviados = 0
    if mudados and enviar(mudados):
        for d in mudados:
            hashes[d["fonte_ref"]] = _hash(d["conteudo"])
        enviados = len(mudados)
    arquivo_hashes.parent.mkdir(parents=True, exist_ok=True)
    arquivo_hashes.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"lodges": len(entradas), "mudados": len(mudados), "enviados": enviados, "indice_gravado": indice_gravado,
            "fotos": sum(e["fotos"] for e in entradas), "videos": sum(e["videos"] for e in entradas)}


def rodar() -> None:
    """Versão tolerante a erros para o laço do trabalhador."""
    log("Catálogo dos lodges: lendo o acervo (somente leitura)...")
    try:
        r = sincronizar()
        log(f"Catálogo dos lodges: {r['lodges']} lodges, {r['fotos']} fotos, {r['videos']} vídeos; "
            f"{r['mudados']} alterado(s), {r['enviados']} enviado(s) ao Cérebro.")
    except Exception as erro:
        log(f"Catálogo dos lodges falhou: {erro}")


if __name__ == "__main__":
    rodar()
