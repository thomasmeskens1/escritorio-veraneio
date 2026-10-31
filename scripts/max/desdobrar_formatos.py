"""Botão "Desdobrar" (Onda 3, item 3; designer-07, gestor_trafego-11; 31/10/2026): a peça pronta em 4:5 e 9:16.

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


def executar(payload: dict, renderizador=None) -> str:
    raiz = int(payload["raiz"])
    formatos = [f for f in payload.get("formatos") or ("1080x1350", "1080x1920") if f in ROTULOS]
    if not formatos:
        raise RuntimeError("Nenhum formato válido para desdobrar.")
    rascunho = RASCUNHOS / str(raiz)
    if not (rascunho / ARQUIVO).is_file():
        return f"{SEM_MOLDE} a peça não foi montada com os moldes (sem {ARQUIVO} no rascunho)."
    try:
        molde.carregar(rascunho / ARQUIVO)
    except (ValueError, KeyError) as erro:
        return f"{SEM_MOLDE} {erro}"
    entrega = pasta_da_entrega(payload.get("pasta") or "")
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
