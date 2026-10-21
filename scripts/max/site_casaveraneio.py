"""Site oficial (www.casaveraneio.com) para o Cérebro.

Lodges: pela API do site (site_api.py), com os números exatos de cada época. Páginas gerais (início, serviços,
eventos, contato, políticas): o site é Next.js e monta o conteúdo por JavaScript, então são renderizadas no
Chrome headless (--dump-dom) e viram texto; só links do próprio domínio. A cópia bruta das páginas fica em
CÉREBRO/SITE/paginas (também é o reserva dos Lodges se a API falhar); o resumo dos Lodges vai em
CÉREBRO/SITE/resumo-lodges.md. Só envia ao Cérebro o que mudou e remove o que sumiu.

Uso avulso: python scripts/max/site_casaveraneio.py [--falhas | --reprocessar]
  --falhas: relê só as páginas que não carregaram; --reprocessar: refaz os documentos sem abrir o Chrome.
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
import site_api
import site_lodges
from comum import log

SITE = "https://www.casaveraneio.com"
PAGINAS_FIXAS = ["/", "/servicos", "/eventos", "/contato", "/politicas-cancelamento", "/politicas-privacidade",
                 "/lodges-orlando"]
PADRAO_PAGINA = re.compile(r"^/[a-z0-9-]+(/[a-z0-9-]+)?$")
IGNORAR = ("/_next", "/uploads", "/api", "/lodges")  # Lodges vêm da API
MAX_PAGINAS = 60
SIMULTANEAS = 4
TEMPO_PAGINA = 90
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PASTA = comum.CEREBRO / "SITE"
ARQUIVO_HASHES = comum.DADOS / "site.hashes.json"
ARQUIVO_FALHAS = comum.DADOS / "site.falhas.json"  # páginas que não carregaram


# ---------- Páginas gerais (Chrome) ----------

def renderizar(caminho: str, tentativas: int = 2) -> str:
    """HTML depois do JavaScript; perfil temporário para várias instâncias em paralelo.
    Se o Chrome travar, usa o HTML do servidor."""
    for _ in range(tentativas):
        with tempfile.TemporaryDirectory(prefix="chrome-site-", ignore_cleanup_errors=True) as perfil:
            try:
                return subprocess.run(
                    [str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={perfil}",
                     "--virtual-time-budget=20000", "--dump-dom", SITE + caminho],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TEMPO_PAGINA,
                    creationflags=comum.SEM_JANELA).stdout
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


def descobrir() -> list[str]:
    """Páginas gerais: as fixas e os links internos delas (sem as páginas de Lodge)."""
    caminhos = set(PAGINAS_FIXAS)
    with ThreadPoolExecutor(SIMULTANEAS) as pool:
        for pagina in pool.map(renderizar, PAGINAS_FIXAS):
            caminhos |= links_internos(pagina)
    return sorted(caminhos)[:MAX_PAGINAS]


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


# ---------- Resumo dos Lodges ----------

def resumo_da_pagina(caminho: str, titulo: str, corpo: str) -> dict:
    """Reserva quando a API não tem o Lodge: resumo tirado da página renderizada."""
    achar = lambda padrao: (m.group(1).strip() if (m := re.search(padrao, corpo)) else "—")
    return {"lodge": titulo.split(" - ")[0] or caminho.rsplit("/", 1)[-1], "url": SITE + caminho,
            "local": achar(r"Favoritar\n(.+)"), "quartos": achar(r"(\d+)\s*quartos?"),
            "pessoas": achar(r"(\d+)\s*pessoas?"), "diaria": achar(r"(A partir de .+?|Diária a combinar)\n"),
            "reveillon": "—"}


def tabela_lodges(resumos: list[dict]) -> str:
    linhas = ["# Resumo dos lodges no site", "", f"Fonte: {SITE} (API do site; reconfira antes de publicar).",
              f"Lodges: {len(resumos)}", "",
              "| Lodge | Local | Quartos | Pessoas | Diária (baixa temporada) | Réveillon | Página |",
              "|---|---|---:|---:|---|---|---|"]
    linhas += [f"| {r['lodge']} | {r['local']} | {r['quartos']} | {r['pessoas']} | {r['diaria']} | {r['reveillon']} "
               f"| {r['url']} |"
               for r in sorted(resumos, key=lambda r: [int(n) if n.isdigit() else n for n in re.split(r"(\d+)", r["url"])])]
    return "\n".join(linhas) + "\n"


# ---------- Documentos para o Cérebro ----------

def _documento(caminho: str, conteudo: str) -> dict:
    return {"fonte_tipo": "site", "fonte_ref": f"site{caminho}",
            "titulo": conteudo.splitlines()[0].lstrip("# ")[:200], "conteudo": conteudo}


def _documentos() -> tuple[list[dict], list[dict]]:
    """Lodges pela API (reserva: página salva) + páginas gerais salvas. Devolve (documentos, resumos)."""
    try:
        lodges, sem_api = site_api.todos()
        log(f"   site: {len(lodges)} Lodges pela API" + (f" ({len(sem_api)} sem resposta)" if sem_api else ""))
    except (OSError, ValueError) as erro:
        log(f"   site: API indisponível ({erro}); Lodges pelas páginas salvas")
        lodges = []
    documentos = [_documento(f"/lodges/{l['slug']}", l["documento"]) for l in lodges]
    resumos = [l["resumo"] for l in lodges]
    pela_api = {f"/lodges/{l['slug']}" for l in lodges}
    for caminho, titulo, corpo in _paginas_salvas():
        if caminho in pela_api:
            continue
        if (conteudo := site_lodges.limpar_pagina(caminho, titulo, SITE + caminho, corpo)):
            documentos.append(_documento(caminho, conteudo))
            if site_lodges.e_lodge(caminho):
                resumos.append(resumo_da_pagina(caminho, titulo, corpo))
    return documentos, resumos


def _hash(conteudo: str) -> str:
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def sincronizar(caminhos: list[str] | None = None, enviar=comum.enviar_ao_cerebro, ler: bool = True) -> dict:
    """Lê as páginas gerais (ou só `caminhos`) no Chrome, busca os Lodges na API e envia ao Cérebro o que mudou.
    ler=False: não abre o Chrome (usa as páginas gerais já salvas)."""
    falhas: list[str] = []
    if ler:
        if not CHROME.exists():
            raise RuntimeError(f"Chrome não encontrado: {CHROME}")
        caminhos = caminhos or descobrir()
        log(f"   site: {len(caminhos)} páginas gerais para ler")
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
    # Enviados antes e que não saem mais (ex.: Lodge despublicado, listagem só com filtros): saem do Cérebro.
    atuais = {d["fonte_ref"] for d in documentos}
    sumidos = [ref for ref in hashes if ref not in atuais]
    if sumidos and comum.remover_do_cerebro("site", sumidos):
        for ref in sumidos:
            hashes.pop(ref)
    ARQUIVO_HASHES.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"paginas": len(documentos) - bool(resumos), "lodges": len(resumos), "falhas": len(falhas),
            "mudados": len(mudados), "enviados": enviados}


def reprocessar() -> dict:
    """Refaz os documentos (Lodges pela API + páginas gerais salvas), sem abrir o Chrome."""
    return sincronizar(ler=False)


def repescar() -> dict:
    """Relê só as páginas gerais que falharam na última leitura."""
    falhas = json.loads(ARQUIVO_FALHAS.read_text(encoding="utf-8")) if ARQUIVO_FALHAS.exists() else []
    if not falhas:
        raise RuntimeError("Nenhuma página pendente da última leitura.")
    return sincronizar(falhas)


def resumo_texto(r: dict) -> str:
    situacao = (f"{r['enviados']} enviada(s) ao Cérebro" if r["enviados"] or not r["mudados"]
                else "envio ao Cérebro pendente")
    pendentes = f" {r['falhas']} página(s) não carregaram e ficam para a próxima leitura." if r["falhas"] else ""
    return (f"Site: {r['paginas']} documentos ({r['lodges']} Lodges no resumo). "
            f"{r['mudados']} novo(s) ou alterado(s); {situacao}. Arquivos em CÉREBRO/SITE.{pendentes}")


if __name__ == "__main__":
    import sys
    modo = {"--falhas": repescar, "--reprocessar": reprocessar}.get(sys.argv[-1], sincronizar)
    log(resumo_texto(modo()))
