"""Sinais de aprendizado, só registrados (Onda 2, N2-cerebro-20): os sinais que o sistema já tem viram linhas de uma
tabela (tipo, agente, empresa, data), para treinar o Cérebro quando houver volume e um sinal único de aprovação.

Por que: a rede do Cérebro precisa de 30 negativos e o histórico tinha 1 👎 para 13 👍. Os sinais implícitos (ajuste
logo depois da entrega, autocorreção do agente) destravam isso sem pedir mais cliques à equipe.

Regras desta fase:
- NADA é treinado e nada muda o prompt: a tabela só é lida pelo resumo da Diretoria;
- nada se apaga (memória "aprendizado nunca se perde"): troca de voto vira linha nova, nunca UPDATE/DELETE;
- peso menor para o sinal implícito que para o humano; a origem fica registrada (`origem` e `chave`, única).

Fontes:
- 👍/👎: avaliacoes.avaliar chama registrar_voto na hora (guarda a troca de voto, que a tabela de votos sobrescreve);
- correção e elogio no chat (observacoes), reação negativa escrita (insatisfacoes) e, nas tarefas, o ajuste logo
  depois da entrega e a autocorreção: varrer() lê o que entrou desde a última vez (marcas por fonte).
"""

import logging
import re
from datetime import datetime, timedelta

import tarefas

log = logging.getLogger(__name__)

# tipo: (nome na tela, peso, valor padrão). Peso 1 = sinal humano explícito.
TIPOS = {
    "voto": ("👍/👎 na resposta", 1.0, 0),
    "voto_retirado": ("Voto retirado", 0.0, 0),
    "correcao": ("Correção explícita no chat", 1.0, -1),
    "elogio": ("Elogio no chat", 1.0, 1),
    "reacao_negativa": ("Reação negativa escrita (com motivo)", 1.0, -1),
    "ajuste_logo_depois": ("Ajuste pedido logo depois da entrega", 0.5, -1),
    "autocorrecao": ("O agente corrigiu a própria resposta", 0.3, -1),
}
JANELA_H = 24             # ajuste ou autocorreção até 24 h depois da entrega (mesma janela das correções)
LOTE_VARREDURA = 2000
TRAVA_PENDENTE_H = 48     # tarefa ainda rodando segura a marca; presa há mais que isso, é pulada
# Autocorreção na resposta (cerebro-18: nas tarefas 91 e 92 o próprio Cérebro corrigiu a 90, que nunca recebeu 👎).
AUTOCORRECAO = re.compile(
    r"\b(corrigindo (a|minha) (resposta|informa[cç][aã]o) anterior|na (minha )?resposta anterior,? (eu )?"
    r"(errei|me enganei|informei errado|disse errado|passei errado)|me enganei|errei (na|no|ao|quando)|"
    r"retifico|retificando|corre[cç][aã]o (da|sobre a|na) (minha )?resposta anterior|"
    r"(desculpe|desculpa|pe[cç]o desculpas)(,)? (pelo|o|por esse|por este) erro)", re.IGNORECASE)
INICIO_RESPOSTA = 800     # a autocorreção aparece no começo da resposta

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS sinais_aprendizado (
    id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, registrado_em TEXT NOT NULL, tipo TEXT NOT NULL,
    agente TEXT NOT NULL, empresa TEXT NOT NULL DEFAULT '*', tarefa_id INTEGER, usuario TEXT,
    valor INTEGER NOT NULL DEFAULT 0, peso REAL NOT NULL, origem TEXT, chave TEXT NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS idx_sinais_tarefa ON sinais_aprendizado(tarefa_id);
CREATE TABLE IF NOT EXISTS sinais_marcas (fonte TEXT PRIMARY KEY, ultimo_id INTEGER NOT NULL);
"""
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.executescript(_ESQUEMA)
        _pronto = True
    return db


def registrar(tipo: str, agente: str, empresa: str | None, em: str, chave: str, tarefa_id: int | None = None,
              usuario: str = "", valor: int | None = None, origem: str = "") -> bool:
    """Grava o sinal uma vez só (a `chave` é única). Devolve True se entrou agora."""
    _, peso, padrao = TIPOS[tipo]
    with _db() as db:
        return db.execute(
            "INSERT OR IGNORE INTO sinais_aprendizado (em, registrado_em, tipo, agente, empresa, tarefa_id, usuario, "
            "valor, peso, origem, chave) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (em or tarefas._agora(), tarefas._agora(), tipo, agente or "*", empresa or "*", tarefa_id, usuario or None,
             padrao if valor is None else valor, peso, origem or None, chave)).rowcount > 0


def registrar_voto(linha, usuario: str, valor: int, em: str) -> None:
    """👍/👎 (ou voto retirado) da tarefa `linha`. Nunca derruba o voto: erro aqui só vai para o log."""
    try:
        registrar("voto" if valor else "voto_retirado", linha["agente"], linha["empresa"], em,
                  f"voto:{linha['id']}:{em}:{valor}", linha["id"], usuario, valor, "avaliacoes")
    except Exception:
        log.exception("Sinais: não registrou o voto da tarefa %s.", linha["id"])


# --- Varredura das fontes que já existem ----------------------------------------------------------------------

def _marca(fonte: str) -> int:
    linha = _db().execute("SELECT ultimo_id FROM sinais_marcas WHERE fonte = ?", (fonte,)).fetchone()
    return linha["ultimo_id"] if linha else 0


def _marcar(fonte: str, ultimo_id: int) -> None:
    with _db() as db:
        db.execute("INSERT INTO sinais_marcas VALUES (?, ?) ON CONFLICT(fonte) DO UPDATE SET ultimo_id = "
                   "MAX(ultimo_id, excluded.ultimo_id)", (fonte, ultimo_id))


def _tabela(nome: str) -> bool:
    return bool(_db().execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nome,)).fetchone())


def _votos_antigos() -> int:
    """Uma vez: os votos que já estavam na tabela antes deste registro (mesma chave do registrar_voto)."""
    if _marca("avaliacoes") or not _tabela("avaliacoes"):
        return 0
    novos = 0
    for v in _db().execute("SELECT a.tarefa_id, a.usuario, a.valor, a.em, t.agente, t.empresa FROM avaliacoes a "
                           "JOIN tarefas t ON t.id = a.tarefa_id"):
        novos += registrar("voto", v["agente"], v["empresa"], v["em"], f"voto:{v['tarefa_id']}:{v['em']}:{v['valor']}",
                           v["tarefa_id"], v["usuario"], v["valor"], "avaliacoes")
    _marcar("avaliacoes", 1)
    return novos


def _observacoes() -> int:
    """Correção e elogio no chat. O comentário do 👍/👎 também vira observação, mas já conta como voto: fica de fora."""
    if not _tabela("observacoes"):
        return 0
    novos, ultimo = 0, _marca("observacoes")
    votos = _tabela("avaliacoes")
    for o in _db().execute(
            "SELECT o.id, o.em, o.usuario, o.agente, o.tipo, o.tarefa_anterior, o.correcao, t.empresa FROM observacoes o "
            "LEFT JOIN tarefas t ON t.id = o.tarefa_anterior WHERE o.id > ? ORDER BY o.id LIMIT ?",
            (ultimo, LOTE_VARREDURA)).fetchall():
        ultimo = o["id"]
        if o["tipo"] not in ("correcao", "elogio") or o["usuario"] == "cerebro":
            continue
        if votos and o["tarefa_anterior"] and _db().execute(
                "SELECT 1 FROM avaliacoes WHERE tarefa_id = ? AND usuario = ? AND comentario = ?",
                (o["tarefa_anterior"], o["usuario"], o["correcao"])).fetchone():
            continue
        novos += registrar(o["tipo"], o["agente"], o["empresa"], o["em"], f"obs:{o['id']}", o["tarefa_anterior"],
                           o["usuario"], origem=f"observacoes:{o['id']}")
    _marcar("observacoes", ultimo)
    return novos


def _insatisfacoes() -> int:
    """Reação negativa escrita no chat (o 👎 do pop-up já entrou como voto)."""
    if not _tabela("insatisfacoes"):
        return 0
    novos, ultimo = 0, _marca("insatisfacoes")
    for i in _db().execute(
            "SELECT i.id, i.em, i.usuario, i.agente, i.tarefa_id, i.origem, t.empresa FROM insatisfacoes i LEFT JOIN "
            "tarefas t ON t.id = i.tarefa_id WHERE i.id > ? ORDER BY i.id LIMIT ?", (ultimo, LOTE_VARREDURA)).fetchall():
        ultimo = i["id"]
        if i["origem"] == "mensagem":
            novos += registrar("reacao_negativa", i["agente"], i["empresa"], i["em"], f"insat:{i['id']}", i["tarefa_id"],
                               i["usuario"], origem=f"insatisfacoes:{i['id']}")
    _marcar("insatisfacoes", ultimo)
    return novos


def _horas_entre(antes: str | None, depois: str | None) -> float | None:
    try:
        formato = "%Y-%m-%dT%H:%M:%SZ"
        return (datetime.strptime(depois, formato) - datetime.strptime(antes, formato)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def _base_da_producao(tarefa_id: int):
    """Peça ajustada ("Ajuste na peça #33"), ligada pela produção (producao_info.base_tarefa_id)."""
    if not _tabela("producao_info"):
        return None
    linha = _db().execute("SELECT base_tarefa_id FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return tarefas.obter(linha["base_tarefa_id"]) if linha and linha["base_tarefa_id"] else None


def _entrega_anterior(t):
    """Última entrega concluída do mesmo agente para a mesma pessoa, antes desta tarefa."""
    return _db().execute(
        "SELECT * FROM tarefas WHERE usuario = ? AND andar = ? AND agente = ? AND status = 'concluida' AND id < ? "
        "AND concluida_em <= ? ORDER BY id DESC LIMIT 1", (t["usuario"], t["andar"], t["agente"], t["id"],
                                                           t["criada_em"])).fetchone()


def _tarefas() -> int:
    """Ajuste logo depois da entrega e autocorreção do agente, a partir das tarefas que já terminaram."""
    import ajustes

    novos, ultimo = 0, _marca("tarefas")
    limite_pendente = tarefas._agora(-timedelta(hours=TRAVA_PENDENTE_H))
    pendente = None  # primeira tarefa que ainda pode terminar: a marca para antes dela (a chave evita repetir)
    for t in _db().execute("SELECT * FROM tarefas WHERE id > ? ORDER BY id LIMIT ?",
                           (ultimo, LOTE_VARREDURA)).fetchall():
        if t["status"] not in ("concluida", "falhou"):
            if pendente is None and t["criada_em"] >= limite_pendente:
                pendente = t["id"]
            elif pendente is None:  # presa há mais de TRAVA_PENDENTE_H: pulada
                ultimo = t["id"]
            continue
        if pendente is None:
            ultimo = t["id"]
        if ajustes.e_ajuste(t["texto"]):
            base = _base_da_producao(t["id"]) or _entrega_anterior(t)
            horas = _horas_entre(base["concluida_em"], t["criada_em"]) if base else None
            if base and horas is not None and 0 <= horas <= JANELA_H:
                novos += registrar("ajuste_logo_depois", base["agente"], base["empresa"], t["criada_em"],
                                   f"ajuste:{t['id']}", base["id"], t["usuario"], origem=f"tarefa:{t['id']}")
        if t["status"] == "concluida" and AUTOCORRECAO.search((t["resposta"] or "")[:INICIO_RESPOSTA]):
            base = _entrega_anterior(t)
            horas = _horas_entre(base["concluida_em"], t["criada_em"]) if base else None
            if base and horas is not None and 0 <= horas <= JANELA_H:
                novos += registrar("autocorrecao", base["agente"], base["empresa"], t["concluida_em"],
                                   f"autocorrecao:{t['id']}", base["id"], t["usuario"], origem=f"tarefa:{t['id']}")
    _marcar("tarefas", ultimo)
    return novos


def varrer() -> int:
    """Registra os sinais que entraram desde a última varredura (idempotente). Devolve quantos entraram."""
    total = 0
    for fonte in (_votos_antigos, _observacoes, _insatisfacoes, _tarefas):
        try:
            total += fonte()
        except Exception:  # uma fonte com problema não segura as outras
            log.exception("Sinais: falha ao varrer %s.", fonte.__name__)
    return total


def resumo(ultimos: int = 30) -> dict:
    """Para a Diretoria: contagens por tipo, agente e empresa e os últimos sinais (sem texto de conversa)."""
    import empresas

    novos = varrer()
    db = _db()

    def contar(coluna: str) -> list[dict]:
        return [{coluna: l[coluna], "total": l["total"], "positivos": l["positivos"], "negativos": l["negativos"],
                 "peso": round(l["peso"] or 0, 2)} for l in db.execute(
            f"SELECT {coluna}, COUNT(*) AS total, SUM(valor > 0) AS positivos, SUM(valor < 0) AS negativos, "
            f"SUM(peso * valor) AS peso FROM sinais_aprendizado GROUP BY {coluna} ORDER BY total DESC")]

    por_tipo = [{**c, "nome": TIPOS.get(c["tipo"], (c["tipo"],))[0]} for c in contar("tipo")]
    por_empresa = [{**c, "empresa_nome": empresas.nome(c["empresa"]) if c["empresa"] != "*" else "—"}
                   for c in contar("empresa")]
    recentes = [dict(l) for l in db.execute(
        "SELECT id, em, tipo, agente, empresa, tarefa_id, valor, peso FROM sinais_aprendizado ORDER BY id DESC LIMIT ?",
        (ultimos,))]
    return {"novos_agora": novos, "total": sum(c["total"] for c in por_tipo), "por_tipo": por_tipo,
            "por_agente": contar("agente"), "por_empresa": por_empresa, "recentes": recentes,
            "tipos": {k: {"nome": v[0], "peso": v[1]} for k, v in TIPOS.items()},
            "observacao": "Só registro: nada é treinado nem entra no prompt ainda (falta o sinal único de aprovação)."}
