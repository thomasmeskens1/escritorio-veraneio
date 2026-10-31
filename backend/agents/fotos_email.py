"""Fotos reais dos Lodges no rascunho do e-mail (Onda 2, email_marketing-04, 31/10/2026).

Versão simples: cada bloco de imóvel ganha a foto de capa da página dele no site da empresa (a mesma do botão), lida
da própria página (og:image, depois a primeira foto do conteúdo). Só fotos que já estão no site, nunca geradas por
IA, e só da página do site DA EMPRESA do e-mail: link de outra empresa ou de outro domínio não é aberto. Sem foto (ou
quando a "capa" é a mesma em vários Lodges, sinal de banner genérico do site), o bloco mostra o aviso
"FOTO DO LODGE N AQUI" para o Thomas encaixar no Brevo. Sem Max e sem subir nada para a galeria do Brevo.
"""

import html
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Site de cada empresa (scripts/max/sites_empresas.py e site_casaveraneio.py). O Corporativo é subdomínio da Casa
# Veraneio: a página dele nunca vale para a Casa Veraneio, e vice-versa.
SITES = {"casa_veraneio": ("casaveraneio.com",), "cv_corporativo": ("corporativo.casaveraneio.com",),
         "casa_vero": ("casaveroimoveis.com",)}
SUBDOMINIOS_DE_OUTRA = {"casa_veraneio": ("corporativo.casaveraneio.com",)}
MAX_PAGINA = 2 * 1024 * 1024
TEMPO_LIMITE = 10
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATRIBUTO = re.compile(r'([\w:-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_EXTENSAO_FOTO = re.compile(r"\.(jpe?g|png|webp)(\?|$)", re.I)
_NAO_FOTO = re.compile(r"logo|icon|favicon|sprite|avatar|whatsapp", re.I)


@dataclass
class Foto:
    url: str = ""
    alt: str = ""
    aviso: str = ""  # "FOTO DO LODGE 16 AQUI" quando não há foto


def do_site_da_empresa(link: str, empresa: str) -> bool:
    host = (urlparse(link or "").hostname or "").lower()
    if urlparse(link or "").scheme != "https" or not host:
        return False
    if any(host == h or host.endswith(f".{h}") for h in SUBDOMINIOS_DE_OUTRA.get(empresa, ())):
        return False
    return any(host == h or host.endswith(f".{h}") for h in SITES.get(empresa, ()))


def _pagina(link: str) -> str:
    """HTML da página (até 2 MB). Separada para os testes simularem o site."""
    requisicao = urllib.request.Request(link, headers={"User-Agent": "EscritorioVeraneio/1.0"})
    with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
        return resposta.read(MAX_PAGINA).decode("utf-8", "replace")


def _atributos(tag: str) -> dict[str, str]:
    return {k.lower(): html.unescape(v.strip("\"'")) for k, v in _ATRIBUTO.findall(tag)}


def capa_da_pagina(pagina: str, link: str) -> tuple[str, str]:
    """(url da foto de capa, texto alternativo do site) ou ("", "")."""
    metas = [_atributos(m) for m in _META.findall(pagina or "")]
    por_nome = {(m.get("property") or m.get("name") or "").lower(): m.get("content", "") for m in metas}
    alt = por_nome.get("og:image:alt", "")
    for chave in ("og:image", "og:image:secure_url", "twitter:image"):
        if por_nome.get(chave):
            return urljoin(link, por_nome[chave]), alt
    for tag in _IMG.findall(pagina or ""):
        a = _atributos(tag)
        fonte = a.get("src") or a.get("data-src") or ""
        if fonte and _EXTENSAO_FOTO.search(fonte) and not _NAO_FOTO.search(fonte):
            return urljoin(link, fonte), a.get("alt", "")
    return "", ""


def aviso(nome: str) -> str:
    nome = re.sub(r"\s+", " ", nome or "imóvel").strip().upper()
    return f"FOTO DO {nome} AQUI"


def fotos(imoveis: list, empresa: str) -> list[Foto]:
    """Uma Foto por imóvel (na mesma ordem). Erro de rede ou página sem foto = aviso no bloco."""
    achadas: list[Foto] = []
    for imovel in imoveis:
        url, alt = "", ""
        if do_site_da_empresa(imovel.botao_link, empresa):
            try:
                url, alt = capa_da_pagina(_pagina(imovel.botao_link), imovel.botao_link)
            except Exception:  # noqa: BLE001 - site fora do ar: o bloco sai com o aviso
                url = ""
        if url and urlparse(url).scheme != "https":
            url = ""
        achadas.append(Foto(url=url, alt=(alt or f"{imovel.nome}, {imovel.local}").strip(" ,")[:150]))
    repetidas = {f.url for f in achadas if f.url and sum(g.url == f.url for g in achadas) > 1}
    for foto, imovel in zip(achadas, imoveis):
        if not foto.url or foto.url in repetidas:  # mesma "capa" em vários Lodges = banner do site, não do Lodge
            foto.url, foto.aviso = "", aviso(imovel.nome)
    return achadas


def bloco(foto: Foto, link: str) -> str:
    """HTML da foto (clicável, com o link do botão do bloco) ou do aviso."""
    e = html.escape
    if foto.url:
        return (f'<a href="{e(link, quote=True)}" style="display:block;margin:0 0 16px">'
                f'<img src="{e(foto.url, quote=True)}" alt="{e(foto.alt, quote=True)}" width="536" '
                'style="display:block;width:100%;max-width:536px;height:auto;border:0;border-radius:4px"></a>')
    return ('<div style="margin:0 0 16px;padding:48px 16px;border:2px dashed #c9bfb2;color:#9a9086;'
            f'text-align:center;font-size:14px;font-weight:bold">{e(foto.aviso)}</div>')


def resumo(imoveis: list, achadas: list[Foto]) -> str:
    """Linha para o chat: qual foto entrou em cada bloco."""
    if not imoveis or not achadas:  # sem imóveis ou e-mail pedido sem fotos
        return ""
    partes = [f"{i.nome}: {'foto de capa da página no site' if f.url else f'sem foto ({f.aviso})'}"
              for i, f in zip(imoveis, achadas)]
    return " Fotos dos blocos: " + "; ".join(partes) + "."
