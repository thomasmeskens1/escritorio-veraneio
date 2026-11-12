"""Botão "Desdobrar" (Onda 3, item 3; designer-07, gestor_trafego-11; 31/10/2026): a peça pronta em 4:5 e 9:16.

Com "destino": "anuncio" (botão "Desdobrar para anúncio", 12/11/2026) gera 1:1, 1,91:1 e 9:16 de anúncio e o cabeçalho
de e-mail na subpasta ANÚNCIO/, com um .txt que diz onde usar cada formato.
Roda no PC, em código e sem o Max: relê o molde.json da peça (rascunho local, versão vigente), renderiza os mesmos
slides nos outros formatos com os moldes (molde.py) e grava em <pasta da peça no Drive>/FORMATOS/. Peça feita fora
dos moldes devolve SEM_MOLDE e o backend (backend/desdobrar.py) põe o desdobramento na fila do Max como ajuste.
"""

import shutil
from pathlib import Path

import comum
import molde
import pasta_final

SEM_MOLDE = "SEM_MOLDE:"  # mesmo marcador de backend/desdobrar.py
RASCUNHOS = comum.TRABALHO / "producoes"  # mesma pasta de trabalhador_max.RASCUNHOS
ARQUIVO = "molde.json"
PASTA = "FORMATOS"
ROTULOS = {"1080x1350": "4x5", "1080x1920": "9x16", "1080x1080": "1x1", "1080x1440": "3x4"}
# "Desdobrar para anúncio" (gestor_trafego-13, designer-21, email_marketing-06; 12/11/2026): payload "destino": "anuncio"
PASTA_ANUNCIO = "ANÚNCIO"
ANUNCIO = {"1080x1080": "1x1", "1200x628": "1.91x1", "1080x1920": "9x16"}
EMAIL = "1200x600"  # cabeçalho de e-mail: 1200 px de largura, exibido a 600 px
ONDE_USAR = {
    "1080x1080": "Quadrado 1:1 (1080x1080): Meta Ads feed (Facebook e Instagram), carrossel de anúncio, LinkedIn e Google "
                 "(Demand Gen / PMax).",
    "1200x628": "Horizontal 1,91:1 (1200x628): Meta Ads feed e coluna direita, link de anúncio, LinkedIn (aceita 1200x627) "
                "e Google (Demand Gen / PMax).",
    "1080x1920": "Vertical 9:16 (1080x1920): Meta Ads Reels e Stories. Texto, selo e logo entre ~300 e ~1250 px de altura: "
                 "a faixa de baixo fica livre para o botão do anúncio (manual 08, seção 3).",
    EMAIL: "Cabeçalho de e-mail (1200x600): imagem do topo do e-mail marketing, inserida com 600 px de largura (fica "
           "nítida em tela retina). Só a capa. Hospedagem da imagem no e-mail: decisão pendente.",
}
LEIA = "LEIA - ONDE USAR CADA FORMATO.txt"


def _livre(destino: Path) -> Path:
    """Nunca troca um arquivo que já está no Drive: o novo ganha _2, _3..."""
    candidato, n = destino, 2
    while candidato.exists():
        candidato, n = destino.with_name(f"{destino.stem}_{n}{destino.suffix}"), n + 1
    return candidato


def pasta_da_entrega(pasta: str) -> Path:
    """Pasta da peça no Drive, sempre dentro do Drive do escritório."""
    entrega = (comum.DRIVE / pasta).resolve()
    if not pasta or not entrega.is_relative_to(comum.DRIVE.resolve()) or not entrega.is_dir():
        raise RuntimeError(f"Pasta da peça não encontrada no Drive: {pasta}")
    return entrega


def leia(gerados: dict[str, list[str]]) -> str:
    """Texto do .txt da pasta ANÚNCIO/: cada formato, onde usar e os arquivos dele."""
    linhas = ["Casa Veraneio · versões para anúncio e e-mail desta peça (geradas pelo molde, sem refazer a arte).",
              "Fotos, textos, selo e logo são os da peça aprovada. Valores não aparecem na arte.", ""]
    for formato, arquivos in gerados.items():
        linhas += [ONDE_USAR[formato]] + [f"  - {a}" for a in arquivos] + [""]
    return "\n".join(linhas)


def executar_anuncio(rascunho: Path, entrega: Path, renderizador=None) -> str:
    """ANÚNCIO/: 1:1, 1,91:1 e 9:16 de anúncio com todos os slides, o cabeçalho de e-mail (só a capa) e o .txt."""
    destino = entrega / PASTA_ANUNCIO
    extras = {"renderizador": renderizador} if renderizador else {}
    gerados: dict[str, list[str]] = {}
    for formato, rotulo in [*ANUNCIO.items(), (EMAIL, "email")]:
        pasta = rascunho / "desdobrar" / f"anuncio_{rotulo}"
        shutil.rmtree(pasta, ignore_errors=True)
        pngs = molde.renderizar(rascunho / ARQUIVO, formato, pasta, anuncio=True, slides=1 if formato == EMAIL else None,
                                **extras)
        for png in pngs:
            nome = Path(pasta_final.chave_e_versao(png.name)[0]).stem
            final = _livre(destino / (f"email_cabecalho_{formato}.png" if formato == EMAIL else f"{nome}_{rotulo}.png"))
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, final)
            gerados.setdefault(formato, []).append(final.name)
    txt = _livre(destino / LEIA)
    txt.write_text(leia(gerados), encoding="utf-8")
    total = sum(len(v) for v in gerados.values())
    comum.log(f"   anúncio: {total} arquivo(s) em {entrega.name}/{PASTA_ANUNCIO}")
    return (f"Versões de anúncio (1:1, 1,91:1 e 9:16) e cabeçalho de e-mail geradas pelo molde, sem Max: {total} "
            f"arquivo(s) e o guia \"{txt.name}\" em ESCRITÓRIO VERANEIO/"
            f"{entrega.relative_to(comum.DRIVE.resolve()).as_posix()}/{PASTA_ANUNCIO}:\n"
            + "\n".join(f"- {a}" for v in gerados.values() for a in v))


def executar(payload: dict, renderizador=None) -> str:
    raiz = int(payload["raiz"])
    anuncio = payload.get("destino") == "anuncio"
    formatos = [f for f in payload.get("formatos") or ("1080x1350", "1080x1920") if f in ROTULOS]
    if not formatos and not anuncio:
        raise RuntimeError("Nenhum formato válido para desdobrar.")
    rascunho = RASCUNHOS / str(raiz)
    if not (rascunho / ARQUIVO).is_file():
        return f"{SEM_MOLDE} a peça não foi montada com os moldes (sem {ARQUIVO} no rascunho)."
    try:
        molde.carregar(rascunho / ARQUIVO)
    except (ValueError, KeyError) as erro:
        return f"{SEM_MOLDE} {erro}"
    entrega = pasta_da_entrega(payload.get("pasta") or "")
    if anuncio:
        return executar_anuncio(rascunho, entrega, renderizador)
    destino = entrega / PASTA
    gerados = []
    for formato in formatos:
        rotulo = ROTULOS[formato]
        pasta = rascunho / "desdobrar" / rotulo
        shutil.rmtree(pasta, ignore_errors=True)
        extras = {"renderizador": renderizador} if renderizador else {}
        for png in molde.renderizar(rascunho / ARQUIVO, formato, pasta, **extras):
            nome = Path(pasta_final.chave_e_versao(png.name)[0])  # capa_v2.png -> capa (a versão vigente)
            final = _livre(destino / f"{nome.stem}_{rotulo}.png")
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, final)
            gerados.append(final.relative_to(entrega).as_posix())
    comum.log(f"   desdobrada: {len(gerados)} arquivo(s) em {entrega.name}/{PASTA}")
    return (f"Desdobrada em {', '.join(ROTULOS[f].replace('x', ':') for f in formatos)} a partir do molde, sem Max: "
            f"{len(gerados)} arquivo(s) em ESCRITÓRIO VERANEIO/{entrega.relative_to(comum.DRIVE.resolve()).as_posix()}"
            f"/{PASTA}:\n" + "\n".join(f"- {g}" for g in gerados))
