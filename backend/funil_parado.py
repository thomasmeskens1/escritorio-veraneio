"""Mutirão do funil parado (N2-estrategista-20, Onda 3 de novembro).

"Estrategista, mutirão do funil" ou "oportunidades paradas": o sistema lê as oportunidades abertas do "[Corp] Funil de
Vendas" no Monday (SÓ LEITURA, nada é gravado) e separa, EM CÓDIGO, sem IA e sem web:
  - destravar: parada há até 30 dias (falta um dado ou uma resposta);
  - reaquecer: de 31 a 90 dias sem contato;
  - encerrar (com elegância): mais de 90 dias, evento com data que já passou ou 3+ tentativas sem retorno há 30+ dias.
Cada uma leva uma sugestão curta de próximo passo, também em código. Quem muda o status no Monday é sempre uma pessoa.
As colunas do quadro são achadas pelo título (etapa, último contato, tentativas, data do evento, pax, decisor); só
entram as que existirem. Sem coluna de último contato, vale a última atualização do item no Monday.
A lista é nominal: só para quem pode ver a carteira (carteira.ve_carteira), com o rodapé de uso interno; os outros
veem só as contagens. Valores do funil não são lidos.
"""

import re
import unicodedata
from datetime import date

AGENTES = {"estrategista", "prospectador"}
GRUPOS_ABERTOS = ["topics"]  # Oportunidades ativas do [Corp] Funil de Vendas
PARADA_DIAS = 7              # menos que isso não é parada (salvo etapa "Aguardando Definição")
DESTRAVAR_ATE = 30
REAQUECER_ATE = 90
TENTATIVAS_MAX = 3
MAX_LINHAS = 25              # por lista
PEDIDO = re.compile(r"\bmutir[aã]o\b|\bfunil (?:de vendas )?parado\b|\boportunidades? parad\w*|"
                    r"\bneg[oó]cios? parad\w*|\baguardando defini[cç][aã]o\b|\blimp\w* (?:o|do) funil\b", re.I)
# Colunas conhecidas do quadro (comercial.COLUNAS_GANHO) e, para as outras, o título (sem acento, minúsculo).
TITULOS = {
    "etapa": r"\b(etapa|status|fase|estagio)\b",
    "contato": r"\b(ultim[oa]s? (contato|interacao|retorno|follow)|follow ?up|data (do|de) contato)\b",
    "tentativas": r"\b(tentativas?|follow ?ups?|contatos feitos)\b",
    "evento": r"\bdata (do|de) evento\b",
    "pax": r"\b(pax|convidados|participantes)\b",
    "decisor": r"\bdecisor\b",
    "tipo": r"\btipo (do|de) evento\b",
}
CONHECIDAS = {"evento": "date_mkp5eds", "pax": "n_meros_mkmgpvds", "tipo": "color_mm4pd1wc"}
FALTA = {"evento": "data do evento", "pax": "número de convidados", "decisor": "decisor", "tipo": "tipo de evento"}


def e_pedido(agente_id: str, texto: str) -> bool:
    return agente_id in AGENTES and bool(PEDIDO.search(texto or ""))


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def colunas_usadas(colunas: list[dict]) -> dict[str, str]:
    """{papel: id da coluna} só com as que existem no quadro."""
    ids = {c["id"] for c in colunas}
    achadas = {papel: col for papel, col in CONHECIDAS.items() if col in ids}
    for papel, padrao in TITULOS.items():
        if papel not in achadas:
            if (col := next((c["id"] for c in colunas if re.search(padrao, _normal(c.get("title", "")))), None)):
                achadas[papel] = col
    return achadas


# --- Monday (só leitura) -------------------------------------------------------------------------------------

def ler(quadro: int | None = None) -> tuple[list[dict], dict[str, str]]:
    """(oportunidades abertas [{nome, atualizado, papel: texto}], colunas usadas)."""
    import comercial
    from monday import _api

    quadro = quadro or comercial.QUADRO_FUNIL
    dados = _api("query ($b: [ID!], $g: [String]) { boards(ids: $b) { columns { id title type } groups(ids: $g) { "
                 "items_page(limit: 500) { cursor items { name updated_at column_values { id text } } } } } }",
                 {"b": [str(quadro)], "g": GRUPOS_ABERTOS})
    quadro_dados = dados["boards"][0]
    usadas = colunas_usadas(quadro_dados.get("columns") or [])
    papeis = {col: papel for papel, col in usadas.items()}
    itens = []

    def guardar(lista: list[dict]) -> None:
        for item in lista:
            valores = {c["id"]: c.get("text") or "" for c in item.get("column_values") or []}
            if valores.get("dropdown_mm3b42sb") == "PF" or "Social" in valores.get("color_mm4pd1wc", ""):
                continue  # PF e Social ficam fora, como nos ganhos (comercial.clientes)
            itens.append({"nome": item["name"], "atualizado": item.get("updated_at") or "",
                          **{papeis[c]: v for c, v in valores.items() if c in papeis}})

    for grupo in quadro_dados.get("groups") or []:
        pagina = grupo["items_page"]
        while True:
            guardar(pagina["items"])
            if not pagina.get("cursor"):
                break
            pagina = _api("query ($k: String!) { next_items_page(limit: 500, cursor: $k) { cursor items { name "
                          "updated_at column_values { id text } } } }", {"k": pagina["cursor"]})["next_items_page"]
    return itens, usadas


# --- Critério (código) ---------------------------------------------------------------------------------------

def _data(texto: str) -> date | None:
    import agenda_clientes

    return agenda_clientes.data((texto or "")[:10] if re.match(r"\d{4}-\d{2}-\d{2}T", texto or "") else texto)


def _tentativas(texto: str) -> int:
    achou = re.search(r"\d+", texto or "")
    return int(achou.group(0)) if achou else 0


def classificar(item: dict, usadas: dict[str, str], hoje: date) -> dict | None:
    """{nome, lista, dias, etapa, falta, motivo, sugestao} ou None (não está parada)."""
    import comercial

    contato = _data(item.get("contato", "")) if "contato" in usadas else None
    contato = contato or _data(item.get("atualizado", ""))
    dias = (hoje - contato).days if contato else None
    etapa = (item.get("etapa") or "").strip()
    aguardando = "aguardando" in _normal(etapa)
    tentativas = _tentativas(item.get("tentativas", "")) if "tentativas" in usadas else 0
    evento = _data(item.get("evento", "")) if "evento" in usadas else None
    falta = [FALTA[p] for p in FALTA if p in usadas and not _data_ou_texto(p, item.get(p, ""))]
    if dias is not None and dias < PARADA_DIAS and not aguardando:
        return None
    if evento and evento < hoje:
        lista, motivo = "encerrar", f"data do evento ({evento:%d/%m/%Y}) já passou"
    elif dias is None:
        lista, motivo = "reaquecer", "sem data de contato no CRM"
    elif dias > REAQUECER_ATE:
        lista, motivo = "encerrar", f"{dias} dias sem contato"
    elif tentativas >= TENTATIVAS_MAX and dias > DESTRAVAR_ATE:
        lista, motivo = "encerrar", f"{tentativas} tentativas sem retorno"
    elif dias > DESTRAVAR_ATE:
        lista, motivo = "reaquecer", f"{dias} dias sem contato"
    else:
        lista, motivo = "destravar", f"{dias} dias sem contato"
    return {"nome": comercial._sem_codigo(item.get("nome", "")), "lista": lista, "dias": dias, "etapa": etapa,
            "falta": falta, "motivo": motivo, "tentativas": tentativas, "evento": evento,
            "sugestao": sugestao(lista, falta, tentativas)}


def _data_ou_texto(papel: str, texto: str) -> bool:
    """Campo preenchido? "Aguardando Definição" na data do evento conta como vazio."""
    if papel == "evento":
        return bool(_data(texto))
    return bool((texto or "").strip()) and "aguardando" not in _normal(texto)


def sugestao(lista: str, falta: list[str], tentativas: int = 0) -> str:
    if lista == "destravar":
        if "data do evento" in falta:
            return "Pergunte só a data: \"Vocês já têm a data do evento? Consigo segurar a agenda até sexta.\""
        if "decisor" in falta:
            return "Descubra quem decide: \"Quem mais precisa aprovar? Posso mandar um resumo para essa pessoa.\""
        if "número de convidados" in falta:
            return "Peça uma faixa de convidados (até 30, 30 a 100, mais de 100) para fechar o formato."
        if falta:
            return f"Peça o que falta ({', '.join(falta)}) numa pergunta de sim ou não."
        return "Proponha um próximo passo com data (ligação de 15 minutos ou visita) e confirme quem decide."
    if lista == "reaquecer":
        return ("Retome com uma novidade útil (data livre, formato novo ou caso parecido) e uma pergunta direta: "
                "\"Ainda faz sentido para vocês neste semestre?\"")
    extra = f" depois de {tentativas} tentativas" if tentativas >= TENTATIVAS_MAX else ""
    return (f"Mande um encerramento elegante{extra} (\"Vamos pausar por aqui; quando voltar a fazer sentido, a "
            "agenda está aberta\") e mude para Perdido ou Pausado no Monday (a mudança é sua).")


def separar(itens: list[dict], usadas: dict[str, str], hoje: date) -> dict[str, list[dict]]:
    listas = {"destravar": [], "reaquecer": [], "encerrar": []}
    for item in itens:
        if (reg := classificar(item, usadas, hoje)):
            listas[reg["lista"]].append(reg)
    for regs in listas.values():  # o evento mais próximo primeiro; depois o mais parado
        regs.sort(key=lambda r: (r["evento"] is None, r["evento"] or hoje, -(r["dias"] or 0)))
    return listas


# --- Texto ---------------------------------------------------------------------------------------------------

TITULO = {"destravar": "1. Destravar (até 30 dias parada)", "reaquecer": "2. Reaquecer (31 a 90 dias)",
          "encerrar": "3. Encerrar com elegância (mais de 90 dias, evento passado ou tentativas esgotadas)"}


def _linha(n: int, reg: dict) -> str:
    detalhes = [reg["motivo"]] + ([f"etapa {reg['etapa']}"] if reg["etapa"] else []) \
        + ([f"falta {', '.join(reg['falta'])}"] if reg["falta"] else [])
    return f"{n}. **{reg['nome']}** · {' · '.join(detalhes)}\n   Próximo passo: {reg['sugestao']}"


def texto(listas: dict[str, list[dict]], usadas: dict[str, str], nomes: bool, hoje: date) -> str:
    total = sum(len(v) for v in listas.values())
    blocos = [f"Mutirão do funil parado do Corporativo em {hoje:%d/%m/%Y}: {total} oportunidades abertas paradas, "
              "separadas no sistema com os dados do Monday (só leitura), sem IA e sem pesquisa na web."]
    sem = [p for p in ("contato", "etapa", "tentativas") if p not in usadas]
    if sem:
        blocos.append("Colunas que o quadro não tem (o critério segue sem elas): " + ", ".join(sem)
                      + (". Dias sem contato contados pela última atualização do item." if "contato" in sem else "."))
    if not nomes:
        blocos.append("Sem acesso à carteira: aqui vão só as contagens.")
    for chave, regs in listas.items():
        if not nomes:
            blocos.append(f"## {TITULO[chave]}\n{len(regs)} oportunidades.")
            continue
        linhas = [_linha(n, r) for n, r in enumerate(regs[:MAX_LINHAS], start=1)] or ["Nenhuma."]
        if len(regs) > MAX_LINHAS:
            linhas.append(f"... e mais {len(regs) - MAX_LINHAS}.")
        blocos.append(f"## {TITULO[chave]}\n" + "\n".join(linhas))
    blocos.append("Nada foi mudado no Monday: a troca para Perdido ou Pausado é sempre de uma pessoa. Datas vazias ou "
                  "desatualizadas no CRM mudam a conta; confira com o vendedor antes de ligar.")
    return "\n\n".join(blocos)


def executar(login: str, hoje: date | None = None, itens: list[dict] | None = None,
             usadas: dict[str, str] | None = None) -> str:
    import carteira

    hoje = hoje or date.today()
    if itens is None:
        try:
            itens, usadas = ler()
        except Exception as erro:
            import logging

            logging.getLogger(__name__).warning("Funil parado: Monday fora (%s).", erro)
            return "Não consegui ler o funil no Monday agora. Tente de novo em alguns minutos."
    usadas = usadas or {}
    nomes = carteira.ve_carteira(login)
    resposta = texto(separar(itens, usadas, hoje), usadas, nomes, hoje)
    return f"{resposta}\n\n{carteira.rodape(login)}" if nomes else resposta

