"""Leitura do site oficial (www.casaveraneio.com) para o Cérebro, com o Chrome do PC.

O site é Next.js e monta o conteúdo por JavaScript; por isso cada página é renderizada no Chrome headless
(--dump-dom) e só então vira texto. Segue apenas links do próprio domínio. A cópia bruta de cada página fica em
CÉREBRO/SITE/paginas; ao Cérebro (fonte "site") vão só os dados do produto (site_lodges.py) e um resumo dos
lodges (local, quartos, pessoas, diária) em CÉREBRO/SITE/resumo-lodges.md. Só envia o que mudou.

Uso avulso: python scripts/max/site_casaveraneio.py [--falhas | --reprocessar]
  --falhas: relê só as páginas que não carregaram; --reprocessar: refaz os documentos sem abrir o site.
"""

import hashlib
import html
import json
import re
import subprocess
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import comum
import site_lodges
from comum import log

SITE = "https://www.casaveraneio.com"
PAGINAS_FIXAS = ["/", "/servicos", "/eventos", "/contato", "/politicas-cancelamento", "/politicas-privacidade"]
LISTAGENS = ["/lodges", "/lodges-orlando"]       # paginadas com ?page=N
PADRAO_PAGINA = re.compile(r"^/[a-z0-9-]+(/[a-z0-9-]+)?$")
IGNORAR = ("/_next", "/uploads", "/api")
MAX_PAGINAS = 300
MAX_PAGINACAO = 40
SIMULTANEAS = 4
TEMPO_PAGINA = 90
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PASTA = comum.CEREBRO / "SITE"
ARQUIVO_HASHES = comum.DADOS / "site.hashes.json"
ARQUIVO_FALHAS = comum.DADOS / "site.falhas.json"  # páginas que não carregaram


def renderizar(caminho: str, tentativas: int = 2) -> str:
    """HTML depois do JavaScript; perfil temporário para várias instâncias em paralelo.
    Se o Chrome travar, usa o HTML do servidor (menos completo: sem a tabela de valores por época)."""
    for _ in range(tentativas):
        with tempfile.TemporaryDirectory(prefix="chrome-site-", ignore_cleanup_errors=True) as perfil:
            try:
                return subprocess.run(
                    [str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={perfil}",
                     "--virtual-time-budget=20000", "--dump-dom", SITE + caminho],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TEMPO_PAGINA).stdout
            except subprocess.TimeoutExpired:
                log(f"   site: {caminho} não carregou em {TEMPO_PAGINA} s")
    return html_do_servidor(caminho)


def html_do_servidor(caminho: str) -> str:
    try:
        requisicao = urllib.request.Request(SITE + caminho, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(requisicao, timeout=60) as resposta:
            log(f"   site: {caminho} lido pelo HTML do servidor")
            return resposta.read().decode("utf-8", errors="replace")
    except OSError as erro:
        log(f"   site: {caminho} também falhou no servidor ({erro})")
        return ""


def links_internos(pagina: str) -> set[str]:
    caminhos = set()
    for href in re.findall(r'href="([^"]+)"', pagina):
        href = html.unescape(href).split("#")[0].split("?")[0]
        href = re.sub(r"^https?://(www\.)?casaveraneio\.com", "", href).rstrip("/") or "/"
        if href == "/" or (PADRAO_PAGINA.match(href) and not href.startswith(IGNORAR)):
            caminhos.add(href)
    return caminhos


def texto(pagina: str) -> tuple[str, str]:
    """(título, texto limpo): sem scripts, menus e rodapé; linhas longas repetidas só uma vez."""
    titulo = html.unescape((re.search(r"<title>(.*?)</title>", pagina, re.S) or [None, ""])[1]).strip()
    corpo = re.sub(r"(?s)<(script|style|noscript|header|footer|nav|svg)[^>]*>.*?</\1>", " ", pagina)
    corpo = html.unescape(re.sub(r"<[^>]+>", "\n", corpo)).replace("\xa0", " ")
    corpo = re.sub(r"=\s*\n\s*", "= ", corpo)  # "Suíte 1 =\n 1 cama king" -> uma linha
    linhas, vistas = [], set()
    for linha in (re.sub(r"\s+", " ", l).strip() for l in corpo.splitlines()):
        if not linha or (len(linha) > 15 and linha in vistas):
            continue
        vistas.add(linha)
        linhas.append(linha)
    return titulo, "\n".join(linhas)


def lodges_da_listagem(listagem: str) -> set[str]:
    """Percorre ?page=1, 2, ... até uma página não trazer lodge novo."""
    achados: set[str] = set()
    for numero in range(1, MAX_PAGINACAO + 1):
        novos = {c for c in links_internos(renderizar(f"{listagem}?page={numero}"))
                 if site_lodges.e_lodge(c)} - achados
        if not novos:
            break
        achados |= novos
    return achados


def descobrir() -> list[str]:
    caminhos = set(PAGINAS_FIXAS)
    with ThreadPoolExecutor(SIMULTANEAS) as pool:
        for lodges in pool.map(lodges_da_listagem, LISTAGENS):
            caminhos |= lodges
        for pagina in pool.map(renderizar, PAGINAS_FIXAS):
            caminhos |= {c for c in links_internos(pagina) if not c.startswith(("/lodges/", "/lodges-orlando/"))}
    return sorted(caminhos)[:MAX_PAGINAS]


def resumo_lodge(caminho: str, titulo: str, corpo: str) -> dict | None:
    if not site_lodges.e_lodge(caminho):
        return None
    achar = lambda padrao: (m.group(1).strip() if (m := re.search(padrao, corpo)) else "—")
    return {"lodge": titulo.split(" - ")[0] or caminho.rsplit("/", 1)[-1], "url": SITE + caminho,
            "local": achar(r"Favoritar\n(.+)"), "quartos": achar(r"(\d+)\s*quartos?"),
            "pessoas": achar(r"(\d+)\s*pessoas?"), "diaria": achar(r"(A partir de .+?|Diária a combinar)\n")}


def tabela_lodges(resumos: list[dict]) -> str:
    linhas = ["# Resumo dos lodges no site", "", f"Fonte: {SITE}/lodges (lido pelo Chrome).",
              f"Lodges: {len(resumos)}", "", "| Lodge | Local | Quartos | Pessoas | Diária a partir de | Página |",
              "|---|---|---:|---:|---|---|"]
    linhas += [f"| {r['lodge']} | {r['local']} | {r['quartos']} | {r['pessoas']} | {r['diaria']} | {r['url']} |"
               for r in sorted(resumos, key=lambda r: [int(n) if n.isdigit() else n for n in re.split(r"(\d+)", r["url"])])]
    return "\n".join(linhas) + "\n"


def _hash(conteudo: str) -> str:
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def _ler(caminhos: list[str]) -> tuple[dict[str, str], list[str]]:
    """Leitura em paralelo e, no fim, uma repescagem uma a uma das que falharam (o site engasga com várias)."""
    with ThreadPoolExecutor(SIMULTANEAS) as pool:
        lidas = dict(zip(caminhos, pool.map(renderizar, caminhos)))
    falhas = [c for c, pagina in lidas.items() if len(texto(pagina)[1]) < 80]
    if falhas:
        log(f"   site: repescando {len(falhas)} página(s), uma por vez")
        for caminho in falhas:
            lidas[caminho] = renderizar(caminho, tentativas=1)
    return lidas, [c for c in falhas if len(texto(lidas[c])[1]) < 80]


def _paginas_salvas() -> list[tuple[str, str, str]]:
    """(caminho, título, texto) de todas as páginas já gravadas em paginas/ (cópia bruta do site)."""
    paginas = []
    for arquivo in sorted((PASTA / "paginas").glob("*.md")):
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        if len(linhas) > 3 and linhas[1].startswith(f"Fonte: {SITE}"):
            paginas.append((linhas[1].removeprefix(f"Fonte: {SITE}"), linhas[0].lstrip("# ").strip(),
                            "\n".join(linhas[3:])))
    return paginas


def _documentos() -> tuple[list[dict], int]:
    """Documentos do Cérebro a partir das páginas salvas: só os dados do produto (site_lodges) + resumo."""
    documentos, resumos = [], []
    for caminho, titulo, corpo in _paginas_salvas():
        if (conteudo := site_lodges.limpar_pagina(caminho, titulo, SITE + caminho, corpo)):
            documentos.append({"fonte_tipo": "site", "fonte_ref": f"site{caminho}",
                               "titulo": conteudo.splitlines()[0].lstrip("# ")[:200], "conteudo": conteudo})
        if (resumo := resumo_lodge(caminho, titulo, corpo)):
            resumos.append(resumo)
    return documentos, resumos


def sincronizar(caminhos: list[str] | None = None, enviar=comum.enviar_ao_cerebro, ler: bool = True) -> dict:
    """Lê o site (ou só `caminhos`), grava a cópia bruta em CÉREBRO/SITE/paginas e envia ao Cérebro o que mudou.
    ler=False: só reprocessa as páginas já salvas (sem abrir o site)."""
    falhas: list[str] = []
    if ler:
        if not CHROME.exists():
            raise RuntimeError(f"Chrome não encontrado: {CHROME}")
        caminhos = caminhos or descobrir()
        log(f"   site: {len(caminhos)} páginas para ler")
        lidas, falhas = _ler(caminhos)
        ARQUIVO_FALHAS.write_text(json.dumps(falhas, indent=1), encoding="utf-8")
        (PASTA / "paginas").mkdir(parents=True, exist_ok=True)
        for caminho, pagina in lidas.items():
            titulo, corpo = texto(pagina)
            if len(corpo) < 80:  # não carregou: fica para a próxima leitura
                continue
            nome = caminho.strip("/").replace("/", "_") or "inicio"
            (PASTA / "paginas" / f"{nome}.md").write_text(
                f"# {titulo or caminho}\nFonte: {SITE}{caminho}\n\n{corpo}\n", encoding="utf-8")

    documentos, resumos = _documentos()
    if not documentos:
        raise RuntimeError("Nenhuma página do site trouxe conteúdo.")
    if resumos:
        tabela = tabela_lodges(resumos)
        (PASTA / "resumo-lodges.md").write_text(tabela, encoding="utf-8")
        documentos.append({"fonte_tipo": "site", "fonte_ref": "site/resumo-lodges",
                           "titulo": "Resumo dos lodges no site", "conteudo": tabela})

    try:
        hashes = json.loads(ARQUIVO_HASHES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hashes = {}
    mudados = [d for d in documentos if hashes.get(d["fonte_ref"]) != _hash(d["conteudo"])]
    enviados = len(mudados) if mudados and enviar(mudados) else 0
    if enviados:
        hashes.update({d["fonte_ref"]: _hash(d["conteudo"]) for d in mudados})
        ARQUIVO_HASHES.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"paginas": len(documentos) - bool(resumos), "lodges": len(resumos), "falhas": len(falhas),
            "mudados": len(mudados), "enviados": enviados}


def reprocessar() -> dict:
    """Refaz os documentos a partir das páginas já salvas (ex.: depois de mudar a limpeza), sem abrir o site."""
    return sincronizar(ler=False)


def repescar() -> dict:
    """Relê só as páginas que falharam na última leitura."""
    falhas = json.loads(ARQUIVO_FALHAS.read_text(encoding="utf-8")) if ARQUIVO_FALHAS.exists() else []
    if not falhas:
        raise RuntimeError("Nenhuma página pendente da última leitura.")
    return sincronizar(falhas)


def resumo_texto(r: dict) -> str:
    situacao = (f"{r['enviados']} enviada(s) ao Cérebro" if r["enviados"] or not r["mudados"]
                else "envio ao Cérebro pendente")
    pendentes = f" {r['falhas']} página(s) não carregaram e ficam para a próxima leitura." if r["falhas"] else ""
    return (f"Site: {r['paginas']} páginas com conteúdo ({r['lodges']} lodges no resumo). "
            f"{r['mudados']} documento(s) novo(s) ou alterado(s); {situacao}. Arquivos em CÉREBRO/SITE.{pendentes}")


if __name__ == "__main__":
    import sys
    modo = {"--falhas": repescar, "--reprocessar": reprocessar}.get(sys.argv[-1], sincronizar)
    log(resumo_texto(modo()))
