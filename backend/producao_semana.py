"""Produzir a semana (gestor-12, fase 2; decisões 4, 5 e 7 do Thomas, 04/11/2026).

Depois da pauta da semana (pauta_semana.py), o Gestor oferece "Produzir a semana" por empresa (botões na própria
pauta, js/chat.js) e aceita o comando digitado ("Produzir a semana", "... da Casa Veraneio", "... do Corp",
"... da Vero"). Um clique e pronto, sem confirmação (decisão 5: o sistema gasta Max sem aprovação; decisão 7: sem
limite por usuário nem por quantidade).

1. Lê o quadro de Social Media (os mesmos leitores da pauta; só leitura) e escolhe os itens da empresa com entrega
   OU postagem nos próximos JANELA_DIAS dias que ainda esperam produção. Sem TIPO no nome, sem descrição/roteiro ou
   sem Conta: ficam de fora, com o motivo no resumo.
2. Os escolhidos entram na fila `producao_semana` (banco). Cada um, na sua vez, segue EXATAMENTE o caminho do botão
   "Enviar" do item (monday._enviar_ao_gestor: Gestor planeja pela rota normal de modelos, a peça vai à fila de
   produção do Max e o resultado volta ao item do Monday). Nenhum caminho de produção novo.
3. Preferência pela noite: a vez de cada item começa a partir de NOITE_INICIO (20:00) até NOITE_FIM (07:00), um item
   por vez no Gestor (as peças se acumulam na fila do Max, que já produz uma por vez). De dia, só sai um item se o
   Max estiver totalmente parado (nenhuma produção nem trabalho na fila): assim a fila anda sem disputar o Max com a
   equipe durante o expediente, e no máximo uma peça do lote roda de dia por vez.
4. PC desligado (decisão 4: ligado à noite quase sempre, não sempre): nada sai da fila enquanto o trabalhador não
   der sinal (max_texto.online). Quem espera aqui não é tarefa, então não cai no prazo de 24 h de
   tarefas.reagendar; e a peça já enfileirada (status "producao") também não tem prazo: espera o PC voltar.
"""

import asyncio
import logging
import re
from datetime import date, datetime, timedelta

import empresas
import max_texto
import monday
import monday_datas
import pauta_semana
import tarefas

log = logging.getLogger(__name__)

AGENTE = "gestor"
PEDIDO = re.compile(r"^\s*produzir\s+a\s+semana\b", re.I)
TAMANHO_MAX_PEDIDO = 120  # comando curto; um briefing longo que comece assim segue como pedido normal ao Gestor
JANELA_DIAS = 7           # hoje e os 6 dias seguintes (entrega ou postagem dentro deles)
NOITE_INICIO, NOITE_FIM = 20, 7  # janela da noite, hora de Brasília: das 20:00 às 06:59
INTERVALO_S = 60          # o vigia olha a fila a cada minuto
# Status do Monday que NÃO esperam produção: encerrados (pauta) e os que o próprio pipeline já marcou.
NAO_ESPERAM = pauta_semana.ENCERRADOS | {monday.EM_PRODUCAO.lower(), monday.NA_FILA.lower()}
# "do Corp", "da Vero" e os nomes completos (empresas.citada não reconhece os apelidos curtos).
APELIDOS = [("cv_corporativo", re.compile(r"\bcorp(?:orativo)?\b", re.I)),
            ("casa_vero", re.compile(r"\bvero\b", re.I)),
            ("casa_veraneio", re.compile(r"\bveraneio\b", re.I))]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS producao_semana (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote INTEGER NOT NULL,           -- tarefa do resumo no chat do Gestor
    item_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    empresa TEXT NOT NULL,
    status TEXT NOT NULL,            -- na_fila | enviado | ignorado
    motivo TEXT,
    criado_em TEXT NOT NULL,
    enviado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_producao_semana_status ON producao_semana(status, id);
"""
_esquema_criado = False


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def e_pedido(agente_id: str, texto: str) -> bool:
    return agente_id == AGENTE and len(texto or "") <= TAMANHO_MAX_PEDIDO and bool(PEDIDO.match(texto or ""))


def empresa_do_pedido(texto: str, da_conversa: str | None) -> str | None:
    """A empresa dita no comando ("da Casa Veraneio Corporativo" antes de "da Casa Veraneio"); senão, a da conversa."""
    resto = PEDIDO.sub("", texto or "", count=1)
    if (citada := empresas.citada(resto)):
        return citada
    achada = next((e for e, padrao in APELIDOS if padrao.search(resto)), None)
    return achada or (da_conversa if empresas.valida(da_conversa) else None)


def _hoje() -> date:
    from agendamentos import FUSO  # import tardio: o agendador puxa o APScheduler

    return datetime.now(FUSO).date()


def janela(hoje: date) -> tuple[date, date]:
    return hoje, hoje + timedelta(days=JANELA_DIAS - 1)


# ---------- Escolha dos itens (conta em código, Monday simulado nos testes) ----------

def _descricao(item: dict) -> str:
    """Roteiro do item (descrição no Monday, leitura). Falha na leitura = sem roteiro: o item fica de fora."""
    return (monday._com_descricao(dict(item)).get("descricao") or "").strip()


def selecionar(quadro: dict[str, list[dict]], empresa: str, hoje: date, ler_descricao=None) -> dict:
    """{"escolhidos": [(data, item)], "pulados": [(nome, motivo)]} dos itens da empresa na janela de 7 dias."""
    ler_descricao = ler_descricao or _descricao
    inicio, fim = janela(hoje)
    rotulo = empresas.EMPRESAS[empresa]["monday"].lower()
    vistos, escolhidos, pulados = set(), [], []
    for itens in quadro.values():
        for item in itens:
            if item["id"] in vistos:
                continue
            vistos.add(item["id"])
            datas = [d for d in (pauta_semana._data(pauta_semana._coluna(item, c))
                                 for c in (pauta_semana.COL_ENTREGA, monday_datas.COL_DATA)) if d]
            na_janela = [d for d in datas if inicio <= d <= fim]
            conta = pauta_semana._coluna(item, monday.COL_CONTA)
            status = pauta_semana._coluna(item, monday.COL_STATUS).lower()
            if not na_janela or status in NAO_ESPERAM:
                continue
            if conta.lower() != rotulo:
                if conta in monday.SEM_CONTA:  # pode ser de qualquer empresa: não produzo no escuro
                    pulados.append((item["name"], "sem Conta (defina a empresa no Monday)"))
                continue
            if not monday.tipo_do_item(item["name"]):
                pulados.append((item["name"], f"sem TIPO no nome ({', '.join(monday.TIPOS)} | Descrição)"))
            elif _na_fila_ou_em_andamento(int(item["id"])):
                pulados.append((item["name"], "já está na fila ou em produção"))
            elif not ler_descricao(item):
                pulados.append((item["name"], "sem descrição/roteiro no item"))
            else:
                escolhidos.append((min(na_janela), item))
    escolhidos.sort(key=lambda x: x[0])
    return {"escolhidos": escolhidos, "pulados": pulados, "inicio": inicio, "fim": fim}


def _na_fila_ou_em_andamento(item_id: int) -> bool:
    if _db().execute("SELECT 1 FROM producao_semana WHERE item_id = ? AND status = 'na_fila'", (item_id,)).fetchone():
        return True
    return monday._em_aberto(item_id)


def enfileirar(lote: int, empresa: str, escolhidos: list[tuple[date, dict]]) -> int:
    """Grava os itens na fila do lote. Sem aprovação (decisão 5): daqui o vigia leva cada um ao pipeline do Enviar."""
    agora = tarefas._agora()
    with _db() as db:
        for _, item in escolhidos:
            db.execute("INSERT INTO producao_semana (lote, item_id, nome, empresa, status, criado_em) "
                       "VALUES (?, ?, ?, ?, 'na_fila', ?)", (lote, int(item["id"]), item["name"], empresa, agora))
    return len(escolhidos)


def resumo(empresa: str, escolha: dict) -> str:
    linhas = [f"PRODUZIR A SEMANA — {empresas.nome(empresa)} (entrega ou postagem de "
              f"{escolha['inicio']:%d/%m} a {escolha['fim']:%d/%m})"]
    if escolha["escolhidos"]:
        linhas.append(f"Na fila de produção ({len(escolha['escolhidos'])}):")
        linhas += [f"- {d:%d/%m} {i['name']}" for d, i in escolha["escolhidos"]]
        linhas.append(f"Começa a partir das {NOITE_INICIO}:00 (antes, só se o Max estiver parado), um item por vez, "
                      "pelo mesmo caminho do botão Enviar: cada peça volta ao seu item no Monday. Com o PC desligado, "
                      "a fila espera ele ligar; nada se perde.")
    else:
        linhas.append("Nenhum item à espera de produção nesta janela.")
    if escolha["pulados"]:
        linhas.append(f"Ficaram de fora ({len(escolha['pulados'])}):")
        linhas += [f"- {nome}: {motivo}" for nome, motivo in escolha["pulados"]]
    return "\n".join(linhas)


async def iniciar(usuario: str, andar: str, agente, texto: str, empresa_conversa: str | None) -> int:
    """Comando ou botão no chat do Gestor: escolhe, enfileira e responde com o resumo (sem modelo, sem confirmação)."""
    import orquestrador  # import tardio: evita ciclo

    empresa = empresa_do_pedido(texto, empresa_conversa)
    tarefa_id = tarefas.criar(usuario, andar, agente.id, texto, "simples", empresa or empresas.PADRAO)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Produzir a semana: leitura do Monday, sem IA")
    try:
        if not empresa:
            texto_final = ("Produzir a semana: diga a empresa (\"Produzir a semana da Casa Veraneio\", \"do Corp\" ou "
                           "\"da Vero\") ou escolha-a no seletor da conversa.")
        elif not monday.ativo():
            texto_final = "Produzir a semana: o Monday não está configurado neste servidor, então não li o quadro."
        else:
            hoje = _hoje()
            quadro = await asyncio.to_thread(pauta_semana.ler_quadro, *janela(hoje))
            escolha = await asyncio.to_thread(selecionar, quadro, empresa, hoje)
            enfileirar(tarefa_id, empresa, escolha["escolhidos"])
            texto_final = resumo(empresa, escolha)
            acordar()
        tarefas.atualizar(tarefa_id, status="concluida", modelo="sistema (sem IA)", resposta=texto_final)
        tarefas.registrar_evento(tarefa_id, "concluida", modelo="sistema (sem IA)")
    except Exception as erro:
        log.exception("Produzir a semana (tarefa %s) falhou.", tarefa_id)
        tarefas.atualizar(tarefa_id, status="falhou", motivo=f"Não consegui ler o Monday para produzir a semana: {erro}")
        tarefas.registrar_evento(tarefa_id, "falhou", detalhe=str(erro)[:300])
    await orquestrador.entregar(tarefas.obter(tarefa_id))
    return tarefa_id


# ---------- Vigia: leva um item por vez ao pipeline do Enviar ----------

def de_noite(agora: datetime | None = None) -> bool:
    from agendamentos import FUSO  # import tardio: o agendador puxa o APScheduler

    hora = (agora or datetime.now(FUSO)).astimezone(FUSO).hour
    return hora >= NOITE_INICIO or hora < NOITE_FIM


def _lote_no_gestor() -> bool:
    """Um item do lote ainda está na etapa do Gestor (planejando ou adiado): o próximo espera."""
    monday._db()  # garante a tabela monday_tarefas
    return bool(_db().execute(
        "SELECT 1 FROM producao_semana p JOIN monday_tarefas m ON m.item_id = p.item_id JOIN tarefas t "
        "ON t.id = m.tarefa_id WHERE p.status = 'enviado' AND t.agente = 'gestor' "
        "AND t.status IN ('executando', 'adiada') LIMIT 1").fetchone())


def _gestor_livre() -> bool:
    from estado import Status, buscar_agente

    gestor = buscar_agente("marketing", AGENTE)
    if not gestor or gestor.status == Status.trabalhando or monday._vez_do_gestor.locked():
        return False
    return not monday._db().execute("SELECT 1 FROM monday_fila LIMIT 1").fetchone() and not _lote_no_gestor()


def _marcar(linha_id: int, status: str, motivo: str | None = None) -> None:
    with _db() as db:
        db.execute("UPDATE producao_semana SET status = ?, motivo = ?, enviado_em = ? WHERE id = ?",
                   (status, motivo, tarefas._agora(), linha_id))


async def despachar_um(agora: datetime | None = None) -> int | None:
    """Leva o próximo item da fila ao pipeline do Enviar, se for a vez dele; devolve o item_id (None = esperar)."""
    linha = _db().execute("SELECT * FROM producao_semana WHERE status = 'na_fila' ORDER BY id LIMIT 1").fetchone()
    if not linha or not max_texto.online():  # PC desligado: espera, sem falhar e sem prazo
        return None
    if not de_noite(agora) and max_texto._ocupado():  # de dia, só com o Max parado
        return None
    if not _gestor_livre():
        return None
    if monday._em_aberto(linha["item_id"]):  # alguém clicou Enviar no item enquanto ele esperava aqui
        _marcar(linha["id"], "ignorado", "já estava em andamento")
        return None
    # O pipeline aceita só quem o Monday autoriza: o lote vai em nome da conta do token (a do Thomas); as
    # notificações do sino vão para ela. Sem resposta do Monday agora, tenta de novo no próximo minuto.
    if not (autorizados := await asyncio.to_thread(monday.autorizados)):
        return None
    _marcar(linha["id"], "enviado")
    await monday._enviar_ao_gestor(linha["item_id"], min(autorizados))
    return linha["item_id"]


_acordar: asyncio.Event | None = None


def acordar() -> None:
    if _acordar is not None:
        _acordar.set()


async def vigiar() -> None:
    """Laço de fundo (main.py): a cada minuto, ou logo depois de um novo lote, tenta levar um item adiante."""
    global _acordar
    _acordar = asyncio.Event()
    while True:
        try:
            await despachar_um()
        except Exception:
            log.exception("Produzir a semana: erro ao despachar o próximo item.")
        try:
            await asyncio.wait_for(_acordar.wait(), INTERVALO_S)
        except asyncio.TimeoutError:
            pass
        _acordar.clear()


def pendentes() -> list[dict]:
    """Itens do lote ainda esperando a vez (painel/consulta)."""
    return [dict(l) for l in _db().execute("SELECT * FROM producao_semana WHERE status = 'na_fila' ORDER BY id")]
