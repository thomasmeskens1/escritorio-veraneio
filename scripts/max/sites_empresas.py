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

    for tipo, titulo in (("servicos", "Serviços para eventos"), ("eventos", "Tipos de evento atendidos"),
                         ("cases", "Cases (eventos já realizados)")):
        itens = []
        for item in _json(f"{CORP}/wp-json/wp/v2/{tipo}?per_page=100"):
            nome = html.unescape(item["title"]["rendered"]).strip()
            descricao = _texto(item.get("content", {}).get("rendered", ""))[:400]
            itens.append(f"- {nome}" + (f": {descricao}" if descricao else ""))
        if itens:
            documentos.append({"fonte_tipo": "site", "empresa": "cv_corporativo", "fonte_ref": f"corporativo/{tipo}",
                               "titulo": f"{titulo} — Casa Veraneio Corporativo",
                               "conteudo": f"Fonte: {CORP} (site da Casa Veraneio Corporativo)\n" + "\n".join(itens)})

    for pagina in _json(f"{CORP}/wp-json/wp/v2/pages?per_page=50&slug=institucional"):
        if (texto := _texto(pagina["content"]["rendered"])):
            documentos.append({"fonte_tipo": "site", "empresa": "cv_corporativo", "fonte_ref": "corporativo/institucional",
                               "titulo": "Institucional — Casa Veraneio Corporativo",
                               "conteudo": f"Fonte: {pagina['link']}\n{texto[:6000]}"})
    return documentos


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
    linhas = [f"Fonte: {url} (site da Casa Vero Imóveis)",
              f"Imóvel Vero {numero} da Casa Vero Imóveis (imobiliária). Não confundir com Lodges da Casa Veraneio "
              "nem com espaços do Corporativo, mesmo com nome ou condomínio parecido.",
              f"Negócio e localização: {cabeca.group(1)} — {cabeca.group(2)}" if cabeca else "Localização: PENDENTE"]
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
    return documentos


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
