"""Biblioteca de modelos de estilo (Onda 3, item 4; cerebro-12 e gestor-22): a fonte "modelo" do Cérebro.

Elogio ("adorei, é isso mesmo") virava regra resumida que perdia o tom, e o texto inteiro era recusado como regra
(correcoes.REGRA_CRUA_MIN). Agora a Diretoria pode guardar o texto aprovado como MODELO: por empresa (nunca
misturadas), agente e formato (legenda, descrição de casa, e-mail, roteiro, anúncio). Candidatos: os elogios da lista
"Correções e elogios" do ratinho do Cérebro e as respostas com 👍 dos agentes de texto. Só entra com a aprovação
(decisão 16: o Thomas aprova fatos e exemplos por empresa).

Aprovado, o modelo entra na busca do Cérebro com etiqueta própria (fonte "modelo", peso 0,7) e o aviso "siga o tom e a
estrutura, nunca copie os fatos". Um 👎 numa resposta que usou o modelo tira pontos dele (avaliacoes.py, como em
qualquer trecho). No máximo MAX_POR_GRUPO por empresa, agente e formato: o mais antigo sai.
"""

import re
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import cerebro_base as base
import correcoes
import empresas
import segredos
import tarefas
from auth import carregar_usuarios

rotas = APIRouter(prefix="/api/modelos")

FORMATOS = {"legenda": "Legenda de post", "descricao_casa": "Descrição de casa", "email": "E-mail",
            "roteiro": "Roteiro de vídeo", "anuncio": "Anúncio", "outro": "Outro texto"}
AGENTES_DE_TEXTO = {"copywriter", "social_media", "email_marketing", "gestor_trafego", "moviemaker", "gestor"}
MAX_POR_GRUPO = 10      # gestor-22: sem curadoria a biblioteca cresce sem fim
TEXTO_MAX = 4000
CANDIDATOS_DIAS = 30
# Rodapé que o sistema acrescenta à resposta (conferente.rodape, avisos do Monday): não é parte do texto aprovado.
RODAPE = re.compile(r"\n+(Conferência automática|Conferência dos itens gravados no Monday|Conferência de dados)"
                    r"[^\n]*\(só aviso.*", re.S)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS modelos_estilo (
    id INTEGER PRIMARY KEY AUTOINCREMENT, empresa TEXT NOT NULL, agente TEXT NOT NULL, formato TEXT NOT NULL,
    texto TEXT NOT NULL, tarefa_id INTEGER, observacao_id INTEGER, aprovado_por TEXT NOT NULL,
    criado_em TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_modelos_grupo ON modelos_estilo(empresa, agente, formato, ativo);
"""
_pronto = False


def _db():
    global _pronto
    conexao = base.db()
    if not _pronto:
        with base._trava:
            conexao.executescript(_ESQUEMA)
        _pronto = True
    return conexao


def formato_provavel(agente: str, texto: str) -> str:
    """Formato sugerido (a Diretoria confirma no pop-up)."""
    texto = texto or ""
    if agente == "email_marketing" or re.search(r"^\W*assunto\s*:", texto, re.I | re.M):
        return "email"
    if agente == "gestor_trafego" or re.search(r"\b(t[íi]tulo|headline)\s+do\s+an[úu]ncio\b", texto, re.I):
        return "anuncio"
    if agente == "moviemaker" or re.search(r"\broteiro\b|\bcena\s+\d", texto, re.I):
        return "roteiro"
    if agente == "social_media" or re.search(r"<<LEGENDA>>|\blegenda\b|#\w+", texto, re.I):
        return "legenda"
    if re.search(r"\bdescri[çc][aã]o\b|\bsite\b", texto, re.I):
        return "descricao_casa"
    return "outro"


def limpar(texto: str) -> str:
    """Texto do modelo: sem o rodapé de conferência, sem segredos e sem contato de cliente."""
    import cerebro  # import tardio: o Cérebro importa este módulo pelas rotas

    texto = RODAPE.sub("", texto or "").strip()
    return cerebro.sem_contatos(segredos.limpar(texto))[:TEXTO_MAX]


def _nome_agente(agente: str) -> str:
    return correcoes._nome(agente)


def _conteudo(formato: str, agente: str, texto: str, quem: str) -> tuple[str, str]:
    # Só o texto no conteúdo: um cabeçalho fixo ("ficha", "imóvel", "Lodge") faria todo modelo casar com qualquer
    # pergunta. A instrução "siga o tom, nunca copie os fatos" vai na etiqueta da fonte (cerebro.AVISO_MODELO).
    return f"Modelo de estilo · {FORMATOS[formato]} · {_nome_agente(agente)} (aprovado por {quem})", texto


def guardar(empresa: str, agente: str, formato: str, texto: str, quem: str, tarefa_id: int | None = None,
            observacao_id: int | None = None) -> int:
    """Grava o modelo aprovado e o põe na busca do Cérebro (só da empresa dele). Devolve o id."""
    if not empresas.valida(empresa):
        raise ValueError("O modelo é sempre de UMA empresa (a da tarefa); não há modelo para as três.")
    if formato not in FORMATOS:
        raise ValueError("Formato desconhecido.")
    texto = limpar(texto)
    if len(texto) < 20:
        raise ValueError("Texto curto demais para servir de modelo.")
    with base._trava, _db() as conexao:
        novo = conexao.execute(
            "INSERT INTO modelos_estilo (empresa, agente, formato, texto, tarefa_id, observacao_id, aprovado_por, "
            "criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (empresa, agente, formato, texto, tarefa_id, observacao_id, quem, base.agora())).lastrowid
        antigos = [l[0] for l in conexao.execute(
            "SELECT id FROM modelos_estilo WHERE empresa = ? AND agente = ? AND formato = ? AND ativo = 1 "
            "ORDER BY id DESC LIMIT -1 OFFSET ?", (empresa, agente, formato, MAX_POR_GRUPO))]
    base.substituir_ref("modelo", f"modelo:{novo}", *_conteudo(formato, agente, texto, quem), empresa)
    for antigo in antigos:
        remover(antigo)
    return novo


def remover(modelo_id: int) -> bool:
    with base._trava, _db() as conexao:
        mudou = conexao.execute("UPDATE modelos_estilo SET ativo = 0 WHERE id = ? AND ativo = 1", (modelo_id,)).rowcount
    base.remover_ref("modelo", f"modelo:{modelo_id}")
    return bool(mudou)


def ativos(empresa: str | None = None) -> list[dict]:
    filtro, valores = ("AND empresa = ?", (empresa,)) if empresa else ("", ())
    with base._trava:
        linhas = _db().execute(f"SELECT * FROM modelos_estilo WHERE ativo = 1 {filtro} ORDER BY id DESC",
                               valores).fetchall()
    return [dict(l) for l in linhas]


def candidatos(limite: int = 20) -> list[dict]:
    """Respostas com 👍 dos agentes de texto nos últimos dias que ainda não viraram modelo."""
    import avaliacoes  # import tardio: avaliações importam o Cérebro

    avaliacoes._db()
    marcas = ",".join("?" * len(AGENTES_DE_TEXTO))
    with base._trava:
        linhas = _db().execute(
            f"SELECT t.id, t.agente, t.empresa, t.resposta, a.usuario, a.em FROM avaliacoes a JOIN tarefas t "
            f"ON t.id = a.tarefa_id WHERE a.valor = 1 AND t.status = 'concluida' AND t.agente IN ({marcas}) "
            "AND a.em >= ? AND t.id NOT IN (SELECT tarefa_id FROM modelos_estilo WHERE tarefa_id IS NOT NULL) "
            "ORDER BY a.em DESC LIMIT ?", (*AGENTES_DE_TEXTO, tarefas._agora(-timedelta(days=CANDIDATOS_DIAS)), limite)
        ).fetchall()
    return [dict(l) for l in linhas if empresas.valida(l["empresa"]) and (l["resposta"] or "").strip()]


def previa(tarefa_id: int | None = None, observacao_id: int | None = None) -> dict:
    """Texto completo e formato sugerido para o pop-up "Guardar como modelo"."""
    obs = None
    if observacao_id:
        obs = correcoes._db().execute("SELECT * FROM observacoes WHERE id = ?", (observacao_id,)).fetchone()
        if not obs or obs["status"] != "nova" or obs["tipo"] != "elogio":
            raise LookupError("Elogio não encontrado ou já revisado.")
        tarefa_id = obs["tarefa_anterior"]
    linha = tarefas.obter(tarefa_id) if tarefa_id else None
    if not linha or not (linha["resposta"] or "").strip():
        raise LookupError("Resposta não encontrada.")
    texto = limpar(linha["resposta"])
    return {"tarefa_id": linha["id"], "observacao_id": observacao_id, "agente": linha["agente"],
            "agente_nome": _nome_agente(linha["agente"]), "empresa": linha["empresa"],
            "empresa_nome": empresas.nome(linha["empresa"]), "texto": texto,
            "formato": formato_provavel(linha["agente"], texto), "formatos": FORMATOS}


# --- Rotas (só a Diretoria; a mesma trava das correções) -------------------------------------------------------

class NovoModelo(BaseModel):
    tarefa_id: int | None = None
    observacao_id: int | None = None
    formato: str = Field(pattern="^(" + "|".join(FORMATOS) + ")$")
    texto: str = Field("", max_length=TEXTO_MAX)  # vazio: a resposta inteira da tarefa


@rotas.get("")
def listar(authorization: str = Header("")):
    correcoes._dono(authorization)
    nomes = {login: dados["nome"] for login, dados in carregar_usuarios().items()}
    return {"formatos": FORMATOS, "maximo_por_grupo": MAX_POR_GRUPO,
            "modelos": [{"id": m["id"], "empresa_nome": empresas.nome(m["empresa"]),
                         "agente_nome": _nome_agente(m["agente"]), "formato": FORMATOS.get(m["formato"], m["formato"]),
                         "previa": m["texto"][:160], "aprovado_por": m["aprovado_por"], "criado_em": m["criado_em"]}
                        for m in ativos()],
            "candidatos": [{"tarefa_id": c["id"], "agente_nome": _nome_agente(c["agente"]),
                            "empresa_nome": empresas.nome(c["empresa"]), "autor": nomes.get(c["usuario"], c["usuario"]),
                            "em": c["em"], "previa": limpar(c["resposta"])[:160]} for c in candidatos()]}


@rotas.get("/previa")
def ver_previa(tarefa_id: int = 0, observacao_id: int = 0, authorization: str = Header("")):
    correcoes._dono(authorization)
    try:
        return previa(tarefa_id or None, observacao_id or None)
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro))


@rotas.post("")
def criar(dados: NovoModelo, authorization: str = Header("")):
    usuario = correcoes._dono(authorization)
    try:
        origem = previa(dados.tarefa_id, dados.observacao_id)
        modelo_id = guardar(origem["empresa"], origem["agente"], dados.formato, dados.texto.strip() or origem["texto"],
                            usuario.get("nome") or usuario["sub"], origem["tarefa_id"], dados.observacao_id)
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    if dados.observacao_id:  # o elogio sai da lista: foi decidido como modelo (não como regra)
        with correcoes._db() as db:
            db.execute("UPDATE observacoes SET status = 'modelo', decidido_em = ? WHERE id = ?",
                       (tarefas._agora(), dados.observacao_id))
    return {"ok": True, "id": modelo_id, "empresa_nome": origem["empresa_nome"]}


@rotas.post("/{modelo_id}/remover")
def remover_rota(modelo_id: int, authorization: str = Header("")):
    correcoes._dono(authorization)
    return {"ok": remover(modelo_id)}
