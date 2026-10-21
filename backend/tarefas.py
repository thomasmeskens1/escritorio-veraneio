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
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarefa_id INTEGER NOT NULL,
    em TEXT NOT NULL,
    tipo TEXT NOT NULL,   -- recebida | tentativa | falha_modelo | consulta_cerebro | etapa_iniciada | etapa_salva | adiada | concluida | falhou
    agente TEXT,
    modelo TEXT,
    detalhe TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_tarefa ON eventos(tarefa_id);
"""

# Colunas adicionadas depois da primeira versão do banco (migração simples).
_COLUNAS_NOVAS = {"tentativas_fila": "INTEGER NOT NULL DEFAULT 0", "proxima_tentativa": "TEXT",
                  "anexos": "TEXT", "contexto_anexos": "TEXT"}  # anexos: JSON com os ids

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


# --- Registro de atividade ------------------------------------------------------------

def registrar_evento(tarefa_id: int, tipo: str, agente: str | None = None, modelo: str | None = None,
                     detalhe: str | None = None) -> None:
    with _db() as db:
        db.execute("INSERT INTO eventos (tarefa_id, em, tipo, agente, modelo, detalhe) VALUES (?, ?, ?, ?, ?, ?)",
                   (tarefa_id, _agora(), tipo, agente, modelo, (detalhe or "")[:300] or None))


def eventos_de(tarefa_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    if not tarefa_ids:
        return {}
    marcadores = ",".join("?" * len(tarefa_ids))
    linhas = _db().execute(f"SELECT * FROM eventos WHERE tarefa_id IN ({marcadores}) ORDER BY id", tarefa_ids).fetchall()
    por_tarefa: dict[int, list] = {}
    for linha in linhas:
        por_tarefa.setdefault(linha["tarefa_id"], []).append(linha)
    return por_tarefa


def contagem_do_agente(agente: str) -> tuple[int, int]:
    """(concluídas, total) de tarefas pedidas diretamente ao agente."""
    linha = _db().execute(
        "SELECT SUM(status = 'concluida'), COUNT(*) FROM tarefas WHERE agente = ?", (agente,)
    ).fetchone()
    return int(linha[0] or 0), int(linha[1] or 0)


def etapas_do_agente(agente: str) -> int:
    """Etapas de projetos do Gestor entregues por este agente."""
    return _db().execute("SELECT COUNT(*) FROM eventos WHERE tipo = 'etapa_salva' AND agente = ?",
                         (agente,)).fetchone()[0]


# --- Orçamento Anthropic ---------------------------------------------------------------

def custo_estimado(modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
    preco_entrada, preco_saida = config.PRECOS_ANTHROPIC.get(modelo, (0.0, 0.0))
    return (tokens_entrada * preco_entrada + tokens_saida * preco_saida) / 1_000_000


def gasto_mes_usd(dificuldade: str | None = None) -> float:
    inicio = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    filtro, params = ("AND dificuldade = ?", (dificuldade,)) if dificuldade else ("", ())
    linha = _db().execute(
        f"SELECT COALESCE(SUM(custo_usd), 0) FROM tarefas WHERE concluida_em >= ? {filtro}", (inicio, *params)
    ).fetchone()
    return float(linha[0])


def chat_rapido_liberado(agente_id: str = "") -> bool:
    """Haiku para tarefas simples, sem passar do teto reservado a elas (protege o orçamento do Gestor).
    Os agentes prioritários não têm esse teto: só o crédito do mês."""
    if agente_id in config.AGENTES_API_PRIORITARIOS:
        return api_liberada(agente_id)
    teto = config.CREDITO_MENSAL_ANTHROPIC_USD * config.FRACAO_CHAT_RAPIDO
    return gasto_mes_usd("simples") < teto and api_liberada(agente_id)


def dias_para_renovar() -> int:
    """Dias até o crédito renovar (virada do mês), contando hoje."""
    hoje = datetime.now(timezone.utc)
    return calendar.monthrange(hoje.year, hoje.month)[1] - hoje.day + 1


def reserva_prioritarios() -> float:
    """Fração do crédito guardada para os agentes prioritários (maior quanto mais longe da renovação)."""
    dias = dias_para_renovar()
    return next(fracao for minimo, fracao in config.RESERVA_PRIORITARIOS if dias >= minimo)


def api_liberada(agente_id: str = "") -> bool:
    """Pode usar a API do Claude agora?
    - Prioritários (Social Media, Construtor): até o fim do crédito utilizável do mês, podendo adiantar o ritmo diário.
    - Demais: no ritmo diário e sem tocar na reserva dos prioritários (eles ainda têm o Max, os gratuitos e o local)."""
    utilizavel = config.CREDITO_MENSAL_ANTHROPIC_USD * config.FRACAO_UTILIZAVEL
    gasto = gasto_mes_usd()
    if agente_id in config.AGENTES_API_PRIORITARIOS:
        return gasto < utilizavel
    return gasto < min(liberado_ate_hoje_usd(), utilizavel * (1 - reserva_prioritarios()))


def liberado_ate_hoje_usd() -> float:
    """Crédito proporcional ao dia do mês: dias sem uso acumulam para os seguintes."""
    hoje = datetime.now(timezone.utc)
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    return config.CREDITO_MENSAL_ANTHROPIC_USD * config.FRACAO_UTILIZAVEL * hoje.day / dias_no_mes


def orcamento_pausado(agente_id: str = "") -> bool:
    """API do Claude bloqueada para este agente (sem agente: para os não prioritários)."""
    return not api_liberada(agente_id)
