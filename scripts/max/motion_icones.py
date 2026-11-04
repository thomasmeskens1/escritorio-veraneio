"""Ícones chapados da vinheta (motion_vinheta.py; Thomas, 04/11/2026): desenho vetorial em Pillow, cada um num
quadrado de lado `tamanho`, feito em 3x e reduzido com LANCZOS (borda lisa, sem serrilhado).

Linguagem da referência profissional da Casa Vero (VINHETA_4K): formas planas, poucas cores da marca (Verde,
Caramelo, Creme e Branco), traço de espessura constante e cantos arredondados. Coordenadas em fração do quadrado
(0 a 1, y para baixo). Parâmetros animados (progresso do aro, fase da onda...) entram arredondados em `passos`
para o cache servir a animação inteira com poucos desenhos.
"""

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from motion_camadas import CORES

SUPER = 3  # superamostragem do desenho
VERDE, CARAMELO, CREME, BRANCO = CORES["verde"], CORES["caramelo"], CORES["creme"], CORES["branco"]
# Caramelo escurecido no Verde (montanha de trás, sombra): mistura das duas cores da marca, não cor nova.
CARAMELO_SOMBRA = tuple(round(c * 0.62 + v * 0.38) for c, v in zip(CARAMELO, VERDE))
LUZ_QUENTE = (247, 206, 132)  # janela acesa: Caramelo clareado com Branco


def _mistura(a, b, p: float):
    return tuple(round(x + (y - x) * max(0.0, min(1.0, p))) for x, y in zip(a, b))


class _Pincel:
    """ImageDraw em coordenadas de fração do quadrado (tudo vezes o lado da tela superamostrada)."""

    def __init__(self, lado: int):
        self.lado = lado
        self.imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.imagem)

    def p(self, *xy):
        return [v * self.lado for v in xy]

    def w(self, espessura: float) -> int:
        return max(1, round(espessura * self.lado))

    def disco(self, cx, cy, r, cor):
        if r <= 0:
            return  # o Pillow desenharia um ponto
        self.d.ellipse(self.p(cx - r, cy - r, cx + r, cy + r), fill=cor)

    def furo(self, cx, cy, r):
        """Fura o desenho (transparente), como o miolo da lupa ou o olho da chave."""
        self.d.ellipse(self.p(cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 0))

    def arco(self, cx, cy, r, inicio, fim, cor, espessura, pontas=True):
        """Arco de traço constante com pontas redondas (ângulos em graus, horário a partir das 3 h)."""
        if fim - inicio <= 0.1:
            return
        meio = espessura / 2
        self.d.arc(self.p(cx - r - meio, cy - r - meio, cx + r + meio, cy + r + meio), inicio, fim, fill=cor,
                   width=self.w(espessura))
        if pontas:
            for ang in (inicio, fim):
                a = math.radians(ang)
                self.disco(cx + r * math.cos(a), cy + r * math.sin(a), meio, cor)

    def linha(self, pontos, cor, espessura):
        self.d.line([v * self.lado for xy in pontos for v in xy], fill=cor, width=self.w(espessura), joint="curve")
        for x, y in (pontos[0], pontos[-1]):
            self.disco(x, y, espessura / 2, cor)

    def poligono(self, pontos, cor):
        self.d.polygon([(x * self.lado, y * self.lado) for x, y in pontos], fill=cor)

    def caixa(self, x0, y0, x1, y1, cor, raio=0.0, contorno=None, espessura=0.0):
        self.d.rounded_rectangle(self.p(x0, y0, x1, y1), radius=raio * self.lado, fill=cor,
                                 outline=contorno, width=self.w(espessura) if contorno else 0)

    def pronto(self, tamanho: int) -> Image.Image:
        return self.imagem.resize((tamanho, tamanho), Image.LANCZOS)


def gota(cx: float, cy: float, r: float, ponta_y: float, n: int = 72) -> list[tuple[float, float]]:
    """Contorno do pino de localização: círculo (cx, cy, r) e ponta em (cx, ponta_y), lados tangentes ao círculo."""
    d = ponta_y - cy
    abertura = math.degrees(math.acos(min(1.0, r / d)))
    inicio, fim = 90 + abertura, 90 - abertura + 360  # tangentes, passando por cima do círculo
    pontos = [(cx, ponta_y)]
    for k in range(n + 1):
        a = math.radians(inicio + (fim - inicio) * k / n)
        pontos.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pontos


def _casinha(p: _Pincel, cx, cy, s, cor, porta=None):
    """Casinha simples (telhado com beiral e corpo), usada dentro da lupa: s = largura."""
    p.poligono([(cx - s * 0.62, cy - s * 0.02), (cx, cy - s * 0.58), (cx + s * 0.62, cy - s * 0.02)], cor)
    p.caixa(cx - s * 0.42, cy - s * 0.12, cx + s * 0.42, cy + s * 0.48, cor, raio=s * 0.04)
    if porta:
        p.caixa(cx - s * 0.11, cy + s * 0.14, cx + s * 0.11, cy + s * 0.48, porta, raio=s * 0.03)


# ---------------------------------------------------------------- Casa Vero (Verde e Caramelo no Creme)

def _lupa(p: _Pincel, aro=1.0, casa=1.0):
    cx = cy = 0.42
    if casa > 0:
        p.disco(cx, cy, 0.215 * casa, CARAMELO)
        _casinha(p, cx, cy + 0.02, 0.24 * casa, BRANCO, porta=CARAMELO)
    p.arco(cx, cy, 0.255, 45, 45 + 360 * aro, VERDE, 0.095, pontas=aro < 0.999)
    cabo = max(0.0, min(1.0, aro * 1.6 - 0.6))  # o cabo cresce depois que o aro passa da metade
    if cabo > 0:
        a0, a1 = 0.42 + 0.30 * 0.7071, 0.42 + (0.30 + 0.28 * cabo) * 0.7071
        p.linha([(a0, a0), (a1, a1)], VERDE, 0.10)


def _pino_vero(p: _Pincel):
    p.poligono(gota(0.5, 0.40, 0.27, 0.92), VERDE)
    p.disco(0.5, 0.40, 0.112, BRANCO)
    p.arco(0.5, 0.40, 0.19, 235, 320, CARAMELO, 0.026)


def _chave(p: _Pincel, argola=True):
    """Chave em pé (o giro vem da camada): cabeça redonda com olho, haste com dentes e argola Caramelo."""
    p.disco(0.5, 0.31, 0.19, VERDE)
    p.caixa(0.455, 0.44, 0.545, 0.93, VERDE, raio=0.02)
    p.caixa(0.42, 0.47, 0.58, 0.52, VERDE, raio=0.015)
    for y0, y1, x1 in ((0.70, 0.75, 0.63), (0.79, 0.85, 0.66)):
        p.caixa(0.5, y0, x1, y1, VERDE, raio=0.012)
    p.furo(0.5, 0.24, 0.055)
    p.arco(0.5, 0.31, 0.12, 200, 300, BRANCO, 0.022)  # brilho da cabeça (o "redemoinho" da referência)
    if argola:
        p.arco(0.5, 0.165, 0.085, 0, 360, CARAMELO, 0.02, pontas=False)  # passa pelo olho da chave


def _casa_vero(p: _Pincel, janelas=1.0, luz=0.0):
    p.caixa(0.66, 0.16, 0.75, 0.38, VERDE, raio=0.01)  # chaminé
    p.poligono([(0.14, 0.50), (0.5, 0.15), (0.86, 0.50)], VERDE)
    p.caixa(0.22, 0.44, 0.78, 0.875, VERDE)
    p.linha([(0.09, 0.515), (0.5, 0.105), (0.91, 0.515)], CARAMELO, 0.034)
    p.linha([(0.16, 0.885), (0.84, 0.885)], CARAMELO, 0.026)
    if janelas > 0:
        cor = _mistura(BRANCO, LUZ_QUENTE, luz) + (round(255 * janelas),)
        for x0 in (0.315, 0.545):
            for y0 in (0.50, 0.64):
                p.caixa(x0, y0, x0 + 0.14, y0 + 0.11, cor, raio=0.018)
        p.caixa(0.45, 0.77, 0.55, 0.875, None, raio=0.012, contorno=CARAMELO, espessura=0.016)


# ---------------------------------------------------------------- Casa Veraneio (Caramelo e Creme no Verde)

def _sol(p: _Pincel):
    p.disco(0.5, 0.5, 0.21, CARAMELO)
    for k in range(12):
        a = math.radians(k * 30)
        p.linha([(0.5 + 0.29 * math.cos(a), 0.5 + 0.29 * math.sin(a)),
                 (0.5 + 0.38 * math.cos(a), 0.5 + 0.38 * math.sin(a))], CREME, 0.02)


def _montanhas(p: _Pincel):
    p.poligono([(0.02, 0.86), (0.34, 0.40), (0.50, 0.58), (0.60, 0.86)], CARAMELO_SOMBRA)
    p.poligono([(0.26, 0.86), (0.62, 0.28), (0.98, 0.86)], CARAMELO)
    p.poligono([(0.62, 0.28), (0.705, 0.415), (0.655, 0.395), (0.62, 0.43), (0.585, 0.39), (0.535, 0.42)], CREME)
    p.poligono([(0.34, 0.40), (0.405, 0.495), (0.365, 0.48), (0.335, 0.51), (0.30, 0.46)], CREME)


def _chale(p: _Pincel):
    """Chalé em A (hospedagem de natureza): telhado Caramelo, fachada de vidro Creme com caixilhos."""
    p.poligono([(0.12, 0.86), (0.5, 0.12), (0.88, 0.86)], CARAMELO)
    p.poligono([(0.29, 0.86), (0.5, 0.44), (0.71, 0.86)], CREME)
    p.linha([(0.5, 0.47), (0.5, 0.86)], CARAMELO, 0.022)
    p.linha([(0.37, 0.69), (0.63, 0.69)], CARAMELO, 0.022)


def _mar(p: _Pincel):
    """Mar (Casa Veraneio na praia): linhas de onda de traço constante, mais largas perto e mais curtas no fundo
    (perspectiva), alternando Caramelo e Creme (no lugar das montanhas)."""
    for y, largura, ondas, cor in ((0.82, 0.92, 3.5, CARAMELO), (0.73, 0.76, 3.0, CREME), (0.64, 0.60, 2.5, CARAMELO),
                                   (0.555, 0.42, 2.0, CREME)):
        x0 = 0.5 - largura / 2
        p.linha([(x0 + largura * k / 60, y - 0.022 * math.sin(2 * math.pi * ondas * k / 60)) for k in range(61)],
                cor, 0.034)


def _folha(p: _Pincel, x0, y0, angulo, comprimento, cair, cor, largura=0.065):
    """Folha de coqueiro: sai do topo do tronco em `angulo` (graus, 0 = direita) e cai na ponta (`cair`)."""
    a = math.radians(angulo)
    lado_a, lado_b = [], []
    for k in range(21):
        f = k / 20
        x = x0 + comprimento * f * math.cos(a)
        y = y0 - comprimento * f * math.sin(a) + cair * f * f
        meia = largura * math.sin(math.pi * min(1.0, f * 1.15)) / 2
        lado_a.append((x, y - meia))
        lado_b.append((x, y + meia))
    p.poligono(lado_a + lado_b[::-1], cor)


def _casa_praia(p: _Pincel):
    """Casa de praia de alto padrão: dois volumes de vidro Creme com lajes Caramelo, o de cima em balanço, e um
    coqueiro ao lado (sombra Caramelo, atrás)."""
    tronco = [(0.13 + 0.05 * (k / 12) ** 1.6, 0.86 - 0.52 * k / 12) for k in range(13)]
    p.linha(tronco, CARAMELO_SOMBRA, 0.026)
    topo = tronco[-1]
    for angulo, comprimento, cair in ((160, 0.17, 0.08), (125, 0.13, 0.04), (90, 0.08, 0.02), (55, 0.15, 0.05),
                                     (20, 0.19, 0.09), (-10, 0.14, 0.09)):
        _folha(p, *topo, angulo, comprimento, cair, CARAMELO_SOMBRA)
    p.caixa(0.24, 0.64, 0.80, 0.86, CREME)                       # térreo de vidro
    p.caixa(0.36, 0.44, 0.94, 0.61, CREME)                       # andar de cima, em balanço
    for x in (0.38, 0.52, 0.66):
        p.caixa(x - 0.008, 0.64, x + 0.008, 0.86, CARAMELO)
    for x in (0.52, 0.66, 0.80):
        p.caixa(x - 0.008, 0.44, x + 0.008, 0.61, CARAMELO)
    p.caixa(0.20, 0.60, 0.84, 0.645, CARAMELO)                   # laje entre os andares
    p.caixa(0.32, 0.395, 0.98, 0.44, CARAMELO)                   # cobertura plana
    p.caixa(0.20, 0.845, 0.86, 0.86, CARAMELO)                   # deque


def _piscina(p: _Pincel, fase=0.0):
    p.caixa(0.08, 0.30, 0.92, 0.70, None, raio=0.2, contorno=CREME, espessura=0.03)
    for n, y in enumerate((0.45, 0.56)):
        pontos = []
        for k in range(41):
            x = 0.22 + 0.56 * k / 40
            pontos.append((x, y + 0.028 * math.sin(2 * math.pi * (k / 40 * 1.6 + fase + n * 0.35))))
        p.linha(pontos, CARAMELO, 0.026)


def _mala(p: _Pincel):
    p.caixa(0.37, 0.15, 0.63, 0.34, None, raio=0.05, contorno=CREME, espessura=0.04)
    p.caixa(0.16, 0.30, 0.84, 0.86, CARAMELO, raio=0.08)
    for x in (0.36, 0.64):
        p.caixa(x - 0.022, 0.30, x + 0.022, 0.86, CREME)
    for x in (0.28, 0.72):
        p.disco(x, 0.90, 0.035, CREME)


# ---------------------------------------------------------------- Casa Veraneio CORP. (eventos)

def _calendario(p: _Pincel, grade=1.0, marca=1.0):
    p.caixa(0.12, 0.18, 0.88, 0.88, CREME, raio=0.07)
    p.caixa(0.12, 0.18, 0.88, 0.38, CARAMELO, raio=0.07)
    p.caixa(0.12, 0.31, 0.88, 0.38, CARAMELO)
    for x in (0.33, 0.67):
        p.caixa(x - 0.028, 0.10, x + 0.028, 0.26, VERDE, raio=0.028)
    total = 20
    for i in range(total):
        linha, coluna = divmod(i, 5)
        aparece = max(0.0, min(1.0, grade * (total + 4) / 5 - i / 5))  # cascata das casas do mês
        if aparece <= 0:
            continue
        x, y = 0.24 + coluna * 0.13, 0.49 + linha * 0.105
        escolhido = (linha, coluna) == (2, 3)
        p.disco(x, y, 0.03 * aparece, CARAMELO if escolhido and marca > 0 else VERDE)
    if marca > 0:
        p.arco(0.24 + 3 * 0.13, 0.49 + 2 * 0.105, 0.062, -90, -90 + 360 * marca, CARAMELO, 0.018,
               pontas=marca < 0.999)


def _holofote(p: _Pincel):
    """Refletor de palco apontando para baixo (o feixe sai de (0.5, 0.36))."""
    p.arco(0.5, 0.22, 0.17, 180, 360, CARAMELO, 0.03)
    p.caixa(0.38, 0.12, 0.62, 0.33, CARAMELO, raio=0.04)
    p.caixa(0.35, 0.31, 0.65, 0.37, CREME, raio=0.02)


def _feixe(p: _Pincel):
    """Cone de luz Creme que some na ponta (desenhado do topo, no meio, até a base)."""
    cone = Image.new("L", (p.lado, p.lado), 0)
    ImageDraw.Draw(cone).polygon([(0.47 * p.lado, 0), (0.53 * p.lado, 0), (0.86 * p.lado, p.lado),
                                  (0.14 * p.lado, p.lado)], fill=255)
    rampa = Image.linear_gradient("L").resize((p.lado, p.lado)).point([round(150 * (1 - v / 255) ** 1.3)
                                                                       for v in range(256)])
    p.imagem = Image.new("RGBA", (p.lado, p.lado), CREME + (0,))
    p.imagem.putalpha(ImageChops.multiply(cone, rampa))


def _palco(p: _Pincel):
    p.caixa(0.10, 0.78, 0.90, 0.86, CARAMELO, raio=0.02)
    p.linha([(0.04, 0.905), (0.96, 0.905)], CREME, 0.014)


def _taca(p: _Pincel, liquido=1.0):
    """Taça de espumante: bojo alto em Creme, espumante Caramelo, haste e pé."""
    bojo = [(0.385, 0.08), (0.40, 0.40), (0.43, 0.48), (0.5, 0.52), (0.57, 0.48), (0.60, 0.40), (0.615, 0.08)]
    nivel = 0.46 - 0.26 * liquido
    dentro = [(x, y) for x, y in bojo[1:-1]]
    p.poligono([(0.395, nivel), *[(x, y) for x, y in dentro if y > nivel], (0.605, nivel)], CARAMELO)
    p.linha(bojo, CREME, 0.026)
    p.linha([(0.5, 0.52), (0.5, 0.84)], CREME, 0.026)
    p.linha([(0.38, 0.86), (0.62, 0.86)], CREME, 0.03)
    for x, y in ((0.47, 0.40), (0.53, 0.33), (0.49, 0.27)):
        if y > nivel + 0.02:
            p.disco(x, y, 0.011, CREME)


# ---------------------------------------------------------------- partículas

def _brilho(p: _Pincel, cor=BRANCO):
    """Estrela de quatro pontas de lados côncavos (faísca da referência): curvas de Bézier entre as pontas."""
    pontas = [(1.0, 0.5), (0.5, 1.0), (0.0, 0.5), (0.5, 0.0)]
    pontos = []
    for (x0, y0), (x1, y1) in zip(pontas, pontas[1:] + pontas[:1]):
        cx, cy = 0.5 + ((x0 + x1) / 2 - 0.5) * 0.12, 0.5 + ((y0 + y1) / 2 - 0.5) * 0.12  # controle perto do meio
        for k in range(24):
            u = k / 24
            pontos.append(((1 - u) ** 2 * x0 + 2 * u * (1 - u) * cx + u * u * x1,
                           (1 - u) ** 2 * y0 + 2 * u * (1 - u) * cy + u * u * y1))
    p.poligono(pontos, cor)


def _faisca(p: _Pincel, cor=BRANCO):
    """Risco de luz (cápsula deitada) que voa para fora no estouro de partículas."""
    p.caixa(0.04, 0.43, 0.96, 0.57, cor, raio=0.07)


DESENHOS = {"lupa": _lupa, "pino_vero": _pino_vero, "chave": _chave, "casa_vero": _casa_vero, "sol": _sol,
            "montanhas": _montanhas, "chale": _chale, "mar": _mar, "casa_praia": _casa_praia, "piscina": _piscina, "mala": _mala,
            "calendario": _calendario, "holofote": _holofote, "feixe": _feixe, "palco": _palco, "taca": _taca,
            "brilho": _brilho, "faisca": _faisca}
# Opções B, C e D da vinheta (Thomas, 04/11/2026): ícones extras em arquivo próprio (limite de 500 linhas).
from motion_icones_opcoes import DESENHOS_OPCOES  # noqa: E402
DESENHOS.update(DESENHOS_OPCOES)


@lru_cache(maxsize=512)
def _icone(nome: str, tamanho: int, parametros: tuple) -> Image.Image:
    pincel = _Pincel(tamanho * SUPER)
    DESENHOS[nome](pincel, **dict(parametros))
    return pincel.pronto(tamanho)


def icone(nome: str, tamanho: int, passos: int = 24, **parametros) -> Image.Image:
    """Ícone RGBA de `tamanho` x `tamanho`. Parâmetros numéricos de 0 a 1 vão em `passos` degraus (cache)."""
    if nome not in DESENHOS:
        raise ValueError(f"Ícone desconhecido: {nome!r}")
    if tamanho < 2:
        raise ValueError("Ícone pequeno demais.")
    chave = tuple(sorted((k, round(v * passos) / passos if isinstance(v, float) else v)
                         for k, v in parametros.items()))
    return _icone(nome, int(tamanho), chave)


def anel(raio: float, espessura: float, cor, opacidade: float = 1.0) -> Image.Image:
    """Anel fino (onda que se expande): traço constante, desenhado em 3x e reduzido."""
    lado = math.ceil(2 * raio + 2 * espessura + 4)
    grande = Image.new("L", (lado * SUPER, lado * SUPER), 0)
    centro, r = lado * SUPER / 2, raio * SUPER
    ImageDraw.Draw(grande).ellipse((centro - r, centro - r, centro + r, centro + r), outline=255,
                                   width=max(1, round(espessura * SUPER)))
    mascara = grande.resize((lado, lado), Image.LANCZOS)
    if opacidade < 0.999:
        mascara = mascara.point([round(v * max(0.0, opacidade)) for v in range(256)])
    imagem = Image.new("RGBA", (lado, lado), tuple(cor[:3]) + (0,))
    imagem.putalpha(mascara)
    return imagem
