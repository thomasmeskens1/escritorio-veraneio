"""Moldes de produção da Casa Veraneio (Onda 3, item 1; criador_imagens-02, designer-02; 31/10/2026).

Capa, ficha do Lodge, fechamento e foto cheia já desenhados em HTML/CSS (scripts/max/moldes/casa_veraneio), com as
medidas dos manuais 03, 06 e 08: foto protagonista, Playfair Extrabold + itálico, Muli, degradê Verde, logo oficial,
"Cidade / UF" e zonas mortas de cada formato. O Max só preenche um molde.json e renderiza; o botão "Desdobrar"
(desdobrar_formatos.py) usa o mesmo arquivo para gerar 4:5 e 9:16 sem o Max.

Uso: python molde.py molde.json [--formato 1080x1920] [--pasta-saida DIR] [--sufixo _9x16]

molde.json (caminhos relativos à pasta dele, sempre dentro dela):
{"empresa": "casa_veraneio", "formato": "1080x1440", "slides": [
  {"molde": "capa", "foto": "acervo/fachada.jpg", "foco": "centro", "kicker": "Casa em destaque",
   "titulo": "Lodge 244", "subtitulo": "Pé na areia em Jurerê", "lodge": 244, "local": "Jurerê Internacional / SC",
   "pessoas": 16, "contagem": {"numero": "45", "texto": "noites para o Réveillon"}, "saida": "entrega/01_capa.png"},
  {"molde": "foto", "foto": "acervo/piscina.jpg", "saida": "entrega/02_foto.png"},
  {"molde": "ficha", "foto": "acervo/sala.jpg", "lodge": 244, "local": "Jurerê Internacional / SC",
   "titulo": "A casa inteira", "subtitulo": "só para o seu grupo", "suites": 8, "pessoas": 16,
   "cta": "Reserve a data do seu grupo", "saida": "entrega/03_ficha.png"},
  {"molde": "fechamento", "kicker": "Réveillon 2027", "titulo": "A virada", "subtitulo": "do seu grupo",
   "linhas": ["8 suítes · até 16 pessoas"], "cta": "Reserve a data do seu grupo", "saida": "entrega/04_fim.png"}]}
Valores (valor, minimo_noites) só saem com "com_valor": true no slide, e só quando o pedido pedir (decisão 3).
"""

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).parent))
import comum  # noqa: E402
import renderizar_png  # noqa: E402

PASTA_MOLDES = Path(__file__).with_name("moldes")
MOLDES = ("capa", "ficha", "fechamento", "foto")
EMPRESAS = ("casa_veraneio",)  # Corp e Vero: identidade ainda em rascunho (decisão 1); entram depois de aprovadas
# Só largura 1080 (feed 3:4, 4:5, 1:1 e 9:16); a classe ajusta zonas mortas, degradês e tamanhos no base.css.
FORMATOS = {"1080x1440": "f34", "1080x1350": "f45", "1080x1920": "f916", "1080x1080": "f11"}
FORMATO_PADRAO = "1080x1440"
# "Desdobrar para anúncio" (gestor_trafego-13, email_marketing-06): classes extras de moldes/casa_veraneio/anuncio.css,
# com a área coberta pela interface dos anúncios (manual 08 §3) e o cabeçalho de e-mail (1200 px, exibido a 600 px).
FORMATOS_ANUNCIO = {"1080x1080": "f11 anuncio", "1200x628": "f191 anuncio", "1080x1920": "f916 anuncio",
                    "1200x600": "femail anuncio"}
FOCOS = {"esquerda": "20% 50%", "centro": "50% 50%", "direita": "80% 50%", "topo": "50% 20%", "base": "50% 80%"}
LOGOS = {"branca": "logo_branca.png", "caramelo": "logo_caramelo_texto_creme.png"}
LOGO_DO_MOLDE = {"capa": "branca", "ficha": "branca", "fechamento": "caramelo"}
FONTES = ("PlayfairDisplay-Variavel.ttf", "PlayfairDisplay-Italico-Variavel.ttf", "Muli-Variavel.ttf",
          "Muli-Italico-Variavel.ttf")
CAMPOS_DE_TEXTO = ("kicker", "titulo", "subtitulo", "local", "cta", "linhas", "contagem")
VALOR_NO_TEXTO = re.compile(r"R\$|\bdi[áa]ria", re.IGNORECASE)
ESPERA_MS = 4000  # fontes locais e foto grande carregam antes do print


def pasta_marcas() -> Path:
    return comum.CEREBRO / "MARCAS"


def _texto(valor) -> str:
    return html.escape(str(valor).strip()) if valor not in (None, "") else ""


def local_padrao(local: str) -> str:
    """"Morungaba, SP", "Morungaba/SP" ou "Morungaba - SP" -> "Morungaba / SP" (decisão 2)."""
    achado = re.match(r"^\s*(.+?)\s*(?:/|,|\s-\s|–)\s*([A-Za-z]{2})\s*$", str(local or ""))
    return f"{achado.group(1)} / {achado.group(2).upper()}" if achado else str(local or "").strip()


def lodge_padrao(lodge) -> str:
    """244, "244" ou "Lodge 244" -> "LODGE 244"."""
    texto = str(lodge or "").strip()
    return f"LODGE {texto}" if texto.isdigit() else texto.upper()


def conferir(slide: dict) -> None:
    """Molde conhecido e nada de valor sem "com_valor" (decisão 3: por padrão a arte sai sem valores)."""
    if slide.get("molde") not in MOLDES:
        raise ValueError(f"Molde desconhecido: {slide.get('molde')!r} (use {', '.join(MOLDES)})")
    if slide.get("com_valor"):
        return
    if slide.get("valor") or slide.get("minimo_noites"):
        raise ValueError("Valor na arte sem \"com_valor\": true (só quando o pedido pedir valores).")
    textos = json.dumps({c: slide.get(c) for c in CAMPOS_DE_TEXTO}, ensure_ascii=False)
    if VALOR_NO_TEXTO.search(textos):
        raise ValueError("Texto com R$ ou diária sem \"com_valor\": true (só quando o pedido pedir valores).")


def _contagem(slide: dict) -> str:
    contagem = slide.get("contagem") or {}
    if not contagem.get("numero"):
        return ""
    return (f'<div class="contagem"><span class="contagem-numero">{_texto(contagem["numero"])}</span>'
            f'<span class="contagem-texto">{_texto(contagem.get("texto"))}</span></div>')


def _colunas(slide: dict) -> str:
    colunas = [(slide.get("suites"), "SUÍTES"), (slide.get("pessoas"), "PESSOAS")]
    if slide.get("com_valor") and slide.get("valor"):
        colunas.append((slide["valor"], slide.get("rotulo_valor") or "DIÁRIA"))
    return "".join(f'<div class="coluna"><span class="numero">{_texto(n)}</span><span class="rotulo">{r}</span></div>'
                   for n, r in colunas if n not in (None, ""))


def campos(slide: dict) -> dict:
    """Valores do Template do molde (texto já escapado)."""
    pessoas = slide.get("pessoas")
    lodge, local = lodge_padrao(slide.get("lodge")), local_padrao(slide.get("local"))
    extra = (f"MÍNIMO DE {_texto(slide['minimo_noites'])} NOITES"
             if slide.get("com_valor") and slide.get("minimo_noites") else "")
    return {
        "kicker": _texto(slide.get("kicker")), "titulo": _texto(slide.get("titulo")),
        "subtitulo": _texto(slide.get("subtitulo")), "lodge": _texto(lodge), "local": _texto(local),
        "lodge_local": _texto(" · ".join(p for p in (lodge, local.upper()) if p)),
        "dados": _texto(f"ATÉ {pessoas} PESSOAS" if str(pessoas or "").isdigit() else pessoas),
        "cta": _texto(slide.get("cta")), "contagem": _contagem(slide), "colunas": _colunas(slide),
        "extra": extra, "foco": FOCOS.get(slide.get("foco") or "centro", FOCOS["centro"]),
        "linhas": "".join(f"<li>{_texto(l)}</li>" for l in slide.get("linhas") or [] if str(l).strip()),
        "logo": LOGOS[slide.get("logo") or LOGO_DO_MOLDE.get(slide["molde"], "branca")],
    }


def montar_html(slide: dict, formato: str = FORMATO_PADRAO, empresa: str = "casa_veraneio", anuncio: bool = False) -> str:
    """HTML do slide (a foto e o logo como foto.<ext> e logo_*.png, ao lado do HTML)."""
    if empresa not in EMPRESAS:
        raise ValueError("Moldes só da Casa Veraneio por enquanto (Corp e Vero aguardam a identidade aprovada).")
    classes = FORMATOS_ANUNCIO if anuncio else FORMATOS
    if formato not in classes:
        raise ValueError(f"Formato fora dos moldes: {formato} (use {', '.join(classes)})")
    conferir(slide)
    pasta = PASTA_MOLDES / empresa
    corpo = Template((pasta / f"{slide['molde']}.html").read_text(encoding="utf-8")).substitute(campos(slide))
    largura, altura = formato.split("x")
    extra = '<link rel="stylesheet" href="anuncio.css">' if anuncio else ""
    return ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><link rel=\"stylesheet\" "
            f"href=\"base.css\">{extra}<style>html,body{{width:{largura}px;height:{altura}px}}</style></head>"
            f"<body class=\"{classes[formato]} molde-{slide['molde']}\">{corpo}</body></html>")


def _dentro(base: Path, relativo: str, campo: str) -> Path:
    """Caminho do molde.json sempre dentro da pasta dele (o desdobrar roda fora da caixa de areia)."""
    caminho = (base / relativo).resolve()
    if not caminho.is_relative_to(base.resolve()):
        raise ValueError(f"{campo} fora da pasta do molde: {relativo}")
    return caminho


def carregar(arquivo: Path) -> dict:
    dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    if not isinstance(dados.get("slides"), list) or not dados["slides"]:
        raise ValueError("molde.json sem slides.")
    for slide in dados["slides"]:
        conferir(slide)
    return dados


def _preparar_pasta(pasta: Path, marcas: Path) -> None:
    """base.css, fontes e logos ao lado dos HTMLs (o renderizador só serve a pasta do HTML)."""
    pasta.mkdir(parents=True, exist_ok=True)
    for css in ("base.css", "anuncio.css"):
        shutil.copy2(PASTA_MOLDES / "casa_veraneio" / css, pasta / css)
    for nome in FONTES:
        if (marcas / "FONTES" / nome).is_file() and not (pasta / nome).exists():
            shutil.copy2(marcas / "FONTES" / nome, pasta / nome)
    for nome in LOGOS.values():
        if (marcas / "CASA_VERANEIO" / nome).is_file() and not (pasta / nome).exists():
            shutil.copy2(marcas / "CASA_VERANEIO" / nome, pasta / nome)


def renderizar(arquivo: Path, formato: str | None = None, pasta_saida: Path | None = None, sufixo: str = "",
               marcas: Path | None = None, renderizador=renderizar_png.renderizar, anuncio: bool = False,
               slides: int | None = None) -> list[Path]:
    """Renderiza os slides do molde.json; devolve os PNGs gerados. `formato`/`pasta_saida`/`sufixo`/`anuncio`/`slides`
    (só os N primeiros): desdobrar."""
    arquivo = Path(arquivo).resolve()
    base, dados = arquivo.parent, carregar(arquivo)
    formato = formato or dados.get("formato") or FORMATO_PADRAO
    largura, altura = (int(v) for v in formato.split("x"))
    trabalho = base / "_moldes"
    _preparar_pasta(trabalho, marcas or pasta_marcas())
    gerados = []
    try:
        for n, slide in enumerate(dados["slides"][:slides], 1):
            pagina = montar_html(slide, formato, dados.get("empresa") or "casa_veraneio", anuncio)
            if slide.get("foto"):
                foto = _dentro(base, slide["foto"], "foto")
                if not foto.is_file():
                    raise ValueError(f"Foto não encontrada: {slide['foto']}")
                shutil.copy2(foto, trabalho / f"foto_{n:02d}{foto.suffix.lower()}")
                pagina = pagina.replace('src="foto"', f'src="foto_{n:02d}{foto.suffix.lower()}"')
            saida = _dentro(base, slide.get("saida") or f"entrega/{n:02d}_{slide['molde']}.png", "saida")
            if pasta_saida:
                saida = Path(pasta_saida) / saida.name
            saida = saida.with_name(f"{saida.stem}{sufixo}.png")
            saida.parent.mkdir(parents=True, exist_ok=True)
            (trabalho / f"slide_{n:02d}.html").write_text(pagina, encoding="utf-8")
            renderizador(trabalho / f"slide_{n:02d}.html", saida, largura, altura, ESPERA_MS)
            gerados.append(saida)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    return gerados


def instrucao(agente: str, empresa: str, entrega: str = "") -> str:
    """Bloco do prompt da produção: preencher o molde em vez de desenhar do zero (só artes da Casa Veraneio)."""
    if agente != "criador_imagens" or empresa not in EMPRESAS or entrega in ("texto", "documento"):
        return ""
    exemplo = json.dumps({"empresa": empresa, "formato": FORMATO_PADRAO, "slides": [
        {"molde": "capa", "foto": "acervo/<foto>.jpg", "foco": "centro", "kicker": "Casa em destaque",
         "titulo": "Lodge N", "subtitulo": "frase curta", "lodge": "N", "local": "Cidade / UF", "pessoas": 16,
         "saida": "entrega/01_capa.png"},
        {"molde": "foto", "foto": "acervo/<foto>.jpg", "saida": "entrega/02_foto.png"},
        {"molde": "ficha", "foto": "acervo/<foto>.jpg", "lodge": "N", "local": "Cidade / UF", "titulo": "...",
         "subtitulo": "...", "suites": 8, "pessoas": 16, "cta": "Reserve a data do seu grupo",
         "saida": "entrega/03_ficha.png"},
        {"molde": "fechamento", "kicker": "...", "titulo": "...", "subtitulo": "...", "linhas": ["..."],
         "cta": "...", "saida": "entrega/04_fechamento.png"}]}, ensure_ascii=False)
    return (
        "MOLDES DA CASA VERANEIO (padrão; Onda 3): capa, foto cheia, ficha do Lodge e fechamento já estão desenhados "
        "em código, com as medidas, fontes, degradês, logo (~135 px no fechamento) e zonas mortas dos manuais. NÃO "
        "desenhe esses slides do zero: escreva os dados num molde.json NA RAIZ da pasta atual (fora de entrega/) e "
        f'renderize todos de uma vez com: python "{Path(__file__).as_posix()}" molde.json\n'
        f"Modelo do molde.json: {exemplo}\n"
        f"Formatos: {', '.join(FORMATOS)} (\"formato\" do arquivo; feed 1080x1440 por padrão, stories 1080x1920). "
        "Campos opcionais: contagem {\"numero\", \"texto\"} na capa; foco esquerda/centro/direita/topo/base para o "
        "recorte da foto; campo vazio some do layout. Local sempre \"Cidade / UF\". Valores (valor, minimo_noites) "
        "só com \"com_valor\": true e só se o pedido pedir valores (o renderizador recusa R$ ou diária sem isso). "
        "Fotos e saídas sempre dentro desta pasta. Abra cada PNG com Read e confira, como sempre. "
        "Saia do molde (HTML próprio com renderizar_png.py, como antes) SÓ quando o pedido pedir o que os moldes "
        "não cobrem (conceito ou layout novo, \"sem molde\", F2 a F6, anúncio 1,91:1); slides do molde e slides "
        "livres podem conviver: diga no resumo quais saíram do molde. Num ajuste, edite o molde.json (saídas com o "
        "sufixo da versão) e renderize de novo; ajuste de peça feita sem molde (sem molde.json aqui) segue o HTML "
        "dela, sem trocar pelo molde, salvo pedido. Mantenha o molde.json com a versão vigente: é dele que o botão "
        "Desdobrar gera 4:5 e 9:16 sem o Max. O editável (PPTX) segue as diretrizes, com os mesmos textos do PNG.")


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("dados")
    args.add_argument("--formato", choices=sorted(FORMATOS))
    args.add_argument("--pasta-saida")
    args.add_argument("--sufixo", default="")
    opcoes = args.parse_args()
    for png in renderizar(Path(opcoes.dados), opcoes.formato, opcoes.pasta_saida and Path(opcoes.pasta_saida),
                          opcoes.sufixo):
        print(f"PNG do molde: {png}")


if __name__ == "__main__":
    main()
