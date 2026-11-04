"""Opções B, C e D da vinheta da Casa Veraneio (Thomas, 04/11/2026: "o ícone no último frame caindo do topo da tela
e com um bouncing curto, quase como uma mola"). Nas três o pino entra de fora do quadro, cai acelerando, toca o
lugar final, achata e quica curto (motion_opcoes_comum.queda) e só depois a seta orbital e o nome entram. Muda o
que vem antes da queda:

- B "Horizonte": minimalista. Uma linha do horizonte se abre, um sol Creme discreto nasce atrás dela; o pino cai
  na frente do sol, a linha cede sob a ponta como cama elástica e o sol se desfaz no anel.
- C "Água": uma gota se forma, cai e abre ondas na água com respingos; o pino cai no centro das ondas e a onda do
  impacto se levanta e vira o anel em volta dele.
- D "Rota": uma trilha pontilhada se desenha entre pinheiros até o chalé, que vira o ponto de destino do mapa;
  o pino cai exatamente nesse ponto e a trilha se apaga.
"""

import math
import random

from motion_camadas import CORES, ease_in_cubic, ease_in_out_cubic, ease_out_back, ease_out_cubic, trecho
from motion_opcoes_comum import ASSENTA, base_do_simbolo, centro_do_circulo, nomes, pino_caindo
from motion_roteiros import _c, faiscas, lampejo, onda

BRANCO, CREME, CARAMELO = CORES["branco"], CORES["creme"], CORES["caramelo"]


def _largura_do_logo(p) -> tuple[float, float]:
    """Borda esquerda e direita do logo inteiro na posição final."""
    caixas = [(q.x + q.imagem.getchannel("A").getbbox()[0], q.x + q.imagem.getchannel("A").getbbox()[2])
              for q in p.pecas.values() if q.imagem.getchannel("A").getbbox()]
    return min(a for a, _ in caixas), max(b for _, b in caixas)


def _respingos(nome: str, t: float, inicio: float, x: float, y: float, s: float, u: float, n: int,
               semente: int, altura: float = 1.0) -> list:
    """Gotinhas que saltam da água em parábola e voltam (a do meio sobe reta, mais alta)."""
    sorteio, camadas = random.Random(semente), []
    for k in range(n):
        meio = k == 0
        dur = sorteio.uniform(0.42, 0.52) if not meio else 0.56
        f = trecho(t, inicio + (0.03 if meio else 0), inicio + dur)
        if not 0 < f < 1:
            continue
        lado = (-1) ** k * sorteio.uniform(0.07, 0.2) * s if not meio else 0.0
        alto = (sorteio.uniform(0.13, 0.22) if not meio else 0.3) * s * altura
        px, py = x + lado * f, y - alto * 4 * f * (1 - f)
        tam = (15 if meio else sorteio.uniform(9, 13)) * u
        camadas.append(_c(f"{nome}{k}", px, py, icone="disco", lado=tam, params={"cor": CREME},
                          opacidade=1 - ease_in_cubic(trecho(f, 0.7, 1.0))))
    return camadas


def _traco(espessura: float, lado: float) -> int:
    """Espessura em px -> milésimos do lado do ícone "aro" (traço constante enquanto o aro cresce)."""
    return max(4, min(200, round(1000 * espessura / max(lado, 1.0))))


def _ondulacao(nome: str, t: float, inicio: float, dur: float, x: float, y: float, r1: float, u: float,
               opacidade: float = 0.85, achata: float = 0.3) -> list:
    """Onda na água: aro achatado (elipse em perspectiva) que se abre e some."""
    q = trecho(t, inicio, inicio + dur)
    if not 0 < q < 1:
        return []
    raio = r1 * (0.08 + 0.92 * ease_out_cubic(q))
    return [_c(nome, x, y, icone="aro", lado=2 * raio, esticar=(1.0, achata),
               params={"cor": CREME, "traco": _traco(2.6 * u / achata ** 0.5, 2 * raio)},
               opacidade=opacidade * (1 - ease_in_cubic(q)) * min(1.0, q * 6))]


# ---------------------------------------------------------------- B: horizonte

BATIDAS_B = {"linha": (0.15, 1.05), "sol": (0.6, 2.4), "queda": (2.15, 2.7), "assenta": (2.7, 2.7 + ASSENTA),
             "anel": (2.72, 3.55), "recolhe": (3.3, 3.9), "rastro": (3.35, 3.95), "nome1": (3.75, 4.3),
             "nome2": (3.87, 4.45)}


def _horizonte(t: float, p) -> list:
    u, s, b = p.u, p.s, BATIDAS_B
    (bx, by), _ = base_do_simbolo(p)
    esquerda, direita = _largura_do_logo(p)
    lado = (direita - esquerda) * 1.3
    x0 = p.largura / 2 - lado / 2
    onde = (bx - x0) / lado
    pino, dy = pino_caindo(t, p, b)
    camadas = []
    # o sol Creme (disco translúcido e aro fino) nasce atrás da linha, centrado onde o círculo do pino vai ficar
    sx, sy = centro_do_circulo(p)
    raio = 0.68 * p.simbolo_altura
    nasce = ease_out_cubic(trecho(t, *b["sol"]))
    desfaz = trecho(t, b["queda"][1], b["queda"][1] + 0.32)
    if nasce > 0 and desfaz < 1:
        y_sol = by + raio * 1.05 - (by + raio * 1.05 - sy) * nasce
        visivel = (by - (y_sol - raio)) / (2 * raio)
        if visivel > 0:
            corte = ("baixo", min(1.0, visivel), 2 * u) if visivel < 1 else None
            cresce = 1 + 0.18 * ease_out_cubic(desfaz)
            camadas.append(_c("sol", sx, y_sol, icone="disco", lado=2 * raio, escala=cresce, revela=corte,
                              params={"cor": CREME}, opacidade=0.2 * (1 - desfaz)))
            camadas.append(_c("sol_aro", sx, y_sol, icone="aro", lado=2 * raio, escala=cresce, revela=corte,
                              params={"cor": CREME}, opacidade=0.75 * (1 - desfaz)))
    # a linha se abre do centro, cede sob a ponta do pino e depois se recolhe para a ponta e some
    abre = ease_in_out_cubic(trecho(t, *b["linha"]))
    recolhe = ease_in_out_cubic(trecho(t, *b["recolhe"]))
    if abre > 0 and recolhe < 1:
        de, ate = 0.5 - 0.5 * abre, 0.5 + 0.5 * abre
        de, ate = de + (onde - de) * recolhe, ate + (onde - ate) * recolhe
        afunda = max(0.0, dy or 0.0) / (0.10 * lado)
        camadas.append(_c("linha", p.largura / 2, by, icone="linha_mola", lado=lado, opacidade=0.9,
                          params={"de": de, "ate": ate, "afunda": afunda, "onde": onde, "passos": 96}))
    toque = b["queda"][1]
    for k in (-1, 1):  # dois riscos de poeira de luz correm pela linha no toque
        q = trecho(t, toque, toque + 0.42)
        if 0 < q < 1:
            camadas.append(_c(f"poeira{k}", bx + k * (0.06 + 0.32 * ease_out_cubic(q)) * s, by - 4 * u,
                              icone="faisca", lado=34 * u * (1 - 0.6 * q), esticar=(1.0, 0.55),
                              params={"cor": CREME}, opacidade=0.9 * (1 - ease_in_cubic(q))))
    camadas += pino
    camadas += onda("anel1", t, b["anel"][0], 0.83, sx, sy, raio, 1.45 * s, 2.4 * u, CARAMELO)
    camadas += onda("anel2", t, b["anel"][0] + 0.12, 0.7, sx, sy, raio * 0.9, 1.1 * s, 1.8 * u, CREME, 0.35)
    return camadas + nomes(t, p, b, "direita")


# ---------------------------------------------------------------- C: água

BATIDAS_C = {"gota": (0.2, 1.32), "respingo": (1.32, 1.9), "ondas": (1.32, 2.55), "queda": (2.2, 2.75),
             "assenta": (2.75, 2.75 + ASSENTA), "anel": (2.75, 3.75), "rastro": (3.4, 4.0), "nome1": (3.8, 4.4),
             "nome2": (3.92, 4.55)}


def _agua(t: float, p) -> list:
    u, s, b = p.u, p.s, BATIDAS_C
    (bx, by), _ = base_do_simbolo(p)
    camadas = []
    # a superfície: uma elipse bem leve que aparece no começo e sai quando o anel se forma
    superficie = min(ease_out_cubic(trecho(t, 0.1, 0.7)), 1 - trecho(t, 3.0, 3.5))
    if superficie > 0:
        camadas.append(_c("superficie", bx, by, icone="aro", lado=1.05 * s, esticar=(1.0, 0.28),
                          params={"cor": CREME, "traco": _traco(4 * u, 1.05 * s)}, opacidade=0.25 * superficie))
    # a gota se forma no alto, pesa (estica), cai acelerando e entra na água
    topo = by - 1.05 * s
    if t < 1.36:
        forma = ease_out_back(trecho(t, 0.2, 0.55), 1.2)
        pesa = ease_in_out_cubic(trecho(t, 0.55, 0.88))
        q = trecho(t, 0.88, 1.32)
        y = topo + (by - 0.08 * s - topo) * q * q
        entra = trecho(t, 1.32, 1.36)
        if forma > 0:
            camadas.append(_c("gota", bx, y, icone="gota_agua", lado=0.27 * s, pivo=(0.5, 0.92),
                              escala=forma * (1 - entra),
                              esticar=(1 - 0.08 * pesa + 0.06 * q, 1 + 0.12 * pesa + 0.28 * q * q)))
    i = b["respingo"][0]
    camadas += _respingos("respingo", t, i, bx, by, s, u, 5, 21)
    for k, (atraso, r1) in enumerate(((0.0, 0.72), (0.14, 0.55), (0.3, 0.4))):
        camadas += _ondulacao(f"onda{k}", t, i + atraso, 1.0 + 0.1 * k, bx, by, r1 * s, u)
    pino, _ = pino_caindo(t, p, b)
    toque = b["queda"][1]
    camadas += _respingos("respingo_pino", t, toque, bx, by, s, u, 4, 5, 0.6)
    # a onda do impacto se abre na água, levanta (a elipse vira círculo) e sobe até o círculo do pino: o anel
    sx, sy = centro_do_circulo(p)
    q = trecho(t, *b["anel"])
    if 0 < q < 1:
        levanta = ease_in_out_cubic(trecho(q, 0.12, 0.6))
        raio = s * (0.08 + 0.62 * ease_out_cubic(trecho(q, 0, 0.45)) + 0.75 * ease_out_cubic(trecho(q, 0.45, 1.0)))
        camadas.append(_c("anel_agua", bx + (sx - bx) * levanta, by + (sy - by) * levanta, icone="aro",
                          lado=2 * raio, esticar=(1.0, 0.3 + 0.7 * levanta),
                          params={"cor": CARAMELO, "traco": _traco(2.6 * u, 2 * raio)},
                          opacidade=0.85 * (1 - ease_in_cubic(trecho(q, 0.4, 1.0)))))
    segundo = toque + 0.085 + 0.21  # o segundo toque do quique faz uma onda pequena
    camadas += _ondulacao("onda_quique", t, segundo, 0.7, bx, by, 0.32 * s, u, 0.6)
    return camadas + pino + nomes(t, p, b, "sobe")


# ---------------------------------------------------------------- D: rota no mapa

BATIDAS_D = {"rota": (0.15, 1.75), "pinheiros": (0.45, 1.55), "chale": (1.5, 2.3), "marca": (2.3, 2.9),
             "queda": (2.4, 2.95), "assenta": (2.95, 2.95 + ASSENTA), "apaga": (3.15, 3.85), "rastro": (3.5, 4.1),
             "nome1": (3.9, 4.5), "nome2": (4.02, 4.65)}
TRACOS_ROTA = 30


def _bezier(a, b, c, d, f):
    g = 1 - f
    return tuple(g ** 3 * a[i] + 3 * g * g * f * b[i] + 3 * g * f * f * c[i] + f ** 3 * d[i] for i in (0, 1))


def _rota_pontos(p) -> list[tuple[float, float, float]]:
    """Traços da trilha (x, y, ângulo) igualmente espaçados numa curva em S do pé do quadro até o destino."""
    s = p.s
    (bx, by), _ = base_do_simbolo(p)
    a, d = (p.cx + 0.85 * s, min(p.cy + 1.6 * s, p.altura * 0.88)), (bx, by + 0.02 * s)
    b, c = (p.cx - 1.35 * s, p.cy + 1.25 * s), (p.cx + 1.25 * s, p.cy + 0.3 * s)
    amostras = [_bezier(a, b, c, d, k / 400) for k in range(401)]
    acumulado = [0.0]
    for p0, p1 in zip(amostras, amostras[1:]):
        acumulado.append(acumulado[-1] + math.dist(p0, p1))
    pontos, j = [], 0
    for k in range(TRACOS_ROTA):
        alvo = acumulado[-1] * (k + 0.5) / (TRACOS_ROTA + 1.2)
        while acumulado[j + 1] < alvo:
            j += 1
        (x0, y0), (x1, y1) = amostras[j], amostras[j + 1]
        pontos.append((x0, y0, -math.degrees(math.atan2(y1 - y0, x1 - x0))))
    return pontos


def _rota(t: float, p) -> list:
    u, s, b = p.u, p.s, BATIDAS_D
    (bx, by), _ = base_do_simbolo(p)
    camadas = []
    pontos = _rota_pontos(p)
    apaga = b["apaga"]
    for k, (x, y, ang) in enumerate(pontos):
        f = k / TRACOS_ROTA
        nasce = trecho(t, b["rota"][0] + f * 1.4, b["rota"][0] + f * 1.4 + 0.22)
        some = trecho(t, apaga[0] + f * 0.45, apaga[0] + f * 0.45 + 0.2)
        if nasce > 0 and some < 1:
            camadas.append(_c(f"rota{k}", x, y, icone="faisca", lado=28 * u, giro=ang,
                              escala=ease_out_back(nasce, 1.4) * (1 - some), params={"cor": CREME},
                              opacidade=0.9))
    # pinheiros crescem do chão ao lado da trilha (e encolhem quando ela se apaga)
    for k, (f, lado_trilha, tam) in enumerate(((0.1, 1, 0.42), (0.36, -1, 0.5), (0.6, 1, 0.38))):
        x, y, _ = pontos[int(f * TRACOS_ROTA)]
        cresce = ease_out_back(trecho(t, b["pinheiros"][0] + 0.3 * k, b["pinheiros"][0] + 0.3 * k + 0.4), 1.5)
        encolhe = ease_in_cubic(trecho(t, apaga[0] + 0.1 * k, apaga[0] + 0.1 * k + 0.32))
        if cresce > 0 and encolhe < 1:
            camadas.append(_c(f"pinheiro{k}", x + lado_trilha * 0.26 * s, y + 0.05 * s, icone="pinheiro",
                              lado=tam * s, pivo=(0.5, 0.96), escala=cresce * (1 - encolhe),
                              params={"cor": CARAMELO}))
    # o chalé nasce no fim da trilha, respira e encolhe até virar o ponto de destino do mapa
    cx_chale, cy_chale = bx, by + 0.02 * s
    q = trecho(t, *b["chale"])
    if 0 < q < 1:
        nasce = ease_out_back(trecho(t, 1.5, 1.9), 1.3)
        antecipa = 0.06 * ease_out_cubic(trecho(t, 2.0, 2.1))
        fecha = ease_in_cubic(trecho(t, 2.1, 2.3))
        camadas.append(_c("chale", cx_chale, cy_chale, icone="chale", lado=0.72 * s, pivo=(0.5, 0.86),
                          escala=(nasce + antecipa) * (1 - 0.9 * fecha), opacidade=1 - trecho(t, 2.22, 2.3)))
    m = trecho(t, 2.22, b["queda"][1] + 0.02)
    if 0 < m < 1:
        camadas.append(_c("marcador", cx_chale, cy_chale, icone="marcador", lado=0.17 * s,
                          escala=ease_out_back(trecho(t, 2.22, 2.4), 1.6)))
    camadas += onda("pulso1", t, 2.3, 0.6, cx_chale, cy_chale, 0.05 * s, 0.32 * s, 1.8 * u, CREME, 0.7)
    camadas += onda("pulso2", t, 2.55, 0.55, cx_chale, cy_chale, 0.05 * s, 0.26 * s, 1.6 * u, CREME, 0.5)
    pino, _ = pino_caindo(t, p, b)
    toque = b["queda"][1]
    camadas += pino
    sx, sy = centro_do_circulo(p)
    camadas += faiscas("f", t, toque, 0.5, bx, by - 0.02 * s, 6, 0.08 * s, 0.4 * s, 30 * u, [CREME, CARAMELO], 13)
    camadas += onda("anel1", t, toque + 0.02, 0.85, sx, sy, 0.3 * s, 1.35 * s, 2.4 * u, CARAMELO)
    return camadas + nomes(t, p, b, "foco")


def _duracao(batidas: dict, parado: float = 1.3) -> float:
    return round(max(fim for _, fim in batidas.values()) + parado, 2)


OPCOES_VERANEIO = {
    "B": {"titulo": "Horizonte", "duracao": _duracao(BATIDAS_B), "batidas": BATIDAS_B, "camadas": _horizonte},
    "C": {"titulo": "Água", "duracao": _duracao(BATIDAS_C), "batidas": BATIDAS_C, "camadas": _agua},
    "D": {"titulo": "Rota", "duracao": _duracao(BATIDAS_D), "batidas": BATIDAS_D, "camadas": _rota},
}
