"""Opções B, C e D da vinheta da Casa Veraneio CORP. (produtora de eventos; Thomas, 04/11/2026):

- B "Cortina": a cortina de palco fechada se abre e se recolhe nas laterais, um refletor acende no meio do palco e
  o pino nasce na luz; a cortina sai, o pino desliza e o nome entra saindo do desfoque.
- C "LED": um painel de pontos se acende em sequência, de cima para baixo, e os pontos acesos desenham o símbolo
  (amostrado do próprio logo); o painel encolhe até o tamanho e o lugar do logo, os pontos se fundem no símbolo e o
  nome aparece como varredura de tela.
- D "Ingresso": um convite entra girando, o canhoto é destacado no picote e cai; o convite vira de costas e o
  verso é o símbolo, que encolhe, desliza para o lugar e o nome sobe de trás de uma linha.
"""

import math
import random

from PIL import Image, ImageDraw

from motion_camadas import CORES, ease_in_cubic, ease_in_out_cubic, ease_out_back, ease_out_cubic, trecho
from motion_icones_opcoes import CARAMELO_SOMBRA
from motion_opcoes_comum import desliza, nomes, registrar, simbolo
from motion_roteiros import _c, faiscas, lampejo, onda

BRANCO, CREME, CARAMELO, VERDE = CORES["branco"], CORES["creme"], CORES["caramelo"], CORES["verde"]


def _mistura(a, b, f: float):
    return tuple(round(x + (y - x) * max(0.0, min(1.0, f))) for x, y in zip(a, b))


def _duracao(batidas: dict, parado: float = 1.3) -> float:
    return round(max(fim for _, fim in batidas.values()) + parado, 2)


# ---------------------------------------------------------------- B: cortina de palco

BATIDAS_B = {"antecipa": (0.15, 0.4), "abre": (0.4, 1.95), "palco": (1.05, 1.6), "luz": (1.2, 1.9),
             "surge": (1.95, 2.5), "anel": (1.98, 2.75), "rastro": (2.4, 2.95), "sai": (3.0, 3.6),
             "desliza": (3.45, 4.0), "nome1": (3.65, 4.15), "nome2": (3.75, 4.25), "nome3": (3.95, 4.4)}


def _veludo(largura: int, altura: int, periodo: float) -> Image.Image:
    """Pano de cortina: dobras verticais (Caramelo nas cristas, Caramelo escurecido no fundo das pregas) e sombra
    Verde no alto, sob a bambinela."""
    fundo = _mistura(CARAMELO_SOMBRA, VERDE, 0.2)
    sorteio, valores, x0 = random.Random(3), [], 0.0
    while len(valores) < largura:  # pregas de larguras diferentes, como um pano de verdade
        largura_prega = periodo * sorteio.uniform(0.7, 1.35)
        realce = sorteio.uniform(0.0, 0.18)
        while len(valores) < largura and len(valores) < x0 + largura_prega:
            f = (len(valores) - x0) / largura_prega
            luz = math.sin(math.pi * f) ** 0.8
            cor = _mistura(fundo, CARAMELO, luz)
            valores.append(_mistura(cor, CREME, realce * max(0.0, (luz - 0.85) / 0.15)))
        x0 += largura_prega
    linha = Image.new("RGB", (largura, 1))
    linha.putdata(valores)
    pano = linha.resize((largura, altura), Image.NEAREST).convert("RGBA")
    sombra = Image.linear_gradient("L").resize((largura, altura)).point(
        [round(150 * max(0.0, 1 - v / 255 / 0.22) ** 2) for v in range(256)])
    veu = Image.new("RGBA", (largura, altura), VERDE + (0,))
    veu.putalpha(sombra)
    return Image.alpha_composite(pano, veu)


def _bambinela(largura: int, altura: int, periodo: float) -> Image.Image:
    """Faixa de cima do palco com festões (meias-luas) e um filete Creme."""
    k = 2
    imagem = Image.new("RGBA", (largura * k, altura * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)
    corpo = round(altura * k * 0.62)
    d.rectangle((0, 0, largura * k, corpo), fill=CARAMELO + (255,))
    r = periodo * k / 2
    x = 0.0
    while x < largura * k + r:
        d.ellipse((x - r, corpo - r * 0.75, x + r, corpo + r * 0.75), fill=CARAMELO + (255,))
        x += periodo * k
    d.rectangle((0, corpo - round(4 * k), largura * k, corpo - round(1.5 * k)), fill=CREME + (255,))
    return imagem.resize((largura, altura), Image.LANCZOS)


def _preparar_cortina(p) -> None:
    u = p.u
    metade = math.ceil(p.largura / 2 + 6 * u)
    periodo = 128 * u
    pano = _veludo(metade, p.altura, periodo)
    registrar(p, "cortina_esq", pano)
    registrar(p, "cortina_dir", pano.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    registrar(p, "bambinela", _bambinela(p.largura, round(0.085 * min(p.altura, 1.6 * p.largura)), 90 * u))


def _cortina(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_B
    camadas = []
    sai = ease_in_cubic(trecho(t, *b["sai"]))
    some_palco = 1 - ease_in_out_cubic(trecho(t, b["sai"][0], b["sai"][1] - 0.1))
    # palco e refletor: a luz acende antes de o pino nascer e apaga quando a cortina sai
    palco = ease_out_cubic(trecho(t, *b["palco"])) * some_palco
    if palco > 0:
        camadas.append(_c("palco", cx, cy + 0.02 * s, icone="palco", lado=1.25 * s, opacidade=palco,
                          revela=("direita", palco, 40 * u) if palco < 1 else None))
    luz = ease_out_cubic(trecho(t, *b["luz"])) * some_palco
    topo = p.pecas["bambinela"].imagem.height * 0.7
    if luz > 0:
        alto = min(880.0, cy + 0.35 * s - topo)
        camadas.append(_c("feixe", cx, topo, icone="feixe", lado=alto, pivo=(0.5, 0.0), opacidade=0.85 * luz,
                          esticar=(0.75, 1.0)))
    # o pino nasce na luz (desfoque ao foco), a seta se desenha e ele desliza para o lugar
    if t >= b["surge"][0]:
        ox, oy = desliza(t, p, b["desliza"])
        q = trecho(t, *b["surge"])
        camadas += simbolo(t, p, b, p.simbolo[0] + ox, p.simbolo[1] + oy, escala=0.8 + 0.2 * ease_out_back(q, 1.3),
                           desfoque=20 * u * (1 - ease_out_cubic(min(1.0, q * 1.2))),
                           opacidade=ease_out_cubic(min(1.0, q * 3)), ox=ox, oy=oy)
        camadas += nomes(t, p, b, "foco", ox, oy)
    camadas += faiscas("f", t, b["surge"][0] + 0.08, 0.6, cx, cy, 7, 0.3 * s, 0.85 * s, 34 * u,
                       [CREME, CARAMELO], 9)
    camadas += onda("anel1", t, b["anel"][0], 0.8, cx, cy, 0.1 * s, 1.3 * s, 2.4 * u, CARAMELO)
    # as duas metades: uma puxada curta para dentro (antecipação), abrem franzindo e por fim saem do quadro
    antecipa = 0.025 * math.sin(math.pi * trecho(t, *b["antecipa"]))
    abre = ease_in_out_cubic(trecho(t, *b["abre"]))
    largura = p.pecas["cortina_esq"].imagem.width
    for nome, lado in (("cortina_esq", -1), ("cortina_dir", 1)):
        franze = 1 + antecipa - 0.64 * abre
        borda = p.largura / 2 + lado * p.largura / 2  # a borda de fora fica presa na lateral do quadro
        x = borda + lado * 0.4 * largura * sai
        camadas.append(_c(nome, x, p.altura / 2, peca=nome, pivo=(0.0 if lado < 0 else 1.0, 0.5),
                          esticar=(franze, 1.0)))
    alto = p.pecas["bambinela"].imagem.height
    camadas.append(_c("bambinela", cx, alto / 2 - 1.15 * alto * sai, peca="bambinela"))
    return camadas


# ---------------------------------------------------------------- C: painel de LED

BATIDAS_C = {"grade": (0.1, 0.6), "acende": (0.55, 2.45), "pulso": (2.45, 2.85), "encolhe": (2.85, 3.55),
             "funde": (3.25, 3.55), "anel": (3.5, 4.25), "nome1": (3.6, 4.1), "nome2": (3.72, 4.22),
             "nome3": (3.92, 4.4)}
_LINHAS_LED = 31
_PAINEIS: dict = {}


def _preparar_led(p) -> None:
    """Amostra o símbolo real (corpo + seta) numa grade de pontos: os acesos desenham o logo em LED."""
    simbolo_img = Image.alpha_composite(p.pecas["corpo"].imagem, p.pecas["rastro"].imagem)
    caixa = simbolo_img.getchannel("A").getbbox()
    alto = 1.75 * p.s
    passo = alto / _LINHAS_LED
    colunas = round((caixa[2] - caixa[0]) / (caixa[3] - caixa[1]) * _LINHAS_LED)
    amostra = simbolo_img.crop(caixa).resize((colunas, _LINHAS_LED), Image.BOX)
    sorteio = random.Random(17)
    acesos = []
    for j in range(_LINHAS_LED):
        for i in range(colunas):
            if amostra.getpixel((i, j))[3] > 110:
                ordem = 0.7 * j / _LINHAS_LED + 0.3 * sorteio.random()
                acesos.append((i, j, BATIDAS_C["acende"][0] + ordem * (BATIDAS_C["acende"][1] - 0.2 -
                                                                       BATIDAS_C["acende"][0])))
    p.led = {"colunas": colunas, "passo": passo, "acesos": acesos, "caixa": caixa}
    # a grade apagada passa 3 pontos para cada lado: é o painel, não só o desenho
    margem, k = 3, 2
    w, h = round((colunas + 2 * margem) * passo), round((_LINHAS_LED + 2 * margem) * passo)
    grade = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(grade)
    r = passo * 0.2 * k
    for j in range(_LINHAS_LED + 2 * margem):
        for i in range(colunas + 2 * margem):
            x, y = (i + 0.5) * passo * k, (j + 0.5) * passo * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=CREME + (46,))
    registrar(p, "led_grade", grade.resize((w, h), Image.LANCZOS))
    _PAINEIS.clear()


def _painel(p, t: float) -> str:
    """Nome da peça com os pontos acesos no instante t (um desenho por quadro, guardado)."""
    t = round(min(max(t, BATIDAS_C["acende"][0]), BATIDAS_C["pulso"][1]) * 30) / 30
    nome = f"led_{round(t * 30)}"
    if nome in p.pecas and _PAINEIS.get(nome) is p.pecas[nome]:
        return nome
    led, k = p.led, 2
    passo = led["passo"]
    w, h = round(led["colunas"] * passo), round(_LINHAS_LED * passo)
    imagem = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)
    pulso = trecho(t, *BATIDAS_C["pulso"])
    for i, j, inicio in led["acesos"]:
        f = trecho(t, inicio, inicio + 0.2)
        if f <= 0:
            continue
        brilho = 1 - ease_out_cubic(f)  # acaba de acender: quase Branco; depois Caramelo
        onda_pulso = max(0.0, math.sin(math.pi * min(1.0, max(0.0, pulso * 1.6 - j / _LINHAS_LED * 0.6))))
        cor = _mistura(_mistura(CARAMELO, BRANCO, 0.85 * brilho), CREME, 0.7 * onda_pulso)
        r = passo * 0.36 * ease_out_back(f, 1.8) * (1 + 0.12 * onda_pulso) * k
        x, y = (i + 0.5) * passo * k, (j + 0.5) * passo * k
        d.ellipse((x - r, y - r, x + r, y + r), fill=cor + (255,))
    registrar(p, nome, imagem.resize((w, h), Image.LANCZOS))
    _PAINEIS[nome] = p.pecas[nome]
    return nome


def _led(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_C
    camadas = []
    led = p.led
    corpo = p.pecas["corpo"]
    caixa = led["caixa"]
    fim_x, fim_y = corpo.x + (caixa[0] + caixa[2]) / 2, corpo.y + (caixa[1] + caixa[3]) / 2
    escala_fim = (caixa[3] - caixa[1]) / (_LINHAS_LED * led["passo"])
    encolhe = ease_in_out_cubic(trecho(t, *b["encolhe"]))
    x, y = cx + (fim_x - cx) * encolhe, cy + (fim_y - cy) * encolhe
    escala = 1 + (escala_fim - 1) * encolhe
    grade = ease_out_cubic(trecho(t, *b["grade"])) * (1 - ease_in_out_cubic(trecho(t, 2.75, 3.1)))
    if grade > 0:
        camadas.append(_c("led_grade", x, y, peca="led_grade", escala=escala * (0.97 + 0.03 * grade),
                          opacidade=grade))
    funde = trecho(t, *b["funde"])
    if t >= b["acende"][0] and funde < 1:
        camadas.append(_c("led", x, y, peca=_painel(p, t), escala=escala, opacidade=1 - ease_in_cubic(funde),
                          desfoque=4 * u * math.sin(math.pi * encolhe)))
    if funde > 0:
        camadas += simbolo(t, p, b, *p.simbolo, opacidade=ease_out_cubic(funde))
    camadas += lampejo("lampejo", t, b["funde"][1] - 0.1, *p.simbolo, 0.3 * s, CREME)
    camadas += onda("anel1", t, b["anel"][0], 0.75, *p.simbolo, 0.25 * s, 1.1 * s, 2.2 * u, CARAMELO)
    return camadas + nomes(t, p, b, "varre")


# ---------------------------------------------------------------- D: ingresso

BATIDAS_D = {"entra": (0.1, 0.85), "picote": (0.85, 1.3), "destaca": (1.4, 2.3), "centra": (1.85, 2.4),
             "vira": (2.45, 2.7), "verso": (2.7, 3.1), "rastro": (3.05, 3.6), "anel": (3.06, 3.85),
             "assenta": (3.1, 3.5), "desliza": (3.7, 4.25), "nome1": (3.85, 4.4), "nome2": (3.95, 4.5),
             "nome3": (4.15, 4.65)}


def _ingresso(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_D
    camadas = []
    lado = 2.0 * s
    entra = trecho(t, *b["entra"])
    flutua = 6 * u * math.sin(2 * math.pi * max(0.0, t - 0.85) / 1.6) * (1 - trecho(t, 2.2, 2.45))
    base_x = cx + p.largura * 0.75 * (1 - ease_out_cubic(entra)) - 0.125 * lado * ease_in_out_cubic(
        trecho(t, *b["centra"]))
    giro = -14 * (1 - ease_out_back(entra, 1.2))
    y = cy + flutua
    # o canhoto: puxão curto (antecipação), solta no picote e cai girando, acelerando, para fora do quadro
    d = trecho(t, *b["destaca"])
    puxa = 3 * math.sin(math.pi * trecho(t, 1.28, 1.45))
    if d < 1:
        queda = p.altura * 0.8 * d * d
        a = math.radians(giro)  # o pé do picote acompanha o giro do corpo enquanto estão presos
        vx, vy = -0.325 * lado, 0.18 * lado
        px = base_x + 0.125 * lado + vx * math.cos(a) + vy * math.sin(a)
        py = y - vx * math.sin(a) + vy * math.cos(a)
        camadas.append(_c("canhoto", px - 0.25 * s * d, py + queda,
                          icone="canhoto", lado=lado, pivo=(0.30, 0.68), giro=giro + puxa + 50 * ease_in_cubic(d),
                          opacidade=1 - trecho(d, 0.8, 1.0)))
    camadas += faiscas("rasgo", t, b["destaca"][0], 0.45, base_x - 0.2 * lado, y, 5, 0.04 * s, 0.3 * s, 24 * u,
                       [CREME, CARAMELO], 4)
    # um brilho percorre o picote antes de destacar
    q = trecho(t, *b["picote"])
    if 0 < q < 1:
        camadas.append(_c("picote", base_x - 0.2 * lado, y + lado * (-0.15 + 0.3 * ease_in_out_cubic(q)),
                          icone="brilho", lado=48 * u * math.sin(math.pi * q), params={"cor": BRANCO}))
    # o corpo do convite vira de costas (achata na horizontal) e o verso é o símbolo
    vira = ease_in_cubic(trecho(t, *b["vira"]))
    if vira < 1:
        camadas.append(_c("ingresso", base_x + 0.125 * lado, y, icone="ingresso", lado=lado, pivo=(0.625, 0.5),
                          giro=giro, esticar=(max(0.0, 1 - vira), 1.0)))
    v = trecho(t, *b["verso"])
    if v > 0:
        ox, oy = desliza(t, p, b["desliza"])
        escala = 1.3 - 0.3 * ease_in_out_cubic(trecho(t, *b["assenta"]))
        camadas += simbolo(t, p, b, p.simbolo[0] + ox, p.simbolo[1] + oy, escala=escala,
                           esticar=(max(0.0, ease_out_back(v, 1.4)), 1.0), ox=ox, oy=oy)
        camadas += nomes(t, p, b, "sobe", ox, oy)
    camadas += onda("anel1", t, b["anel"][0], 0.8, cx, cy, 0.25 * s, 1.3 * s, 2.4 * u, CARAMELO)
    camadas += onda("anel2", t, b["anel"][0] + 0.12, 0.7, cx, cy, 0.2 * s, 1.0 * s, 1.8 * u, CREME, 0.35)
    return camadas


OPCOES_CORP = {
    "B": {"titulo": "Cortina", "duracao": _duracao(BATIDAS_B), "batidas": BATIDAS_B, "camadas": _cortina,
          "preparar": _preparar_cortina},
    "C": {"titulo": "LED", "duracao": _duracao(BATIDAS_C), "batidas": BATIDAS_C, "camadas": _led,
          "preparar": _preparar_led},
    "D": {"titulo": "Ingresso", "duracao": _duracao(BATIDAS_D), "batidas": BATIDAS_D, "camadas": _ingresso},
}
