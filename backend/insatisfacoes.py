"""Registro de insatisfações (Thomas, 30/10/2026): toda reação negativa na conversa (👎 ou mensagem do tipo "não era
isso") abre um pop-up perguntando o porquê. A resposta fica guardada aqui com o pedido e a resposta do agente, para o
master analisar junto com a equipe. Caso que motivou: carrossel de 6 Lodges que saiu só com o Lodge 35 (#232).

Quem registra: o dono do pedido. Quem vê e marca como analisada: só o master.
"""

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import tarefas
from auth import carregar_usuarios, validar_token
from estado import buscar_agente

rotas = APIRouter(prefix="/api/insatisfacoes")

CATEGORIAS = {
    "pedido": "Não seguiu o pedido",
    "dados": "Dados errados ou inventados",
    "faltou": "Faltou alguma coisa",
    "qualidade": "Visual ou qualidade fraca",
    "demora": "Demorou demais ou travou",
    "outro": "Outro motivo",
}
# Reação negativa escrita no chat: o pop-up abre depois do envio (js/avaliacao.js usa a mesma lista).
NEGATIVA = re.compile(
    r"\b(n[aã]o\s+(gostei|curti|era\s+(isso|o\s+que)|foi\s+(isso|o\s+que)|ficou\s+(bom|legal)|[ée]\s+(isso|o\s+que))|"
    r"(est[aá]|ficou)\s+(errad|ruim|horr[ií]vel|p[ée]ssim|feio)|p[ée]ssim|horr[ií]vel|decepcion|insatisfeit|"
    r"pedi\s+.{1,80}\s+e\s+(veio|voc[eê]\s+(fez|mandou|entregou))|errou|errad[oa])", re.IGNORECASE)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS insatisfacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, usuario TEXT NOT NULL, andar TEXT NOT NULL,
    agente TEXT NOT NULL, tarefa_id INTEGER, origem TEXT NOT NULL, categoria TEXT NOT NULL, motivo TEXT,
    mensagem TEXT, pedido TEXT, resposta TEXT, status TEXT NOT NULL DEFAULT 'nova', nota TEXT,
    analisada_em TEXT, analisada_por TEXT)
"""
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def e_negativa(texto: str) -> bool:
    return bool(NEGATIVA.search(texto or ""))


def registrar(linha, usuario: str, origem: str, categoria: str, motivo: str = "", mensagem: str = "") -> int:
    """Guarda a insatisfação com o pedido e a resposta da tarefa. `origem`: 'voto' (👎) ou 'mensagem' (chat)."""
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO insatisfacoes (em, usuario, andar, agente, tarefa_id, origem, categoria, motivo, mensagem, "
            "pedido, resposta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tarefas._agora(), usuario, linha["andar"], linha["agente"], linha["id"], origem,
             categoria if categoria in CATEGORIAS else "outro", (motivo or "")[:1000] or None,
             (mensagem or "")[:1000] or None, (linha["texto"] or "")[:4000], (linha["resposta"] or "")[:4000]))
    return cursor.lastrowid


def novas() -> int:
    return _db().execute("SELECT COUNT(*) FROM insatisfacoes WHERE status = 'nova'").fetchone()[0]


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def _master(authorization: str) -> dict:
    usuario = _usuario(authorization)
    if not usuario.get("master"):
        raise HTTPException(status_code=403, detail="Só o master vê o registro de insatisfações.")
    return usuario


class Insatisfacao(BaseModel):
    tarefa_id: int
    categoria: str = Field("outro", max_length=20)
    motivo: str = Field("", max_length=1000)
    mensagem: str = Field("", max_length=1000)
    origem: str = Field("voto", pattern="^(voto|mensagem)$")


@rotas.post("")
def criar(dados: Insatisfacao, authorization: str = Header("")):
    usuario = _usuario(authorization)
    linha = tarefas.obter(dados.tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not dados.motivo.strip() and dados.categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail="Diga o motivo.")
    novo = registrar(linha, usuario["sub"], dados.origem, dados.categoria, dados.motivo.strip(), dados.mensagem.strip())
    return {"ok": True, "id": novo}


@rotas.get("")
def listar(status: str = "", authorization: str = Header("")):
    _master(authorization)
    filtro, params = ("WHERE status = ? ", (status,)) if status in ("nova", "analisada") else ("", ())
    linhas = _db().execute(f"SELECT * FROM insatisfacoes {filtro}ORDER BY id DESC LIMIT 200", params).fetchall()
    nomes = {login: d["nome"] for login, d in carregar_usuarios().items()}
    itens = []
    for l in linhas:
        agente = buscar_agente(l["andar"], l["agente"])
        itens.append({**dict(l), "usuario_nome": nomes.get(l["usuario"], l["usuario"]),
                      "agente_nome": agente.nome if agente else l["agente"],
                      "categoria_nome": CATEGORIAS.get(l["categoria"], l["categoria"])})
    return {"itens": itens, "novas": novas(), "categorias": CATEGORIAS}


class Analise(BaseModel):
    nota: str = Field("", max_length=2000)


@rotas.post("/{insatisfacao_id}/analisar")
def analisar(insatisfacao_id: int, dados: Analise, authorization: str = Header("")):
    usuario = _master(authorization)
    with _db() as db:
        feito = db.execute("UPDATE insatisfacoes SET status = 'analisada', nota = ?, analisada_em = ?, "
                           "analisada_por = ? WHERE id = ?",
                           (dados.nota.strip() or None, tarefas._agora(), usuario["sub"], insatisfacao_id)).rowcount
    if not feito:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return {"ok": True, "novas": novas()}


@rotas.post("/{insatisfacao_id}/reabrir")
def reabrir(insatisfacao_id: int, authorization: str = Header("")):
    _master(authorization)
    with _db() as db:
        db.execute("UPDATE insatisfacoes SET status = 'nova' WHERE id = ?", (insatisfacao_id,))
    return {"ok": True, "novas": novas()}
