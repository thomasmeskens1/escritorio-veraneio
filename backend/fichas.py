"""Fichas canônicas dos Lodges (nível 2 da "árvore de compactação" do conhecimento).

Nível 1: regras de ouro (sempre no contexto, agents/perfis.py). Nível 2: esta ficha, montada do documento oficial
do site (resumo, bairro, valores por época, taxa) e colocada INTEIRA no contexto quando o pedido cita o Lodge.
Nível 3: a busca do Cérebro, para o resto.

Stress test: o Designer marcou a capacidade do Lodge 20 como "pendente" porque a busca devolveu trechos sem o
número (os dados ficam espalhados entre site, planilha e acervo). Com a ficha, o essencial chega sempre junto.
"""

import re

import cerebro_base as base

LODGE_CITADO = re.compile(r"\blodges?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)
VERO_CITADO = re.compile(r"\bvero\s*#?0*(\d{1,4})\b", re.IGNORECASE)  # imóveis da Casa Vero: "Vero 87"
# Onde está a ficha de cada empresa (ingestão do site de cada uma; nunca procurar na base de outra).
REF_FICHA = {"casa_veraneio": "site/lodges/lodge-{n}", "cv_corporativo": "corporativo/espacos/lodge-{n}",
             "casa_vero": "vero/imoveis/vero-{n}"}
MAX_FICHAS = 3
CABECALHO = ("FICHAS OFICIAIS DOS IMÓVEIS CITADOS, DESTA EMPRESA (dados do site; valem sobre a conversa anterior e "
             "sobre trechos soltos do Cérebro; reconfira preços antes de publicar):")


def _trechos(ref: str, empresa: str = "casa_veraneio") -> list:
    with base._trava:
        return base.db().execute("SELECT titulo, conteudo FROM conhecimento WHERE ativo = 1 AND fonte_ref = ? "
                                 "AND empresa = ? ORDER BY id", (ref, empresa)).fetchall()


def _da_empresa(numero: str, empresa: str) -> str | None:
    """Corporativo e Casa Vero: o documento do site inteiro (já é curto e estruturado)."""
    trechos = _trechos(REF_FICHA[empresa].format(n=numero), empresa)
    if not trechos:
        return None
    titulo = trechos[0]["titulo"].split(" › ")[0]
    corpo = "\n".join(t["conteudo"] for t in trechos)
    return f"- {titulo}\n  " + "\n  ".join(l.strip() for l in corpo.splitlines() if l.strip())[:1800]


def _do_site(numero: str) -> str | None:
    trechos = _trechos(f"site/lodges/lodge-{numero}")
    if not trechos:
        return None
    linhas = []
    for trecho in trechos:
        for linha in trecho["conteudo"].splitlines():
            linha = linha.strip()
            if linha.startswith(("# ", "Fonte:", "Resumo:", "Bairro:")) or (
                    trecho["titulo"].endswith("Valores por época") and linha.startswith("- ")):
                linhas.append(linha)
    # "Lodge 20 — Praia de Iporanga - SP": o divisor de trechos leva o cabeçalho para o título do trecho.
    titulo = next((l[2:] for l in linhas if l.startswith("# ")), trechos[0]["titulo"].split(" › ")[0])
    corpo = [l for l in linhas if not l.startswith("# ")]
    return f"- {titulo}\n  " + "\n  ".join(dict.fromkeys(corpo))


def _da_planilha(numero: str) -> str | None:
    """Reserva quando o Lodge não está no site: planilha de 2023, sem o endereço exato (nunca publicar)."""
    trechos = _trechos(f"drive/planilha/info-lodges/lodge-{numero}")
    if not trechos:
        return None
    texto = "\n".join(l for l in trechos[0]["conteudo"].splitlines()
                      if l.strip() and not l.lower().startswith(("endereço", "endereco")))
    return f"- Lodge {numero} (SEM página no site; planilha interna de 2023, conferir antes de usar)\n  {texto[:500]}"


def ficha(numero: str, empresa: str = "casa_veraneio") -> str | None:
    numero = str(int(numero))
    if empresa != "casa_veraneio":
        return _da_empresa(numero, empresa)
    return _do_site(numero) or _da_planilha(numero)


def fichas_citadas(texto: str, empresa: str = "casa_veraneio") -> str:
    """Fichas dos imóveis citados no pedido, SÓ da empresa do trabalho (até MAX_FICHAS); "" se nenhum.
    Citado e sem ficha nessa empresa: o agente é avisado para não usar dado de outra empresa nem inventar."""
    padrao = VERO_CITADO if empresa == "casa_vero" else LODGE_CITADO
    numeros = list(dict.fromkeys(str(int(n)) for n in padrao.findall(texto or "")))[:MAX_FICHAS]
    if not numeros:
        return ""
    achadas = {n: ficha(n, empresa) for n in numeros}
    linhas = [f for f in achadas.values() if f]
    faltando = [n for n, f in achadas.items() if not f]
    if faltando:
        rotulo = "Vero" if empresa == "casa_vero" else "Lodge"
        linhas.append(f"- SEM FICHA nesta empresa: {', '.join(f'{rotulo} {n}' for n in faltando)}. Não use dados de "
                      "outra empresa com o mesmo nome nem invente: pergunte ao usuário com um formulário.")
    return f"{CABECALHO}\n" + "\n".join(linhas)
