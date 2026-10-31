"""Pauta da semana, fase 1 (Onda 2, item 15; gestor-12, social_media-10).

Rotina de segunda criada pelo botão "Agendar tarefa" do Gestor (mecanismo de rotinas, agendamentos.py) com a tarefa
"Pauta da semana". No horário, o sistema LÊ o quadro de Social Media do Monday (monday.BOARD; só leitura, nenhum
outro quadro) e compara, por empresa, as peças da semana com a grade do manual 15. A pauta chega no chat do Gestor:
o que falta, o que sobra, itens sem Conta ou sem TIPO, entregas vencendo em 48 h e contagens "N NOITES" que não batem
com a Data Postagem. Sem IA e sem Max: é conta em código. Fase 1: nada é criado, alterado nem enfileirado; o botão
"Produzir a semana" e a produção à noite dependem da decisão 4 (PC ligado à noite), em aberto.
"""

import asyncio
import logging
import re
from datetime import date, timedelta

import calendario
import empresas
import monday
import monday_datas
import tarefas

log = logging.getLogger(__name__)

AGENTE = "gestor"
PEDIDO = re.compile(r"\bpauta\s+da\s+semana\b", re.I)
# Decisão 4 em aberto (PC ligado à noite): a rotina da pauta só roda entre 07:00 e 21:59.
HORA_MINIMA, HORA_MAXIMA = 7, 21
COL_ENTREGA = "date_mm0p7s2f"
# Manual 15 §1 (28/10/2026), por semana, só os TIPOS que existem no Monday. Shorts e TikTok saem do próprio Reels
# ("também Short e TikTok") e não contam à parte; Stories contam em DIAS com Stories. (mínimo, máximo)
GRADE = {
    "casa_veraneio": {"REELS": (3, 3), "CARROSSEL": (2, 2), "STORIES": (5, 7)},
    "cv_corporativo": {"REELS": (2, 2), "CARROSSEL": (1, 1), "STORIES": (3, 3)},
    "casa_vero": {"REELS": (2, 2), "CARROSSEL": (1, 1), "STORIES": (4, 4)},
}
ENCERRADOS = {"revisão", "finalizado"}
NOITES = re.compile(r"\b(\d{1,3})\s+NOITES\b", re.I)


def e_pedido(texto: str) -> bool:
    return bool(PEDIDO.search(texto or ""))


def horario_invalido(regra: dict) -> str | None:
    """Mensagem de erro se a rotina da pauta cairia de madrugada (ou em intervalo, que roda a qualquer hora)."""
    if regra.get("tipo") == "intervalo":
        return "A pauta da semana não roda em intervalo de horas: escolha \"Toda semana\" (segunda) e um horário."
    hora = int(regra.get("hora", 9)) if regra.get("tipo") == "cron" else int(regra["quando"][11:13])
    if not HORA_MINIMA <= hora <= HORA_MAXIMA:
        return (f"A pauta da semana não roda de madrugada (decisão 4 em aberto): escolha um horário entre "
                f"{HORA_MINIMA:02d}:00 e {HORA_MAXIMA}:59.")
    return None


def semana(hoje: date) -> tuple[date, date]:
    """Segunda a domingo da semana de `hoje`."""
    segunda = hoje - timedelta(days=hoje.weekday())
    return segunda, segunda + timedelta(days=6)


# ---------- Leitura do Monday (só leitura; nos testes, substituída) ----------

def _itens(grupo_id: str) -> list[dict]:
    dados = monday._api("query ($b: [ID!], $g: [String]) { boards(ids: $b) { groups(ids: $g) { items_page(limit: 200) "
                        f"{{ items {{ id name column_values(ids: [\"{monday_datas.COL_DATA}\", \"{monday.COL_STATUS}\", "
                        f"\"{monday.COL_CONTA}\", \"{COL_ENTREGA}\", \"{monday.COL_LEGENDA}\"]) {{ id text }} }} }} "
                        "} } }", {"b": [str(monday.BOARD)], "g": [grupo_id]})
    return dados["boards"][0]["groups"][0]["items_page"]["items"]


def ler_quadro(inicio: date, fim: date) -> dict[str, list[dict]]:
    """Grupos do mês (ou dos dois meses) da semana e "Definir Data": {título: itens}."""
    nomes = [monday_datas.MESES[inicio.month - 1], monday_datas.MESES[fim.month - 1], monday_datas.GRUPO_SEM_DATA]
    quadro = {}
    for nome in dict.fromkeys(nomes):
        if (grupo := monday.grupo_por_nome(nome)):  # criar=False: só lê
            quadro[nome] = _itens(grupo["id"])
    return quadro


# ---------- Análise (conta em código) ----------

def _coluna(item: dict, coluna: str) -> str:
    return next(((c.get("text") or "").strip() for c in item.get("column_values", []) if c["id"] == coluna), "")


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat(texto[:10]) if texto else None
    except ValueError:
        return None


def _contagem_errada(item: dict) -> str | None:
    """"REELS | ... 45 NOITES" com a postagem atual pedindo outro número (analista_tendencias-27)."""
    postagem = _data(_coluna(item, monday_datas.COL_DATA))
    texto = f"{item['name']}\n{_coluna(item, monday.COL_LEGENDA)}"
    if not postagem or not (achado := NOITES.search(texto)):
        return None
    alvo_nome = "Carnaval" if re.search(r"carnaval", texto, re.I) else "Réveillon"
    certo = calendario.faltam(calendario.data_do_alvo(alvo_nome, postagem), postagem)
    if int(achado.group(1)) == certo:
        return None
    return (f"{item['name']}: diz {achado.group(1)} noites, mas com a postagem em {postagem:%d/%m/%Y} faltam "
            f"{certo} para o {alvo_nome}")


def _diferenca(tipo: str, feito: int, minimo: int, maximo: int) -> str:
    unidade = " dias com Stories" if tipo == "STORIES" else ""
    meta = f"{minimo}" if minimo == maximo else f"{minimo} a {maximo}"
    if feito < minimo:
        situacao = f"FALTAM {minimo - feito}"
    elif feito > maximo:
        situacao = f"{feito - maximo} A MAIS"
    else:
        situacao = "ok"
    return f"{tipo}: {feito} de {meta}{unidade} ({situacao})"


def analisar(quadro: dict[str, list[dict]], empresa: str, hoje: date) -> dict:
    """Peças da semana da empresa contra a grade; itens sem Conta ficam à parte (não contam para ninguém)."""
    inicio, fim = semana(hoje)
    rotulo = empresas.EMPRESAS[empresa]["monday"].lower()
    vistos, da_semana, sem_conta, sem_data = set(), [], [], 0
    for grupo, itens in quadro.items():
        for item in itens:
            if item["id"] in vistos:
                continue
            vistos.add(item["id"])
            conta = _coluna(item, monday.COL_CONTA)
            postagem = _data(_coluna(item, monday_datas.COL_DATA))
            if conta.lower() != rotulo:
                if conta in monday.SEM_CONTA and postagem and inicio <= postagem <= fim:
                    sem_conta.append(item["name"])
                continue
            if grupo == monday_datas.GRUPO_SEM_DATA or not postagem:
                sem_data += 1
            elif inicio <= postagem <= fim:
                da_semana.append((postagem, item))
    da_semana.sort(key=lambda x: x[0])
    contagem = {tipo: 0 for tipo in GRADE[empresa]}
    dias_stories, fora_da_grade, sem_tipo = set(), {}, []
    for postagem, item in da_semana:
        tipo = monday.tipo_do_item(item["name"])
        if tipo == "STORIES":
            dias_stories.add(postagem)
        elif tipo in contagem:
            contagem[tipo] += 1
        elif tipo:
            fora_da_grade[tipo] = fora_da_grade.get(tipo, 0) + 1
        else:
            sem_tipo.append(item["name"])
    contagem["STORIES"] = len(dias_stories)
    vencendo = [f"{item['name']} (entrega {entrega:%d/%m}, {_coluna(item, monday.COL_STATUS) or 'sem status'})"
                for _, item in da_semana
                if (entrega := _data(_coluna(item, COL_ENTREGA))) and hoje <= entrega <= hoje + timedelta(days=2)
                and _coluna(item, monday.COL_STATUS).lower() not in ENCERRADOS]
    return {"empresa": empresa, "inicio": inicio, "fim": fim, "itens": da_semana,
            "grade": [_diferenca(t, contagem[t], *GRADE[empresa][t]) for t in GRADE[empresa]],
            "fora_da_grade": fora_da_grade, "sem_tipo": sem_tipo, "sem_conta": sem_conta, "sem_data": sem_data,
            "vencendo": vencendo, "contagens": [c for _, i in da_semana if (c := _contagem_errada(i))]}


def _texto_empresa(a: dict) -> str:
    linhas = [f"**{empresas.nome(a['empresa'])}** — semana de {a['inicio']:%d/%m} a {a['fim']:%d/%m}",
              "- Grade (manual 15): " + "; ".join(a["grade"])]
    if a["fora_da_grade"]:
        linhas.append("- Fora da grade semanal: " + ", ".join(f"{t} {n}" for t, n in a["fora_da_grade"].items()))
    if a["vencendo"]:
        linhas.append("- Entregas vencendo em 48 h: " + "; ".join(a["vencendo"]))
    if a["contagens"]:
        linhas.append("- Contagem que não bate com a Data Postagem: " + "; ".join(a["contagens"]))
    if a["sem_tipo"]:
        linhas.append("- Sem TIPO no nome (não contam na grade): " + "; ".join(a["sem_tipo"]))
    if a["sem_data"]:
        linhas.append(f"- {a['sem_data']} item(ns) desta empresa sem Data Postagem (Definir Data).")
    if a["itens"]:
        linhas.append("- Peças da semana: " + "; ".join(
            f"{p:%d/%m} {i['name']} [{_coluna(i, monday.COL_STATUS) or 'sem status'}]" for p, i in a["itens"]))
    else:
        linhas.append("- Nenhuma peça desta empresa com postagem nesta semana.")
    return "\n".join(linhas)


def montar(empresa: str | None, hoje: date | None = None, quadro: dict | None = None) -> str:
    """Pauta pronta para o chat do Gestor: a empresa da rotina, ou as três SEPARADAS quando é "todas"."""
    hoje = hoje or date.today()
    if quadro is None:
        if not monday.ativo():
            return "Pauta da semana: o Monday não está configurado neste servidor, então não consegui ler o quadro."
        quadro = ler_quadro(*semana(hoje))
    lista = [empresa] if empresa in GRADE else list(GRADE)
    analises = [analisar(quadro, e, hoje) for e in lista]
    partes = [f"PAUTA DA SEMANA ({hoje:%d/%m/%Y}): quadro de Social Media do Monday comparado com a grade do "
              "manual 15, empresa por empresa."]
    partes += [_texto_empresa(a) for a in analises]
    sem_conta = sorted({n for a in analises for n in a["sem_conta"]})
    if sem_conta:
        partes.append("Itens da semana sem Conta (não contam para nenhuma empresa; defina a Conta no Monday): "
                      + "; ".join(sem_conta))
    partes.append("Fase 1: só li o quadro; nada foi criado, alterado ou enfileirado no Monday. Para preencher um "
                  "buraco, peça aqui o planejamento das peças que faltam.")
    return "\n\n".join(partes)


async def entregar(usuario: str, andar: str, agente, empresa: str | None) -> int:
    """Disparo da rotina: monta a pauta (sem modelo) e a entrega no chat do Gestor como resposta dele."""
    import orquestrador  # import tardio: evita ciclo

    tarefa_id = tarefas.criar(usuario, andar, agente.id, "Pauta da semana (rotina)", "simples",
                              empresa or empresas.COMUM)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Pauta da semana: leitura do Monday, sem IA")
    try:
        texto = await asyncio.to_thread(montar, empresa)
        tarefas.atualizar(tarefa_id, status="concluida", modelo="sistema (sem IA)", resposta=texto)
        tarefas.registrar_evento(tarefa_id, "concluida", modelo="sistema (sem IA)")
    except Exception as erro:
        log.exception("Pauta da semana (tarefa %s) falhou.", tarefa_id)
        tarefas.atualizar(tarefa_id, status="falhou", motivo=f"Não consegui ler o Monday para a pauta: {erro}")
        tarefas.registrar_evento(tarefa_id, "falhou", detalhe=str(erro)[:300])
    await orquestrador.entregar(tarefas.obter(tarefa_id))
    return tarefa_id
