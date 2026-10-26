"""Sites das outras empresas do grupo para o Cérebro, cada uma com a SUA etiqueta (nunca misturar com a Casa Veraneio).

- Casa Veraneio Corporativo (corporativo.casaveraneio.com, WordPress): pela API pública de leitura (wp-json), cada
  espaço ("Lodge N" do Corporativo, que é OUTRA ficha que o Lodge N da Casa Veraneio) com cidade, convidados,
  tipos de evento e comodidades; mais serviços, tipos de evento, cases e a página institucional.
- Casa Vero Imóveis (casaveroimoveis.com): o sitemap lista os imóveis; cada página vira a ficha "Vero N" (tipo,
  cidade, condomínio, dormitórios, área, descrição, características, valores) e a página "Sobre".
Telefones e WhatsApp saem do texto (regra de ouro: nunca em publicações). Somente leitura.

Uso: python scripts/max/sites_empresas.py (também roda junto com o catálogo, a cada 6 h).
"""

import html
import json
import re
import urllib.request

import comum
from comum import log

CORP = "https://corporativo.casaveraneio.com"
VERO = "https://www.casaveroimoveis.com"
AGENTE = {"User-Agent": "EscritorioVeraneio/1.0 (leitura para a base interna)"}
TELEFONE = re.compile(r"\(?\b\d{2}\)?\s*9?\d{4}[-\s]?\d{4}\b|wa\.me/\S+|api\.whatsapp\.com/\S+", re.IGNORECASE)


def _baixar(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=60) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


def _json(url: str):
    return json.loads(_baixar(url))


def _texto(trecho_html: str) -> str:
    sem_codigo = re.sub(r"<script.*?</script>|<style.*?</style>", " ", trecho_html or "", flags=re.S)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", sem_codigo))
    return TELEFONE.sub("", re.sub(r"\s+", " ", texto)).strip()


# --- Casa Veraneio Corporativo ---------------------------------------------------------------------

def _termos(taxonomia: str) -> dict[int, str]:
    return {t["id"]: html.unescape(t["name"]) for t in
            _json(f"{CORP}/wp-json/wp/v2/{taxonomia}?per_page=100&_fields=id,name")}


def _maior_publico(nomes: list[str]) -> int | None:
    numeros = [int(n) for nome in nomes for n in re.findall(r"\d+", nome)]
    return max(numeros) if numeros else None


def corporativo() -> list[dict]:
    termos = {t: _termos(t) for t in ("comodidades_", "localizacao", "tipo-de-evento", "no-de-convidados")}
    documentos = []
    for espaco in _json(f"{CORP}/wp-json/wp/v2/imoveis?per_page=100"):
        nome = html.unescape(espaco["title"]["rendered"]).strip()
        numero = re.search(r"\d+", nome)
        if not numero:
            continue
        local = ", ".join(termos["localizacao"].get(i, "") for i in espaco.get("localizacao") or [])
        convidados = _maior_publico([termos["no-de-convidados"].get(i, "") for i in espaco.get("no-de-convidados") or []])
        eventos = [termos["tipo-de-evento"].get(i, "") for i in espaco.get("tipo-de-evento") or []]
        comodidades = [termos["comodidades_"].get(i, "") for i in espaco.get("comodidades_") or []]
        linhas = [f"Fonte: {espaco['link']} (site da Casa Veraneio Corporativo, atualizado em {espaco['modified'][:10]})",
                  f"Espaço para eventos da Casa Veraneio Corporativo ({nome}). Não confundir com o {nome} da Casa "
                  "Veraneio (hospedagem): são fichas de empresas diferentes.",
                  f"Local: {local or 'PENDENTE'}",
                  f"Convidados: até {convidados} pessoas (maior faixa indicada no site)" if convidados
                  else "Convidados: PENDENTE"]
        if eventos:
            linhas.append("Tipos de evento: " + ", ".join(e for e in eventos if e))
        if comodidades:
            linhas.append("Comodidades: " + ", ".join(c for c in comodidades if c))
        if (descricao := _texto(espaco.get("content", {}).get("rendered", ""))):
            linhas.append(f"Sobre: {descricao[:1500]}")
        documentos.append({"fonte_tipo": "site", "empresa": "cv_corporativo",
                           "fonte_ref": f"corporativo/espacos/lodge-{int(numero.group())}",
                           "titulo": f"{nome} — {local or 'local pendente'} (Corporativo)", "conteudo": "\n".join(linhas)})

    espacos = list(documentos)
    documentos += _paginas_corporativo()
    documentos.append(_panorama_corporativo(espacos, [d for d in documentos if d["fonte_ref"].startswith("corporativo/cases/")]))

    for pagina in _json(f"{CORP}/wp-json/wp/v2/pages?per_page=50&slug=institucional"):
        if (texto := _texto(pagina["content"]["rendered"])):
            documentos.append({"fonte_tipo": "site", "empresa": "cv_corporativo", "fonte_ref": "corporativo/institucional",
                               "titulo": "Institucional — Casa Veraneio Corporativo",
                               "conteudo": f"Fonte: {pagina['link']}\n{texto[:6000]}"})
    return documentos


def _miolo_corporativo(url: str) -> str:
    """Texto da página renderizada sem o menu (até "Solicite um Orçamento") e sem o rodapé (contatos, CNPJ).
    O site é montado no Elementor: o conteúdo de cases, eventos e serviços não vem pela API, só na página."""
    texto = _texto(_baixar(url))
    botao = "Solicite um Orçamento"
    inicio = texto.find(botao, texto.find(botao) + 1) if texto.count(botao) > 1 else texto.find(botao)
    fins = [i for i in (texto.find(" Instagram Facebook Linkedin"), texto.find("Entre em contato")) if i > 0]
    miolo = texto[inicio + len(botao) if inicio >= 0 else 0:min(fins or [len(texto)])]
    return re.sub(r"\S+@\S+", "", miolo.replace(" Saiba mais", "")).strip()


def _doc_corp(ref: str, titulo: str, url: str, texto: str) -> dict:
    return {"fonte_tipo": "site", "empresa": "cv_corporativo", "fonte_ref": ref,
            "titulo": f"{titulo} — Casa Veraneio Corporativo",
            "conteudo": f"Fonte: {url} (site da Casa Veraneio Corporativo)\n{texto[:6000]}"}


def _paginas_corporativo() -> list[dict]:
    """Um documento por case e por tipo de evento; serviços, orçamento e apresentação com o texto completo."""
    documentos, cases = [], []
    for tipo, rotulo in (("cases", "Case"), ("eventos", "Tipo de evento")):
        for item in _json(f"{CORP}/wp-json/wp/v2/{tipo}?per_page=100&_fields=slug,title,link"):
            nome = html.unescape(item["title"]["rendered"]).strip()
            try:
                texto = _miolo_corporativo(item["link"])
            except OSError as erro:
                log(f"   Corporativo: não li {item['link']} ({erro})")
                continue
            if tipo == "cases":  # clientes reais, alguns pessoa física: referência interna, não material de post
                texto += ("\nUso: referência de evento já realizado. Nome de cliente (sobretudo pessoa física) em "
                          "publicação só com autorização do Thomas.")
            documentos.append(_doc_corp(f"corporativo/{tipo}/{item['slug']}", f"{rotulo}: {nome}", item["link"], texto))
            if tipo == "cases":
                cases.append(f"- {nome}: " + texto[:220])
    # Índices (mesmas refs dos resumos antigos, que assim são substituídos)
    documentos.append(_doc_corp("corporativo/cases", "Cases (eventos já realizados)", f"{CORP}/_cases/",
                                "Eventos já produzidos pela Casa Veraneio Corporativo (um documento por case):\n"
                                + "\n".join(cases)))
    for slug, ref, titulo in (("servicoss", "corporativo/servicos", "Serviços (produção 360°)"),
                              ("eventos-2", "corporativo/eventos", "Eventos que produzimos"),
                              ("solicite-um-orcamento", "corporativo/orcamento",
                               "Pedido de orçamento: o que o cliente informa"),
                              ("home-2", "corporativo/home", "Página inicial")):
        for pagina in _json(f"{CORP}/wp-json/wp/v2/pages?slug={slug}&_fields=link"):
            try:
                documentos.append(_doc_corp(ref, titulo, pagina["link"], _miolo_corporativo(pagina["link"])))
            except OSError as erro:
                log(f"   Corporativo: não li {pagina['link']} ({erro})")
    return documentos


def _panorama_corporativo(espacos: list[dict], cases: list[dict]) -> dict:
    """Visão geral do portfólio: espaços por cidade, com o maior público e os cases realizados em cada um."""
    por_cidade: dict[str, list[str]] = {}
    for doc in espacos:
        local = re.search(r"Local: (.+)", doc["conteudo"])
        convidados = re.search(r"até (\d+) pessoas", doc["conteudo"])
        numero = doc["fonte_ref"].rsplit("-", 1)[-1]
        realizados = [re.sub(r" — Casa Veraneio Corporativo$", "", c["titulo"]).removeprefix("Case: ")
                      for c in cases if re.search(rf"Espaço:\s*Lodge 0*{numero}\b", c["conteudo"])]
        por_cidade.setdefault(local.group(1) if local else "local pendente", []).append(
            f"Lodge {numero}" + (f" (até {convidados.group(1)} convidados)" if convidados else "")
            + (f" — cases: {', '.join(realizados)}" if realizados else ""))
    linhas = [f"- {cidade} ({len(itens)} espaço(s)): " + "; ".join(itens) for cidade, itens in
              sorted(por_cidade.items(), key=lambda par: -len(par[1]))]
    return _doc_corp("corporativo/panorama", "Panorama dos espaços por cidade", f"{CORP}/espacos/",
                     f"{len(espacos)} espaços no site, em {len(por_cidade)} cidade(s). A numeração \"Lodge N\" é a do "
                     "Corporativo (não é a dos Lodges da Casa Veraneio).\n" + "\n".join(linhas))


# --- Casa Vero Imóveis -----------------------------------------------------------------------------

CAMPOS_VERO = [("Dormitório(s)", "dormitórios"), ("Suíte(s)", "suítes"), ("Banheiro(s)", "banheiros"),
               ("Vaga(s)", "vagas")]


def _imovel_vero(url: str) -> dict | None:
    texto = _texto(_baixar(url))
    codigo = re.search(r"Código:\s*Vero\s*(\d+)", texto)
    if not codigo:
        return None
    numero = int(codigo.group(1))
    cabeca = re.search(r"Voltar Fotos (?:Vídeo )?(Venda|Locação)\s+(.*?)\s+Código:", texto)
    resumo = [f"{valor} {rotulo}" for rotulo_site, rotulo in CAMPOS_VERO
              if (valor := (re.search(rf"(\d+)\s*{re.escape(rotulo_site)}", texto) or [None, None])[1])]
    area = re.search(r"(\d[\d.,]*)\s*m²\s*Contru[íi]do", texto)
    terreno = re.search(r"Terreno:\s*(\d[\d.,]*)", texto)
    sobre = re.search(r"Sobre o Imóvel\s*(.*?)\s*Características do Imóvel", texto)
    caracteristicas = re.search(r"Características do Imóvel\s*(.*?)\s*(?:Venda|Locação)\s+R\$", texto)
    valores = re.findall(r"(Venda|Locação|Condomínio|IPTU)\s+(R\$\s*[\d.,]+|Consulte)", texto)
    # Título comercial do anúncio (ex.: "Casa no Condomínio Terras de São José 1"), entre o código e os números.
    # (o primeiro "Código:" da página é o do título da aba; o anúncio começa em "Voltar")
    chamada = re.search(rf"Código:\s*Vero\s*{numero}\s+(.*?)\s+\d+\s*(?:Dormitório|Suíte|Banheiro|Vaga)",
                        texto[max(texto.find("Voltar"), 0):])
    linhas = [f"Fonte: {url} (site da Casa Vero Imóveis)",
              f"Imóvel Vero {numero} da Casa Vero Imóveis (imobiliária). Não confundir com Lodges da Casa Veraneio "
              "nem com espaços do Corporativo, mesmo com nome ou condomínio parecido.",
              f"Negócio e localização: {cabeca.group(1)} — {cabeca.group(2)}" if cabeca else "Localização: PENDENTE"]
    if chamada and len(chamada.group(1)) < 160 and chamada.group(1).strip() != f"Vero {numero}":
        linhas.append(f"Título do anúncio no site: {chamada.group(1)}")
    if resumo or area or terreno:
        linhas.append("Resumo: " + " | ".join(resumo + ([f"{area.group(1)} m² construídos"] if area else [])
                                              + ([f"terreno {terreno.group(1)} m²"] if terreno else [])))
    if sobre:
        linhas.append(f"Sobre: {sobre.group(1)[:1500]}")
    if caracteristicas:
        linhas.append(f"Características: {caracteristicas.group(1)[:600]}")
    if valores:
        linhas.append("Valores: " + " | ".join(f"{rotulo} {valor}" for rotulo, valor in dict(valores).items()))
    titulo = f"Vero {numero} — {cabeca.group(2)[:80]} (Casa Vero)" if cabeca else f"Vero {numero} (Casa Vero)"
    return {"fonte_tipo": "site", "empresa": "casa_vero", "fonte_ref": f"vero/imoveis/vero-{numero}",
            "titulo": titulo, "conteudo": "\n".join(linhas)}


def casa_vero() -> list[dict]:
    urls = sorted(set(re.findall(r"https?://[^<\s\"]*/imovel/[a-z0-9-]+/\d+", _baixar(f"{VERO}/sitemap.xml"))))
    documentos = []
    for url in urls:
        try:
            if (doc := _imovel_vero(url)):
                documentos.append(doc)
        except OSError as erro:
            log(f"   Casa Vero: não li {url} ({erro})")
    sobre = _texto(_baixar(f"{VERO}/sobre"))
    if (inicio := sobre.find("Conectamos pessoas")) >= 0:
        documentos.append({"fonte_tipo": "site", "empresa": "casa_vero", "fonte_ref": "vero/sobre",
                           "titulo": "Sobre a Casa Vero Imóveis",
                           "conteudo": f"Fonte: {VERO}/sobre\n" + sobre[inicio:inicio + 2500].split(" Contato ")[0]})
    documentos += _paginas_vero()
    documentos.append(_panorama_vero([d for d in documentos if d["fonte_ref"].startswith("vero/imoveis/")]))
    return documentos


def _miolo_vero(url: str) -> str:
    """Texto da página sem o menu do topo e sem o rodapé (endereço, CRECI, aviso de cookies)."""
    texto = _texto(_baixar(url))
    texto = texto.split(" Meu Favoritos ", 1)[-1]
    return texto.split(" Casa Vero Imóveis Casa Vero Imóveis - ")[0].split(" Usamos cookies")[0].strip()


def _paginas_vero() -> list[dict]:
    documentos = []
    for caminho, ref, titulo in (("/", "vero/home", "Página inicial: cidades, tipos e condomínios atendidos"),
                                 ("/anuncie", "vero/anuncie", "Anuncie: o que o proprietário informa para vender")):
        try:
            texto = _miolo_vero(f"{VERO}{caminho}")
        except OSError as erro:
            log(f"   Casa Vero: não li {caminho} ({erro})")
            continue
        documentos.append({"fonte_tipo": "site", "empresa": "casa_vero", "fonte_ref": ref,
                           "titulo": f"{titulo} — Casa Vero Imóveis",
                           "conteudo": f"Fonte: {VERO}{caminho} (site da Casa Vero Imóveis)\n{texto[:6000]}"})
    return documentos


def _panorama_vero(imoveis: list[dict]) -> dict:
    """Visão geral do portfólio (por cidade e por tipo), com o título de cada anúncio. Sem preços: a regra geral
    da Casa Vero é não publicar valores (cada ficha guarda os seus, para consulta interna)."""
    por_cidade: dict[str, list[str]] = {}
    tipos: dict[str, int] = {}
    for doc in imoveis:
        local = re.search(r"Negócio e localização: \w+ — (.+)", doc["conteudo"])
        chamada = re.search(r"Título do anúncio no site: (.+)", doc["conteudo"])
        resumo = re.search(r"Resumo: (.+)", doc["conteudo"])
        numero = doc["fonte_ref"].rsplit("-", 1)[-1]
        tipo = next((t for t in ("Casa em Condomínio", "Fazenda", "Sítio", "Casa") if local and local.group(1).startswith(t)),
                    "Outro")
        tipos[tipo] = tipos.get(tipo, 0) + 1
        cidade = (local.group(1).removeprefix(tipo).strip() if local else "local pendente")
        por_cidade.setdefault(cidade.split(" Condomínio")[0], []).append(
            f"Vero {numero}" + (f" \"{chamada.group(1)}\"" if chamada else "")
            + (f" ({resumo.group(1).split(' | ')[0]})" if resumo else ""))
    linhas = [f"- {cidade}: " + "; ".join(itens) for cidade, itens in sorted(por_cidade.items(), key=lambda p: -len(p[1]))]
    return {"fonte_tipo": "site", "empresa": "casa_vero", "fonte_ref": "vero/panorama",
            "titulo": "Panorama do portfólio — Casa Vero Imóveis",
            "conteudo": (f"Fonte: {VERO}/imoveis (site da Casa Vero Imóveis)\n{len(imoveis)} imóveis à venda no site. "
                         "Por tipo: " + ", ".join(f"{t} {n}" for t, n in sorted(tipos.items(), key=lambda p: -p[1]))
                         + ".\nPor local (título do anúncio e dormitórios):\n" + "\n".join(linhas))}


def rodar() -> None:
    for nome, leitor in (("Casa Veraneio Corporativo", corporativo), ("Casa Vero Imóveis", casa_vero)):
        try:
            documentos = leitor()
            enviados = comum.enviar_ao_cerebro(documentos)
            log(f"{nome}: {len(documentos)} documento(s) lidos do site{'' if enviados else ' (envio adiado)'}.")
        except Exception as erro:  # um site fora do ar não derruba o trabalhador
            log(f"{nome}: não foi possível ler o site ({erro}).")


if __name__ == "__main__":
    rodar()
