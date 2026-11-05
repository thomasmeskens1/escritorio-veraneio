"""Roteiros das vinhetas (motion_vinheta.py; Thomas, 04/11/2026): a história em ícones de cada empresa, quadro a
quadro, como lista de camadas. As batidas (início, fim em segundos) ficam em ROTEIROS para conferir nos testes.

- casa_vero (imobiliária de alto padrão): a referência profissional adaptada fielmente: lupa com casa (busca) que
  encolhe e vira pino, o pino gira e vira chave, a casa nasce, a chave dá a volta e gira na porta, a casa acende,
  faíscas, a casa encolhe até um ponto, onda em anel e o logo se forma (pino saindo do desfoque, chave subindo).
- casa_veraneio (casas de alto padrão para grupos): sol nascendo atrás do mar, casa de praia de alto padrão
  (vidro, lajes, coqueiro) com piscina (Thomas, 04/11/2026: praia e casa de luxo no lugar de montanhas e chalé), um carro chega e freia (05/11/2026: no lugar da mala), tudo converge num ponto, o pino cai do topo da tela, toca no anel e quica
  curto como mola (versão definitiva, Thomas 04/11/2026), e a seta orbital se desenha em volta dele.
- cv_corporativo (produtora 360° de eventos): calendário com o dia marcado, palco com refletores cruzando os
  feixes, duas taças brindam com faíscas, tudo converge, anel, pino e seta orbital, "CORP." por último.
Nos três o símbolo nasce no centro e desliza para o lugar dele enquanto o nome sai de trás, linha a linha.
"""

import math
import random

from motion_camadas import (CORES, ease_in_cubic, ease_in_out_cubic, ease_out_back, ease_out_cubic, mola,
                            trecho)

BRANCO, CREME, CARAMELO = CORES["branco"], CORES["creme"], CORES["caramelo"]


class Palco:
    """Medidas do quadro: unidade `u` (lado menor 1080 = 1; 16:9 cresce 25%), centro da história e ícone base."""

    def __init__(self, largura: int, altura: int, pecas: dict, fundo: str):
        self.largura, self.altura, self.pecas, self.fundo = largura, altura, pecas, fundo
        self.u = min(largura, altura) / 1080 * (1.25 if largura > altura else 1.0)
        self.cx, self.cy = largura / 2, altura * 0.47
        self.s = 340 * self.u
        principal = "pino" if "pino" in pecas else "corpo"
        self.principal = principal
        peca = pecas[principal]
        x0, y0, x1, y1 = peca.imagem.getchannel("A").getbbox()
        self.pivo = ((x0 + x1) / 2 / peca.imagem.width, (y0 + y1) / 2 / peca.imagem.height)
        self.simbolo = (peca.x + (x0 + x1) / 2, peca.y + (y0 + y1) / 2)  # centro do pino na posição final
        self.simbolo_altura = y1 - y0
        caixas = [(p.x, p.imagem.getchannel("A").getbbox()) for n, p in pecas.items() if not n.startswith("nome")]
        self.simbolo_direita = max(x + caixa[2] for x, caixa in caixas if caixa)
        self.nomes = sorted(n for n in pecas if n.startswith("nome"))


def _c(*args, **kw):
    from motion_vinheta import Camada  # import tardio: motion_vinheta importa este módulo
    return Camada(*args, **kw)


def _anel(*args, **kw):
    from motion_vinheta import Anel
    return Anel(*args, **kw)


def faiscas(nome: str, t: float, inicio: float, dur: float, x: float, y: float, n: int, r0: float, r1: float,
            lado: float, cores: list, semente: int) -> list:
    """Estouro de partículas: riscos de luz e estrelinhas que voam para fora desacelerando e somem."""
    if not inicio <= t <= inicio + dur:
        return []
    sorteio = random.Random(semente)
    p, saida = (t - inicio) / dur, []
    for k in range(n):
        angulo = 360 * k / n + sorteio.uniform(-12, 12)
        q = trecho(p, sorteio.uniform(0, 0.18), 1.0)
        fator = sorteio.uniform(0.75, 1.2)
        if q <= 0:
            continue
        dist = r0 + (r1 - r0) * fator * ease_out_cubic(q)
        a = math.radians(angulo)
        px, py = x + dist * math.cos(a), y + dist * math.sin(a)
        opacidade = 1 - ease_in_cubic(q)
        cor = cores[k % len(cores)]
        if k % 3 == 2:
            saida.append(_c(f"{nome}{k}", px, py, icone="brilho", lado=lado * 0.75 * fator * (1 - 0.5 * q),
                            params={"cor": cor}, giro=40 * q, opacidade=opacidade))
        else:
            saida.append(_c(f"{nome}{k}", px, py, icone="faisca", lado=lado * fator * (1.1 - 0.75 * q),
                            esticar=(1.0, 0.7), params={"cor": cor}, giro=-angulo, opacidade=opacidade))
    return saida


def onda(nome: str, t: float, inicio: float, dur: float, x: float, y: float, r0: float, r1: float,
         espessura: float, cor, opacidade: float = 0.9) -> list:
    """Anel fino que se expande e some (a "ondulação" que apresenta o logo)."""
    q = trecho(t, inicio, inicio + dur)
    if q <= 0 or q >= 1:
        return []
    return [_anel(nome, x, y, r0 + (r1 - r0) * ease_out_cubic(q), espessura * (1 - 0.4 * q), cor,
                  opacidade * (1 - ease_in_cubic(q)) * min(1.0, q * 8))]


def lampejo(nome: str, t: float, inicio: float, x: float, y: float, lado: float, cor) -> list:
    """Brilho curto no ponto onde a história se fecha (a casa que vira ponto, o encontro dos ícones)."""
    q = trecho(t, inicio, inicio + 0.26)
    if q <= 0 or q >= 1:
        return []
    return [_c(nome, x, y, icone="brilho", lado=lado * math.sin(math.pi * q), params={"cor": cor},
               giro=45 * q)]


def logo(t: float, p: Palco, b: dict) -> list:
    """O logo real se forma: símbolo do desfoque ao foco no centro (com a chave subindo, na Vero, ou a seta
    orbital se desenhando, no pino das montanhas), desliza para o lugar e o nome sai de trás dele, linha a linha."""
    if t < b["surge"][0]:
        return []
    u = p.u
    desliza = ease_in_out_cubic(trecho(t, *b["desliza"]))
    ox, oy = (p.cx - p.simbolo[0]) * (1 - desliza), (p.cy - p.simbolo[1]) * (1 - desliza)
    x, y = p.simbolo[0] + ox, p.simbolo[1] + oy
    camadas = []
    for nome in p.nomes:
        q = trecho(t, *b[nome])
        if q <= 0:
            continue
        peca = p.pecas[nome]
        e = ease_out_cubic(q)
        camadas.append(_c(nome, peca.x + peca.imagem.width / 2 - 22 * u * (1 - e),
                          peca.y + peca.imagem.height / 2, peca=nome,
                          revela=("direita", e, 70 * u) if q < 1 else None, opacidade=min(1.0, q * 2.5),
                          corte_esq=p.simbolo_direita + ox - 10 * u if desliza < 1 else None))
    if "queda" in b:  # Casa Veraneio: o pino cai do topo e quica curto, como mola (Thomas, 04/11/2026)
        from motion_opcoes_comum import base_do_simbolo, queda  # import tardio: aquele módulo importa este
        (bx, by), pivo = base_do_simbolo(p)
        dy, esticar = queda(t, *b["queda"], p.simbolo_altura, by + oy + 0.04 * p.altura)
        x, y = bx + ox, by + oy + dy
        comum = {"pivo": pivo, "escala": 1.0, "esticar": esticar}
        oy += dy
        camadas.append(_c(p.principal, x, y, peca=p.principal, **comum))
    else:
        s = trecho(t, *b["surge"])
        escala = 0.8 + 0.2 * ease_out_back(s, 1.3)
        comum = {"pivo": p.pivo, "escala": escala}
        desfoque = 22 * u * (1 - ease_out_cubic(min(1.0, s * 1.2)))
        camadas.append(_c(p.principal, x, y, peca=p.principal, desfoque=desfoque,
                          opacidade=ease_out_cubic(min(1.0, s * 3)), **comum))
    if "chave" in p.pecas:  # Vero: a chave sobe para dentro do pino (LOGO_anima)
        k = trecho(t, *b["chave"])
        if k > 0:
            subida = 0.6 * p.simbolo_altura * (1 - ease_out_back(k, 0.9))
            camadas.append(_c("chave", x, y + subida, peca="chave", desfoque=6 * u * (1 - k),
                              opacidade=min(1.0, k * 4), **comum))
    else:  # pino das montanhas: a seta orbital se desenha da cauda até a ponta
        r = trecho(t, *b["rastro"])
        if r > 0:
            from motion_vinheta import geometria_do_pino
            geo = geometria_do_pino(p.pecas["rastro"].imagem.size)
            atual = geo["rastro_inicio"] - (geo["rastro_inicio"] - geo["rastro_fim"]) * ease_in_out_cubic(r)
            camadas.append(_c("rastro", x, y, peca="rastro",
                              setor=(geo["cx"], geo["cy"], atual, geo["rastro_inicio"] + 8) if r < 1 else None,
                              **comum))
            caixa = p.pecas["rastro"].imagem.getchannel("A").getbbox()
            ponta = (p.pecas["rastro"].x + caixa[2] + ox - 6 * u, p.pecas["rastro"].y + caixa[1] + oy + 6 * u)
            camadas += lampejo("ponta", t, b["rastro"][1] - 0.04, *ponta, 46 * u, CREME)
    return camadas


# ---------------------------------------------------------------- Casa Vero

BATIDAS_VERO = {"lupa": (0.0, 1.12), "pino": (0.98, 1.85), "chave": (1.62, 3.02), "casa": (2.0, 3.55),
                "faiscas": (2.98, 3.5), "anel": (3.52, 4.3), "surge": (3.56, 4.1), "chave_logo": (3.78, 4.3),
                "desliza": (4.25, 4.8), "nome1": (4.42, 4.9), "nome2": (4.52, 5.0), "nome3": (4.7, 5.12)}


def _vero(t: float, p: Palco) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_VERO
    camadas = []
    if t < b["lupa"][1]:
        encolhe = ease_in_out_cubic(trecho(t, 0.45, 1.05))
        some = trecho(t, 0.98, 1.12)
        camadas.append(_c("lupa", cx - 30 * u * (1 - encolhe), cy - 24 * u * (1 - encolhe), icone="lupa", lado=s,
                          escala=(1.2 - 0.62 * encolhe) * (1 - 0.2 * some), giro=-8 * encolhe, opacidade=1 - some,
                          params={"aro": ease_out_cubic(trecho(t, 0.0, 0.5)),
                                  "casa": ease_out_back(trecho(t, 0.12, 0.55), 1.4)}))
    hx, hy = cx, cy + 0.12 * s  # onde a casa nasce
    if b["pino"][0] <= t < b["pino"][1]:
        q = trecho(t, 0.98, 1.4)
        inclina = 14 * ease_in_out_cubic(trecho(t, 1.38, 1.55))
        gira = -400 * ease_in_out_cubic(trecho(t, 1.55, 1.85))
        camadas.append(_c("pino", cx, cy - 40 * u * (1 - ease_out_cubic(q)), icone="pino_vero", lado=0.8 * s,
                          escala=0.5 + 0.5 * ease_out_back(q, 1.6), giro=inclina + gira,
                          opacidade=min(1.0, q * 4) * (1 - trecho(t, 1.66, 1.74))))
    chave = []
    if b["chave"][0] <= t < b["chave"][1]:
        # Contínua de uma fase para a outra (posição e giro), senão o desfoque de movimento mostra "fantasmas".
        aparece = trecho(t, 1.66, 1.74)
        balanco = -30 * math.exp(-3.5 * max(0.0, t - 1.85)) * math.sin(2 * math.pi * 1.4 * max(0.0, t - 1.85))
        a0, r0 = math.radians(-50), 0.66 * s
        inicio_volta = (hx + r0 * math.cos(a0), hy + 0.02 * s + r0 * math.sin(a0) * 0.92)
        if t < 1.85:  # termina o giro do pino já como chave (-386° = -26°)
            giro = 374 - 400 * ease_in_out_cubic(trecho(t, 1.55, 1.85))
            x, y = cx, cy
        elif t < 2.4:  # sobe para o lado da casa balançando, como pendurada na argola
            q = ease_in_out_cubic(trecho(t, 1.85, 2.4))
            x, y = cx + (inicio_volta[0] - cx) * q, cy + (inicio_volta[1] - cy) * q
            giro = -26 + balanco
        else:  # dá a volta na casa até a porta, gira na fechadura e entra
            q = ease_in_out_cubic(trecho(t, 2.4, 2.86))
            ang = a0 + math.radians(140) * q
            raio = r0 - 0.34 * s * q
            x, y = hx + raio * math.cos(ang), hy + 0.02 * s + raio * math.sin(ang) * (0.92 + 0.08 * q)
            giro = -26 + balanco + 26 * q + 90 * ease_in_out_cubic(trecho(t, 2.86, 3.0))
        entra = trecho(t, 2.6, 2.86)
        chave.append(_c("chave", x, y, icone="chave", lado=0.85 * s, escala=1 - 0.86 * ease_in_out_cubic(entra),
                        giro=giro, opacidade=aparece * (1 - trecho(t, 2.9, 3.0))))
    if t < 2.62:  # atrás da casa enquanto dá a volta; na frente quando chega à porta
        camadas += chave
    if b["casa"][0] <= t < b["casa"][1]:
        nasce = ease_out_back(trecho(t, 2.0, 2.45), 1.3)
        pulso = 0.05 * math.sin(math.pi * trecho(t, 2.96, 3.2))
        antecipa = 0.07 * ease_out_cubic(trecho(t, 3.15, 3.27))
        fecha = ease_in_cubic(trecho(t, 3.27, 3.52))
        camadas.append(_c("casa", hx, hy, icone="casa_vero", lado=s,
                          escala=(nasce + pulso + antecipa) * (1 - fecha), giro=-12 * fecha,
                          params={"luz": ease_out_cubic(trecho(t, 2.95, 3.15)),
                                  "janelas": 1 - trecho(t, 3.22, 3.36)}))
    if t >= 2.62:
        camadas += chave
    camadas += faiscas("f", t, *b["faiscas"][:1], 0.52, hx, hy - 0.05 * s, 9, 0.5 * s, 0.95 * s, 46 * u,
                       [BRANCO, CARAMELO, BRANCO], 7)
    camadas += lampejo("lampejo", t, 3.48, hx, hy, 0.32 * s, BRANCO)
    camadas += onda("anel1", t, 3.52, 0.78, cx, cy, 0.1 * s, 1.3 * s, 2.6 * u, CARAMELO)
    camadas += onda("anel2", t, 3.66, 0.7, cx, cy, 0.1 * s, 1.0 * s, 2.0 * u, CARAMELO, 0.5)
    batidas = {**b, "chave": b["chave_logo"]}
    return camadas + logo(t, p, batidas)


# ---------------------------------------------------------------- Casa Veraneio

# "queda" (início, toque): o pino cai do topo enquanto a história converge e toca o centro junto do lampejo, das
# faíscas e do anel; quica ~0,53 s (motion_opcoes_comum.QUIQUE) e só então a seta se desenha.
BATIDAS_VERANEIO = {"paisagem": (0.0, 3.25), "chale": (1.2, 3.25), "piscina": (1.45, 3.25), "carro": (1.95, 3.25),
                    "converge": (2.85, 3.25), "queda": (2.86, 3.28), "surge": (2.86, 3.81), "faiscas": (3.25, 3.8),
                    "anel": (3.27, 4.05), "rastro": (3.84, 4.42), "desliza": (4.42, 4.97), "nome1": (4.59, 5.07),
                    "nome2": (4.69, 5.17)}


def _converge(t: float, inicio: float, fim: float, x: float, y: float, cx: float, cy: float, giro: float):
    """Antecipação curta e o voo para o ponto do centro (posição, fator de escala, giro extra)."""
    antes = 0.04 * ease_out_cubic(trecho(t, inicio - 0.15, inicio))
    q = ease_in_cubic(trecho(t, inicio, fim))
    return x + (cx - x) * q, y + (cy - y) * q, (1 + antes) * (1 - 0.95 * q), giro * q


def _veraneio(t: float, p: Palco) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_VERANEIO
    camadas = []
    if t < 3.25:
        hy = cy + 0.3 * s  # horizonte, depois o chão do chalé
        conv = b["converge"]
        linha = ease_out_cubic(trecho(t, 0.0, 0.45))
        x, y2, esc, _ = _converge(t, *conv, cx, hy, cx, cy, 0)
        camadas.append(_c("horizonte", x, y2, icone="faisca", lado=1.5 * s * linha, esticar=(1.0, 0.11),
                          params={"cor": CREME}, opacidade=0.9, escala=esc))
        # o sol nasce atrás do mar (abaixo da onda do fundo não aparece) e depois fica atrás da casa de praia
        vira = ease_in_out_cubic(trecho(t, 1.05, 1.45))
        mont_lado = 1.3 * s
        mont_y = hy - 0.36 * mont_lado + 0.6 * mont_lado * (1 - ease_out_back(trecho(t, 0.1, 0.7), 1.0))
        corte_sol = min(hy, mont_y + 0.03 * mont_lado) if t < 1.05 else hy  # a onda do fundo (mar em linhas)
        sol_lado = 0.8 * s * (1 - 0.25 * vira)
        sol_x = cx - 0.05 * s + 0.4 * s * vira
        sol_y = hy + 0.45 * s - 1.33 * s * ease_out_cubic(trecho(t, 0.3, 1.15)) + 0.1 * s * vira
        visivel = (corte_sol - (sol_y - sol_lado / 2)) / sol_lado
        if visivel > 0:
            x, y2, esc, g = _converge(t, *conv, sol_x, sol_y, cx, cy, -30)
            camadas.append(_c("sol", x, y2, icone="sol", lado=sol_lado, escala=esc, giro=18 * t + g,
                              revela=("baixo", min(1.0, visivel), 2 * u) if visivel < 1 else None))
        if t < 1.45:  # o mar sobe do horizonte e depois encolhe para dentro da casa de praia
            visivel = (hy - (mont_y - mont_lado / 2)) / mont_lado
            if visivel > 0:
                camadas.append(_c("mar", cx, mont_y + 0.25 * s * vira, icone="mar", lado=mont_lado,
                                  escala=1 - 0.55 * vira, opacidade=1 - ease_in_cubic(trecho(t, 1.1, 1.42)),
                                  revela=("baixo", min(1.0, visivel), 2 * u) if visivel < 1 else None))
        if t >= 1.15:
            q = trecho(t, 1.15, 1.6)
            x, y2, esc, g = _converge(t, *conv, cx, hy - 0.012 * s, cx, cy, 20)
            camadas.append(_c("casa", x, y2, icone="casa_praia", lado=1.0 * s, pivo=(0.5, 0.885),
                              escala=ease_out_back(q, 1.3) * esc, giro=g, opacidade=min(1.0, q * 4)))
        if t >= 1.45:
            q = trecho(t, 1.45, 1.85)
            x, y2, esc, g = _converge(t, *conv, cx, hy + 0.2 * s, cx, cy, -20)
            camadas.append(_c("piscina", x, y2, icone="piscina", lado=0.85 * s,
                              escala=(0.7 + 0.3 * ease_out_cubic(q)) * esc, esticar=(1.0, 0.62), giro=g,
                              opacidade=ease_out_cubic(q), params={"fase": (t * 0.7) % 1.0}))
        if t >= 1.95:  # o carro chega pela direita (Thomas, 05/11/2026: no lugar da mala), freia e balança na
            q = trecho(t, 1.95, 2.42)  # suspensão até assentar; as rodas giram com a distância andada
            falta = (p.largura * 0.62 + 0.1 * s) * (1 - ease_out_cubic(q))
            lado = 0.5 * s
            freio = t - 2.3
            giro = 5 * math.exp(-5 * freio) * math.sin(2 * math.pi * 1.8 * freio) if freio > 0 else 0.0
            x, y2, esc, g = _converge(t, *conv, cx + 0.62 * s + falta, hy - 0.012 * s, cx, cy, 35)
            camadas.append(_c("carro", x, y2, icone="carro", lado=lado, pivo=(0.5, 0.8), giro=giro + g, escala=esc,
                              params={"roda": (falta / (2 * math.pi * 0.09 * lado) * 5) % 1.0}))
    camadas += lampejo("lampejo", t, 3.2, cx, cy, 0.34 * s, CREME)
    camadas += faiscas("f", t, b["faiscas"][0], 0.55, cx, cy, 9, 0.35 * s, 1.0 * s, 46 * u,
                       [CREME, CARAMELO, CREME], 11)
    camadas += onda("anel1", t, 3.27, 0.78, cx, cy, 0.1 * s, 1.35 * s, 2.6 * u, CARAMELO)
    camadas += onda("anel2", t, 3.4, 0.7, cx, cy, 0.1 * s, 1.05 * s, 2.0 * u, CREME, 0.35)
    return camadas + logo(t, p, b)


# ---------------------------------------------------------------- Casa Veraneio CORP.

BATIDAS_CORP = {"calendario": (0.0, 1.32), "palco": (1.2, 2.95), "tacas": (2.25, 3.42), "brinde": (2.88, 3.35),
                "converge": (3.05, 3.42), "faiscas": (3.42, 3.95), "anel": (3.44, 4.2), "surge": (3.47, 4.0),
                "rastro": (3.85, 4.4), "desliza": (4.4, 4.95), "nome1": (4.57, 5.05), "nome2": (4.67, 5.15),
                "nome3": (4.85, 5.25)}


def _corp(t: float, p: Palco) -> list:
    u, s, cx, cy, b = p.u, p.s, p.cx, p.cy, BATIDAS_CORP
    camadas = []
    if t < b["calendario"][1]:
        q = trecho(t, 0.04, 0.54)  # o primeiro quadro fica só no fundo
        vira = ease_in_cubic(trecho(t, 1.1, 1.32))
        camadas.append(_c("calendario", cx, cy + 30 * u * (1 - ease_out_cubic(q)) - 20 * u * vira, icone="calendario",
                          lado=0.95 * s, escala=(0.85 + 0.15 * ease_out_back(q, 1.2))
                          * (1 + 0.04 * ease_out_cubic(trecho(t, 1.0, 1.1))),
                          esticar=(1.0, max(0.02, 1 - vira)), opacidade=min(1.0, q * 4) * (1 - trecho(t, 1.24, 1.32)),
                          params={"grade": ease_in_out_cubic(trecho(t, 0.15, 0.62)),
                                  "marca": ease_in_out_cubic(trecho(t, 0.55, 0.95))}))
    if b["palco"][0] <= t < b["palco"][1]:
        apaga = 1 - ease_in_out_cubic(trecho(t, 2.6, 2.95))
        camadas.append(_c("palco", cx, cy + 0.05 * s, icone="palco", lado=1.3 * s, opacidade=apaga,
                          revela=("direita", ease_in_out_cubic(trecho(t, 1.2, 1.55)), 40 * u)))
        luz = ease_out_cubic(trecho(t, 1.5, 1.8)) * apaga
        for lado_sinal, nome in ((-1, "esq"), (1, "dir")):
            q = trecho(t, 1.25 + (0.08 if lado_sinal > 0 else 0), 1.62 + (0.08 if lado_sinal > 0 else 0))
            hx = cx + lado_sinal * 0.55 * s
            hy = cy - 0.62 * s - 0.4 * s * (1 - ease_out_back(q, 1.2))
            varre = 22 + 16 * math.sin(2 * math.pi * (t - 1.5) / 1.3)
            giro = -lado_sinal * varre
            if luz > 0:
                camadas.append(_c(f"feixe_{nome}", hx, hy + 0.05 * s, icone="feixe", lado=1.25 * s, pivo=(0.5, 0.0),
                                  giro=giro, opacidade=luz))
            camadas.append(_c(f"holofote_{nome}", hx, hy, icone="holofote", lado=0.5 * s, pivo=(0.5, 0.22),
                              giro=giro, opacidade=min(1.0, q * 4) * apaga))
    if b["tacas"][0] <= t < b["tacas"][1]:
        entra = ease_out_cubic(trecho(t, 2.25, 2.72))
        encosta = ease_in_out_cubic(trecho(t, 2.72, 2.88))
        recuo = 0.03 * s * math.sin(math.pi * trecho(t, 2.88, 3.08))
        for lado_sinal, nome in ((-1, "esq"), (1, "dir")):
            x = cx + lado_sinal * (0.31 * s - 0.085 * s * encosta + recuo + (p.largura * 0.6) * (1 - entra))
            giro = lado_sinal * (12 * encosta + 6 * (1 - entra))
            x, y, esc, g = _converge(t, *b["converge"], x, cy + 0.05 * s, cx, cy, lado_sinal * 40)
            camadas.append(_c(f"taca_{nome}", x, y, icone="taca", lado=0.95 * s, pivo=(0.5, 0.55), giro=giro + g,
                              escala=esc))
    camadas += faiscas("brinde", t, b["brinde"][0], 0.47, cx, cy - 0.4 * s, 7, 0.06 * s, 0.42 * s, 30 * u,
                       [CREME, CARAMELO], 5)
    camadas += lampejo("lampejo", t, 3.37, cx, cy, 0.34 * s, CREME)
    camadas += faiscas("f", t, b["faiscas"][0], 0.53, cx, cy, 9, 0.35 * s, 1.0 * s, 46 * u,
                       [CREME, CARAMELO, CREME], 3)
    camadas += onda("anel1", t, 3.44, 0.76, cx, cy, 0.1 * s, 1.35 * s, 2.6 * u, CARAMELO)
    camadas += onda("anel2", t, 3.57, 0.7, cx, cy, 0.1 * s, 1.05 * s, 2.0 * u, CREME, 0.35)
    return camadas + logo(t, p, b)


ROTEIROS = {
    "casa_vero": {"duracao": 6.35, "batidas": BATIDAS_VERO, "camadas": _vero},
    "casa_veraneio": {"duracao": 6.4, "batidas": BATIDAS_VERANEIO, "camadas": _veraneio},
    "cv_corporativo": {"duracao": 6.45, "batidas": BATIDAS_CORP, "camadas": _corp},
}
