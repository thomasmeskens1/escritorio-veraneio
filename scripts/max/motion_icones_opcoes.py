"""Ícones das opções B, C e D da vinheta (motion_opcoes*.py; Thomas, 04/11/2026), na mesma linguagem de
motion_icones.py: formas chapadas ou traço fino de espessura constante, só as cores da marca, coordenadas em fração
do quadrado. Registrados no DESENHOS de motion_icones (importado lá no fim, sem ciclo de importação).

Os de "traço" (planta baixa, fachada) desenham só a fração `progresso` do comprimento total, na ordem dos traços:
o desenho se faz como uma caneta. Use `passos` maior (params={"passos": 72}) para não andar aos saltos.
"""

import math

from PIL import Image, ImageChops, ImageDraw

from motion_camadas import CORES

VERDE, CARAMELO, CREME, BRANCO = CORES["verde"], CORES["caramelo"], CORES["creme"], CORES["branco"]
CARAMELO_SOMBRA = tuple(round(c * 0.62 + v * 0.38) for c, v in zip(CARAMELO, VERDE))
LUZ_QUENTE = (247, 206, 132)


def _tracos(p, polilinhas, progresso: float, cor, espessura: float) -> None:
    """Desenha as polilinhas em ordem até a fração `progresso` do comprimento somado (caneta que anda)."""
    comprimentos = [sum(math.dist(a, b) for a, b in zip(linha, linha[1:])) for linha in polilinhas]
    resta = max(0.0, min(1.0, progresso)) * sum(comprimentos)
    for linha, total in zip(polilinhas, comprimentos):
        if resta <= 1e-6:
            return
        if resta >= total:
            p.linha(linha, cor, espessura)
            resta -= total
            continue
        pontos = [linha[0]]
        for a, b in zip(linha, linha[1:]):
            trecho = math.dist(a, b)
            if resta >= trecho:
                pontos.append(b)
                resta -= trecho
                continue
            f = resta / trecho
            pontos.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            break
        p.linha(pontos, cor, espessura)
        return


def _retangulo(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


# ---------------------------------------------------------------- formas simples

def _disco(p, cor=CREME):
    p.disco(0.5, 0.5, 0.48, cor)


def _aro(p, cor=CREME, traco=22):
    """Anel de traço fino (onda na água, contorno do sol): achatado pela camada vira elipse em perspectiva.
    `traco` em milésimos do lado (inteiro: não entra nos degraus do cache), para o traço não engrossar ao crescer."""
    espessura = traco / 1000
    p.arco(0.5, 0.5, 0.5 - espessura / 2 - 0.004, 0, 360, cor, espessura, pontas=False)


def _losango(p, cor=CARAMELO):
    p.poligono([(0.5, 0.02), (0.98, 0.5), (0.5, 0.98), (0.02, 0.5)], cor)


# ---------------------------------------------------------------- Casa Veraneio

def _linha_mola(p, de=0.0, ate=1.0, afunda=0.0, onde=0.5):
    """Linha do horizonte (y = 0,5) de `de` a `ate` que cede sob a ponta do pino em `onde` (cama elástica):
    `afunda` 1 = 10% do lado para baixo, numa curva suave."""
    if ate - de <= 0.002:
        return
    pontos = []
    for k in range(97):
        x = de + (ate - de) * k / 96
        pontos.append((x, 0.5 + 0.10 * afunda * math.exp(-((x - onde) / 0.075) ** 2)))
    p.linha(pontos, CREME, 0.007)


def _gota_agua(p):
    """Gota d'água em pé (ponta para cima): Creme com um reflexo Branco."""
    from motion_icones import gota
    contorno = [(x, 1 - y) for x, y in gota(0.5, 1 - 0.64, 0.25, 1 - 0.08)]
    p.poligono(contorno, CREME)
    p.arco(0.5, 0.64, 0.15, 200, 260, BRANCO, 0.04)


def _pinheiro(p, cor=CARAMELO):
    p.caixa(0.46, 0.80, 0.54, 0.96, CARAMELO_SOMBRA, raio=0.01)
    for topo, base, meia in ((0.06, 0.40, 0.20), (0.24, 0.62, 0.28), (0.44, 0.84, 0.36)):
        p.poligono([(0.5, topo), (0.5 + meia, base), (0.5 - meia, base)], cor)


def _marcador(p):
    """Ponto de destino do mapa: miolo Caramelo e aro Creme."""
    p.arco(0.5, 0.5, 0.36, 0, 360, CREME, 0.08, pontas=False)
    p.disco(0.5, 0.5, 0.2, CARAMELO)


# ---------------------------------------------------------------- Casa Veraneio CORP. (ingresso)

# O ingresso deitado ocupa y 0,32 a 0,68; o picote fica em x = 0,30 (canhoto à esquerda, corpo à direita).
_PICOTE, _TOPO, _BASE = 0.30, 0.32, 0.68


def _furos_do_picote(p):
    p.furo(_PICOTE, _TOPO, 0.035)
    p.furo(_PICOTE, _BASE, 0.035)
    for k in range(7):
        p.furo(_PICOTE, _TOPO + 0.07 + k * 0.037, 0.0055)


def _ingresso(p):
    """Corpo do ingresso: Creme com filete Caramelo, losango e duas linhas de texto (só o desenho)."""
    p.caixa(_PICOTE, _TOPO, 0.95, _BASE, CREME, raio=0.025)
    p.caixa(_PICOTE, _TOPO, 0.40, _BASE, CREME)  # canto reto junto do picote
    p.caixa(_PICOTE + 0.035, _TOPO + 0.03, 0.92, _BASE - 0.03, None, raio=0.015, contorno=CARAMELO, espessura=0.008)
    p.poligono([(0.48, 0.5), (0.52, 0.45), (0.56, 0.5), (0.52, 0.55)], CARAMELO)
    p.linha([(0.62, 0.465), (0.86, 0.465)], CARAMELO, 0.022)
    p.linha([(0.62, 0.535), (0.79, 0.535)], CARAMELO_SOMBRA, 0.012)
    _furos_do_picote(p)


def _canhoto(p):
    """Canhoto destacável: Creme com barras Caramelo (código do convite)."""
    p.caixa(0.05, _TOPO, _PICOTE, _BASE, CREME, raio=0.025)
    p.caixa(0.20, _TOPO, _PICOTE, _BASE, CREME)
    for k, largura in enumerate((0.012, 0.006, 0.016, 0.006, 0.01, 0.006, 0.014)):
        x = 0.10 + k * 0.022
        p.caixa(x, 0.40, x + largura, 0.60, CARAMELO)
    _furos_do_picote(p)


# ---------------------------------------------------------------- Casa Vero (traço arquitetônico, porta)

_PAREDES = [
    [(0.42, 0.80), (0.14, 0.80), (0.14, 0.20), (0.86, 0.20), (0.86, 0.80), (0.56, 0.80)],
    [(0.60, 0.20), (0.60, 0.38)], [(0.60, 0.48), (0.60, 0.56), (0.86, 0.56)],
    [(0.14, 0.50), (0.30, 0.50)], [(0.40, 0.50), (0.46, 0.50)],
]
_DETALHES = [
    [(0.24, 0.20), (0.40, 0.20)], [(0.24, 0.215), (0.40, 0.215)],          # janela
    [(0.86, 0.30), (0.86, 0.44)], [(0.845, 0.30), (0.845, 0.44)],          # janela
    [(0.14, 0.12), (0.86, 0.12)], [(0.14, 0.10), (0.14, 0.14)], [(0.86, 0.10), (0.86, 0.14)],  # cota
]


def _planta(p, progresso=1.0):
    """Planta baixa em traço fino: paredes Verdes, portas em arco, janelas e cota Caramelo."""
    paredes = min(1.0, progresso / 0.7)
    _tracos(p, _PAREDES, paredes, VERDE, 0.016)
    resto = max(0.0, (progresso - 0.55) / 0.45)
    if resto > 0:
        for cx, cy, r, ini in ((0.42, 0.80, 0.14, 270), (0.60, 0.38, 0.10, 90), (0.30, 0.50, 0.10, 0)):
            p.arco(cx, cy, r, ini, ini + 90 * min(1.0, resto * 1.6), CARAMELO, 0.006, pontas=False)
        _tracos(p, _DETALHES, resto, CARAMELO, 0.006)


_FACHADA = [
    [(0.10, 0.86), (0.90, 0.86)],
    [(0.24, 0.86), (0.24, 0.50), (0.50, 0.24), (0.76, 0.50), (0.76, 0.86)],
    [(0.64, 0.38), (0.64, 0.27), (0.70, 0.27), (0.70, 0.44)],
    [(0.45, 0.86), (0.45, 0.70), (0.55, 0.70), (0.55, 0.86)],
    _retangulo(0.31, 0.58, 0.40, 0.66), _retangulo(0.60, 0.58, 0.69, 0.66),
]


def _fachada(p, progresso=1.0):
    """Fachada em traço (elevação): chão, paredes e telhado, chaminé, porta e janelas; beiral Caramelo."""
    _tracos(p, _FACHADA, progresso, VERDE, 0.016)
    beiral = max(0.0, (progresso - 0.3) / 0.4)
    if beiral > 0:
        _tracos(p, [[(0.17, 0.555), (0.50, 0.19), (0.83, 0.555)]], beiral, CARAMELO, 0.008)


# A porta ocupa o vão x 0,30 a 0,70 e y 0,12 a 0,88 do quadrado; a dobradiça fica na esquerda (x = 0,30).
_VAO = (0.30, 0.12, 0.70, 0.88)


def _batente(p, luz=0.0):
    """Vão da porta (Verde escuro que acende em luz quente) com batente Caramelo e soleira."""
    x0, y0, x1, y1 = _VAO
    dentro = tuple(round(a + (b - a) * min(1.0, luz)) for a, b in zip(VERDE, LUZ_QUENTE))
    p.caixa(x0, y0, x1, y1, dentro)
    p.linha([(x0 - 0.025, y1), (x0 - 0.025, y0 - 0.025), (x1 + 0.025, y0 - 0.025), (x1 + 0.025, y1)], CARAMELO,
            0.03)
    p.linha([(x0 - 0.09, y1 + 0.012), (x1 + 0.09, y1 + 0.012)], VERDE, 0.01)


def _porta(p):
    """Folha da porta: Verde com almofadas em filete Caramelo e a maçaneta."""
    x0, y0, x1, y1 = _VAO
    p.caixa(x0, y0, x1, y1, VERDE)
    for a, b in ((0.18, 0.46), (0.54, 0.82)):
        p.caixa(x0 + 0.06, a, x1 - 0.06, b, None, raio=0.01, contorno=CARAMELO, espessura=0.007)
    p.disco(x1 - 0.045, 0.50, 0.018, CARAMELO)


def _luz_chao(p):
    """Luz que sai pela porta aberta e se espalha no chão (Branco que some na ponta)."""
    cone = Image.new("L", (p.lado, p.lado), 0)
    ImageDraw.Draw(cone).polygon([(0.30 * p.lado, 0), (0.70 * p.lado, 0), (1.0 * p.lado, p.lado),
                                  (0.0, p.lado)], fill=255)
    rampa = Image.linear_gradient("L").resize((p.lado, p.lado)).point([round(170 * (1 - v / 255) ** 1.6)
                                                                       for v in range(256)])
    p.imagem = Image.new("RGBA", (p.lado, p.lado), BRANCO + (0,))
    p.imagem.putalpha(ImageChops.multiply(cone, rampa))


DESENHOS_OPCOES = {"disco": _disco, "aro": _aro, "losango": _losango, "linha_mola": _linha_mola,
                   "gota_agua": _gota_agua, "pinheiro": _pinheiro, "marcador": _marcador, "ingresso": _ingresso,
                   "canhoto": _canhoto, "planta": _planta, "fachada": _fachada, "batente": _batente,
                   "porta": _porta, "luz_chao": _luz_chao}
