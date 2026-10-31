"""Medição do Max (despachante-07, 31/10/2026): quanto cada trabalho do Claude Code consome da cota do plano Max.

Antes o sistema só descobria que a cota tinha acabado quando chegava o erro de limite. Agora, quando um trabalho
termina (concluído ou falho), o backend grava o volume de texto (caracteres de entrada e saída), os tokens, as
rodadas e a duração que o Claude Code devolve na saída JSON, com o tipo do trabalho, o agente e a empresa. O painel
da Diretoria mostra o resumo dos últimos 7 dias. Trabalhador antigo (sem os números de uso): grava o que o backend
sabe (tamanho do pedido e da resposta).
"""

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

import tarefas

log = logging.getLogger("veraneio.uso_max")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS uso_max (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    em TEXT NOT NULL,
    tipo TEXT NOT NULL,              -- texto | anexo | prospeccao | producao
    status TEXT NOT NULL,            -- concluido | falhou
    agente TEXT,
    empresa TEXT,
    tarefa_id INTEGER,
    trabalho_id INTEGER,
    chars_entrada INTEGER NOT NULL DEFAULT 0,
    chars_saida INTEGER NOT NULL DEFAULT 0,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_cache INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    rodadas INTEGER NOT NULL DEFAULT 0,
    duracao_s REAL NOT NULL DEFAULT 0,
    modelo TEXT
);
CREATE INDEX IF NOT EXISTS idx_uso_max_em ON uso_max(em);
"""
TIPOS = {"texto", "anexo", "prospeccao", "producao"}  # "site" é lido pelo Chrome, sem o Claude Code
AGENTE_DO_TIPO = {"prospeccao": "prospectador"}
EMPRESA_DO_TIPO = {"prospeccao": "cv_corporativo"}  # a Prospecção Ativa é do Corporativo
TETO = 10 ** 9  # número absurdo vindo do PC não estraga a soma
_esquema_criado = False


class Uso(BaseModel):
    """Números que o trabalhador envia junto com o resultado (todos opcionais: trabalhador antigo não envia)."""
    chars_entrada: int = Field(0, ge=0, le=TETO)
    chars_saida: int = Field(0, ge=0, le=TETO)
    tokens_entrada: int = Field(0, ge=0, le=TETO)
    tokens_cache: int = Field(0, ge=0, le=TETO)
    tokens_saida: int = Field(0, ge=0, le=TETO)
    rodadas: int = Field(0, ge=0, le=100000)
    duracao_s: float = Field(0, ge=0, le=7 * 86400)
    modelo: str = Field("", max_length=80)


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def registrar(tipo: str, status: str, uso: Uso | None = None, tarefa_id: int | None = None,
              trabalho_id: int | None = None, agente: str = "", chars_entrada: int = 0, chars_saida: int = 0) -> None:
    """Grava o consumo de um trabalho que terminou. Nunca derruba a conclusão do trabalho."""
    if tipo not in TIPOS:
        return
    try:
        uso = uso or Uso()
        linha = tarefas.obter(tarefa_id) if tarefa_id else None
        agente = agente or (linha["agente"] if linha else "") or AGENTE_DO_TIPO.get(tipo, "")
        empresa = (linha["empresa"] if linha else "") or EMPRESA_DO_TIPO.get(tipo, "")
        with _db() as db:
            db.execute(
                "INSERT INTO uso_max (em, tipo, status, agente, empresa, tarefa_id, trabalho_id, chars_entrada, "
                "chars_saida, tokens_entrada, tokens_cache, tokens_saida, rodadas, duracao_s, modelo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tarefas._agora(), tipo, status, agente or None, empresa or None, tarefa_id, trabalho_id,
                 uso.chars_entrada or chars_entrada, uso.chars_saida or chars_saida, uso.tokens_entrada,
                 uso.tokens_cache, uso.tokens_saida, uso.rodadas, uso.duracao_s, uso.modelo or None))
    except Exception:
        log.exception("Uso do Max: não consegui registrar o trabalho %s (tarefa %s).", trabalho_id, tarefa_id)


def _somar(linhas, campo: str, nomes=None) -> list[dict]:
    grupos: dict[str, dict] = {}
    for l in linhas:
        chave = l[campo] or "—"
        g = grupos.setdefault(chave, {"chave": chave, "nome": (nomes or {}).get(chave, chave), "trabalhos": 0,
                                      "falhas": 0, "chars": 0, "tokens": 0, "rodadas": 0, "duracao_s": 0.0})
        g["trabalhos"] += 1
        g["falhas"] += l["status"] != "concluido"
        g["chars"] += l["chars_entrada"] + l["chars_saida"]
        g["tokens"] += l["tokens_entrada"] + l["tokens_cache"] + l["tokens_saida"]
        g["rodadas"] += l["rodadas"]
        g["duracao_s"] += l["duracao_s"]
    for g in grupos.values():
        g["duracao_s"] = round(g["duracao_s"])
    return sorted(grupos.values(), key=lambda g: (-g["duracao_s"], -g["chars"]))


def resumo(dias: int = 7, nome_do_agente=None) -> dict:
    """Consumo dos últimos `dias` por tipo, agente e empresa (para o painel da Diretoria)."""
    import empresas  # import tardio: lê as empresas do grupo

    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = _db().execute("SELECT * FROM uso_max WHERE em >= ?", (desde,)).fetchall()
    agentes = {l["agente"]: nome_do_agente(l["agente"]) for l in linhas if l["agente"]} if nome_do_agente else {}
    nomes_empresas = {e: empresas.nome(e) for e in {l["empresa"] for l in linhas if l["empresa"]}}
    return {"dias": dias, "total": _total(linhas),
            "por_tipo": _somar(linhas, "tipo"), "por_agente": _somar(linhas, "agente", agentes),
            "por_empresa": _somar(linhas, "empresa", nomes_empresas)}


def _total(linhas) -> dict:
    soma = {"trabalhos": len(linhas), "chars": 0, "tokens": 0, "rodadas": 0, "duracao_s": 0}
    for g in _somar(linhas, "tipo"):
        for k in ("chars", "tokens", "rodadas", "duracao_s"):
            soma[k] += g[k]
    return soma
