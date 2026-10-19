"""Registro das tarefas (SQLite): dificuldade, tempo, modelo, custo e fila adiada."""

import calendar
import sqlite3
from datetime import datetime, timedelta, timezone

import config

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL,
    andar TEXT NOT NULL,
    agente TEXT NOT NULL,
    texto TEXT NOT NULL,
    dificuldade TEXT NOT NULL,
    status TEXT NOT NULL,            -- executando | concluida | adiada | falhou
    modelo TEXT,
    tentativas INTEGER NOT NULL DEFAULT 0,
    tempo_segundos REAL NOT NULL DEFAULT 0,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    custo_usd REAL NOT NULL DEFAULT 0,
    resposta TEXT,
    motivo TEXT,
    entregue INTEGER NOT NULL DEFAULT 0,
    criada_em TEXT NOT NULL,
    concluida_em TEXT,
    tentativas_fila INTEGER NOT NULL DEFAULT 0,
    proxima_tentativa TEXT
);
CREATE INDEX IF NOT EXISTS idx_tarefas_status ON tarefas(status);
"""

# Colunas adicionadas depois da primeira versão do banco (migração simples).
_COLUNAS_NOVAS = {"tentativas_fila": "INTEGER NOT NULL DEFAULT 0", "proxima_tentativa": "TEXT"}

MAX_TENTATIVAS_FILA = 6
INTERVALO_REAGENDAMENTO = timedelta(minutes=30)

_conexao: sqlite3.Connection | None = None


def _agora(depois: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + depois).strftime("%Y-%m-%dT%H:%M:%SZ")


def _db() -> sqlite3.Connection:
    global _conexao
    if _conexao is None:
        config.ARQUIVO_BANCO.parent.mkdir(exist_ok=True)
        _conexao = sqlite3.connect(config.ARQUIVO_BANCO, check_same_thread=False)
        _conexao.row_factory = sqlite3.Row
        _conexao.executescript(_ESQUEMA)
        existentes = {linha["name"] for linha in _conexao.execute("PRAGMA table_info(tarefas)")}
        for coluna, tipo in _COLUNAS_NOVAS.items():
            if coluna not in existentes:
                _conexao.execute(f"ALTER TABLE tarefas ADD COLUMN {coluna} {tipo}")
    return _conexao


def iniciar() -> None:
    """Tarefas interrompidas por reinício do servidor voltam para a fila."""
    with _db() as db:
        db.execute("UPDATE tarefas SET status='adiada', motivo='Servidor reiniciado durante a execução.' "
                   "WHERE status='executando'")


def criar(usuario: str, andar: str, agente: str, texto: str, dificuldade: str) -> int:
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO tarefas (usuario, andar, agente, texto, dificuldade, status, criada_em) "
            "VALUES (?, ?, ?, ?, ?, 'executando', ?)",
            (usuario, andar, agente, texto, dificuldade, _agora()),
        )
        return cursor.lastrowid


def atualizar(tarefa_id: int, **campos) -> None:
    if campos.get("status") in ("concluida", "falhou"):
        campos.setdefault("concluida_em", _agora())
    colunas = ", ".join(f"{c} = ?" for c in campos)
    with _db() as db:
        db.execute(f"UPDATE tarefas SET {colunas} WHERE id = ?", (*campos.values(), tarefa_id))


def registrar_tentativa(tarefa_id: int, segundos: float) -> None:
    with _db() as db:
        db.execute("UPDATE tarefas SET tentativas = tentativas + 1, tempo_segundos = tempo_segundos + ? "
                   "WHERE id = ?", (segundos, tarefa_id))


def obter(tarefa_id: int) -> sqlite3.Row:
    return _db().execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()


def proximas_adiadas() -> list[sqlite3.Row]:
    """Adiadas prontas para tentar agora (respeita o reagendamento)."""
    return _db().execute(
        "SELECT * FROM tarefas WHERE status = 'adiada' AND (proxima_tentativa IS NULL OR proxima_tentativa <= ?) "
        "ORDER BY id", (_agora(),),
    ).fetchall()


def reagendar(tarefa_id: int) -> bool:
    """Devolve a tarefa à fila para daqui a pouco; False se já esgotou as tentativas."""
    linha = obter(tarefa_id)
    if linha["tentativas_fila"] + 1 >= MAX_TENTATIVAS_FILA:
        return False
    atualizar(tarefa_id, status="adiada", tentativas_fila=linha["tentativas_fila"] + 1,
              proxima_tentativa=_agora(INTERVALO_REAGENDAMENTO))
    return True


def historico(usuario: str, andar: str, agente: str, antes_de: int, limite: int = 3) -> list[sqlite3.Row]:
    """Últimas trocas concluídas com o mesmo agente (contexto para qualquer modelo que assumir)."""
    linhas = _db().execute(
        "SELECT texto, resposta FROM tarefas WHERE usuario = ? AND andar = ? AND agente = ? "
        "AND status = 'concluida' AND id < ? ORDER BY id DESC LIMIT ?",
        (usuario, andar, agente, antes_de, limite),
    ).fetchall()
    return list(reversed(linhas))


def nao_entregues(usuario: str) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM tarefas WHERE usuario = ? AND entregue = 0 AND status IN ('concluida', 'falhou') ORDER BY id",
        (usuario,),
    ).fetchall()


def listar(usuario: str | None, limite: int = 50) -> list[sqlite3.Row]:
    """`usuario=None` lista de todos (diretoria)."""
    filtro, params = ("WHERE usuario = ?", (usuario,)) if usuario else ("", ())
    return _db().execute(f"SELECT * FROM tarefas {filtro} ORDER BY id DESC LIMIT ?", (*params, limite)).fetchall()


def contagem_por_status(usuario: str | None) -> dict[str, int]:
    filtro, params = ("WHERE usuario = ?", (usuario,)) if usuario else ("", ())
    linhas = _db().execute(f"SELECT status, COUNT(*) n FROM tarefas {filtro} GROUP BY status", params).fetchall()
    contagem = {s: 0 for s in ("executando", "concluida", "adiada", "falhou")}
    contagem.update({linha["status"]: linha["n"] for linha in linhas})
    return contagem


# --- Orçamento Anthropic ---------------------------------------------------------------

def custo_estimado(modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
    preco_entrada, preco_saida = config.PRECOS_ANTHROPIC.get(modelo, (0.0, 0.0))
    return (tokens_entrada * preco_entrada + tokens_saida * preco_saida) / 1_000_000


def gasto_mes_usd() -> float:
    inicio = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    linha = _db().execute("SELECT COALESCE(SUM(custo_usd), 0) FROM tarefas WHERE concluida_em >= ?", (inicio,)).fetchone()
    return float(linha[0])


def liberado_ate_hoje_usd() -> float:
    """Crédito proporcional ao dia do mês: dias sem uso acumulam para os seguintes."""
    hoje = datetime.now(timezone.utc)
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    return config.CREDITO_MENSAL_ANTHROPIC_USD * config.FRACAO_UTILIZAVEL * hoje.day / dias_no_mes


def orcamento_pausado() -> bool:
    return gasto_mes_usd() >= liberado_ate_hoje_usd()
