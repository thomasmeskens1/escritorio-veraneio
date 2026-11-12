"""Material do MARKETING da Casa Veraneio para artes, vídeos e o Cérebro (Thomas, 12/11/2026). SOMENTE LEITURA.

Duas pastas do Drive (NOVO) CASA VERANEIO > MARKETING passam a valer como fonte da Casa Veraneio, além do acervo
"Lodges N-M" (catalogo_lodges.py):
- LODGES: fotos e vídeos por categoria ("LODGES PRAIA", "LODGES CAMPO"...) > pasta do Lodge. A categoria vira
  informação para o Cérebro (o Lodge 112 é de praia). "FORA DO PORTIFOLIO" e Orlando ficam de fora (Orlando não
  entra na busca: memória empresas-do-grupo).
- SABORES CV: a série de gastronomia (ano > episódio: chef, receita, data especial) e o logo animado da série.

Gera um documento por pasta para o Cérebro (só o que mudou, hash em backend/dados/) e o índice
CÉREBRO/catalogo_marketing.md, que o trabalhador copia para a pasta da peça. Nunca grava nada nessas pastas.

Uso avulso: python scripts/max/acervo_marketing.py
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import comum
from catalogo_lodges import MAX_NOMES, PADRAO_NUMERO, catalogar_lodge
from comum import log

LODGES = comum.MARKETING / "LODGES"
SABORES = comum.MARKETING / "SABORES CV"
FORA = re.compile(r"fora\s+do\s+portif|orlando", re.IGNORECASE)
CATEGORIA = re.compile(r"^\s*lodges\s+(.+?)\s*$", re.IGNORECASE)
ARQUIVO_HASHES = comum.DADOS / "acervo_marketing.hashes.json"
INDICE = comum.CEREBRO / "catalogo_marketing.md"


def _categoria(pasta: Path) -> str:
    """'LODGES PRAIA' -> 'Praia'; outras pastas (Novos Lodges, captações) -> o nome dela."""
    casamento = CATEGORIA.match(pasta.name)
    return casamento.group(1).strip().capitalize() if casamento else pasta.name.strip()


def _pastas(raiz: Path) -> list[Path]:
    return sorted((p for p in raiz.iterdir() if p.is_dir() and not FORA.search(p.name)), key=lambda p: p.name.lower())


def catalogar_lodges(raiz: Path = LODGES) -> list[dict]:
    """Uma entrada por pasta de Lodge dentro de cada categoria; pasta solta na raiz (ex.: "LODGE 35") vale sozinha."""
    entradas = []
    for pasta in _pastas(raiz):
        filhos = _pastas(pasta)
        if PADRAO_NUMERO.search(pasta.name) or not filhos:
            entrada = catalogar_lodge(pasta, raiz)
            entrada["categoria"] = ""
            entradas.append(entrada)
            continue
        for filho in filhos:
            entrada = catalogar_lodge(filho, pasta)
            entrada["categoria"] = _categoria(pasta)
            entradas.append(entrada)
    return entradas


def catalogar_sabores(raiz: Path = SABORES) -> list[dict]:
    """Uma entrada por episódio (ano > episódio); o logo animado e pastas sem ano entram como estão."""
    entradas = []
    for pasta in _pastas(raiz):
        episodios = _pastas(pasta) if re.fullmatch(r"\d{4}", pasta.name.strip()) else []
        for episodio in episodios or [pasta]:
            entrada = catalogar_lodge(episodio, pasta)
            entrada["ano"] = pasta.name.strip() if episodios else ""
            entradas.append(entrada)
    return entradas


def _comum(entrada: dict) -> list[str]:
    extensoes = ", ".join(f"{e} ({n})" for e, n in entrada["extensoes"].items()) or "nenhuma"
    return [f"Caminho no Drive (somente leitura): {entrada['caminho']}",
            f"Fotos: {entrada['fotos']} | Vídeos: {entrada['videos']} | Outros arquivos: {entrada['outros']}",
            f"Extensões: {extensoes}", f"Subpastas: {', '.join(entrada['subpastas']) or 'nenhuma'}",
            f"Arquivos (até {MAX_NOMES}):", *(f"- {nome}" for nome in entrada["arquivos"])]


def documento_lodge(e: dict) -> dict:
    cabeca = [f"# {e['lodge']} — material do Marketing da Casa Veraneio",
              f"Categoria: {e['categoria']}" if e["categoria"] else "Categoria: (sem categoria na pasta)",
              f"Número do lodge: {e['numero']}" if e["numero"] else "",
              "Use para artes e vídeos da Casa Veraneio (fotos e vídeos reais, editados pelo Marketing)."]
    return {"fonte_tipo": "drive", "fonte_ref": f"drive/marketing/lodges/{e['faixa']}/{e['lodge']}",
            "titulo": f"Material do Marketing — {e['lodge']}" + (f" ({e['categoria']})" if e["categoria"] else ""),
            "conteudo": "\n".join(l for l in cabeca + _comum(e) if l)}


def documento_sabores(e: dict) -> dict:
    cabeca = [f"# Sabores CV — {e['lodge']}" + (f" ({e['ano']})" if e["ano"] else ""),
              "Sabores CV é a série de gastronomia da Casa Veraneio (chefs, receitas e datas especiais). Material "
              "real para artes e vídeos de cardápio, compras, cozinheira e experiência à mesa da Casa Veraneio."]
    return {"fonte_tipo": "drive", "fonte_ref": f"drive/marketing/sabores/{e['faixa']}/{e['lodge']}",
            "titulo": f"Sabores CV — {e['lodge']}" + (f" ({e['ano']})" if e["ano"] else ""),
            "conteudo": "\n".join(cabeca + _comum(e))}


def indice(lodges: list[dict], sabores: list[dict]) -> str:
    linhas = ["# Material do Marketing da Casa Veraneio (somente leitura)", "",
              "Fonte para artes, vídeos e o Cérebro da Casa Veraneio, além do acervo \"Lodges N-M\" "
              "(catalogo_lodges.md). Nunca grave, mova ou renomeie nada aqui.", "",
              f"## LODGES por categoria ({LODGES})", "",
              "| Categoria | Lodge | Fotos | Vídeos | Caminho |", "|---|---|---:|---:|---|"]
    linhas += [f"| {e['categoria'] or '-'} | {e['lodge']} | {e['fotos']} | {e['videos']} | {e['caminho']} |"
               for e in lodges]
    linhas += ["", f"## SABORES CV, série de gastronomia ({SABORES})", "",
               "| Ano | Episódio | Fotos | Vídeos | Caminho |", "|---|---|---:|---:|---|"]
    linhas += [f"| {e['ano'] or '-'} | {e['lodge']} | {e['fotos']} | {e['videos']} | {e['caminho']} |"
               for e in sabores]
    return "\n".join(linhas) + "\n"


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sincronizar(lodges_raiz: Path = LODGES, sabores_raiz: Path = SABORES, arquivo_indice: Path = INDICE,
                arquivo_hashes: Path = ARQUIVO_HASHES, enviar=comum.enviar_ao_cerebro) -> dict:
    """Cataloga as duas pastas, grava o índice (se mudou) e envia ao Cérebro só as pastas novas ou alteradas."""
    lodges = catalogar_lodges(lodges_raiz) if lodges_raiz.is_dir() else []
    sabores = catalogar_sabores(sabores_raiz) if sabores_raiz.is_dir() else []
    if not lodges and not sabores:
        raise RuntimeError(f"Pastas do Marketing não encontradas: {lodges_raiz} / {sabores_raiz}")
    try:
        hashes = json.loads(arquivo_hashes.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hashes = {}
    corpo = indice(lodges, sabores)
    if hashes.get("__indice__") != _hash(corpo) or not arquivo_indice.exists():
        arquivo_indice.parent.mkdir(parents=True, exist_ok=True)
        arquivo_indice.write_text(corpo + f"\n_Atualizado em {datetime.now():%Y-%m-%d %H:%M}._\n", encoding="utf-8")
        hashes["__indice__"] = _hash(corpo)
    documentos = [documento_lodge(e) for e in lodges] + [documento_sabores(e) for e in sabores]
    mudados = [d for d in documentos if hashes.get(d["fonte_ref"]) != _hash(d["conteudo"])]
    enviados = 0
    for inicio in range(0, len(mudados), comum.LOTE_CEREBRO):  # lotes: o Cérebro calcula embeddings na hora
        lote = mudados[inicio:inicio + comum.LOTE_CEREBRO]
        if enviar(lote):
            for d in lote:
                hashes[d["fonte_ref"]] = _hash(d["conteudo"])
            enviados += len(lote)
    arquivo_hashes.parent.mkdir(parents=True, exist_ok=True)
    arquivo_hashes.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"lodges": len(lodges), "sabores": len(sabores), "mudados": len(mudados), "enviados": enviados}


def pastas_do_lodge(numero: int, raiz: Path = LODGES) -> list[Path]:
    """Pastas do Lodge `numero` no material do Marketing (uma listagem por categoria, sem descer nos arquivos)."""
    if not raiz.is_dir():
        return []
    achadas = []
    for pasta in _pastas(raiz):
        for candidata in [pasta, *(_pastas(pasta) if not PADRAO_NUMERO.search(pasta.name) else [])]:
            casamento = PADRAO_NUMERO.search(candidata.name)
            if casamento and int(casamento.group(1)) == numero:
                achadas.append(candidata)
    return achadas


def rodar() -> None:
    """Versão tolerante a erros para o laço do trabalhador."""
    log("Material do Marketing (LODGES e SABORES CV): lendo (somente leitura)...")
    try:
        r = sincronizar()
        log(f"Material do Marketing: {r['lodges']} pasta(s) de Lodge, {r['sabores']} episódio(s) do Sabores CV; "
            f"{r['mudados']} alterado(s), {r['enviados']} enviado(s) ao Cérebro.")
    except Exception as erro:
        log(f"Material do Marketing falhou: {erro}")


if __name__ == "__main__":
    rodar()
