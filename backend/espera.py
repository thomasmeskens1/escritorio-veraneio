"""Produção em espera: o Gestor terminou o plano com uma pergunta ao usuário, então a produção no Max aguarda a
resposta no chat onde o pedido nasceu. Teste real: o Gestor perguntou "mantém as três casas?" e já acionou o
Criador de Imagens e o Editor de Vídeo; a resposta do usuário ainda foi parar no Social Media, que se perdeu.

A próxima mensagem do usuário naquele chat é a resposta: ela entra no briefing da produção como decisão final.
"""

import re

import tarefas

# O Gestor é instruído a fechar com "PERGUNTA: ..." quando falta uma decisão; as frases servem de reserva.
MARCA = re.compile(r"^\s*PERGUNTA\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
PEDE_DECISAO = re.compile(
    r"precis\w*\s+de\s+(uma\s+)?(confirma|defini|resposta|decis)|confirma[çc][aã]o\s+sua|"
    r"aguard\w*\s+(a\s+|sua\s+)?(defini|confirma|resposta|decis)|pendente\s+(de\s+)?defini|"
    r"me\s+(diga|confirme)\b|voc[eê]\s+prefere|prefere\s+que", re.IGNORECASE)
CANCELAR = re.compile(r"^\s*(cancel\w*|n[aã]o\s+produz\w*|n[aã]o\s+precisa\w*|pare\b)", re.IGNORECASE)
# Confirmação explícita (pedido que não falava em arquivo): só isto dispara a produção.
PRODUZIR = re.compile(r"^\s*(sim\b|pode\s+(seguir|produzir)|produz\w*|quero\s+(a\s+)?pe[cç]a|pe[cç]a\s+final)",
                      re.IGNORECASE)

_ESQUEMA = """CREATE TABLE IF NOT EXISTS producao_em_espera (
    tarefa_id INTEGER PRIMARY KEY, usuario TEXT NOT NULL, andar TEXT NOT NULL, agente TEXT NOT NULL,
    pergunta TEXT NOT NULL, criada_em TEXT NOT NULL)"""
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        if "confirmar_arquivo" not in {c[1] for c in db.execute("PRAGMA table_info(producao_em_espera)")}:
            db.execute("ALTER TABLE producao_em_espera ADD COLUMN confirmar_arquivo INTEGER NOT NULL DEFAULT 0")
        _pronto = True
    return db


def pergunta_pendente(texto: str) -> str | None:
    """A pergunta ao usuário que fecha a entrega do Gestor; None se não há decisão pendente."""
    if (marca := MARCA.search(texto or "")):
        return marca.group(1).strip()
    final = (texto or "").strip()[-900:]
    if not PEDE_DECISAO.search(final):
        return None
    paragrafos = [p.strip() for p in final.split("\n\n") if p.strip()]
    com_pergunta = [p for p in paragrafos if "?" in p]
    return (com_pergunta or paragrafos or [final])[-1][:500]


def guardar(tarefa_id: int, usuario: str, andar: str, agente: str, pergunta: str,
            confirmar_arquivo: bool = False) -> None:
    """`confirmar_arquivo`: o pedido não falava em arquivo (ex.: persona da Francielle, tarefa #224, que virou
    produção de vídeo na #226). Só um "produzir" explícito dispara a produção; outra resposta segue como conversa."""
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO producao_em_espera (tarefa_id, usuario, andar, agente, pergunta, criada_em, "
                   "confirmar_arquivo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (tarefa_id, usuario, andar, agente, pergunta, tarefas._agora(), int(confirmar_arquivo)))


def no_chat(usuario: str, andar: str, agente: str):
    """Produção esperando resposta neste chat (a mais recente), ou None."""
    return _db().execute("SELECT * FROM producao_em_espera WHERE usuario = ? AND andar = ? AND agente = ? "
                         "ORDER BY tarefa_id DESC LIMIT 1", (usuario, andar, agente)).fetchone()


def remover(tarefa_id: int) -> None:
    with _db() as db:
        db.execute("DELETE FROM producao_em_espera WHERE tarefa_id = ?", (tarefa_id,))
