"""Tarefas de texto pelo plano Max (Claude Code no PC do dono), no lugar dos créditos da API.

O Trabalhador Max faz uma coisa por vez; a API roda na nuvem e atende em paralelo. Então:
  Max livre e ligado → a tarefa vai para o Max (custo zero);
  Max ocupado (outra tarefa, produção, anexo) ou desligado → segue para a API (Haiku/Sonnet), em paralelo.
Só para a conta do dono do plano Max. Agentes com ferramentas do sistema (Construtor, Social Media/Monday)
continuam na API: o Claude Code do PC não tem essas ferramentas.
"""

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import config
import saude
from agents.perfis import ESTILO_CHAT

MODELO = "claude-code/max"
LIMITE_S = 15 * 60
ONLINE_S = 90            # o trabalhador pede a fila a cada ~10 s quando está livre
AGENTES_COM_FERRAMENTAS = {"construtor", "social_media", "prospectador"}

ARQUIVO_CONTATO = config.DADOS_DIR / "max.contato"  # a data de modificação = último contato
_trava = threading.Lock()


def registrar_contato() -> None:
    """Chamado a cada pedido de fila do trabalhador (ele está ligado)."""
    ARQUIVO_CONTATO.touch()


def online() -> bool:
    try:
        return time.time() - ARQUIVO_CONTATO.stat().st_mtime < ONLINE_S
    except OSError:
        return False


def _db():
    import producao  # import tardio: produção depende do orquestrador
    return producao._db()


def _ocupado() -> bool:
    db = _db()
    # Reserva vira pedido em segundos; parada há mais de 10 min é sobra de uma etapa que falhou no meio e não pode
    # bloquear o Max até o próximo reinício (30/10/2026: trabalho 33, da tarefa 133).
    recente = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    trabalhos = db.execute("SELECT 1 FROM trabalhos_max WHERE status IN ('pendente', 'executando') "
                           "OR (status = 'reservado' AND criado_em >= ?) LIMIT 1", (recente,)).fetchone()
    producoes = db.execute("SELECT 1 FROM tarefas WHERE status IN ('producao', 'produzindo') LIMIT 1").fetchone()
    return bool(trabalhos or producoes)


def pode_usar(usuario: str, agente_id: str) -> bool:
    """O Max entra na rota desta tarefa? (dono, agente sem ferramentas próprias e trabalhador ligado)."""
    return config.usa_max(usuario) and agente_id not in AGENTES_COM_FERRAMENTAS and online()


def reservar() -> int | None:
    """Cria o trabalho de texto se o Max estiver livre agora (atômico); None = ocupado, use a API."""
    with _trava:
        if not online() or _ocupado():
            return None
        with _db() as db:
            cursor = db.execute(
                # "reservado": o trabalhador só pega quando o pedido já estiver gravado (status pendente)
                "INSERT INTO trabalhos_max (tipo, payload, status, criado_em) VALUES ('texto', '{}', 'reservado', ?)",
                (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),))
            return cursor.lastrowid


_trabalhos_da_tarefa: dict[int, set[int]] = {}


def registrar_trabalho(tarefa_id: int, trabalho_id: int) -> None:
    _trabalhos_da_tarefa.setdefault(tarefa_id, set()).add(trabalho_id)


def cancelar_da_tarefa(tarefa_id: int) -> int:
    """"Parar": o trabalho de texto que o Max ainda não começou sai da fila (o Max fica livre para os outros)."""
    ids = _trabalhos_da_tarefa.pop(tarefa_id, set())
    if not ids:
        return 0
    marcas = ",".join("?" * len(ids))
    with _db() as db:
        return db.execute(f"UPDATE trabalhos_max SET status = 'falhou', resultado = 'parada pelo usuário' "
                          f"WHERE id IN ({marcas}) AND status IN ('reservado', 'pendente')", tuple(ids)).rowcount


def executar(trabalho_id: int, prompt: str, limite_s: int = LIMITE_S) -> str:
    """Entrega o pedido ao trabalho reservado e espera a resposta (em thread). Levanta TimeoutError/saude.FalhaDoModelo."""
    with _db() as db:
        db.execute("UPDATE trabalhos_max SET payload = ?, status = 'pendente' WHERE id = ?",
                   (json.dumps({"prompt": prompt, "limite_s": limite_s}, ensure_ascii=False), trabalho_id))
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        linha = _db().execute("SELECT status, resultado FROM trabalhos_max WHERE id = ?", (trabalho_id,)).fetchone()
        if not linha:
            raise saude.FalhaDoModelo("Trabalho do Max não encontrado.")
        if linha["status"] == "concluido":
            return linha["resultado"] or ""
        if linha["status"] in ("falhou", "cancelado"):
            raise saude.FalhaDoModelo(f"Claude Code (Max): {linha['resultado'] or 'falhou'}")
        time.sleep(2)
    import producao  # import tardio: produção depende do orquestrador

    producao.cancelar_trabalho(trabalho_id, "tempo esgotado")  # na fila ou rodando: o trabalhador para
    raise TimeoutError("O Claude Code (Max) não respondeu a tempo.")


def montar_prompt(perfil: dict, extras: str, contexto_cerebro: str, descricao: str, esperado: str) -> str:
    """Pedido completo para o Claude Code: persona, diretrizes, trechos do Cérebro e a tarefa."""
    return "\n\n".join(filter(None, [
        f"Você é o agente {perfil['role']} do Escritório Veraneio (Casa Veraneio). Objetivo: {perfil['goal']}",
        perfil["backstory"], extras,
        f"Conhecimento do Cérebro (fonte oficial; use só o que estiver aqui ou no pedido, sem inventar):\n{contexto_cerebro}"
        if contexto_cerebro else "",
        f"TAREFA:\n{descricao}",
        f"Entregue: {esperado} Responda só com a entrega final, em português do Brasil, sem usar ferramentas. "
        f"{ESTILO_CHAT}",
    ]))
