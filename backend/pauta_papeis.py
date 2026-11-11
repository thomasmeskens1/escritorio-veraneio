"""Pauta da semana confere o PAPEL das peças, não só a quantidade (gestor-13, Onda 1 de novembro).

A pauta contava Reels, Carrosséis e Stories, mas não dizia se a semana tinha peça de Conversão. Perto de uma data
comercial, uma semana só de Descoberta deixa reserva na mesa; uma semana só de "chame no Direct" cansa o público.
O papel (manual 15 §5) "fica no texto do planejamento, não é coluna do Monday": aqui ele é lido do nome do item ou da
legenda ("Papel: Conversão" ou a palavra solta). Conta em código, sem IA e sem escrever nada no Monday.
"""

import re
from datetime import date, timedelta

import calendario
import calendario_eventos
import empresas
import monday

PAPEIS = ("Descoberta", "Consideração", "Confiança", "Conversão", "Relacionamento")
PRINCIPAIS = ("Descoberta", "Consideração", "Conversão")
_PADRAO = {"Descoberta": r"descoberta", "Consideração": r"considera[cç][aã]o", "Confiança": r"confian[cç]a",
           "Conversão": r"convers[aã]o", "Relacionamento": r"relacionamento"}
EXPLICITO = re.compile(r"\bpapel\s*(?:na\s+jornada)?\s*[:=]\s*(\w+)", re.I)
JANELA_DATA, JANELA_PRAZO = 21, 14  # data comercial e prazo "fechar até" que pedem Conversão na semana


def papel(texto: str) -> str:
    """Papel citado ("Papel: Conversão" vale mais que a palavra solta); "" se nenhum."""
    alvo = texto or ""
    if (explicito := EXPLICITO.search(alvo)):
        alvo = explicito.group(1)
    return next((p for p in PAPEIS if re.search(rf"\b{_PADRAO[p]}\b", alvo, re.I)), "")


def datas_comerciais(empresa: str, hoje: date) -> list[str]:
    """Datas da empresa nos próximos 21 dias e prazos "fechar até" válidos nos próximos 14."""
    nome, fim = empresas.nome(empresa), hoje + timedelta(days=JANELA_DATA)
    achadas = {}
    for e in calendario_eventos.proximos(hoje, meses=1):
        if e["empresas"] in (nome, "todas") and hoje <= e["data"] <= fim:
            achadas.setdefault(e["nome"], e["data"])
    for e in calendario.eventos(empresa, hoje, fim):
        if e["tipo"] == "data da empresa" and hoje <= e["data"] <= fim:
            achadas.setdefault(e["nome"], e["data"])
    linhas = [f"{n} em {d:%d/%m} (daqui a {(d - hoje).days} dias)" for n, d in sorted(achadas.items(), key=lambda x: x[1])]
    import prazos_comerciais  # import tardio: lê o calendario.json

    linhas += [f"fechamento de {p['momento']} até {p['fechar_ate']:%d/%m} (faltam {p['faltam']} dias)"
               for p in prazos_comerciais.prazos(empresa, hoje) if p["valido"] and p["faltam"] <= JANELA_PRAZO]
    return linhas


def _sugerir(itens: list[tuple[dict, str]], conversao: bool) -> str:
    """Item para trocar de papel (entre os que são ou não são Conversão): um Carrossel primeiro (manual 15: o
    Carrossel fica com a conversão)."""
    candidatos = [i for i, p in itens if (p == "Conversão") == conversao]
    carrossel = [i for i in candidatos if monday.tipo_do_item(i["name"]) == "CARROSSEL"]
    return (carrossel or candidatos or [{"name": ""}])[-1]["name"]


def analisar(itens: list[dict], empresa: str, hoje: date, coluna) -> dict:
    """{"mistura": "3 Descoberta, 1 Consideração, 0 Conversão", "avisos_papel": [...]} dos itens da semana."""
    if not itens:
        return {"mistura": "", "avisos_papel": []}
    com_papel = [(i, papel(f"{i['name']}\n{coluna(i, monday.COL_LEGENDA)}")) for i in itens]
    contagem = {p: sum(1 for _, x in com_papel if x == p) for p in PAPEIS}
    mostrar = [p for p in PAPEIS if p in PRINCIPAIS or contagem[p]]
    avisos = []
    sem = [i["name"] for i, p in com_papel if not p]
    if contagem["Conversão"] == 0 and (datas := datas_comerciais(empresa, hoje)):
        sugestao = _sugerir(com_papel, conversao=False)
        avisos.append("nenhuma peça de Conversão e há data comercial perto (" + "; ".join(datas[:3]) + ")"
                      + (f": sugiro passar \"{sugestao}\" para Conversão" if sugestao else ""))
    if contagem["Conversão"] * 2 > len(itens):
        sugestao = _sugerir(com_papel, conversao=True)
        avisos.append(f"mais da metade da semana é Conversão ({contagem['Conversão']} de {len(itens)}): o público "
                      "cansa" + (f"; sugiro passar \"{sugestao}\" para Descoberta" if sugestao else ""))
    if sem:
        avisos.append(f"{len(sem)} peça(s) sem papel no nome ou na legenda (escreva \"Papel: ...\"): "
                      + "; ".join(sem[:5]))
    return {"mistura": ", ".join(f"{contagem[p]} {p}" for p in mostrar), "avisos_papel": avisos}
