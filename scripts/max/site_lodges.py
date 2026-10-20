"""Limpeza das páginas do site para o Cérebro: só os dados do produto.

Página de lodge -> documento estruturado (local, capacidade, diária, suítes, descrição, valores por época,
estadia mínima, comodidades). Fica de fora: menus, galeria, mapa, avaliações de hóspedes, "outros lodges
semelhantes" e rodapé. Demais páginas: sem filtros de busca nem rodapé.
"""

import re

ROTULOS_VALOR = {"Diária": "diária", "Estadia mínima": "estadia mínima", "Taxa ativação (*)": "taxa de ativação"}
FIM_DESCRICAO = ("Ver mais", "Veja a lista de valores")
FIM_VALORES = ("Galeria de Fotos", "Avaliação Casa Veraneio", "Comodidades", "Localização")
FIM_COMODIDADES = ("Ver mais", "Localização")
CORTES = ("Confira nossos outros Lodges semelhantes",)
INICIO_RODAPE = re.compile(r"^\(\d{2}\) \d{4,5}-\d{4}$")         # telefone do rodapé
FIM_INTRO_LISTAGEM = ("Escolha o Lodge", "Filtrar")


def e_lodge(caminho: str) -> bool:
    return caminho.startswith("/lodges/")


def _ate(linhas: list[str], fins: tuple[str, ...]) -> list[str]:
    for i, linha in enumerate(linhas):
        if linha.startswith(fins):
            return linhas[:i]
    return linhas


def _depois(linhas: list[str], marco: str) -> list[str]:
    return linhas[linhas.index(marco) + 1:] if marco in linhas else []


def _sem_rodape(linhas: list[str]) -> list[str]:
    linhas = _ate(linhas, CORTES)
    for i, linha in enumerate(linhas):
        if INICIO_RODAPE.match(linha):
            return linhas[:i]
    return linhas


def _suites(linhas: list[str]) -> list[str]:
    """Entre o local e o "N quartos"; junta "• Suíte 1" + "– 1 cama queen;" numa linha."""
    suites: list[str] = []
    for linha in linhas:
        if re.match(r"^\d+(\s*quartos?)?$", linha):
            break
        if linha.startswith(("–", "-")) and suites:
            suites[-1] += " " + linha
        else:
            suites.append(linha.lstrip("• ").strip())
    return [s for s in suites if s]


def _valores(linhas: list[str]) -> list[str]:
    """Blocos "Época / Diária / R$ x / Estadia mínima / 2 noites" -> "- Época: diária R$ x | estadia mínima 2 noites"."""
    epocas: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if linha in ROTULOS_VALOR and epocas and i + 1 < len(linhas):
            epocas[-1][1].append(f"{ROTULOS_VALOR[linha]} {linhas[i + 1]}")
            i += 2
            continue
        epocas.append((linha, []))
        i += 1
    return [f"- {epoca}: " + " | ".join(itens) if itens else f"- {epoca}" for epoca, itens in epocas]


def estruturar_lodge(titulo: str, url: str, corpo: str) -> str:
    linhas = _sem_rodape(corpo.splitlines())
    achar = lambda padrao: (m.group(1).strip() if (m := re.search(padrao, "\n".join(linhas))) else "")
    nome = titulo.split(" - Casa Veraneio")[0].strip() or titulo
    local = achar(r"Favoritar\n(.+)")
    capacidade = " | ".join(filter(None, [
        f"{q} quartos" if (q := achar(r"(\d+)\s*quartos?")) else "",
        f"{p} pessoas" if (p := achar(r"(\d+)\s*pessoas?")) else "",
        f"{e} estrelas" if (e := achar(r"(\d+)\s*estrelas?")) else "",
        f"a partir de {d}" + (" + taxa" if "+ taxa" in linhas else "") if (d := achar(r"A partir de (.+)")) else "",
        d if (d := achar(r"(?m)^(Diária a combinar)$")) else "",
    ]))
    suites = _suites(_depois(linhas, local)) if local else []
    sobre = _depois(linhas, "Valores")
    descricao = _ate(sobre, FIM_DESCRICAO)
    valores = _valores(_ate(_depois(linhas, "Veja a lista de valores abaixo por época do ano"), FIM_VALORES))
    comodidades = _ate(_depois(linhas, "Comodidades"), FIM_COMODIDADES)
    nota_taxa = [l for l in linhas if l.startswith("(*)")]

    partes = [f"# {nome}" + (f" — {local}" if local else ""), f"Fonte: {url}"]
    if capacidade:
        partes.append(f"Resumo: {capacidade}")
    for rotulo, itens in (("Acomodações", suites), ("Sobre o lodge", descricao),
                          ("Valores por época", valores + nota_taxa)):
        if itens:
            partes += ["", f"## {rotulo}", *itens]
    if comodidades:
        partes += ["", "## Comodidades", ", ".join(comodidades)]
    return "\n".join(partes)


def limpar_pagina(caminho: str, titulo: str, url: str, corpo: str) -> str:
    """Conteúdo que vai ao Cérebro ("" = página sem conteúdo útil, ex.: só a listagem com filtros)."""
    if e_lodge(caminho):
        return estruturar_lodge(titulo, url, corpo)
    linhas = _sem_rodape(corpo.splitlines())
    if caminho in ("/lodges", "/lodges-orlando"):  # listagens: só a apresentação antes dos filtros
        linhas = _ate(linhas, FIM_INTRO_LISTAGEM)
    if len(linhas) < 3:
        return ""
    return f"# {titulo or caminho}\nFonte: {url}\n\n" + "\n".join(linhas)
