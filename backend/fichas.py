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
MAX_FICHAS = 3
CABECALHO = ("FICHAS OFICIAIS DOS LODGES CITADOS (dados do site; valem sobre a conversa anterior e sobre trechos "
             "soltos do Cérebro; reconfira preços antes de publicar):")


def _trechos(ref: str) -> list:
    with base._trava:
        return base.db().execute("SELECT titulo, conteudo FROM conhecimento WHERE ativo = 1 AND fonte_ref = ? "
                                 "ORDER BY id", (ref,)).fetchall()


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


def ficha(numero: str) -> str | None:
    numero = str(int(numero))
    return _do_site(numero) or _da_planilha(numero)


def fichas_citadas(texto: str) -> str:
    """Fichas dos Lodges citados no pedido (até MAX_FICHAS, na ordem em que aparecem); "" se nenhum."""
    numeros = list(dict.fromkeys(str(int(n)) for n in LODGE_CITADO.findall(texto or "")))[:MAX_FICHAS]
    fichas = [f for n in numeros if (f := ficha(n))]
    return f"{CABECALHO}\n" + "\n".join(fichas) if fichas else ""
