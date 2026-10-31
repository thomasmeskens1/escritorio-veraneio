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
# Onde errou (Onda 2, cerebro-20): num projeto com várias etapas o 👎 caía todo no último agente. Pergunta opcional
# do pop-up; o padrão é "não sei". A consolidação semanal usa para propor a regra ao agente daquela etapa.
ETAPAS = {
    "plano": "Plano/briefing",
    "texto": "Texto",
    "imagem": "Imagem/vídeo",
    "dados": "Dados do Lodge",
    "nao_sei": "Não sei",
}
AGENTES_DA_ETAPA = {"plano": "gestor", "texto": "copywriter", "imagem": "criador_imagens ou editor_video",
                    "dados": "quem montou as fichas/dados (ou *)"}
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
        if "etapa" not in {c[1] for c in db.execute("PRAGMA table_info(insatisfacoes)")}:
            db.execute("ALTER TABLE insatisfacoes ADD COLUMN etapa TEXT")
        _pronto = True
    return db


def e_negativa(texto: str) -> bool:
    return bool(NEGATIVA.search(texto or ""))


def registrar(linha, usuario: str, origem: str, categoria: str, motivo: str = "", mensagem: str = "",
              etapa: str = "") -> int:
    """Guarda a insatisfação com o pedido e a resposta da tarefa. `origem`: 'voto' (👎) ou 'mensagem' (chat)."""
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO insatisfacoes (em, usuario, andar, agente, tarefa_id, origem, categoria, motivo, mensagem, "
            "pedido, resposta, etapa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tarefas._agora(), usuario, linha["andar"], linha["agente"], linha["id"], origem,
             categoria if categoria in CATEGORIAS else "outro", (motivo or "")[:1000] or None,
             (mensagem or "")[:1000] or None, (linha["texto"] or "")[:4000], (linha["resposta"] or "")[:4000],
             etapa if etapa in ETAPAS and etapa != "nao_sei" else None))
    return cursor.lastrowid


def texto_seguro(texto: str) -> str:
    """Motivo escrito pela equipe antes de ir ao Max: sem chaves/tokens (segredos.limpar) e sem e-mail, telefone,
    CPF/CNPJ de cliente (cerebro.sem_contatos)."""
    import cerebro  # import tardio: o Cérebro carrega o banco e os embeddings
    import segredos

    return cerebro.sem_contatos(segredos.limpar(texto or ""))


def da_semana(desde: str) -> list[dict]:
    """Insatisfações desde `desde`, com a empresa da tarefa e o texto já filtrado, para a consolidação semanal
    (Onda 2, cerebro-08: antes o motivo do 👎 ficava só para o master e a regra saía "preventiva")."""
    linhas = _db().execute(
        "SELECT i.agente, i.categoria, i.etapa, i.motivo, i.nota, i.pedido, t.empresa FROM insatisfacoes i "
        "LEFT JOIN tarefas t ON t.id = i.tarefa_id WHERE i.em >= ? ORDER BY i.id", (desde,)).fetchall()
    return [{"agente": l["agente"], "empresa": l["empresa"], "categoria": CATEGORIAS.get(l["categoria"], l["categoria"]),
             "etapa": ETAPAS.get(l["etapa"] or "", ""), "motivo": texto_seguro(l["motivo"] or "")[:300],
             "nota_master": texto_seguro(l["nota"] or "")[:300], "pedido": texto_seguro(l["pedido"] or "")[:200]}
            for l in linhas]


def so_demora(tarefa_ids) -> set[int]:
    """Tarefas cujas insatisfações são todas "demora": o 👎 delas não diz nada sobre o conteúdo (reranker)."""
    try:
        linhas = _db().execute("SELECT tarefa_id, categoria FROM insatisfacoes WHERE tarefa_id IS NOT NULL").fetchall()
    except Exception:
        return set()
    categorias: dict[int, set] = {}
    for l in linhas:
        categorias.setdefault(l["tarefa_id"], set()).add(l["categoria"])
    return {t for t in tarefa_ids if categorias.get(t) == {"demora"}}


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
    etapa: str = Field("", max_length=20)  # opcional: onde errou (ETAPAS)


@rotas.post("")
def criar(dados: Insatisfacao, authorization: str = Header("")):
    usuario = _usuario(authorization)
    linha = tarefas.obter(dados.tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not dados.motivo.strip() and dados.categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail="Diga o motivo.")
    novo = registrar(linha, usuario["sub"], dados.origem, dados.categoria, dados.motivo.strip(), dados.mensagem.strip(),
                     dados.etapa)
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
                      "categoria_nome": CATEGORIAS.get(l["categoria"], l["categoria"]),
                      "etapa_nome": ETAPAS.get(l["etapa"] or "", "")})
    return {"itens": itens, "novas": novas(), "categorias": CATEGORIAS, "etapas": ETAPAS}


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
