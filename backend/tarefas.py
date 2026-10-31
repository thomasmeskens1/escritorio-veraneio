"""Registro das tarefas (SQLite): dificuldade, tempo, modelo, custo e fila adiada."""

import calendar
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import config

log = logging.getLogger("veraneio.tarefas")

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
-- Livro de gastos da API: cada chamada paga entra na hora (tentativas que falham ou estouram o tempo também).
CREATE TABLE IF NOT EXISTS gastos_api (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    em TEXT NOT NULL,
    tarefa_id INTEGER,
    agente TEXT,
    modelo TEXT,
    dificuldade TEXT,
    custo_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gastos_em ON gastos_api(em);
-- Consultas mais frequentes (histórico do chat, andamento, painel, registro).
CREATE INDEX IF NOT EXISTS idx_tarefas_chat ON tarefas(usuario, andar, agente, id);
CREATE INDEX IF NOT EXISTS idx_tarefas_status ON tarefas(status);
CREATE INDEX IF NOT EXISTS idx_eventos_tipo ON eventos(tipo, em);
"""

# Colunas adicionadas depois da primeira versão do banco (migração simples).
_COLUNAS_NOVAS = {"tentativas_fila": "INTEGER NOT NULL DEFAULT 0", "proxima_tentativa": "TEXT",
                  "anexos": "TEXT", "contexto_anexos": "TEXT",  # anexos: JSON com os ids
                  "empresa": "TEXT NOT NULL DEFAULT 'casa_veraneio'"}  # empresas.py: nunca misturar

MAX_TENTATIVAS_FILA = 6  # mínimo de tentativas reais antes de desistir (e só depois de PRAZO_FILA)

_conexao: sqlite3.Connection | None = None


class _ConexaoCompartilhada(sqlite3.Connection):
    """A conexão é uma só para o loop e as threads dos agentes. Sem trava, duas threads abriam transação ao mesmo
    tempo ("cannot start a transaction within a transaction") e o rollback de uma desfazia o INSERT da outra
    (Francielle, 30/10/2026: tarefas 133 e 134). Agora cada comando e cada bloco `with db:` é atômico: enquanto uma
    thread está num bloco, as outras esperam o commit/rollback dela. Comando de escrita fora de bloco grava na hora
    (antes ficava pendurado na transação de quem fizesse o próximo commit ou rollback)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._trava = threading.RLock()
        self._local = threading.local()  # profundidade de blocos `with` desta thread

    def __enter__(self):
        self._trava.acquire()
        self._local.blocos = getattr(self._local, "blocos", 0) + 1
        try:
            return super().__enter__()
        except BaseException:
            self._local.blocos -= 1
            self._trava.release()
            raise

    def __exit__(self, *erro):
        try:
            return super().__exit__(*erro)
        finally:
            self._local.blocos -= 1
            self._trava.release()

    def _avulso(self, metodo, *args, **kwargs):
        with self._trava:
            cursor = metodo(*args, **kwargs)
            if not getattr(self._local, "blocos", 0) and self.in_transaction:
                self.commit()
            return cursor

    def execute(self, *args, **kwargs):
        return self._avulso(super().execute, *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._avulso(super().executemany, *args, **kwargs)

    def executescript(self, *args, **kwargs):
        with self._trava:
            return super().executescript(*args, **kwargs)


def _agora(depois: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + depois).strftime("%Y-%m-%dT%H:%M:%SZ")


def _db() -> sqlite3.Connection:
    global _conexao
    if _conexao is None:
        config.ARQUIVO_BANCO.parent.mkdir(parents=True, exist_ok=True)
        _migrar_para_o_volume()
        _restaurar_da_copia()
        _conexao = sqlite3.connect(config.ARQUIVO_BANCO, check_same_thread=False, factory=_ConexaoCompartilhada)
        _conexao.row_factory = sqlite3.Row
        if config.ARQUIVO_BANCO.parent != config.DADOS_DIR:  # WAL só é seguro fora da pasta compartilhada
            _conexao.execute("PRAGMA journal_mode=WAL")
            _conexao.execute("PRAGMA synchronous=NORMAL")
        _conexao.executescript(_ESQUEMA)
        existentes = {linha["name"] for linha in _conexao.execute("PRAGMA table_info(tarefas)")}
        for coluna, tipo in _COLUNAS_NOVAS.items():
            if coluna not in existentes:
                _conexao.execute(f"ALTER TABLE tarefas ADD COLUMN {coluna} {tipo}")
        if not _conexao.execute("SELECT 1 FROM gastos_api LIMIT 1").fetchone():  # 1ª vez: traz o que já foi gasto
            with _conexao:
                _conexao.execute("INSERT INTO gastos_api (em, tarefa_id, agente, modelo, dificuldade, custo_usd) "
                                 "SELECT concluida_em, id, agente, modelo, dificuldade, custo_usd FROM tarefas "
                                 "WHERE custo_usd > 0 AND concluida_em IS NOT NULL")
    return _conexao


def _migrar_para_o_volume() -> None:
    """1ª subida com o banco no volume: copia (de forma consistente) o banco antigo de dados/ e guarda o antigo
    como .migrado, para nunca haver dois bancos "vivos"."""
    antigo = config.DADOS_DIR / "escritorio.db"
    if config.ARQUIVO_BANCO == antigo or config.ARQUIVO_BANCO.exists() or not antigo.exists():
        return
    origem, destino = sqlite3.connect(antigo), sqlite3.connect(config.ARQUIVO_BANCO)
    try:
        origem.backup(destino)
    finally:
        origem.close()
        destino.close()
    antigo.replace(antigo.with_suffix(".db.migrado"))


class BancoAusente(RuntimeError):
    """O banco do volume sumiu e as cópias existentes estão estragadas: subir vazio apagaria o histórico."""


def _copias() -> list:
    return [config.ARQUIVO_COPIA_BANCO, config.ARQUIVO_COPIA_BANCO.with_suffix(".db.anterior")]


def _abrir_so_leitura(arquivo) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True)


def _integro(arquivo) -> bool:
    try:
        conexao = _abrir_so_leitura(arquivo)
        try:
            return conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conexao.close()
    except sqlite3.Error:
        return False


def _total_de_tarefas(conexao: sqlite3.Connection) -> int:
    try:
        return conexao.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]
    except sqlite3.Error:
        return 0


def _restaurar_da_copia() -> None:
    """Revisão de 30/10/2026 (item 1.5): um "Clean/Purge data" do Docker Desktop apaga o volume, e o sistema subia
    com um banco vazio que, horas depois, ainda substituía a cópia boa. Agora o banco volta da cópia em dados/;
    sem cópia nenhuma (primeira instalação) sobe vazio; com cópias, mas estragadas, recusa subir."""
    if config.ARQUIVO_BANCO.parent == config.DADOS_DIR or config.ARQUIVO_BANCO.exists():
        return
    existentes = [c for c in _copias() if c.exists()]
    for copia in existentes:
        if not _integro(copia):
            continue
        origem, destino = _abrir_so_leitura(copia), sqlite3.connect(config.ARQUIVO_BANCO)
        try:
            origem.backup(destino)
        finally:
            origem.close()
            destino.close()
        log.warning("Banco do volume não encontrado: restaurado de %s.", copia.name)
        return
    if existentes:
        raise BancoAusente("O banco do volume sumiu e as cópias em dados/ estão estragadas. Restaure um backup com "
                           "scripts/restaurar_banco.py antes de subir o sistema.")


def copiar_para_backup() -> None:
    """Cópia consistente do banco em dados/ para o backup diário do Windows (que não enxerga o volume). Nunca troca
    a cópia por uma com menos tarefas (banco recriado vazio) nem por uma estragada; a anterior fica como .anterior."""
    if config.ARQUIVO_BANCO.parent == config.DADOS_DIR:
        return
    temporario = config.ARQUIVO_COPIA_BANCO.with_suffix(".tmp")
    # Conexão própria só para a cópia: na conexão do servidor, a cópia segurava o banco e congelava os chats por
    # alguns segundos (revisão de 30/10/2026). No WAL, essa leitura não trava quem escreve; num passo só, a cópia
    # não recomeça quando o servidor grava no meio.
    origem, destino = sqlite3.connect(config.ARQUIVO_BANCO, timeout=30), sqlite3.connect(temporario)
    try:
        origem.backup(destino)
        destino.execute("PRAGMA journal_mode=DELETE")  # a cópia herdava o WAL e deixava -wal/-shm em dados/
        novas = _total_de_tarefas(destino)
    finally:
        origem.close()
        destino.close()
    if not _integro(temporario):
        temporario.unlink(missing_ok=True)
        raise RuntimeError("A cópia do banco saiu estragada (integrity_check); a cópia anterior foi mantida.")
    if config.ARQUIVO_COPIA_BANCO.exists():
        atual = _abrir_so_leitura(config.ARQUIVO_COPIA_BANCO)
        try:
            antigas = _total_de_tarefas(atual)
        finally:
            atual.close()
        if novas < antigas:
            temporario.unlink(missing_ok=True)
            raise RuntimeError(f"O banco tem menos tarefas ({novas}) que a cópia ({antigas}); a cópia foi mantida. "
                               "Confira se o volume do Docker foi apagado (scripts/restaurar_banco.py).")
        config.ARQUIVO_COPIA_BANCO.replace(config.ARQUIVO_COPIA_BANCO.with_suffix(".db.anterior"))
    temporario.replace(config.ARQUIVO_COPIA_BANCO)


def iniciar() -> None:
    """Tarefas interrompidas por reinício do servidor voltam para a fila."""
    with _db() as db:
        db.execute("UPDATE tarefas SET status='adiada', motivo='Servidor reiniciado durante a execução.' "
                   "WHERE status='executando'")


def criar(usuario: str, andar: str, agente: str, texto: str, dificuldade: str, empresa: str = "casa_veraneio") -> int:
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO tarefas (usuario, andar, agente, texto, dificuldade, status, criada_em, empresa) "
            "VALUES (?, ?, ?, ?, ?, 'executando', ?, ?)",
            (usuario, andar, agente, texto, dificuldade, _agora(), empresa),
        )
        return cursor.lastrowid


MOTIVO_PARADA = "Solicitação parada"  # botão "Parar" ou formulário fechado (parar.py)


def parada(tarefa_id: int) -> bool:
    """A tarefa foi parada pelo usuário: nada mais muda o status dela (o resultado que chegar depois é descartado)."""
    linha = _db().execute("SELECT status, motivo FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
    return bool(linha) and linha["status"] == "falhou" and (linha["motivo"] or "").startswith(MOTIVO_PARADA)


def atualizar(tarefa_id: int, **campos) -> None:
    if "status" in campos and parada(tarefa_id):
        return  # parada: o modelo, a fila ou o Max terminaram depois do "Parar"; não volta a rodar nem é entregue
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


# Brainstorm de 31/10/2026 (despachante-18): espera crescente e prazo de 24 h no lugar das 6 tentativas de 30 em 30 min.
ESPERAS_FILA = (timedelta(minutes=15), timedelta(minutes=30), timedelta(minutes=60))
ESPERA_SEM_MODELO = timedelta(minutes=5)  # nenhum modelo chegou a rodar (Max ou local ocupados): não conta tentativa
PRAZO_FILA = timedelta(hours=24)


def reagendar(tarefa_id: int, rodou_modelo: bool = True) -> bool:
    """Devolve a tarefa à fila para daqui a pouco; False se passou do prazo (24 h) depois de MAX_TENTATIVAS_FILA."""
    linha = obter(tarefa_id)
    vencida = (linha["criada_em"] or "") < _agora(-PRAZO_FILA)
    if not rodou_modelo:
        if vencida:
            return False
        atualizar(tarefa_id, status="adiada", proxima_tentativa=_agora(ESPERA_SEM_MODELO))
        return True
    tentativas = linha["tentativas_fila"] + 1
    if tentativas >= MAX_TENTATIVAS_FILA and vencida:
        return False
    atualizar(tarefa_id, status="adiada", tentativas_fila=tentativas,
              proxima_tentativa=_agora(ESPERAS_FILA[min(tentativas, len(ESPERAS_FILA)) - 1]))
    return True


def falhas_de_modelo_desde(tarefa_id: int, desde: str) -> int:
    """Falhas de modelos que de fato rodaram (sem "Max ocupado") desde `desde` (ISO UTC)."""
    return _db().execute("SELECT COUNT(*) FROM eventos WHERE tarefa_id = ? AND tipo = 'falha_modelo' AND em >= ? "
                         "AND COALESCE(detalhe, '') NOT LIKE 'Max ocupado%'", (tarefa_id, desde)).fetchone()[0]


def historico(usuario: str, andar: str, agente: str, antes_de: int, limite: int = 3,
              empresa: str | None = None) -> list[sqlite3.Row]:
    """Últimas trocas concluídas com o mesmo agente e da MESMA empresa (contexto para qualquer modelo)."""
    filtro, extra = ("AND empresa = ? ", (empresa,)) if empresa else ("", ())
    linhas = _db().execute(
        "SELECT texto, resposta, criada_em FROM tarefas WHERE usuario = ? AND andar = ? AND agente = ? "
        f"AND status = 'concluida' AND id < ? {filtro}ORDER BY id DESC LIMIT ?",
        (usuario, andar, agente, antes_de, *extra, limite),
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


def registrar_gasto(tarefa_id: int | None, agente: str, modelo: str, custo_usd: float) -> None:
    """Toda chamada paga à API, na hora: o orçamento enxerga também tentativas que falharam ou estouraram o tempo."""
    if custo_usd <= 0:
        return
    tarefa = obter(tarefa_id) if tarefa_id else None
    with _db() as db:
        db.execute("INSERT INTO gastos_api (em, tarefa_id, agente, modelo, dificuldade, custo_usd) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   (_agora(), tarefa_id or None, agente, modelo, tarefa["dificuldade"] if tarefa else None, custo_usd))


def gasto_mes_usd(dificuldade: str | None = None) -> float:
    inicio = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    filtro, params = ("AND dificuldade = ?", (dificuldade,)) if dificuldade else ("", ())
    linha = _db().execute(
        f"SELECT COALESCE(SUM(custo_usd), 0) FROM gastos_api WHERE em >= ? {filtro}", (inicio, *params)
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
