"""Datas do planejamento no Monday: cada item fica no grupo do mês da Data Postagem, em ordem de data.

- Sem data: o item vai para o grupo "Definir Data" (o agente nunca inventa data; Thomas, 26/10/2026).
- Data definida ou alterada (webhook da coluna Data Postagem, ou item criado pelo Social Media): o item vai para o
  grupo do mês e fica logo abaixo do último item com data igual ou anterior (10/12 em cima, 12/12 embaixo).
- Data apagada: volta para "Definir Data".
Só o board do planejamento (monday.BOARD); o mês vem da data (o board é de um ano só).
"""

import logging

import monday

log = logging.getLogger(__name__)

GRUPO_SEM_DATA = "Definir Data"
COL_DATA = "data"  # Data Postagem
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
VERSAO_POSICAO = "2025-10"  # change_item_position só existe a partir desta versão da API


def grupo_do_mes(data: str) -> str:
    return MESES[int(data[5:7]) - 1]


def _item(item_id: int) -> dict | None:
    itens = monday._api("query ($i: [ID!]) { items(ids: $i) { id board { id } group { id title } "
                        f"column_values(ids: [\"{COL_DATA}\"]) {{ text }} }} }}", {"i": [str(item_id)]})["items"]
    return itens[0] if itens else None


def _posicionar(item_id: int, relativo_a: str, metodo: str) -> None:
    monday._api("mutation ($i: ID!, $r: ID!, $m: PositionRelative!) { change_item_position(item_id: $i, "
                "relative_to: $r, position_relative_method: $m) { id } }",
                {"i": str(item_id), "r": relativo_a, "m": metodo}, versao=VERSAO_POSICAO)


def reposicionar(item_id: int) -> str:
    """Leva o item ao grupo certo pela Data Postagem e o coloca em ordem de data. Devolve o que fez."""
    item = _item(item_id)
    if not item or int(item["board"]["id"]) != monday.BOARD:
        return "fora do board"
    data = (item["column_values"][0]["text"] or "").strip()[:10]
    destino = monday.grupo_por_nome(grupo_do_mes(data) if data else GRUPO_SEM_DATA, criar=True)
    if item["group"]["id"] != destino["id"]:
        monday._api("mutation ($i: ID!, $g: String!) { move_item_to_group(item_id: $i, group_id: $g) { id } }",
                    {"i": str(item_id), "g": destino["id"]})
    if not data:
        return f"sem data → {destino['title']}"
    # Ordem: logo abaixo do último item com data <= a deste; se nenhum, no topo do grupo.
    outros = [i for i in monday.itens_do_grupo(destino["id"]) if str(i["id"]) != str(item_id)]
    datas = {i["id"]: next((c["text"] or "" for c in i["column_values"] if c["id"] == COL_DATA), "")[:10] for i in outros}
    anteriores = [i for i in outros if datas[i["id"]] and datas[i["id"]] <= data]
    if anteriores:
        _posicionar(item_id, anteriores[-1]["id"], "after_at")
    elif outros:
        _posicionar(item_id, outros[0]["id"], "before_at")
    return f"{data} → {destino['title']}"


def reposicionar_seguro(item_id: int) -> None:
    try:
        log.info("Monday: item %s %s", item_id, reposicionar(item_id))
    except Exception as erro:  # a automação nunca derruba o webhook nem a criação do item
        log.warning("Monday: não reposicionei o item %s (%s)", item_id, erro)


def criar_webhook(url: str) -> dict:
    """Webhook da coluna Data Postagem (a mesma URL do botão Enviar; o tratamento separa pela coluna)."""
    import json

    return monday._api("mutation ($b: ID!, $u: String!, $c: JSON!) { create_webhook(board_id: $b, url: $u, "
                       "event: change_specific_column_value, config: $c) { id board_id } }",
                       {"b": str(monday.BOARD), "u": url, "c": json.dumps({"columnId": COL_DATA})})["create_webhook"]
