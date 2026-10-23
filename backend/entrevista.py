"""Entrevista das empresas (só o Thomas): completa os pontos PENDENTES dos documentos do Corporativo (11) e da
Casa Vero (12). Cada linha "- Rótulo: PENDENTE" vira um campo do formulário; a resposta substitui o PENDENTE no
documento, que é reindexado no Cérebro e já vale para os agentes (as diretrizes leem o arquivo atualizado).
"""

import asyncio
import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import config
import empresas
from auth import validar_token

rotas = APIRouter(prefix="/api/cerebro/entrevista")

DOCUMENTOS = {"cv_corporativo": "11_casa_veraneio_corporativo.md", "casa_vero": "12_casa_vero.md"}
PENDENTE = re.compile(r"^- (?P<rotulo>[^:\n]+(?:\?)?):\s*PENDENTE.*$", re.MULTILINE)


def _dono(authorization: str) -> None:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if usuario["sub"] != config.DONO_MAX:
        raise HTTPException(status_code=403, detail="Só o Thomas responde a entrevista das empresas.")


def _arquivo(empresa: str):
    if empresa not in DOCUMENTOS:
        raise HTTPException(status_code=404, detail="Empresa sem entrevista.")
    return config.PASTA_CONHECIMENTO / DOCUMENTOS[empresa]


def pendentes(empresa: str) -> list[str]:
    arquivo = _arquivo(empresa)
    return [m["rotulo"].strip() for m in PENDENTE.finditer(arquivo.read_text(encoding="utf-8"))] if arquivo.exists() else []


@rotas.get("")
def listar(authorization: str = Header("")):
    _dono(authorization)
    return {e: {"nome": empresas.nome(e), "pendentes": pendentes(e)} for e in DOCUMENTOS}


class Respostas(BaseModel):
    respostas: dict[str, str] = Field(max_length=40)


@rotas.post("/{empresa}")
async def responder(empresa: str, dados: Respostas, authorization: str = Header("")):
    import cerebro  # import tardio: o Cérebro carrega o banco

    _dono(authorization)
    arquivo = _arquivo(empresa)
    texto = arquivo.read_text(encoding="utf-8")
    preenchidos = 0
    for rotulo, resposta in dados.respostas.items():
        resposta = " ".join(str(resposta).split())[:1000]
        if not resposta:
            continue
        linha = re.compile(rf"^- {re.escape(rotulo.strip())}:\s*PENDENTE.*$", re.MULTILINE)
        texto, n = linha.subn(lambda _m, r=rotulo.strip(), v=resposta: f"- {r}: {v}", texto, count=1)
        preenchidos += n
    if preenchidos:
        arquivo.write_text(texto, encoding="utf-8")
        await asyncio.to_thread(cerebro.indexar_oficiais)  # o Cérebro passa a responder com o que foi confirmado
    return {"ok": True, "preenchidos": preenchidos, "faltam": pendentes(empresa)}
