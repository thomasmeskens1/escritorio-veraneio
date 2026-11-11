"""Uma pasta por peça do Monday (brainstorm de 11/11/2026, Onda 2: social_media-01 e gestor-07).

A mesma peça virava duas pastas no Drive ("REELS - LODGE 32 BEIRA-MAR" e "REELS - LODGE 32 JUQUEHY"), porque o nome
saía do título digitado. Quando a produção nasce de um item do Monday, o trabalhador recebe aqui o item (número,
nome, TIPO e descrição) e monta a pasta "SIGLA ｜ TIPO - DESCRIÇÃO #<item>" (scripts/max/pasta_da_peca.py). Uma nova
produção do mesmo item volta para a mesma pasta, numa subpasta v2, v3...; o tipo da pasta é o TIPO do item.
Sem consulta à API: o nome do item já vem no briefing ("Item do Monday: POST | ... (grupo ...)").
"""

import re

import monday

ITEM_NO_TEXTO = re.compile(r"Item do Monday: (.+?) \(grupo ")
PASTA_TIPO = {"NEWSLETTER": "E-MAIL"}  # nome do tipo na pasta (os demais iguais ao do Monday)


def item_da_producao(tarefa_id: int, texto: str) -> dict | None:
    """{"id", "nome", "tipo", "descricao"} do item ligado à produção; None se ela não veio do Monday."""
    if not (item_id := monday.item_da_tarefa(tarefa_id)):
        return None
    nome = (m.group(1).strip() if (m := ITEM_NO_TEXTO.search(texto or "")) else "")
    tipo = monday.tipo_do_item(nome) or ""
    descricao = monday.NOME_PADRAO.match(nome).group(2) if tipo else nome
    return {"id": int(item_id), "nome": nome[:200], "tipo": PASTA_TIPO.get(tipo, tipo),
            "descricao": re.sub(r"\s+", " ", descricao).strip()[:120]}
