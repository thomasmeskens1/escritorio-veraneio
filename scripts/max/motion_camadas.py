"""Camadas do motion graphics (motion.py; Thomas, 04/11/2026): cores da marca, curvas de suavização, fontes e o
desenho de cada elemento em Pillow, uma vez só, como "sprite" (imagem RGBA recortada + posição na tela).

Só Pillow (sem numpy: o python do PC não tem e a caixa de areia não deixa instalar). A animação (motion.py) só move,
recorta, escala e muda a opacidade desses sprites; o texto só é redesenhado quando o próprio efeito muda o texto
(espaçamento das letras em "letras" e o número em "contagem"), com cache.
"""

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Manual 01/08: Verde #00361B, Caramelo #D9A15B, Creme #F0DBC3 e Branco (preto só para escurecer o vídeo).
CORES = {"verde": (0, 54, 27), "caramelo": (217, 161, 91), "creme": (240, 219, 195), "branco": (255, 255, 255),
         "preto": (0, 0, 0)}
HEX = re.compile(r"^#([0-9a-f]{6})([0-9a-f]{2})?$", re.IGNORECASE)

# Fontes da marca (CÉREBRO/MARCAS/FONTES, copiadas para _referencias/FONTES da pasta da peça).
ARQUIVOS_FONTE = {"playfair": "PlayfairDisplay-Variavel.ttf", "playfair_italico": "PlayfairDisplay-Italico-Variavel.ttf",
                  "muli": "Muli-Variavel.ttf", "muli_italico": "Muli-Italico-Variavel.ttf"}
# Título primário em Playfair Extrabold 800; secundário em Playfair Regular itálico; corpo em Muli Regular.
PESO_PADRAO = {"playfair": 800, "playfair_italico": 400, "muli": 400, "muli_italico": 400}
ITALICO_DE = {"playfair": "playfair_italico", "muli": "muli_italico"}
LOGOS = {"branca": "logo_branca.png", "caramelo": "logo_caramelo_texto_creme.png"}  # Casa Veraneio


def cor(valor, opacidade: float = 1.0) -> tuple[int, int, int, int]:
    """"verde", "caramelo", "creme", "branco", "preto" ou "#RRGGBB"/"#RRGGBBAA" -> RGBA."""
    nome = str(valor or "").strip().lower()
    if nome in CORES:
        r, g, b = CORES[nome]
        a = 255
    elif (achado := HEX.match(nome)):
        r, g, b = (int(achado.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        a = int(achado.group(2), 16) if achado.group(2) else 255
    else:
        raise ValueError(f"Cor desconhecida: {valor!r} (use verde, caramelo, creme, branco, preto ou #RRGGBB)")
    return r, g, b, round(a * max(0.0, min(1.0, float(opacidade))))


# Curvas de suavização: só desaceleração suave (nada de quique nem elástico, que a marca não usa).
def _limite(t: float) -> float:
    return 0.0 if t <= 0 else 1.0 if t >= 1 else float(t)


def linear(t: float) -> float:
    return _limite(t)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - _limite(t)) ** 3


def ease_out_quint(t: float) -> float:
    return 1 - (1 - _limite(t)) ** 5


def ease_in_out_cubic(t: float) -> float:
    t = _limite(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_in_cubic(t: float) -> float:
    return _limite(t) ** 3


CURVAS = {"linear": linear, "ease_out_cubic": ease_out_cubic, "ease_out_quint": ease_out_quint,
          "ease_in_out_cubic": ease_in_out_cubic, "ease_in_cubic": ease_in_cubic}


@dataclass
class Sprite:
    imagem: Image.Image  # RGBA, recortada no que tem tinta
    x: int               # canto superior esquerdo na tela
    y: int

    @property
    def largura(self) -> int:
        return self.imagem.width

    @property
    def altura(self) -> int:
        return self.imagem.height


def aparar(sprite: Sprite) -> Sprite:
    """Recorta a parte transparente em volta (menos pixels para compor a cada quadro)."""
    caixa = sprite.imagem.getchannel("A").getbbox()
    if not caixa:
        return Sprite(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), sprite.x, sprite.y)
    return Sprite(sprite.imagem.crop(caixa), sprite.x + caixa[0], sprite.y + caixa[1])


def juntar(sprites: list[Sprite]) -> Sprite:
    """Vários sprites (palavras) num só, na posição de cada um."""
    if not sprites:
        return Sprite(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0, 0)
    x0, y0 = min(s.x for s in sprites), min(s.y for s in sprites)
    x1, y1 = max(s.x + s.largura for s in sprites), max(s.y + s.altura for s in sprites)
    imagem = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for s in sprites:
        imagem.alpha_composite(s.imagem, (s.x - x0, s.y - y0))
    return Sprite(imagem, x0, y0)


def colar(tela: Image.Image, imagem: Image.Image, x: int, y: int) -> None:
    """alpha_composite que aceita sprite saindo da tela (o Pillow recusa destino negativo)."""
    esquerda, topo = max(0, -x), max(0, -y)
    direita, base = min(imagem.width, tela.width - x), min(imagem.height, tela.height - y)
    if direita <= esquerda or base <= topo:
        return
    if (esquerda, topo, direita, base) != (0, 0, imagem.width, imagem.height):
        imagem = imagem.crop((esquerda, topo, direita, base))
    tela.alpha_composite(imagem, (x + esquerda, y + topo))


def com_opacidade(imagem: Image.Image, opacidade: float) -> Image.Image:
    if opacidade >= 0.999:
        return imagem
    r, g, b, a = imagem.split()
    tabela = [round(v * opacidade) for v in range(256)]
    return Image.merge("RGBA", (r, g, b, a.point(tabela)))


def com_sombra(sprite: Sprite, opacidade: float, raio: int) -> Sprite:
    """Sombra suave e baixa sob o texto (só leitura sobre vídeo claro; nada de brilho)."""
    margem = raio * 3
    w, h = sprite.largura + 2 * margem, sprite.altura + 2 * margem
    alfa = Image.new("L", (w, h), 0)
    alfa.paste(sprite.imagem.getchannel("A"), (margem, margem + max(1, raio // 3)))
    alfa = alfa.filter(ImageFilter.GaussianBlur(raio)).point([round(v * opacidade) for v in range(256)])
    imagem = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    imagem.putalpha(alfa)
    imagem.alpha_composite(sprite.imagem, (margem, margem))
    return aparar(Sprite(imagem, sprite.x - margem, sprite.y - margem))


class Fontes:
    """Acha as fontes da marca nas pastas dadas (a da peça primeiro) e guarda cada (fonte, tamanho, peso)."""

    def __init__(self, pastas: list[Path]):
        self.pastas = [Path(p) for p in pastas]
        self.avisos: list[str] = []
        self._cache: dict = {}
        self._arquivos: dict = {}

    def arquivo(self, nome: str) -> Path | None:
        if nome not in self._arquivos:
            alvo = ARQUIVOS_FONTE.get(nome, nome)
            self._arquivos[nome] = next((p / alvo for p in self.pastas if (p / alvo).is_file()), None)
        return self._arquivos[nome]

    def fonte(self, nome: str, tamanho: int, peso: int | None = None):
        chave = (nome, int(tamanho), peso)
        if chave in self._cache:
            return self._cache[chave]
        arquivo = self.arquivo(nome)
        if arquivo is None:
            aviso = f"fonte {ARQUIVOS_FONTE.get(nome, nome)} não encontrada: usando a padrão do Pillow (só teste)"
            if aviso not in self.avisos:
                self.avisos.append(aviso)
            fonte = ImageFont.load_default(int(tamanho))
        else:
            fonte = ImageFont.truetype(str(arquivo), int(tamanho))
            peso = peso or PESO_PADRAO.get(nome)
            try:
                eixos = fonte.get_variation_axes()
                if peso and eixos:
                    fonte.set_variation_by_axes([max(eixos[0]["minimum"], min(eixos[0]["maximum"], peso))])
            except (OSError, AttributeError):  # fonte estática ou FreeType sem variações: fica o peso do arquivo
                pass
        self._cache[chave] = fonte
        return fonte


def largura_texto(fonte, texto: str, espacamento: float = 0) -> float:
    if not texto:
        return 0.0
    if not espacamento:
        return fonte.getlength(texto)
    return sum(fonte.getlength(c) for c in texto) + espacamento * (len(texto) - 1)


def _escrever(desenho: ImageDraw.ImageDraw, x: float, base: float, texto: str, fonte, preenchimento, espacamento):
    if not espacamento:
        desenho.text((x, base), texto, font=fonte, fill=preenchimento, anchor="ls")
        return
    for letra in texto:  # espaçamento de letras da marca (o Pillow não tem tracking)
        desenho.text((x, base), letra, font=fonte, fill=preenchimento, anchor="ls")
        x += fonte.getlength(letra) + espacamento


def linhas_do_texto(el: dict) -> list[dict]:
    """"texto" (com \\n) ou "linhas" (texto ou {texto, italico, fonte, peso, tamanho, cor}) -> lista de dicts."""
    brutas = el.get("linhas") if el.get("linhas") is not None else str(el.get("texto", "")).split("\n")
    linhas = []
    for n, linha in enumerate(brutas):
        linha = {"texto": linha} if isinstance(linha, str) else dict(linha)
        if el.get("italico_ultima") and n == len(brutas) - 1 and len(brutas) > 1:
            linha.setdefault("italico", True)
        texto = str(linha.get("texto", ""))
        linha["texto"] = texto.upper() if el.get("maiusculas") else texto
        linhas.append(linha)
    return linhas


def sprites_de_palavras(el: dict, largura_tela: int, fontes: Fontes, espacamento: float | None = None,
                        texto: str | None = None) -> list[Sprite]:
    """Cada palavra do texto como sprite, já na posição final (alinhamento, entrelinha e espaçamento da marca)."""
    if texto is not None:
        el = {**el, "texto": texto, "linhas": None}
    tamanho = int(el.get("tamanho", 48))
    entrelinha = float(el.get("entrelinha") or round(tamanho * 1.2))
    espacamento = float(el.get("espacamento", 0) if espacamento is None else espacamento)
    alinhamento = el.get("alinhamento", "centro")
    x = el.get("x", "centro")
    ancora = largura_tela / 2 if x == "centro" else float(x)
    y = float(el.get("y", 0))
    sprites, primeira_subida = [], None
    for n, linha in enumerate(linhas_do_texto(el)):
        nome = linha.get("fonte") or el.get("fonte", "muli")
        if linha.get("italico", el.get("italico")):
            nome = ITALICO_DE.get(nome, nome)
        tam = int(linha.get("tamanho", tamanho))
        peso = linha.get("peso") or (el.get("peso") if nome == el.get("fonte", "muli") else None)
        fonte = fontes.fonte(nome, tam, peso)
        subida, descida = fonte.getmetrics()
        primeira_subida = subida if primeira_subida is None else primeira_subida
        base = y + primeira_subida + n * entrelinha
        preenchimento = cor(linha.get("cor") or el.get("cor", "branco"), el.get("opacidade", 1.0))
        palavras = linha["texto"].split()
        larguras = [largura_texto(fonte, p, espacamento) for p in palavras]
        vao = fonte.getlength(" ") + espacamento
        total = sum(larguras) + vao * max(0, len(palavras) - 1)
        cursor = ancora - total / 2 if alinhamento == "centro" else ancora - total if alinhamento == "direita" else ancora
        margem = math.ceil(tam * 0.4)  # itálico e acentos passam da caixa da letra
        for palavra, largura in zip(palavras, larguras):
            imagem = Image.new("RGBA", (math.ceil(largura) + 2 * margem, subida + descida + 2 * margem), (0, 0, 0, 0))
            dx = cursor - math.floor(cursor)  # posição subpixel preservada (sem tremor entre palavras)
            _escrever(ImageDraw.Draw(imagem), margem + dx, margem + subida, palavra, fonte, preenchimento, espacamento)
            sprite = aparar(Sprite(imagem, math.floor(cursor) - margem, round(base - subida) - margem))
            if el.get("sombra"):
                sprite = com_sombra(sprite, float(el["sombra"]), max(2, tam // 14))
            sprites.append(sprite)
            cursor += largura + vao
    return sprites


def sprite_caixa(el: dict, largura_tela: int, fontes: Fontes) -> Sprite:
    """Caixa de cantos arredondados (POV R2: Creme, raio 12), com o texto dentro quando houver."""
    texto = None
    if el.get("texto") or el.get("linhas"):
        estilo = {k: v for k, v in el.items() if k not in ("x", "y", "cor", "sombra")}
        texto = juntar(sprites_de_palavras({**estilo, "x": 0, "y": 0, "cor": el.get("cor_texto", "verde")},
                                           largura_tela, fontes))
    margem_h, margem_v = el.get("margem", (36, 22))
    largura = int(el.get("largura") or (texto.largura + 2 * margem_h if texto else 200))
    altura = int(el.get("altura") or (texto.altura + 2 * margem_v if texto else 80))
    imagem = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ImageDraw.Draw(imagem).rounded_rectangle((0, 0, largura - 1, altura - 1), radius=int(el.get("raio", 12)),
                                             fill=cor(el.get("cor", "creme"), el.get("opacidade", 1.0)))
    if texto:
        imagem.alpha_composite(texto.imagem, ((largura - texto.largura) // 2, (altura - texto.altura) // 2))
    return Sprite(imagem, _x_do_elemento(el, largura, largura_tela), int(el.get("y", 0)))


def _x_do_elemento(el: dict, largura: int, largura_tela: int) -> int:
    """x = centro do elemento ("centro" = meio da tela); com "alinhamento" esquerda/direita, x é essa borda."""
    x = el.get("x", "centro")
    ancora = largura_tela / 2 if x == "centro" else float(x)
    alinhamento = el.get("alinhamento", "centro")
    return round(ancora - largura / 2 if alinhamento == "centro" else ancora - largura if alinhamento == "direita"
                 else ancora)


def sprite_filete(el: dict, largura_tela: int) -> Sprite:
    vertical = bool(el.get("vertical"))
    comprimento, espessura = int(el.get("largura", 120)), int(el.get("espessura", 2))
    tamanho = (espessura, comprimento) if vertical else (comprimento, espessura)
    imagem = Image.new("RGBA", tamanho, cor(el.get("cor", "caramelo"), el.get("opacidade", 1.0)))
    return Sprite(imagem, _x_do_elemento(el, tamanho[0], largura_tela), int(el.get("y", 0)))


def sprite_degrade(el: dict, largura_tela: int, altura_tela: int) -> Sprite:
    """Degradê vertical (Verde leve na faixa de baixo) ou véu uniforme ("opacidade" número = escurecimento)."""
    y0, y1 = int(el.get("y0", 0)), int(el.get("y1", altura_tela))
    altura = max(1, y1 - y0)
    opacidade = el.get("opacidade", (0.0, 0.85))
    topo, base = (opacidade, opacidade) if isinstance(opacidade, (int, float)) else opacidade
    r, g, b, _ = cor(el.get("cor", "verde"))
    rampa = Image.linear_gradient("L").resize((1, altura), Image.BILINEAR)
    curva = el.get("curva_degrade", 1.6)  # >1: o degradê só pesa perto da base (a foto é a protagonista)
    alfa = rampa.point([round(255 * (topo + (base - topo) * (v / 255) ** curva)) for v in range(256)])
    imagem = Image.new("RGBA", (1, altura), (r, g, b, 0))
    imagem.putalpha(alfa)
    return Sprite(imagem.resize((largura_tela, altura), Image.NEAREST), 0, y0)


def sprite_imagem(el: dict, arquivo: Path, largura_tela: int) -> Sprite:
    """Logo ou imagem PNG, redimensionada por "altura" ou "largura" (logo do fechamento: ~135 px de altura)."""
    with Image.open(arquivo) as aberta:
        imagem = aberta.convert("RGBA")
    if el.get("altura"):
        imagem = imagem.resize((max(1, round(imagem.width * el["altura"] / imagem.height)), int(el["altura"])),
                               Image.LANCZOS)
        if el.get("recorte"):  # só uma faixa do logo (símbolo ou nome, na vinheta), medida em fração da largura
            esquerda, direita = el["recorte"]
            imagem = imagem.crop((round(imagem.width * esquerda), 0, round(imagem.width * direita), imagem.height))
    elif el.get("largura"):
        imagem = imagem.resize((int(el["largura"]), max(1, round(imagem.height * el["largura"] / imagem.width))),
                               Image.LANCZOS)
    imagem = com_opacidade(imagem, float(el.get("opacidade", 1.0)))
    if el.get("recorte"):  # x é a borda esquerda da faixa (posição dela dentro do logo inteiro)
        return aparar(Sprite(imagem, round(float(el.get("x", 0))), int(el.get("y", 0))))
    return aparar(Sprite(imagem, _x_do_elemento(el, imagem.width, largura_tela), int(el.get("y", 0))))


def numero_br(valor: float, casas: int = 0) -> str:
    """1234 -> "1.234" (milhar com ponto, como no Brasil)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


# ---------------------------------------------------------------- fontes e logos da peça

def pastas_de_recursos(base: Path) -> list[Path]:
    """Onde procurar fontes e logos: a pasta da peça (_referencias/ copiado do CÉREBRO) e, no PC, o CÉREBRO."""
    marcas = pasta_marcas()
    return ([base / "_referencias" / "FONTES", base / "_referencias" / "CASA_VERANEIO", base / "FONTES", base]
            + [marcas / "FONTES", marcas / "CASA_VERANEIO"])


def pasta_marcas() -> Path:
    """CÉREBRO/MARCAS no Drive (mesmo caminho de comum.CEREBRO; só leitura)."""
    drive = Path(os.getenv("ESCRITORIO_DRIVE", r"G:\Drives compartilhados\(NOVO) CASA VERANEIO\ESCRITÓRIO VERANEIO"))
    return drive / "CÉREBRO" / "MARCAS"


def _dentro(base: Path, relativo: str, campo: str) -> Path:
    caminho = (base / relativo).resolve()
    if not caminho.is_relative_to(base.resolve()):
        raise ValueError(f"{campo} fora da pasta do motion.json: {relativo}")
    return caminho


def _arquivo_imagem(el: dict, base: Path, pastas: list[Path]) -> Path:
    if el.get("arquivo"):
        caminho = _dentro(base, el["arquivo"], "imagem")
        if caminho.is_file():
            return caminho
        nome = Path(el["arquivo"]).name
    else:
        nome = LOGOS[el["logo"]]
    achado = next((p / nome for p in pastas if (p / nome).is_file()), None)
    if not achado:
        raise ValueError(f"Imagem não encontrada: {el.get('arquivo') or nome}")
    return achado
