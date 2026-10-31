"""Saúde dos modelos: quem falha sai da rota por um tempo; quem falha sempre é afastado por dias.

Tudo fica no banco (sobrevive a reinícios). Teste real: o Nemotron Super deu "404 not found" 17 vezes em
dois dias porque a pausa vivia só na memória e cada reinício da API devolvia o modelo à rota.

- Cota/crédito/limite: pausa até a cota voltar (meia-noite UTC, próximo mês, 2 min).
- Estourou o tempo: pausa de 15 min (antes o mesmo modelo lento era tentado de novo em toda tarefa).
- Indisponível no provedor (404) ou erro desconhecido: pausa curta (6 h / 1 min) e, na 3ª falha do mesmo tipo
  em 24 h, o modelo é AFASTADO por 7 dias. Ao voltar, fica 7 dias "em teste": uma nova falha afasta de novo;
  um sucesso limpa o histórico.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("veraneio.saude")

RECORRENTES = {"indisponivel", "erro"}  # tipos que contam para o afastamento (cota e limite são esperados)
REPETICOES_PARA_AFASTAR = 3
JANELA_S = 24 * 3600
AFASTAMENTO_S = 7 * 24 * 3600
TESTE_S = 7 * 24 * 3600
RETENCAO_S = 30 * 24 * 3600  # falhas mais antigas saem do banco

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS saude_modelos (
    modelo TEXT PRIMARY KEY, ate REAL NOT NULL, motivo TEXT NOT NULL, tipo TEXT NOT NULL,
    afastamentos INTEGER NOT NULL DEFAULT 0, em_teste_ate REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS falhas_modelos (
    id INTEGER PRIMARY KEY, modelo TEXT NOT NULL, tipo TEXT NOT NULL, em REAL NOT NULL, erro TEXT);
CREATE INDEX IF NOT EXISTS idx_falhas_modelos ON falhas_modelos (modelo, tipo, em);
"""

# Plano Max sem cota (janela de 5 h) ou deslogado: o Max volta sozinho; 30 min fora e tenta de novo.
SEM_COTA_MAX = ("usage limit", "limit reached", "5-hour limit", "out of usage", "limit will reset",
                "not logged in", "/login")
PAUSA_SEM_COTA_MAX_S = 30 * 60
NUNCA_AFASTAR = ("claude-code/",)  # o Max é nosso: falha dele pausa, mas não o tira da rota por 7 dias


class FalhaDoModelo(Exception):
    """O modelo respondeu mal ou o Max devolveu falha: a tarefa segue para o próximo modelo da rota. Sem esta
    marca, o erro nasce num arquivo do backend e o orquestrador o tomaria por "erro interno" (revisão de 30/10/2026:
    Max sem cota ou plano sem JSON encerravam a tarefa em vez de tentar outro modelo). `ja_registrada`: a falha já foi
    contada no modelo que de fato rodou (ex.: a API reserva numa etapa do Max)."""

    def __init__(self, mensagem: str = "", ja_registrada: bool = False):
        super().__init__(mensagem)
        self.ja_registrada = ja_registrada


_trava = threading.Lock()
_cache: dict[str, float] | None = None  # modelo -> até quando fica fora (lido do banco uma vez)


_pronto = False  # tabelas criadas uma vez por processo


def _db():
    global _pronto
    import tarefas  # import tardio: tarefas importa config e o banco

    db = tarefas._db()
    if not _pronto:
        db.executescript(_ESQUEMA)
        _pronto = True
    return db


def _ate_cache() -> dict[str, float]:
    global _cache
    if _cache is None:
        _cache = {l["modelo"]: l["ate"] for l in _db().execute("SELECT modelo, ate FROM saude_modelos")}
    return _cache


def _proxima_meia_noite_utc() -> float:
    amanha = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime(amanha.year, amanha.month, amanha.day, tzinfo=timezone.utc).timestamp()


def _proximo_mes_utc() -> float:
    hoje = datetime.now(timezone.utc)
    ano, mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
    return datetime(ano, mes, 1, tzinfo=timezone.utc).timestamp()


def _classificar(erro: str) -> tuple[str, float, str]:
    """(tipo, até quando fica fora, motivo) conforme o erro."""
    texto = erro.lower()
    agora = time.time()
    if any(m in texto for m in SEM_COTA_MAX):              # plano Max: janela de uso esgotada ou login vencido
        return "cota", agora + PAUSA_SEM_COTA_MAX_S, "plano Max sem cota agora (ou deslogado)"
    if "credit balance" in texto:                          # crédito Anthropic do mês acabou
        return "credito", _proximo_mes_utc(), "crédito do mês esgotado"
    if "per-day" in texto or "per day" in texto:          # cota diária gratuita (OpenRouter)
        return "cota", _proxima_meia_noite_utc(), "cota diária esgotada"
    # Revisão de 30/10/2026 (2.10): pedido grande demais não é falha do modelo; sobrecarga e resposta vazia são
    # passageiras (antes contavam como erro recorrente e 3 em 24 h afastavam o modelo por 7 dias).
    if "413" in texto or "too large" in texto or "request_too_large" in texto:
        return "grande", agora, "pedido grande demais para este modelo"
    if any(m in texto for m in ("503", "overloaded", "unavailable", "none or empty", "empty response")):
        return "limite", agora + 5 * 60, "sobrecarregado ou resposta vazia"
    if "429" in texto or "rate" in texto:                 # limite por minuto ou provedor sobrecarregado
        return "limite", agora + 120, "limite temporário"
    if texto.startswith("excedeu"):                        # timeout: modelo lento agora, tenta outro por 15 min
        return "lento", agora + 15 * 60, "lento demais (estourou o tempo)"
    if "404" in texto or "not found" in texto:            # modelo fora do ar no provedor
        return "indisponivel", agora + 6 * 3600, "indisponível no provedor"
    return "erro", agora + 60, "erro recente"              # erro desconhecido: pausa curta


def registrar_falha(modelo: str, erro: str) -> None:
    """Grava a falha e decide por quanto tempo o modelo sai da rota (afasta por 7 dias se for recorrente)."""
    tipo, ate, motivo = _classificar(erro)
    agora = time.time()
    with _trava, _db() as db:
        db.execute("INSERT INTO falhas_modelos (modelo, tipo, em, erro) VALUES (?, ?, ?, ?)",
                   (modelo, tipo, agora, erro[:300]))
        db.execute("DELETE FROM falhas_modelos WHERE em < ?", (agora - RETENCAO_S,))
        atual = db.execute("SELECT afastamentos, em_teste_ate FROM saude_modelos WHERE modelo = ?",
                           (modelo,)).fetchone()
        afastamentos, em_teste_ate = (atual["afastamentos"], atual["em_teste_ate"]) if atual else (0, 0)
        if tipo in RECORRENTES and not modelo.startswith(NUNCA_AFASTAR):
            repeticoes = db.execute("SELECT COUNT(*) FROM falhas_modelos WHERE modelo = ? AND tipo = ? AND em >= ?",
                                    (modelo, tipo, agora - JANELA_S)).fetchone()[0]
            em_teste = em_teste_ate > agora
            if em_teste or repeticoes >= REPETICOES_PARA_AFASTAR:
                afastamentos += 1
                motivo = (f"afastado: voltou em teste e falhou de novo ({motivo})" if em_teste else
                          f"afastado: {repeticoes} falhas em 24 h ({motivo})")
                tipo, ate = "afastado", agora + AFASTAMENTO_S
                em_teste_ate = ate + TESTE_S
                log.warning("Modelo %s afastado por 7 dias: %s", modelo, motivo)
        db.execute("INSERT OR REPLACE INTO saude_modelos (modelo, ate, motivo, tipo, afastamentos, em_teste_ate) "
                   "VALUES (?, ?, ?, ?, ?, ?)", (modelo, ate, motivo, tipo, afastamentos, em_teste_ate))
        _ate_cache()[modelo] = ate


def devolver_a_rota(modelo: str) -> bool:
    """Botão da Diretoria no painel: o modelo volta à rota agora (o histórico de falhas fica)."""
    with _trava, _db() as db:
        mudou = db.execute("UPDATE saude_modelos SET ate = 0 WHERE modelo = ?", (modelo,)).rowcount
        _ate_cache()[modelo] = 0
    return bool(mudou)


def registrar_sucesso(modelo: str) -> None:
    """Modelo respondeu: se estava em teste depois de um afastamento, o histórico de afastamentos é limpo."""
    with _trava, _db() as db:
        db.execute("UPDATE saude_modelos SET afastamentos = 0, em_teste_ate = 0 "
                   "WHERE modelo = ? AND (afastamentos > 0 OR em_teste_ate > 0) AND ate <= ?", (modelo, time.time()))


def disponivel(modelo: str) -> bool:
    return time.time() >= _ate_cache().get(modelo, 0)


def resumo() -> list[dict]:
    """Modelos fora da rota agora (para o painel), afastados primeiro."""
    agora = time.time()
    linhas = _db().execute(
        "SELECT s.*, (SELECT COUNT(*) FROM falhas_modelos f WHERE f.modelo = s.modelo AND f.em >= ?) AS falhas_24h "
        "FROM saude_modelos s WHERE s.ate > ? ORDER BY s.tipo = 'afastado' DESC, s.ate DESC", (agora - JANELA_S, agora))
    return [{"modelo": l["modelo"], "motivo": l["motivo"], "afastado": l["tipo"] == "afastado",
             "falhas_24h": l["falhas_24h"],
             "volta_em": datetime.fromtimestamp(l["ate"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            for l in linhas]


def estatisticas(dias: int = 7) -> list[dict]:
    """Por modelo, nos últimos `dias`: tentativas, falhas, taxa de falha e tempo médio das respostas concluídas."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = _db().execute(
        "SELECT e.modelo, SUM(e.tipo = 'tentativa') AS tentativas, "
        "SUM(e.tipo = 'falha_modelo' AND COALESCE(e.detalhe, '') NOT LIKE 'Max ocupado%') AS falhas, "
        "(SELECT AVG(t.tempo_segundos) FROM tarefas t WHERE t.modelo = e.modelo AND t.status = 'concluida' "
        " AND t.concluida_em >= ?) AS tempo_medio "
        "FROM eventos e WHERE e.em >= ? AND e.modelo IS NOT NULL AND e.tipo IN ('tentativa', 'falha_modelo') "
        "GROUP BY e.modelo HAVING tentativas > 0 ORDER BY tentativas DESC", (desde, desde))
    return [{"modelo": l["modelo"], "tentativas": l["tentativas"], "falhas": l["falhas"],
             "taxa_falha": round(l["falhas"] / l["tentativas"], 2),
             "tempo_medio_s": round(l["tempo_medio"], 1) if l["tempo_medio"] else None} for l in linhas]


BACKUP_ATRASADO_H = 36


def aviso_backup() -> str | None:
    """Último "Backup ok" do backup diário do Windows (scripts/backup_dados.py) há mais de 36 h: aviso no painel da
    Diretoria (revisão de 30/10/2026: dias sem backup só ficavam registrados no backup.log)."""
    import config  # import tardio: config lê o ambiente

    try:
        linhas = config.ARQUIVO_LOG_BACKUP.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "Nenhum backup diário registrado ainda (backup.log não encontrado)."
    falhas = 0
    for linha in reversed(linhas):
        if "Backup FALHOU" in linha:
            falhas += 1
        if "Backup ok" in linha:
            try:
                ultimo = datetime.strptime(linha[1:20], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            horas = (datetime.now() - ultimo).total_seconds() / 3600  # o log usa a hora local do PC
            if horas > BACKUP_ATRASADO_H:
                return (f"Último backup diário bom foi há {horas / 24:.1f} dias ({ultimo:%d/%m %H:%M})"
                        + (f"; {falhas} tentativa(s) falharam depois." if falhas else "."))
            return None
    return "Nenhum backup diário bom registrado no backup.log."


# --- Diagnóstico da operação (revisão de 30/10/2026, 2.29, 2.30 e 2.31): antes /api/saude sempre dizia "ok" e as
# falhas do trabalhador, do Ollama e da rota só iam para os logs. Os avisos aparecem no painel da Diretoria.
TRABALHADOR_FORA_MIN = 5
ROTA_MINIMA = 2  # gratuitos no ar abaixo disso: a rota encolheu


def banco_ok() -> bool:
    try:
        _db().execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def ollama_ok() -> bool:
    import httpx

    import config

    try:
        return httpx.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def avisos_da_operacao() -> list[str]:
    """Problemas de operação agora, em linguagem simples (vazio = tudo certo)."""
    import config
    import max_texto

    avisos = [a for a in [aviso_backup()] if a]
    try:
        parado_s = time.time() - max_texto.ARQUIVO_CONTATO.stat().st_mtime
    except OSError:
        parado_s = None
    fila = _db().execute("SELECT COUNT(*) FROM tarefas WHERE status = 'producao'").fetchone()[0]
    if parado_s is None or parado_s > TRABALHADOR_FORA_MIN * 60:
        quanto = "nunca respondeu" if parado_s is None else f"sem responder há {int(parado_s // 60)} min"
        avisos.append(f"Trabalhador do Max {quanto}" + (f", com {fila} peça(s) na fila" if fila else "")
                      + ". Confira se o PC está ligado e se o trabalhador está rodando.")
    if not ollama_ok():
        avisos.append("Ollama fora do ar: o Cérebro está só com a busca por palavras e o modelo local de reserva "
                      "não funciona. Abra o Ollama no PC.")
    import agentes_dinamicos  # agente novo proposto e parado (construtor-02/27): aparece aqui até alguém decidir

    if (propostas := agentes_dinamicos.propostas_pendentes()):
        avisos.append(f"{propostas} agente(s) proposto(s) pelo Construtor esperando a aprovação de quem pediu "
                      "(chat do Construtor: Aprovar, Pedir ajuste ou Descartar).")
    no_ar = [m for m in config.modelos_gratuitos() if config.modelo_disponivel(m) and disponivel(m)]
    if len(no_ar) < ROTA_MINIMA:
        avisos.append(f"Só {len(no_ar)} modelo(s) gratuito(s) no ar agora: as tarefas podem cair no modelo local "
                      "(lento). Veja \"Modelos fora da rota\" abaixo.")
    import cerebro_prova  # prova semanal do Cérebro (cerebro-06): retreino descartado, nota em queda, gabarito velho

    return avisos + avisos_da_caixa_de_areia() + cerebro_prova.avisos()


def avisos_da_caixa_de_areia() -> list[str]:
    """Peças em que a caixa de areia barrou leitura de segredo, rede ou programa nas últimas 24 h (brainstorm de
    31/10/2026, despachante-27): pode ser instrução escondida num pedido, PDF ou item do Monday."""
    import producao  # import tardio: a produção importa este módulo

    try:
        bloqueios = producao.bloqueios_recentes()
    except Exception:  # aviso nunca derruba o painel
        log.exception("Não foi possível ler os bloqueios da caixa de areia.")
        return []
    return [f"Caixa de areia: a peça da tarefa {b['tarefa_id']} (usuário {b['usuario']}"
            + (f", item do Monday {b['monday']}" if b["monday"] else "")
            + f") teve {b['total']} tentativa(s) barrada(s), ex.: {b['exemplo'][:140]}. Confira o pedido, os anexos e "
              "as referências: pode ser uma instrução escondida." for b in bloqueios]
