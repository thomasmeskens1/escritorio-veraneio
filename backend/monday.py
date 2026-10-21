"""Integração com o Monday: board "Planejamento Automático 2026" (Social Media → Escritório Veraneio).

- Botão "Enviar" no item → webhook → tarefa para o Gestor (que distribui aos agentes). O Status do item
  acompanha o andamento: Em produção / Na fila / Revisão (falha volta para Aguardando, com comentário).
- Entrega: resumo do Gestor em comentário; legenda na coluna Legenda (ou em comentário, se já houver);
  artes da produção anexadas em Criativos. Referências do item vão para o rascunho da produção no Max.
- Item citado no chat ('... o item "FEED | ..."'): os dados do item entram no pedido do agente.
Só este board; só a marca Casa Veraneio por enquanto (as outras ainda não foram educadas).
"""

import asyncio
import hmac
import html
import json
import logging
import os
import re
import secrets
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

import config
import tarefas

log = logging.getLogger(__name__)

API = "https://api.monday.com/v2"
VERSAO_API = "2025-04"
TOKEN = os.getenv("MONDAY_API_TOKEN", "").strip()
BOARD = 18436414505
COL_BOTAO, COL_STATUS, COL_CONTA = "button_mm8bdsnh", "status", "color_mks99tq4"
COL_LEGENDA, COL_REFERENCIAS, COL_CRIATIVOS = "texto_longo_1_mkmf3wmy", "file_mm8bmmxv", "arquivos_mkmd1v3v"
MARCAS_PRONTAS = {"Casa Veraneio"}
EM_PRODUCAO, NA_FILA, REVISAO, AGUARDANDO, FALHA = "Em produção", "Na fila", "Revisão", "Aguardando", "Falha"
SEM_CONTA = {"", "Sem definição"}
MARCA_LEGENDA = ("<<LEGENDA>>", "<<FIM DA LEGENDA>>")
ESPERA_GESTOR_S, ESPERA_MAXIMA_S = 15, 4 * 3600
ARQUIVO_SEGREDO = config.ARQUIVO_BANCO.parent / "monday.webhook.token"
CITACAO = re.compile(r"\bitem\s+[\"“”']([^\"“”']{3,200})[\"“”']", re.IGNORECASE)

rotas = APIRouter(prefix="/api/integracoes/monday")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS monday_tarefas (
    tarefa_id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monday_item ON monday_tarefas(item_id);
CREATE TABLE IF NOT EXISTS monday_eventos (gatilho TEXT PRIMARY KEY, em TEXT NOT NULL);
"""
_esquema_criado = False
_em_andamento: set[asyncio.Task] = set()


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def ativo() -> bool:
    return bool(TOKEN)


def segredo_webhook() -> str:
    if not ARQUIVO_SEGREDO.exists():
        ARQUIVO_SEGREDO.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return ARQUIVO_SEGREDO.read_text(encoding="utf-8").strip()


# ---------- API (bloqueante: chamar com asyncio.to_thread) ----------

def _api(consulta: str, variaveis: dict | None = None) -> dict:
    corpo = json.dumps({"query": consulta, "variables": variaveis or {}}).encode()
    requisicao = urllib.request.Request(API, data=corpo, headers={
        "Authorization": TOKEN, "Content-Type": "application/json", "API-Version": VERSAO_API})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        dados = json.load(resposta)
    if dados.get("errors"):
        raise RuntimeError(f"Monday: {dados['errors']}")
    return dados["data"]


_CAMPOS_ITEM = """id name board { id } group { title } creator { name }
  column_values { id type text ... on FileValue { files { __typename
    ... on FileAssetValue { asset { name public_url } } ... on FileLinkValue { name url } } } }
  updates(limit: 5) { text_body creator { name } created_at }"""


def obter_item(item_id: int) -> dict | None:
    itens = _api(f"query ($ids: [ID!]) {{ items(ids: $ids) {{ {_CAMPOS_ITEM} }} }}", {"ids": [str(item_id)]})["items"]
    return itens[0] if itens else None


def buscar_item(nome: str) -> dict | None:
    """Item do board pelo nome (exato; senão, o primeiro que contém o texto)."""
    regras = {"rules": [{"column_id": "name", "compare_value": [nome], "operator": "contains_text"}]}
    itens = _api(f"query ($board: [ID!], $q: ItemsQuery) {{ boards(ids: $board) {{ items_page(limit: 5, query_params: $q) "
                 f"{{ items {{ {_CAMPOS_ITEM} }} }} }} }}", {"board": [str(BOARD)], "q": regras})
    candidatos = (itens["boards"] or [{}])[0].get("items_page", {}).get("items", [])
    exato = [i for i in candidatos if i["name"].strip().lower() == nome.strip().lower()]
    return (exato or candidatos or [None])[0]


def _valor(item: dict, coluna: str) -> dict:
    return next((c for c in item["column_values"] if c["id"] == coluna), {})


def arquivos(item: dict, coluna: str) -> list[dict]:
    """[{nome, url}] da coluna de arquivos (links de arquivos enviados valem ~1 h)."""
    saida = []
    for f in _valor(item, coluna).get("files") or []:
        if f.get("asset"):
            saida.append({"nome": f["asset"]["name"], "url": f["asset"]["public_url"]})
        elif f.get("url"):
            saida.append({"nome": f.get("name") or "link", "url": f["url"]})
    return saida


def mudar_status(item_id: int, rotulo: str) -> None:
    _api("mutation ($b: ID!, $i: ID!, $v: JSON!) { change_column_value(board_id: $b, item_id: $i, column_id: \"status\", "
         "value: $v) { id } }", {"b": str(BOARD), "i": str(item_id), "v": json.dumps({"label": rotulo})})


def escrever_legenda(item_id: int, texto: str) -> None:
    _api("mutation ($b: ID!, $i: ID!, $c: String!, $v: JSON!) { change_column_value(board_id: $b, item_id: $i, "
         "column_id: $c, value: $v) { id } }",
         {"b": str(BOARD), "i": str(item_id), "c": COL_LEGENDA, "v": json.dumps({"text": texto})})


def comentar(item_id: int, texto: str) -> None:
    corpo = "".join(f"<p>{html.escape(linha) or '&nbsp;'}</p>" for linha in texto.strip().splitlines())
    _api("mutation ($i: ID!, $t: String!) { create_update(item_id: $i, body: $t) { id } }", {"i": str(item_id), "t": corpo})


def anexar_criativo(item_id: int, nome: str, conteudo: bytes) -> None:
    """Envia um arquivo para a coluna Criativos (multipart da API de arquivos)."""
    fronteira = secrets.token_hex(16)
    consulta = (f'mutation ($file: File!) {{ add_file_to_column (item_id: {int(item_id)}, column_id: "{COL_CRIATIVOS}", '
                "file: $file) { id } }")
    partes = [(f'--{fronteira}\r\nContent-Disposition: form-data; name="query"\r\n\r\n{consulta}\r\n').encode(),
              (f'--{fronteira}\r\nContent-Disposition: form-data; name="variables[file]"; filename="{nome}"\r\n'
               "Content-Type: application/octet-stream\r\n\r\n").encode() + conteudo + b"\r\n",
              f"--{fronteira}--\r\n".encode()]
    requisicao = urllib.request.Request(f"{API}/file", data=b"".join(partes), headers={
        "Authorization": TOKEN, "API-Version": VERSAO_API, "Content-Type": f"multipart/form-data; boundary={fronteira}"})
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        dados = json.load(resposta)
    if dados.get("errors"):
        raise RuntimeError(f"Monday (arquivo): {dados['errors']}")


def _chave(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().lower()


def grupos() -> list[dict]:
    return _api("query ($b: [ID!]) { boards(ids: $b) { groups { id title } } }", {"b": [str(BOARD)]})["boards"][0]["groups"]


def grupo_por_nome(nome: str, criar: bool = False) -> dict | None:
    """Grupo pelo título, sem diferenciar maiúsculas/acentos ("dezembro" = "Dezembro"); cria se pedido."""
    achado = next((g for g in grupos() if _chave(g["title"]) == _chave(nome)), None)
    if achado or not criar:
        return achado
    return _api("mutation ($b: ID!, $n: String!) { create_group(board_id: $b, group_name: $n) { id title } }",
                {"b": str(BOARD), "n": nome.strip().capitalize()})["create_group"]


def itens_do_grupo(grupo_id: str) -> list[dict]:
    dados = _api("query ($b: [ID!], $g: [String]) { boards(ids: $b) { groups(ids: $g) { items_page(limit: 200) "
                 "{ items { id name column_values(ids: [\"data\", \"status\"]) { id text } } } } } }",
                 {"b": [str(BOARD)], "g": [grupo_id]})
    return dados["boards"][0]["groups"][0]["items_page"]["items"]


def criar_item(grupo_id: str, nome: str, valores: dict) -> dict:
    """`valores`: coluna -> valor no formato da API (ex.: {"data": {"date": "2026-12-05"}})."""
    return _api("mutation ($b: ID!, $g: String!, $n: String!, $v: JSON!) { create_item(board_id: $b, group_id: $g, "
                "item_name: $n, column_values: $v) { id name url } }",
                {"b": str(BOARD), "g": grupo_id, "n": nome, "v": json.dumps(valores)})["create_item"]


def criar_webhook(url: str) -> dict:
    """Webhook do botão Enviar (o clique conta como mudança da coluna)."""
    return _api("mutation ($b: ID!, $u: String!, $c: JSON!) { create_webhook(board_id: $b, url: $u, "
                "event: change_specific_column_value, config: $c) { id board_id } }",
                {"b": str(BOARD), "u": url, "c": json.dumps({"columnId": COL_BOTAO})})["create_webhook"]


# ---------- Briefing ----------

def briefing(item: dict) -> str:
    """Pedido ao Gestor/agente com os dados do item (texto, colunas, referências, comentários recentes)."""
    campos = {c["id"]: (c.get("text") or "").strip() for c in item["column_values"]}
    linhas = [f"Item do Monday: {item['name']} (grupo {item['group']['title']})"]
    for rotulo, coluna in (("Conta (marca)", COL_CONTA), ("Objetivo", "dropdown_mm8bagtr"),
                           ("Responsável", "dropdown_mm8b5ds4"), ("Data de entrega", "date_mm0p7s2f"),
                           ("Data de postagem", "data"), ("Horário", "hora_mkmpv7kt"), ("Status", COL_STATUS)):
        if campos.get(coluna):
            linhas.append(f"- {rotulo}: {campos[coluna]}")
    if campos.get(COL_LEGENDA):
        linhas.append(f"- Legenda já existente:\n{campos[COL_LEGENDA][:1500]}")
    for rotulo, coluna in (("Referências (ponto de partida, não regra absoluta)", COL_REFERENCIAS),
                           ("Criativos já anexados", COL_CRIATIVOS)):
        if (lista := arquivos(item, coluna)):
            linhas.append(f"- {rotulo}: " + ", ".join(a["nome"] for a in lista))
    comentarios = [f"  · {u['creator']['name'] if u.get('creator') else '?'}: {u['text_body'][:300]}"
                   for u in item.get("updates") or [] if u.get("text_body")]
    if comentarios:
        linhas.append("- Comentários recentes:\n" + "\n".join(comentarios))
    return "\n".join(linhas)


def contexto_citado(texto: str) -> str:
    """Pedido que cita um item ('o item "FEED | ..."'): dados do item para juntar ao pedido ("" se não houver)."""
    citacao = CITACAO.search(texto)
    if not (citacao and ativo()):
        return ""
    try:
        item = buscar_item(citacao.group(1))
    except Exception as erro:
        log.warning("Monday: falha ao buscar item citado (%s)", erro)
        return ""
    return f"[Dados do item no Monday]\n{briefing(item)}" if item else ""


# ---------- Vínculo tarefa ↔ item e andamento ----------

def vincular(tarefa_id: int, item_id: int) -> None:
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO monday_tarefas (tarefa_id, item_id, criado_em) VALUES (?, ?, ?)",
                   (tarefa_id, item_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))


def item_da_tarefa(tarefa_id: int) -> int | None:
    linha = _db().execute("SELECT item_id FROM monday_tarefas WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return linha["item_id"] if linha else None


def _em_aberto(item_id: int) -> bool:
    return bool(_db().execute(
        "SELECT 1 FROM monday_tarefas m JOIN tarefas t ON t.id = m.tarefa_id WHERE m.item_id = ? AND t.status IN "
        "('executando', 'adiada', 'producao', 'produzindo', 'recebida')", (item_id,)).fetchone())


def _em_segundo_plano(corrotina) -> None:
    tarefa = asyncio.create_task(corrotina)
    _em_andamento.add(tarefa)
    tarefa.add_done_callback(_em_andamento.discard)


async def _seguro(funcao, *args) -> None:
    try:
        await asyncio.to_thread(funcao, *args)
    except Exception as erro:  # o Monday fora do ar nunca derruba a tarefa
        log.warning("Monday: %s falhou (%s)", getattr(funcao, "__name__", funcao), erro)


def andamento(tarefa_id: int, evento: str, texto: str = "", producao_a_seguir: bool = False) -> None:
    """Chamado pelo orquestrador/produção: atualiza o item vinculado (se houver), sem bloquear."""
    item_id = item_da_tarefa(tarefa_id)
    if item_id and ativo():
        _em_segundo_plano(_andamento(item_id, evento, texto, producao_a_seguir))


async def _andamento(item_id: int, evento: str, texto: str, producao_a_seguir: bool) -> None:
    if evento == "adiada":
        await _seguro(mudar_status, item_id, NA_FILA)
    elif evento == "produzindo":
        await _seguro(mudar_status, item_id, EM_PRODUCAO)
    elif evento == "falhou":
        await _seguro(comentar, item_id, f"⚠️ O Escritório Veraneio não concluiu esta tarefa: {texto[:500]}\n"
                                         "Clique em Enviar para tentar de novo.")
        await _seguro(mudar_status, item_id, FALHA)
    elif evento == "concluida":
        await _entregar_texto(item_id, texto, producao_a_seguir)
    elif evento == "produzida":
        await _seguro(comentar, item_id, texto)
        await _seguro(mudar_status, item_id, REVISAO)


async def _entregar_texto(item_id: int, texto: str, producao_a_seguir: bool) -> None:
    """Resumo do Gestor em comentário; legenda na coluna (ou em comentário, se a coluna já tiver texto)."""
    legenda = None
    ini, fim = MARCA_LEGENDA
    if ini in texto:
        legenda = texto.split(ini, 1)[1].split(fim, 1)[0].strip()
        texto = texto.replace(f"{ini}", "Legenda:").replace(fim, "")
    try:
        item = await asyncio.to_thread(obter_item, item_id)
    except Exception:
        item = None
    if legenda and item and not (_valor(item, COL_LEGENDA).get("text") or "").strip():
        await _seguro(escrever_legenda, item_id, legenda)
        texto += "\n\n(A legenda foi escrita na coluna Legenda.)"
    sufixo = ("\n\nAs artes seguiram para produção no Claude Code; os arquivos chegam na coluna Criativos."
              if producao_a_seguir else "")
    await _seguro(comentar, item_id, f"🤖 Escritório Veraneio · Gestor\n\n{texto.strip()[:9000]}{sufixo}")
    await _seguro(mudar_status, item_id, NA_FILA if producao_a_seguir else REVISAO)


# ---------- Webhook do botão Enviar ----------

@rotas.post("/webhook/{segredo}")
async def webhook(segredo: str, request: Request):
    if not hmac.compare_digest(segredo, segredo_webhook()):
        raise HTTPException(status_code=404)
    corpo = await request.json()
    if "challenge" in corpo:  # verificação do Monday ao criar o webhook
        return {"challenge": corpo["challenge"]}
    evento = corpo.get("event") or {}
    if int(evento.get("boardId") or 0) != BOARD or evento.get("columnId") != COL_BOTAO or not evento.get("pulseId"):
        return {"ok": True, "ignorado": True}
    gatilho = str(evento.get("triggerUuid") or f"{evento['pulseId']}-{evento.get('triggerTime')}")
    with _db() as db:  # o Monday pode reenviar: um clique = uma tarefa
        if db.execute("SELECT 1 FROM monday_eventos WHERE gatilho = ?", (gatilho,)).fetchone():
            return {"ok": True, "repetido": True}
        db.execute("INSERT INTO monday_eventos (gatilho, em) VALUES (?, ?)",
                   (gatilho, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    _em_segundo_plano(_enviar_ao_gestor(int(evento["pulseId"])))
    return {"ok": True}


async def _enviar_ao_gestor(item_id: int) -> None:
    import orquestrador  # import tardio: o orquestrador avisa este módulo
    from estado import Status, buscar_agente

    try:
        item = await asyncio.to_thread(obter_item, item_id)
    except Exception as erro:
        log.warning("Monday: não li o item %s (%s)", item_id, erro)
        return
    if not item:
        return
    marca = (_valor(item, COL_CONTA).get("text") or "").strip()
    if marca in SEM_CONTA:
        await _seguro(comentar, item_id, "Escolha a Conta (marca) deste item e clique em Enviar de novo.")
        return
    if marca not in MARCAS_PRONTAS:
        await _seguro(comentar, item_id, f"O Escritório Veraneio ainda não foi preparado para a marca "
                                         f"\"{marca or 'sem definição'}\". Por enquanto, só itens da Casa Veraneio.")
        return
    if _em_aberto(item_id):
        await _seguro(comentar, item_id, "Este item já está em andamento no Escritório Veraneio.")
        return
    gestor = buscar_agente("marketing", "gestor")
    if not gestor:
        return
    if gestor.status == Status.trabalhando:  # espera o Gestor terminar o que está fazendo
        await _seguro(mudar_status, item_id, NA_FILA)
        for _ in range(ESPERA_MAXIMA_S // ESPERA_GESTOR_S):
            await asyncio.sleep(ESPERA_GESTOR_S)
            if gestor.status != Status.trabalhando:
                break
    await _seguro(mudar_status, item_id, EM_PRODUCAO)
    pedido = (f"Produza a peça do item abaixo, do planejamento de Social Media no Monday.\n\n{briefing(item)}\n\n"
              f"Na entrega final, inclua a legenda pronta (se a peça tiver legenda) entre as linhas "
              f"{MARCA_LEGENDA[0]} e {MARCA_LEGENDA[1]}.")
    await orquestrador.nova_tarefa(config.DONO_MAX, "marketing", gestor, pedido,
                                   ao_criar=lambda tarefa_id: vincular(tarefa_id, item_id))


@rotas.post("/criativos/{tarefa_id}")
async def receber_criativo(tarefa_id: int, arquivo: UploadFile = File(...), authorization: str = Header("")):
    """O Trabalhador Max envia cada arquivo final; vai para a coluna Criativos do item vinculado."""
    from producao import _exigir_operador

    _exigir_operador(authorization)
    item_id = item_da_tarefa(tarefa_id)
    if not item_id:
        raise HTTPException(status_code=404, detail="Tarefa sem item do Monday")
    await asyncio.to_thread(anexar_criativo, item_id, arquivo.filename or "criativo", await arquivo.read())
    return {"ok": True}


def referencias_da_tarefa(tarefa_id: int) -> list[dict]:
    """Referências do item (links novos, válidos por ~1 h) para a produção baixar."""
    item_id = item_da_tarefa(tarefa_id)
    if not (item_id and ativo()):
        return []
    try:
        item = obter_item(item_id)
        return arquivos(item, COL_REFERENCIAS) if item else []
    except Exception as erro:
        log.warning("Monday: referências do item %s indisponíveis (%s)", item_id, erro)
        return []
