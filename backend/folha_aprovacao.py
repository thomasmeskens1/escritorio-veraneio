"""Folha de aprovação da peça no chat (Onda 2, designer-10, 31/10/2026).

O trabalhador do Max monta um JPG com as miniaturas numeradas da pasta FINAL/ (scripts/max/pasta_final.py) e envia
para cá antes de concluir a peça. O arquivo vira um anexo do dono do pedido (dados/anexos, mesma tabela e mesma rota
das miniaturas do chat) e aparece junto com a resposta da produção. Um ajuste troca a folha pela da versão nova.
"""

import uuid

from fastapi import APIRouter, File, Header, HTTPException, UploadFile

import anexos
import producao
import tarefas

rotas = APIRouter(prefix="/api/producao")

_ESQUEMA = "CREATE TABLE IF NOT EXISTS folhas_aprovacao (tarefa_id INTEGER PRIMARY KEY, anexo_id TEXT NOT NULL)"
_pronto = False


def _db():
    global _pronto
    db = anexos._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def guardar(tarefa_id: int, conteudo: bytes, nome: str = "FOLHA DE APROVAÇÃO.jpg") -> str:
    """Grava o JPG como anexo do dono da tarefa; devolve o id do anexo."""
    linha = tarefas.obter(tarefa_id)
    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not conteudo or len(conteudo) > anexos.TAMANHO_MAX:
        raise HTTPException(status_code=413, detail="Folha vazia ou maior que 15 MB.")
    if anexos._tipo_pelo_conteudo(conteudo[:16]) != "image/jpeg":
        raise HTTPException(status_code=415, detail="A folha de aprovação precisa ser JPG.")
    anexo_id = uuid.uuid4().hex[:12]
    relativo = f"dados/anexos/{anexo_id}.jpg"
    anexos.PASTA.mkdir(parents=True, exist_ok=True)
    anexos._absoluto(relativo).write_bytes(conteudo)
    with _db() as db:
        db.execute("INSERT INTO anexos (id, usuario, nome_original, mime, tamanho, caminho, descricao, status, "
                   "criado_em) VALUES (?, ?, ?, 'image/jpeg', ?, ?, ?, 'descrito', ?)",
                   (anexo_id, linha["usuario"], anexos._nome_seguro(nome), len(conteudo), relativo,
                    f"Folha de aprovação da peça #{tarefa_id}", tarefas._agora()))
        db.execute("INSERT OR REPLACE INTO folhas_aprovacao (tarefa_id, anexo_id) VALUES (?, ?)", (tarefa_id, anexo_id))
    return anexo_id


def de(tarefa_id: int) -> list[dict]:
    """Metadados da folha (no formato dos anexos do chat) ou []."""
    linha = _db().execute("SELECT a.id, a.nome_original, a.mime, a.tamanho FROM folhas_aprovacao f JOIN anexos a "
                          "ON a.id = f.anexo_id WHERE f.tarefa_id = ?", (tarefa_id,)).fetchone()
    return [{"id": linha["id"], "nome": linha["nome_original"], "mime": linha["mime"],
             "tamanho": linha["tamanho"]}] if linha else []


@rotas.post("/{tarefa_id}/folha")
async def receber_folha(tarefa_id: int, arquivo: UploadFile = File(...), authorization: str = Header("")):
    producao._exigir_operador(authorization)  # só o trabalhador do Max (token de operador)
    conteudo = await arquivo.read(anexos.TAMANHO_MAX + 1)
    return {"ok": True, "anexo_id": guardar(tarefa_id, conteudo, arquivo.filename or "FOLHA DE APROVAÇÃO.jpg")}
