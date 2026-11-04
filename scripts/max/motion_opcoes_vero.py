"""Opções B, C e D da vinheta da Casa Vero (imobiliária de alto padrão; Thomas, 04/11/2026), no fundo Creme:

- B "Planta": uma planta baixa em traço fino se desenha, deita e vira o chão; a fachada sobe em traço a partir
  dela, o contorno do próprio logo se desenha em volta e se preenche no pino; a chave sobe para dentro.
- C "Porta": uma porta fechada, uma fresta de luz; ela se abre, a luz quente invade o chão e o pino sai pela porta
  (do desfoque ao foco) enquanto atravessamos o batente.
- D "Formas": só geometria e tipografia. Um filete, um círculo e um losango entram em tempos diferentes e se
  encaixam na silhueta do pino; o filete gira e vira a chave; tudo se funde no logo e o nome sobe por máscaras.
"""

import math

from PIL import Image, ImageChops, ImageFilter

from motion_camadas import CORES, ease_in_cubic, ease_in_out_cubic, ease_out_back, ease_out_cubic, trecho
from motion_opcoes_comum import desliza, nomes, registrar, simbolo
from motion_roteiros import _c, faiscas, lampejo, onda

BRANCO, CREME, CARAMELO, VERDE = CORES["branco"], CORES["creme"], CORES["caramelo"], CORES["verde"]


def _duracao(batidas: dict, parado: float = 1.3) -> float:
    return round(max(fim for _, fim in batidas.values()) + parado, 2)


def _no_centro(t: float, p, b: dict, *, escala=1.0, desfoque=0.0, opacidade=1.0, dy=0.0) -> list:
    """O símbolo nascido no centro (e deslizando para o lugar em b["desliza"]) com o nome em b["nome*"]."""
    ox, oy = desliza(t, p, b["desliza"])
    camadas = simbolo(t, p, b, p.simbolo[0] + ox, p.simbolo[1] + oy + dy, escala=escala, desfoque=desfoque,
                      opacidade=opacidade, ox=ox, oy=oy)
    return camadas, ox, oy


# ---------------------------------------------------------------- B: planta baixa

BATIDAS_B = {"planta": (0.1, 1.65), "deita": (1.55, 2.05), "fachada": (1.85, 2.9), "contorno": (2.7, 3.4),
             "preenche": (3.3, 3.7), "chave": (3.7, 4.2), "anel": (3.62, 4.4), "desliza": (4.2, 4.75),
             "nome1": (4.4, 4.9), "nome2": (4.5, 5.0), "nome3": (4.7, 5.15)}


def _preparar_planta(p) -> None:
    """Contorno em traço Verde do símbolo inteiro (silhueta do pino e o desenho da chave), do tamanho do logo."""
    pino, chave = p.pecas["pino"], p.pecas["chave"]
    m = round(8 * p.u)
    w, h = pino.imagem.width + 2 * m, pino.imagem.height + 2 * m
    raio = max(1, round(1.4 * p.u))

    def borda(alfa: Image.Image) -> Image.Image:
        cheio = Image.new("L", (w, h), 0)
        cheio.paste(alfa.point(lambda v: 255 if v > 128 else 0), (m, m))
        return ImageChops.subtract(cheio.filter(ImageFilter.MaxFilter(2 * raio + 1)), cheio)

    uniao = ImageChops.lighter(pino.imagem.getchannel("A"), chave.imagem.getchannel("A"))
    linhas = ImageChops.lighter(borda(uniao), borda(chave.imagem.getchannel("A")))
    contorno = Image.new("RGBA", (w, h), VERDE + (0,))
    contorno.putalpha(linhas.filter(ImageFilter.GaussianBlur(0.6)))
    registrar(p, "contorno", contorno, pino.x - m, pino.y - m)
    p.contorno_pivo = ((p.pivo[0] * pino.imagem.width + m) / w, (p.pivo[1] * pino.imagem.height + m) / h)


def _planta(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_B
    camadas = []
    chao = cy + 0.42 * s
    # a planta se desenha girando de leve; depois deita (achata em perspectiva) e vira o chão da fachada
    desenha = ease_in_out_cubic(trecho(t, *b["planta"]))
    deita = ease_in_out_cubic(trecho(t, *b["deita"]))
    some = trecho(t, 2.55, 3.0)
    if desenha > 0 and some < 1:
        camadas.append(_c("planta", cx, cy - 0.05 * s + (chao - cy + 0.05 * s) * deita, icone="planta",
                          lado=1.7 * s, giro=-5 * (1 - desenha) * (1 - deita), escala=0.95 + 0.05 * desenha,
                          esticar=(1.0, 1 - 0.72 * deita), opacidade=(1 - 0.45 * deita) * (1 - some),
                          params={"progresso": desenha, "passos": 90}))
    f = ease_in_out_cubic(trecho(t, *b["fachada"]))
    funde = trecho(t, *b["preenche"])
    if f > 0 and funde < 1:
        camadas.append(_c("fachada", cx, chao, icone="fachada", lado=1.0 * s, pivo=(0.5, 0.86),
                          escala=1 - 0.25 * ease_in_out_cubic(trecho(t, 2.9, 3.45)),
                          opacidade=1 - ease_in_cubic(funde), params={"progresso": f, "passos": 90}))
    # o contorno do logo se desenha em volta da casa (varredura angular) e o pino se preenche por dentro
    c = trecho(t, *b["contorno"])
    escala = 1.3 - 0.3 * ease_in_out_cubic(trecho(t, 3.3, 3.95))
    ox, oy = desliza(t, p, b["desliza"])
    if c > 0 and funde < 1:
        atual = 270 - 360 * ease_in_out_cubic(c)
        caixa = p.pecas["contorno"].imagem.size
        camadas.append(_c("contorno", cx, cy, peca="contorno", pivo=p.contorno_pivo, escala=escala,
                          setor=(caixa[0] * p.contorno_pivo[0], caixa[1] * p.contorno_pivo[1], atual, 270)
                          if c < 1 else None, opacidade=1 - ease_in_cubic(funde)))
    if funde > 0:
        camadas += simbolo(t, p, b, p.simbolo[0] + ox, p.simbolo[1] + oy, escala=escala,
                           opacidade=ease_out_cubic(funde), ox=ox, oy=oy)
    camadas += lampejo("lampejo", t, b["preenche"][1] - 0.15, cx, cy - 0.1 * s, 0.3 * s, BRANCO)
    camadas += onda("anel1", t, b["anel"][0], 0.78, cx, cy, 0.2 * s, 1.25 * s, 2.4 * u, CARAMELO)
    return camadas + nomes(t, p, b, "foco", ox, oy)


# ---------------------------------------------------------------- C: porta

BATIDAS_C = {"batente": (0.1, 0.65), "fresta": (0.75, 1.05), "abre": (1.05, 1.95), "sai": (2.0, 2.8),
             "atravessa": (2.25, 2.9), "chave": (2.55, 3.05), "anel": (2.7, 3.45), "desliza": (3.4, 3.95),
             "nome1": (3.6, 4.1), "nome2": (3.7, 4.2), "nome3": (3.9, 4.35)}


def _porta(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_C
    camadas = []
    lado = 1.6 * s
    nasce = ease_out_back(trecho(t, *b["batente"]), 1.2)
    atravessa = ease_in_cubic(trecho(t, *b["atravessa"]))
    escala = (0.9 + 0.1 * nasce) * (1 + 0.3 * atravessa)  # até 1,3x: ícone <= 1024 px
    opacidade = min(1.0, trecho(t, *b["batente"]) * 3) * (1 - atravessa)
    fresta = ease_in_out_cubic(trecho(t, *b["fresta"]))
    abre = ease_in_out_cubic(trecho(t, *b["abre"]))
    luz = 0.25 * fresta + 0.75 * abre
    if opacidade > 0:
        # tudo cresce a partir do meio do vão (a câmera atravessa a porta)
        base = cy + (0.88 - 0.5) * lado * escala
        if luz > 0.02:
            camadas.append(_c("luz_chao", cx, base, icone="luz_chao", lado=0.95 * lado, pivo=(0.5, 0.0),
                              escala=escala, esticar=(1.0, 0.42), opacidade=luz * opacidade))
        camadas.append(_c("batente", cx, cy, icone="batente", lado=lado, escala=escala, opacidade=opacidade,
                          params={"luz": luz}))
        dobra = 1 - 0.07 * fresta - 0.81 * abre  # a folha gira na dobradiça: achata para a esquerda
        if dobra > 0.1:
            camadas.append(_c("porta", cx + (0.30 - 0.5) * lado * escala, cy, icone="porta", lado=lado,
                              escala=escala, pivo=(0.30, 0.5), esticar=(dobra, 1.0), opacidade=opacidade))
    # o pino sai pela porta: pequeno e desfocado no vão, cresce até o tamanho certo na frente do batente
    q = trecho(t, *b["sai"])
    camadas += lampejo("lampejo", t, b["sai"][0] - 0.08, cx, cy, 0.4 * s, BRANCO)
    camadas += faiscas("f", t, b["sai"][0] + 0.15, 0.6, cx, cy, 7, 0.2 * s, 0.8 * s, 32 * u,
                       [BRANCO, CARAMELO], 8)
    if q > 0:
        e = ease_out_cubic(q)
        pino, ox, oy = _no_centro(t, p, b, escala=0.3 + 0.7 * ease_out_back(q, 1.1), desfoque=14 * u * (1 - e),
                                  opacidade=min(1.0, q * 3), dy=-0.05 * s * (1 - e))
        camadas += pino + nomes(t, p, b, "direita", ox, oy)
    camadas += onda("anel1", t, b["anel"][0], 0.75, cx, cy, 0.2 * s, 1.25 * s, 2.4 * u, CARAMELO)
    return camadas


# ---------------------------------------------------------------- D: formas

BATIDAS_D = {"filete": (0.15, 0.75), "circulo": (0.5, 1.15), "losango": (0.85, 1.5), "chave_forma": (1.5, 2.1),
             "respira": (2.1, 2.35), "funde": (2.35, 2.85), "anel": (2.8, 3.55), "desliza": (3.3, 3.85),
             "nome1": (3.5, 4.0), "nome2": (3.62, 4.12), "nome3": (3.85, 4.35)}


def _formas(t: float, p) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_D
    camadas = []
    pino = p.pecas["pino"]
    x0, y0, x1, y1 = pino.imagem.getchannel("A").getbbox()
    raio_px = (x1 - x0) / 2
    centro_dy = (y0 + raio_px) - (y0 + y1) / 2  # círculo do pino em relação ao centro do símbolo
    ponta_dy = (y1 - y0) / 2
    respira = 0.035 * math.sin(math.pi * trecho(t, *b["respira"]))
    funde = trecho(t, *b["funde"])
    e = (1.45 - 0.45 * ease_in_out_cubic(funde)) * (1 + respira)  # o desenho geométrico, maior, encolhe ao logo
    some = 1 - ease_in_cubic(funde)
    R = raio_px * e
    ccy = cy + centro_dy * e
    if some > 0:
        # losango: entra de baixo girando e assenta com a ponta onde fica a ponta do pino
        q = trecho(t, *b["losango"])
        if q > 0:
            meia = 0.86 * R
            ly = cy + ponta_dy * e - meia
            camadas.append(_c("losango", cx, ly + 0.9 * s * (1 - ease_out_cubic(q)), icone="losango", lado=2 * meia,
                              giro=90 * (1 - ease_out_back(q, 1.1)), opacidade=min(1.0, q * 3) * some,
                              params={"cor": CARAMELO}))
        # círculo: nasce do ponto, passa um pouco e assenta
        q = trecho(t, *b["circulo"])
        if q > 0:
            camadas.append(_c("circulo", cx, ccy, icone="disco", lado=2 * R, escala=ease_out_back(q, 1.4),
                              params={"cor": CARAMELO}, opacidade=some))
            camadas.append(_c("miolo", cx, ccy, icone="disco", lado=1.1 * R,
                              escala=ease_out_back(trecho(t, 1.05, 1.5), 1.6), params={"cor": CREME},
                              opacidade=some))
        # filete: se estende na horizontal e depois gira e encolhe até virar a haste da chave, com a cabeça
        f = ease_in_out_cubic(trecho(t, *b["filete"]))
        k = ease_in_out_cubic(trecho(t, *b["chave_forma"]))
        if f > 0:
            comprimento = 3.2 * R * (1 - k) + 1.55 * R * k
            chao = cy + ponta_dy * e + 0.1 * s  # filete de base, abaixo da ponta, como uma linha de texto
            fy = chao + (ccy + 0.78 * R - chao) * k
            camadas.append(_c("filete", cx, fy, icone="faisca", lado=comprimento, giro=90 * k,
                              esticar=(f, max(0.02, 0.14 * R / (0.14 * comprimento) * 0.55)),
                              params={"cor": VERDE}, opacidade=some))
            cabeca = ease_out_back(trecho(t, 1.85, 2.15), 1.6)
            if cabeca > 0:
                camadas.append(_c("cabeca", cx, ccy, icone="disco", lado=0.62 * R, escala=cabeca,
                                  params={"cor": VERDE}, opacidade=some))
    if funde > 0:
        pino_c, ox, oy = _no_centro(t, p, b, escala=e, opacidade=ease_out_cubic(min(1.0, funde * 1.4)))
        camadas += pino_c + nomes(t, p, b, "sobe", ox, oy)
    camadas += onda("anel1", t, b["anel"][0], 0.75, cx, cy, 0.25 * s, 1.25 * s, 2.4 * u, CARAMELO)
    camadas += onda("anel2", t, b["anel"][0] + 0.12, 0.7, cx, cy, 0.2 * s, 1.0 * s, 1.8 * u, VERDE, 0.25)
    return camadas


OPCOES_VERO = {
    "B": {"titulo": "Planta", "duracao": _duracao(BATIDAS_B), "batidas": BATIDAS_B, "camadas": _planta,
          "preparar": _preparar_planta},
    "C": {"titulo": "Porta", "duracao": _duracao(BATIDAS_C), "batidas": BATIDAS_C, "camadas": _porta},
    "D": {"titulo": "Formas", "duracao": _duracao(BATIDAS_D), "batidas": BATIDAS_D, "camadas": _formas},
}
