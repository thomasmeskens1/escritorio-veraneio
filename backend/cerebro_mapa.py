"""Mapa do Cérebro (diretoria): a árvore do conhecimento ativo para a visualização radial.

Raiz → empresa (Casa Veraneio, Corporativo, Casa Vero, comum às três) → fonte (oficial, ensinado, site, drive,
tarefa) → grupo (quando a fonte tem muitos documentos) → documento, com o nº de trechos de cada um (densidade).
"""

import re

from fastapi import APIRouter, Header, HTTPException

import cerebro_base as base
import empresas
from auth import validar_token

rotas = APIRouter(prefix="/api/cerebro")

ROTULOS_FONTE = {"oficial": "Manuais oficiais", "ensinado": "Ensinado pelo Thomas", "site": "Site",
                 "drive": "Drive", "tarefa": "Tarefas concluídas"}
POR_GRUPO = 25  # fonte com mais documentos que isso ganha um nível de grupos (o anel não vira uma mancha)


def _numero(texto: str) -> int:
    achado = re.search(r"\d+", texto or "")
    return int(achado.group()) if achado else 10**9


def _rotulo_documento(ref: str, titulo: str) -> str:
    return (titulo or ref).split(" › ")[0][:70]


def _grupos(documentos: list[dict]) -> list[dict]:
    """Documentos em ordem numérica (Lodge 1, 2, 10...), em grupos de POR_GRUPO quando são muitos."""
    documentos = sorted(documentos, key=lambda d: (_numero(d["nome"]), d["nome"]))
    if len(documentos) <= POR_GRUPO:
        return documentos
    grupos = []
    for inicio in range(0, len(documentos), POR_GRUPO):
        bloco = documentos[inicio:inicio + POR_GRUPO]
        primeiro, ultimo = _numero(bloco[0]["nome"]), _numero(bloco[-1]["nome"])
        nome = (f"Nº {primeiro}–{ultimo}" if ultimo < 10**9 else f"{bloco[0]['nome'][:20]} … {bloco[-1]['nome'][:20]}")
        grupos.append({"nome": nome, "trechos": sum(d["trechos"] for d in bloco), "filhos": bloco})
    return grupos


def mapa() -> dict:
    with base._trava:
        linhas = base.db().execute(
            "SELECT empresa, fonte_tipo, fonte_ref, MIN(titulo) AS titulo, COUNT(*) AS trechos FROM conhecimento "
            "WHERE ativo = 1 GROUP BY empresa, fonte_tipo, fonte_ref").fetchall()
    arvore: dict[str, dict[str, list]] = {}
    for l in linhas:
        arvore.setdefault(l["empresa"], {}).setdefault(l["fonte_tipo"], []).append(
            {"nome": _rotulo_documento(l["fonte_ref"], l["titulo"]), "trechos": l["trechos"]})
    ordem = [*empresas.EMPRESAS, empresas.COMUM]
    filhos = []
    for empresa in sorted(arvore, key=lambda e: ordem.index(e) if e in ordem else 99):
        fontes = [{"nome": ROTULOS_FONTE.get(f, f), "trechos": sum(d["trechos"] for d in docs), "filhos": _grupos(docs)}
                  for f, docs in sorted(arvore[empresa].items())]
        filhos.append({"nome": empresas.nome(empresa) if empresa != empresas.COMUM else "Comum às três",
                       "empresa": empresa, "trechos": sum(f["trechos"] for f in fontes), "filhos": fontes})
    return {"nome": "Cérebro", "trechos": sum(f["trechos"] for f in filhos), "filhos": filhos}


@rotas.get("/mapa")
def mapa_do_cerebro(authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if usuario.get("role") != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria vê o mapa do Cérebro.")
    return mapa()
