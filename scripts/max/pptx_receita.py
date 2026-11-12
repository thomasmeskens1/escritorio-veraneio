"""PPTX editável gerado pelo código a partir da receita da peça (Onda 3 de novembro, 12/11/2026; moviemaker-35,
criador_imagens-04 e designer-31).

Antes o Max montava o PPTX do editável à mão em cada peça: um aumento de logo (52 para 135 px) custou uma produção
inteira e houve PPTX de 22 MB. Agora o sistema gera o PPTX sozinho, sem gastar o Max, da receita conferida
(receita.py) e do motion.json ou molde.json da pasta: um slide por cena ou por slide (igual ao MP4/PNG), no tamanho
da peça, com a foto (ou um quadro do vídeo) posicionada, os textos EDITÁVEIS nas fontes e cores da marca
(backend/marcas_regras.json) e o logo oficial. Fotos vão reduzidas (JPEG ~1080 px): o arquivo fica leve.

Cada forma leva um nome fixo ("texto|c<cena>|<papel>", "foto|c<cena>", "logo|c<cena>") e a foto leva no texto
alternativo a origem e o hash: é assim que pptx_diferenca.py lê o PPTX que a equipe devolve e mostra o que mudou.
As medidas do molde.json são aproximadas (o desenho exato está no HTML do molde); as do motion.json são as do vídeo.

Uso: python pptx_receita.py <pasta da peça> [saida.pptx]
"""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import receita as receita_mod  # noqa: E402

EMU_POR_PX = 9525              # 1 px = 9525 EMU = 0,75 pt: tamanho em px do motion vira pt * 0,75
MARGEM_PX = 60                 # margem lateral das caixas de texto
FOTO_LARGURA_MAX = 1080        # fotos reduzidas para o PPTX ficar leve
FOTO_QUALIDADE = 82
SUFIXO = "_editavel.pptx"
# Nomes das fontes no PowerPoint (manual 08: Playfair Display Extrabold, Playfair itálico e Muli).
FONTES = {"playfair": "Playfair Display", "muli": "Muli"}
PESO_NEGRITO = 600
PESO_PADRAO = {"playfair": 800, "muli": 400}
# Reserva quando o marcas_regras.json não está à mão (no contêiner o backend fica em /app).
PALETA_RESERVA = {"verde": "#00361B", "creme": "#F0DBC3", "caramelo": "#D9A15B", "branco": "#FFFFFF",
                  "preto": "#000000"}
# Layout aproximado do molde.json (artes da Casa Veraneio): papel -> (fonte, tamanho px, peso, itálico, cor, caixa alta)
ESTILO_MOLDE = {"kicker": ("muli", 26, 700, False, "caramelo", True), "titulo": ("playfair", 84, 800, False, "branco", False),
                "subtitulo": ("playfair", 52, 400, True, "branco", False), "local": ("muli", 30, 400, False, "creme", False),
                "linhas": ("muli", 32, 400, False, "branco", False), "cta": ("muli", 30, 700, False, "caramelo", False)}
PAPEIS_MOLDE = ("kicker", "titulo", "subtitulo", "local", "linhas", "cta")
VIDEOS = {".mp4", ".mov", ".m4v", ".webm"}
FOTOS = {".jpg", ".jpeg", ".png", ".webp"}


def _ler_json(arquivo: Path):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def paleta() -> dict:
    """Cores da marca: as do backend/marcas_regras.json (nas três empresas), com a reserva acima."""
    for pasta in (Path(__file__).resolve().parents[2] / "backend", Path("/app")):
        if isinstance(dados := _ler_json(pasta / "marcas_regras.json"), dict) and isinstance(dados.get("paleta"), dict):
            return {**PALETA_RESERVA, **{k: v for k, v in dados["paleta"].items() if not k.startswith("_")}}
    return dict(PALETA_RESERVA)


def hex_da_cor(valor, cores: dict) -> str:
    valor = str(valor or "branco")
    return (cores.get(valor) or (valor if valor.startswith("#") and len(valor) == 7 else cores["branco"])).upper()


def _medidas(formato) -> tuple[int, int]:
    achado = receita_mod.FORMATO.match(str(formato or ""))
    return (int(achado[1]), int(achado[2])) if achado else (1080, 1920)


# ---------------------------------------------------------------- plano (sem python-pptx: testável no contêiner)

def _linhas(el: dict) -> list[dict]:
    brutas = el.get("linhas") if el.get("linhas") is not None else str(el.get("texto", "")).split("\n")
    if el.get("tipo") == "contagem":
        brutas = [f"{el.get('prefixo', '')}{el.get('valor')}{el.get('sufixo', '')}".strip()]
    linhas = []
    for n, linha in enumerate(brutas):
        linha = {"texto": linha} if isinstance(linha, str) else dict(linha)
        if el.get("italico_ultima") and n == len(brutas) - 1 and len(brutas) > 1:
            linha.setdefault("italico", True)
        fonte = linha.get("fonte") or el.get("fonte", "muli")
        peso = linha.get("peso") or el.get("peso") or PESO_PADRAO.get(fonte, 400)
        linhas.append({"texto": str(linha.get("texto", "")), "fonte": fonte,
                       "tamanho": int(linha.get("tamanho") or el.get("tamanho", 48)),
                       "italico": bool(linha.get("italico", el.get("italico", False))), "negrito": peso >= PESO_NEGRITO,
                       "cor": linha.get("cor") or el.get("cor", "branco")})
    return linhas


def _caixa_de_texto(el: dict, largura: int, chave: str, papel: str) -> dict:
    linhas = _linhas(el)
    tamanho = max(l["tamanho"] for l in linhas) if linhas else 48
    entrelinha = float(el.get("entrelinha") or round(tamanho * 1.2))
    alinhamento = el.get("alinhamento", "centro")
    x = el.get("x", "centro")
    if alinhamento == "esquerda" and x != "centro":
        esquerda, larg = float(x), largura - float(x) - MARGEM_PX
    elif alinhamento == "direita" and x != "centro":
        esquerda, larg = MARGEM_PX, float(x) - MARGEM_PX
    else:
        esquerda, larg = MARGEM_PX, largura - 2 * MARGEM_PX
    caixa = {"chave": chave, "papel": papel, "linhas": linhas, "x": round(esquerda), "y": round(float(el.get("y", 0))),
             "largura": round(max(larg, 100)), "altura": round(entrelinha * len(linhas) + tamanho * 0.4),
             "alinhamento": alinhamento, "entrelinha": entrelinha, "maiusculas": bool(el.get("maiusculas")),
             "espacamento": float(el.get("espacamento") or 0), "fundo": None}
    if el.get("tipo") == "caixa":  # caixa reta da marca com o texto dentro (largura estimada pelo tamanho do texto)
        maior = max((len(l["texto"]) for l in linhas), default=8)
        larg = int(el.get("largura") or min(largura - 2 * MARGEM_PX, maior * tamanho * 0.55 + 72))
        caixa.update(largura=larg, x=round((largura - larg) / 2) if x == "centro" else round(float(x)),
                     altura=int(el.get("altura") or caixa["altura"] + 44), fundo=el.get("cor", "creme"))
        for linha in linhas:
            linha["cor"] = el.get("cor_texto", "verde")
    return caixa


def _midia(origem: str) -> tuple[str | None, str | None]:
    origem = str(origem or "")
    if not origem or origem.startswith("fundo:"):
        return None, None
    sufixo = Path(origem).suffix.lower()
    return origem, "video" if sufixo in VIDEOS else "foto" if sufixo in FOTOS else None


def _slide_vazio(n: int, cena: dict) -> dict:
    origem = str(cena.get("origem") or "fundo:verde")
    midia, tipo = _midia(origem)
    return {"n": n, "cena": cena.get("n", n), "fundo": origem[6:] if origem.startswith("fundo:") else "verde",
            "midia": midia, "midia_tipo": tipo, "de": float(cena.get("de") or 0), "textos": [], "filetes": [],
            "imagens": [], "logo": None, "duracao_s": cena.get("duracao_s"), "velocidade": cena.get("velocidade")}


def _logo(apelido, empresa: str, receita: dict, x_centro: float, y: float, altura: float, n: int) -> dict:
    arquivo = None
    if isinstance(receita.get("logo"), dict) and receita["logo"].get("apelido") == apelido:
        arquivo = receita["logo"].get("arquivo")
    arquivo = arquivo or receita_mod._arquivo_do_logo(empresa, apelido)
    return {"chave": f"logo|c{n}", "apelido": apelido, "arquivo": arquivo, "x_centro": round(x_centro), "y": round(y),
            "altura": round(altura)}


def _plano_motion(receita: dict, spec: dict, largura: int, altura: int) -> list[dict]:
    slides = []
    cenas_receita = receita.get("cenas") or []
    for n, cena in enumerate(spec.get("cenas") or [], 1):
        base = cenas_receita[n - 1] if n <= len(cenas_receita) and isinstance(cenas_receita[n - 1], dict) else {}
        slide = _slide_vazio(n, {"n": n, "origem": cena.get("video") or f"fundo:{cena.get('fundo') or 'verde'}",
                                 "de": cena.get("de", 0), "duracao_s": cena.get("duracao"),
                                 "velocidade": base.get("velocidade")})
        t = 0
        for el in [e for e in cena.get("elementos") or [] if isinstance(e, dict)]:
            tipo = el.get("tipo")
            if tipo in ("texto", "caixa", "contagem") and (el.get("texto") or el.get("linhas") or tipo == "contagem"):
                t += 1
                slide["textos"].append(_caixa_de_texto(el, largura, f"texto|c{n}|t{t}", f"texto {t}"))
            elif tipo == "filete":
                larg = int(el.get("largura", 120))
                slide["filetes"].append({"x": round((largura - larg) / 2), "y": int(el.get("y", 0)), "largura": larg,
                                         "altura": int(el.get("espessura", 4)), "cor": el.get("cor", "caramelo")})
            elif tipo == "imagem" and el.get("logo"):
                slide["logo"] = _logo(el["logo"], receita.get("empresa"), receita, largura / 2, float(el.get("y", 0)),
                                      float(el.get("altura") or 135), n)
            elif tipo == "imagem" and el.get("arquivo"):
                slide["imagens"].append({"arquivo": el["arquivo"], "y": int(el.get("y", 0)),
                                         "altura": int(el.get("altura") or 200)})
        slides.append(slide)
    return slides


def _plano_molde(receita: dict, dados: dict, largura: int, altura: int, feed_px: int) -> list[dict]:
    slides = []
    for n, folha in enumerate(dados.get("slides") or [], 1):
        fechamento = folha.get("molde") == "fechamento"
        slide = _slide_vazio(n, {"n": n, "origem": folha.get("foto") or "fundo:verde"})
        papeis = [(p, folha[p]) for p in PAPEIS_MOLDE if folha.get(p)]
        y = altura * (0.36 if fechamento else 0.58)
        for papel, valor in papeis:
            fonte, tamanho, peso, italico, cor, caixa_alta = ESTILO_MOLDE[papel]
            linhas = [str(v) for v in valor] if isinstance(valor, list) else [str(valor)]
            el = {"linhas": linhas, "fonte": fonte, "tamanho": tamanho, "peso": peso, "italico": italico, "cor": cor,
                  "maiusculas": caixa_alta, "y": y, "alinhamento": "centro" if fechamento else "esquerda",
                  "x": "centro" if fechamento else 80}
            slide["textos"].append(_caixa_de_texto(el, largura, f"texto|c{n}|{papel}", papel))
            y += tamanho * 1.25 * len(linhas) + 18
        if (apelido := folha.get("logo") or {"capa": "clara", "ficha": "clara", "fechamento": "caramelo"}.get(folha.get("molde"))):
            apelido = {"branca": "clara"}.get(apelido, apelido)
            altura_logo = 135 if fechamento else feed_px
            slide["logo"] = _logo(apelido, receita.get("empresa"), receita, largura / 2,
                                  altura * 0.12 if fechamento else 70, altura_logo, n)
        slides.append(slide)
    return slides


def _plano_receita(receita: dict, largura: int, altura: int, feed_px: int) -> list[dict]:
    """Sem motion.json nem molde.json: os textos de cada cena empilhados no meio, o logo embaixo."""
    slides = []
    for n, cena in enumerate([c for c in receita.get("cenas") or [] if isinstance(c, dict)], 1):
        slide = _slide_vazio(n, cena)
        y = altura * 0.38
        for t, texto in enumerate([str(x) for x in cena.get("textos") or [] if str(x).strip()], 1):
            el = {"texto": texto, "fonte": "playfair" if t == 1 else "muli", "tamanho": 72 if t == 1 else 40,
                  "cor": "branco", "y": y}
            slide["textos"].append(_caixa_de_texto(el, largura, f"texto|c{n}|t{t}", f"texto {t}"))
            y += (72 if t == 1 else 40) * 1.3 + 16
        if cena.get("logo"):
            slide["logo"] = _logo(cena["logo"], receita.get("empresa"), receita, largura / 2,
                                  altura - 340 - feed_px if altura > 1500 else altura - 80 - feed_px, feed_px, n)
        slides.append(slide)
    return slides


def planejar(receita: dict, spec: dict | None = None, dados_molde: dict | None = None) -> dict:
    """Plano do PPTX (medidas em px da peça): um slide por cena do motion.json, por slide do molde.json ou, sem
    eles, por cena da receita. O motion/molde só vale se tiver o mesmo número de cenas da receita."""
    largura, altura = _medidas(receita.get("formato"))
    cenas = len(receita.get("cenas") or [])
    feed_px = 112
    if isinstance(spec, dict) and spec.get("cenas") and (not cenas or len(spec["cenas"]) == cenas):
        slides, fonte = _plano_motion(receita, spec, largura, altura), "motion.json"
    elif isinstance(dados_molde, dict) and dados_molde.get("slides") and (not cenas or len(dados_molde["slides"]) == cenas):
        slides, fonte = _plano_molde(receita, dados_molde, largura, altura, feed_px), "molde.json"
    else:
        slides, fonte = _plano_receita(receita, largura, altura, feed_px), "receita.json"
    return {"largura": largura, "altura": altura, "empresa": receita.get("empresa"), "peca": receita.get("peca") or "",
            "fonte": fonte, "slides": slides}


def plano_da_pasta(rascunho: Path, receita: dict | None = None) -> dict | None:
    """Plano a partir da pasta da peça: a receita conferida (entrega/EDITÁVEL) ou a do rascunho, mais o
    motion.json/molde.json da raiz."""
    rascunho = Path(rascunho)
    if receita is None:
        receita = _ler_json(rascunho / "entrega" / receita_mod.DESTINO)
        if not isinstance(receita, dict):
            receita, _ = receita_mod.carregar(rascunho)
    if not isinstance(receita, dict) or receita.get("_invalida") or not receita.get("cenas"):
        return None
    return planejar(receita, _ler_json(rascunho / "motion.json"), _ler_json(rascunho / "molde.json"))


# ---------------------------------------------------------------- escrita do PPTX (python-pptx)

def hash_de(dados: bytes) -> str:
    return hashlib.sha1(dados).hexdigest()[:12]


def _achar(rascunho: Path, nome: str | None, marcas: Path | None, empresa: str | None) -> Path | None:
    if not nome:
        return None
    candidatos = [rascunho / nome]
    if marcas is not None:
        try:
            import logos_empresas
            candidatos.append(Path(marcas) / logos_empresas.LOGOS[logos_empresas.empresa_valida(empresa)]["pasta"] / nome)
        except (ImportError, KeyError):
            pass
    achado = next((c for c in candidatos if c.is_file()), None)
    return achado or next((p for p in rascunho.rglob(Path(nome).name) if p.is_file()), None)


def _quadro(rascunho: Path, slide: dict, largura: int, altura: int) -> bytes | None:
    """Foto reduzida e recortada no tamanho da peça (JPEG); vídeo vira um quadro parado (ffmpeg)."""
    arquivo = _achar(rascunho, slide.get("midia"), None, None)
    if arquivo is None:
        return None
    from PIL import Image, ImageOps
    try:
        if slide.get("midia_tipo") == "video":
            with tempfile.TemporaryDirectory() as pasta:
                saida = Path(pasta) / "quadro.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(slide.get("de") or 0), "-i",
                                str(arquivo), "-frames:v", "1", str(saida)], capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                imagem = Image.open(saida).convert("RGB")
        else:
            imagem = Image.open(arquivo).convert("RGB")
    except (OSError, subprocess.SubprocessError):
        return None
    escala = min(1.0, FOTO_LARGURA_MAX / largura)
    imagem = ImageOps.fit(imagem, (round(largura * escala), round(altura * escala)))
    buffer = io.BytesIO()
    imagem.save(buffer, "JPEG", quality=FOTO_QUALIDADE, optimize=True)
    return buffer.getvalue()


def _rgb(hexa: str):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(hexa.lstrip("#"))


def _escrever_texto(slide_pptx, caixa: dict, cores: dict, px):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.util import Pt
    if caixa.get("fundo"):
        forma = slide_pptx.shapes.add_shape(MSO_SHAPE.RECTANGLE, px(caixa["x"]), px(caixa["y"]), px(caixa["largura"]),
                                            px(caixa["altura"]))
        forma.fill.solid()
        forma.fill.fore_color.rgb = _rgb(hex_da_cor(caixa["fundo"], cores))
        forma.line.fill.background()
    else:
        forma = slide_pptx.shapes.add_textbox(px(caixa["x"]), px(caixa["y"]), px(caixa["largura"]), px(caixa["altura"]))
    forma.name = caixa["chave"]
    quadro = forma.text_frame
    quadro.word_wrap = True
    quadro.margin_left = quadro.margin_right = quadro.margin_top = quadro.margin_bottom = 0
    quadro.vertical_anchor = MSO_ANCHOR.MIDDLE if caixa.get("fundo") else MSO_ANCHOR.TOP
    alinhar = {"esquerda": PP_ALIGN.LEFT, "direita": PP_ALIGN.RIGHT}.get(caixa["alinhamento"], PP_ALIGN.CENTER)
    for n, linha in enumerate(caixa["linhas"]):
        paragrafo = quadro.paragraphs[0] if n == 0 else quadro.add_paragraph()
        paragrafo.alignment = alinhar
        paragrafo.line_spacing = Pt(caixa["entrelinha"] * 0.75)
        corrida = paragrafo.add_run()
        corrida.text = linha["texto"]
        fonte = corrida.font
        fonte.name = FONTES.get(linha["fonte"], linha["fonte"])
        fonte.size = Pt(linha["tamanho"] * 0.75)
        fonte.bold = linha["negrito"]
        fonte.italic = linha["italico"]
        fonte.color.rgb = _rgb(hex_da_cor(linha["cor"], cores))
        if caixa.get("maiusculas"):
            corrida._r.get_or_add_rPr().set("cap", "all")
        if caixa.get("espacamento"):  # espaçamento entre letras em centésimos de pt
            corrida._r.get_or_add_rPr().set("spc", str(round(caixa["espacamento"] * 75)))


def escrever(plano: dict, rascunho: Path, destino: Path, marcas: Path | None = None) -> tuple[Path, list[str]]:
    """Grava o PPTX do plano. Devolve (arquivo, avisos)."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    rascunho, destino = Path(rascunho), Path(destino)
    cores, avisos = paleta(), []
    largura, altura = plano["largura"], plano["altura"]

    def px(valor):
        return int(round(float(valor) * EMU_POR_PX))

    apresentacao = Presentation()
    apresentacao.slide_width, apresentacao.slide_height = px(largura), px(altura)
    vazio = apresentacao.slide_layouts[6]
    for slide in plano["slides"]:
        folha = apresentacao.slides.add_slide(vazio)
        folha.background.fill.solid()
        folha.background.fill.fore_color.rgb = _rgb(hex_da_cor(slide["fundo"], cores))
        if slide.get("midia"):
            if (dados := _quadro(rascunho, slide, largura, altura)) is not None:
                foto = folha.shapes.add_picture(io.BytesIO(dados), 0, 0, px(largura), px(altura))
                foto.name = f"foto|c{slide['cena']}"
                foto._element.nvPicPr.cNvPr.set("descr", f"origem={slide['midia']} hash={hash_de(dados)}")
            else:
                avisos.append(f"slide {slide['n']}: {slide['midia']} não encontrado (fundo liso no lugar)")
        for imagem in slide.get("imagens") or []:
            if (arquivo := _achar(rascunho, imagem["arquivo"], marcas, plano.get("empresa"))) is not None:
                figura = folha.shapes.add_picture(str(arquivo), 0, px(imagem["y"]), height=px(imagem["altura"]))
                figura.left = int((px(largura) - figura.width) / 2)
                figura.name = f"imagem|c{slide['cena']}"
        for filete in slide.get("filetes") or []:
            linha = folha.shapes.add_shape(MSO_SHAPE.RECTANGLE, px(filete["x"]), px(filete["y"]), px(filete["largura"]),
                                           px(filete["altura"]))
            linha.fill.solid()
            linha.fill.fore_color.rgb = _rgb(hex_da_cor(filete["cor"], cores))
            linha.line.fill.background()
            linha.name = f"filete|c{slide['cena']}"
        for caixa in slide["textos"]:
            _escrever_texto(folha, caixa, cores, px)
        if (logo := slide.get("logo")):
            arquivo = _achar(rascunho, logo.get("arquivo"), marcas, plano.get("empresa"))
            if arquivo is not None:
                figura = folha.shapes.add_picture(str(arquivo), 0, px(logo["y"]), height=px(logo["altura"]))
                figura.left = int(px(logo["x_centro"]) - figura.width / 2)
                figura.name = logo["chave"]
                figura._element.nvPicPr.cNvPr.set("descr", f"origem={logo.get('arquivo')} hash={hash_de(arquivo.read_bytes())}")
            else:  # marcador no lugar do logo (a equipe vê onde ele vai; o leitor não acusa "logo removido")
                avisos.append(f"slide {slide['n']}: logo {logo.get('arquivo') or logo.get('apelido')} não encontrado")
                altura_logo = px(logo["altura"])
                marcador = folha.shapes.add_textbox(int(px(logo["x_centro"]) - altura_logo), px(logo["y"]),
                                                    2 * altura_logo, altura_logo)
                marcador.name = logo["chave"]
                marcador.text_frame.text = f"[logo {logo.get('apelido')}]"
        notas = [f"Cena {slide['cena']} da receita"]
        if slide.get("duracao_s"):
            notas.append(f"duração {str(slide['duracao_s']).replace('.', ',')} s")
        if slide.get("midia_tipo") == "video":
            notas.append(f"vídeo {slide['midia']} a partir de {slide['de']:g} s (no PPTX vai só um quadro parado)")
        folha.notes_slide.notes_text_frame.text = " · ".join(notas)
    destino.parent.mkdir(parents=True, exist_ok=True)
    apresentacao.save(str(destino))
    return destino, avisos


def nome_do_pptx(receita: dict) -> str:
    arquivos = [a for a in receita.get("arquivos") or [] if isinstance(a, str)]
    base = Path(arquivos[0]).stem if arquivos else (receita.get("peca") or "peca")
    return f"EDITÁVEL/{base}{SUFIXO}"


def na_producao(rascunho: Path, final: Path, marcas: Path | None = None) -> tuple[str | None, str]:
    """Gera entrega/EDITÁVEL/<peça>_editavel.pptx da receita conferida. (nome relativo a entrega/ ou None, linha
    para o resumo). Nunca derruba a entrega."""
    try:
        receita = _ler_json(Path(final) / receita_mod.DESTINO)
        if not isinstance(receita, dict) or not receita.get("cenas"):
            return None, ""
        plano = plano_da_pasta(rascunho, receita)
        nome = nome_do_pptx(receita)
        arquivo, avisos = escrever(plano, rascunho, Path(final) / nome, marcas)
    except ImportError:
        return None, "⚠ PPTX editável: python-pptx não instalado no PC do Max (pip install python-pptx)."
    except Exception as erro:  # noqa: BLE001 - o editável nunca derruba a entrega
        return None, f"⚠ PPTX editável: não gerado ({erro})."
    tamanho = arquivo.stat().st_size / 1024 / 1024
    linha = (f"PPTX editável gerado pelo sistema ({len(plano['slides'])} slide(s), {tamanho:.1f} MB, medidas do "
             f"{plano['fonte']}); em {nome}.")
    return nome, linha + (" Atenção: " + "; ".join(avisos[:4]) + "." if avisos else "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pasta = Path(sys.argv[1])
    plano_cli = plano_da_pasta(pasta)
    if plano_cli is None:
        sys.exit("sem receita na pasta")
    receita_cli = _ler_json(pasta / "entrega" / receita_mod.DESTINO) or receita_mod.carregar(pasta)[0]
    saida_cli = Path(sys.argv[2]) if len(sys.argv) > 2 else pasta / "entrega" / nome_do_pptx(receita_cli)
    print(*escrever(plano_cli, pasta, saida_cli), sep="\n")
