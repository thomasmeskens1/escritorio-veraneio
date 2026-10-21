"""Dados dos Lodges pela API do site (back.casaveraneio.com, somente leitura), para o Cérebro.

Mais rápida e exata que renderizar as páginas: quartos, capacidade, preços por época com estadia mínima,
taxa de ativação, comodidades e descrição. Ficam de fora o endereço exato, as coordenadas, as reservas
(nunca afirmar disponibilidade) e os depoimentos.
"""

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://back.casaveraneio.com/api/lodges"
SITE = "https://www.casaveraneio.com"
POR_PAGINA = 100
SIMULTANEAS = 6
EPOCAS = [("PrecoBaixaTemporada", "Baixa temporada"), ("PrecoAltaTemporada", "Alta temporada (julho, dezembro e janeiro)"),
          ("PrecoFeriados", "Feriados (exceto Réveillon e Carnaval)"), ("PrecoReveillon", "Réveillon"),
          ("PrecoCarnaval", "Carnaval")]


def _get(url: str) -> dict:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "EscritorioVeraneio/1.0"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.load(resposta)


def slugs() -> list[str]:
    """Todos os Lodges publicados (paginado)."""
    encontrados, pagina = [], 1
    while True:
        consulta = urllib.parse.urlencode({"locale": "pt-BR", "fields[0]": "slug", "pagination[pageSize]": POR_PAGINA,
                                           "pagination[page]": pagina})
        dados = _get(f"{API}?{consulta}")
        encontrados += [d["attributes"]["slug"] for d in dados.get("data") or [] if d["attributes"].get("slug")]
        if pagina >= dados.get("meta", {}).get("pagination", {}).get("pageCount", 1):
            return encontrados
        pagina += 1


def _reais(valor) -> str:
    texto = str(valor or "").strip()
    return f"R$ {int(texto):,}".replace(",", ".") if texto.isdigit() else texto


def _nomes(relacao) -> list[str]:
    return [d["attributes"]["name"] for d in (relacao or {}).get("data") or [] if d.get("attributes", {}).get("name")]


def _limpo(texto: str) -> str:
    texto = re.sub(r"<br\s*/?>", "", str(texto or ""))
    return re.sub(r"\*\*(.+?)\*\*", r"\1", texto).strip()


def lodge(slug: str) -> dict | None:
    """{"slug", "documento" (texto do Cérebro), "resumo" (linha da tabela)}; None se a API não tem o Lodge."""
    dados = (_get(f"{API}/{urllib.parse.quote(slug)}?locale=pt-BR").get("data") or {}).get("attributes")
    if not dados:
        return None
    nome = (dados.get("name") or slug).strip()
    local = " - ".join(filter(None, [dados.get("Cidade"), dados.get("Estado")]))
    url = f"{SITE}/lodges/{slug}"
    categorias = _nomes(dados.get("categories"))
    resumo = [f"{dados['bedrooms']} quartos" if dados.get("bedrooms") else "",
              f"{dados['bathrooms']} banheiros" if dados.get("bathrooms") else "",
              f"até {dados['capacity']} pessoas" if dados.get("capacity") else "",
              f"categoria: {', '.join(categorias)}" if categorias else ""]
    valores = []
    for campo, rotulo in EPOCAS:
        preco = dados.get(campo) or {}
        if preco.get("ValorDiaria") or preco.get("QuantMinimaDias"):
            minimo = f" | estadia mínima {preco['QuantMinimaDias']} noites" if preco.get("QuantMinimaDias") else ""
            valores.append(f"- {rotulo}: diária {_reais(preco.get('ValorDiaria')) or '—'}{minimo}")
    if dados.get("TaxaDeAtivacao"):
        valores.append(f"- Taxa de ativação: {_reais(dados['TaxaDeAtivacao'])} por reserva")

    partes = [f"# {nome} — {local}" if local else f"# {nome}",
              f"Fonte: {url} (dados oficiais do site, atualizados em {str(dados.get('updatedAt', ''))[:10]})",
              "Resumo: " + " | ".join(filter(None, resumo))]
    if dados.get("Bairro"):
        partes.append(f"Bairro: {dados['Bairro']}")
    for titulo, itens in (("Acomodações", [_limpo(dados.get("Detalhes"))]), ("Sobre o lodge", [_limpo(dados.get("Descricao"))]),
                          ("Valores por época", valores), ("Comodidades", [", ".join(_nomes(dados.get("comforts")))])):
        itens = [i for i in itens if i]
        if itens:
            partes += ["", f"## {titulo}", *itens]
    if dados.get("video"):
        partes += ["", f"Vídeo no site: {dados['video']}"]
    reveillon = dados.get("PrecoReveillon") or {}
    return {"slug": slug, "documento": "\n".join(partes), "resumo": {
        "lodge": nome, "url": url, "local": local or "—", "quartos": str(dados.get("bedrooms") or "—"),
        "pessoas": str(dados.get("capacity") or "—"),
        "diaria": _reais((dados.get("PrecoBaixaTemporada") or {}).get("ValorDiaria")) or "—",
        "reveillon": _reais(reveillon.get("ValorDiaria")) or "—"}}


def todos() -> tuple[list[dict], list[str]]:
    """(Lodges lidos, slugs que falharam)."""
    lista = slugs()
    with ThreadPoolExecutor(SIMULTANEAS) as pool:
        resultados = list(pool.map(_tentar, lista))
    return [r for r in resultados if r], [s for s, r in zip(lista, resultados) if not r]


def _tentar(slug: str) -> dict | None:
    try:
        return lodge(slug)
    except (OSError, ValueError):
        return None
