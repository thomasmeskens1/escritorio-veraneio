"""Peças comuns das opções B, C e D da vinheta (Thomas, 04/11/2026): o símbolo real da empresa em qualquer
pose (posição, escala, achatamento, desfoque), a revelação do nome em quatro estilos, a queda com quique de mola
do pino da Casa Veraneio e o registro de imagens próprias de uma opção (cortina, painel de LED, contorno do logo)
como peças extras do Palco.

A opção A (motion_roteiros.py) não usa nada daqui: continua exatamente como foi aprovada.
"""

import math

from motion_camadas import CORES, ease_in_out_cubic, ease_out_back, ease_out_cubic, trecho
from motion_roteiros import _c, lampejo

CREME = CORES["creme"]


def registrar(p, nome: str, imagem, x: float = 0, y: float = 0) -> None:
    """Imagem própria da opção como peça do Palco (a camada usa peca=nome; x, y = canto na posição final)."""
    from motion_vinheta import Peca
    p.pecas[nome] = Peca(imagem, round(x), round(y))


def base_do_simbolo(p) -> tuple[tuple[float, float], tuple[float, float]]:
    """Ponta de baixo do símbolo na posição final (x, y na tela) e o pivô (fração do sprite) nesse ponto: o eixo
    do achatamento quando o pino toca o chão."""
    peca = p.pecas[p.principal]
    _, _, _, y1 = peca.imagem.getchannel("A").getbbox()
    return (p.simbolo[0], peca.y + y1), (p.pivo[0], y1 / peca.imagem.height)


def centro_do_circulo(p) -> tuple[float, float]:
    """Centro do círculo do pino das montanhas na tela (posição final)."""
    from motion_vinheta import geometria_do_pino
    peca = p.pecas[p.principal]
    geo = geometria_do_pino(peca.imagem.size)
    return peca.x + geo["cx"], peca.y + geo["cy"]


def desliza(t: float, p, intervalo) -> tuple[float, float]:
    """Deslocamento (ox, oy) do símbolo nascido no centro até o lugar dele, como na opção A."""
    q = ease_in_out_cubic(trecho(t, *intervalo))
    return (p.cx - p.simbolo[0]) * (1 - q), (p.cy - p.simbolo[1]) * (1 - q)


# ---------------------------------------------------------------- símbolo e nome

def simbolo(t: float, p, b: dict, x: float, y: float, *, pivo=None, escala: float = 1.0, esticar=(1.0, 1.0),
            giro: float = 0.0, desfoque: float = 0.0, opacidade: float = 1.0, ox: float = 0.0,
            oy: float = 0.0) -> list:
    """O símbolo real na pose pedida ((x, y) = ponto `pivo` do sprite, padrão o centro do pino). A chave da Vero
    sobe para dentro do pino em b["chave"]; a seta orbital do pino das montanhas se desenha em b["rastro"]. Sem a
    batida, a parte já aparece inteira. (ox, oy): quanto o símbolo está fora do lugar final (para o brilho da ponta
    da seta)."""
    u = p.u
    comum = {"pivo": pivo or p.pivo, "escala": escala, "esticar": esticar, "giro": giro}
    camadas = [_c(p.principal, x, y, peca=p.principal, desfoque=desfoque, opacidade=opacidade, **comum)]
    if "chave" in p.pecas:
        k = trecho(t, *b["chave"]) if "chave" in b else 1.0
        if k > 0:
            subida = 0.6 * p.simbolo_altura * escala * (1 - ease_out_back(k, 0.9))
            camadas.append(_c("chave", x, y + subida, peca="chave", desfoque=max(desfoque, 6 * u * (1 - k)),
                              opacidade=min(1.0, k * 4) * opacidade, **comum))
        return camadas
    r = trecho(t, *b["rastro"]) if "rastro" in b else 1.0
    if r > 0:
        from motion_vinheta import geometria_do_pino
        geo = geometria_do_pino(p.pecas["rastro"].imagem.size)
        atual = geo["rastro_inicio"] - (geo["rastro_inicio"] - geo["rastro_fim"]) * ease_in_out_cubic(r)
        camadas.append(_c("rastro", x, y, peca="rastro", desfoque=desfoque, opacidade=opacidade,
                          setor=(geo["cx"], geo["cy"], atual, geo["rastro_inicio"] + 8) if r < 1 else None, **comum))
        if "rastro" in b:
            caixa = p.pecas["rastro"].imagem.getchannel("A").getbbox()
            ponta = (p.pecas["rastro"].x + caixa[2] + ox - 6 * u, p.pecas["rastro"].y + caixa[1] + oy + 6 * u)
            camadas += lampejo("ponta", t, b["rastro"][1] - 0.04, *ponta, 46 * u, CREME)
    return camadas


def nomes(t: float, p, b: dict, estilo: str = "direita", ox: float = 0.0, oy: float = 0.0) -> list:
    """As linhas do nome, cada uma na batida dela (b["nome1"], ...), num de quatro estilos:
    - "direita": sai de trás do símbolo, da esquerda para a direita (como na A);
    - "sobe": sobe de trás de uma linha invisível na base da própria linha (máscara);
    - "varre": aparece de cima para baixo, como uma varredura de tela;
    - "foco": sai do desfoque para o foco, encolhendo um pouco até o tamanho certo."""
    u, camadas = p.u, []
    for nome in p.nomes:
        q = trecho(t, *b[nome])
        if q <= 0:
            continue
        peca = p.pecas[nome]
        w, h = peca.imagem.size
        e = ease_out_cubic(q)
        x, y = peca.x + w / 2 + ox, peca.y + h / 2 + oy
        if estilo == "direita":
            camadas.append(_c(nome, x - 22 * u * (1 - e), y, peca=nome, revela=("direita", e, 70 * u) if q < 1 else None,
                              opacidade=min(1.0, q * 2.5), corte_esq=p.simbolo_direita + ox - 10 * u))
        elif estilo == "sobe":
            desce = 0.9 * h * (1 - e)
            camadas.append(_c(nome, x, y + desce, peca=nome, opacidade=min(1.0, q * 3),
                              revela=("baixo", 1 - desce / h, 0.12 * h) if q < 1 else None))
        elif estilo == "varre":
            camadas.append(_c(nome, x, y, peca=nome, revela=("baixo", e, 0.5 * h) if q < 1 else None))
        else:  # foco
            camadas.append(_c(nome, x, y, peca=nome, escala=1 + 0.05 * (1 - e), desfoque=9 * u * (1 - e),
                              opacidade=e))
    return camadas


# ---------------------------------------------------------------- queda com quique de mola

# Depois do toque: contato (achata e afunda um pouco, como mola), salto curto, contato menor, salto mínimo e o
# último toque. (tipo, duração em s, achatamento ou altura em fração da altura do símbolo, afundamento)
QUIQUE = (("contato", 0.085, 0.12, 0.045), ("salto", 0.21, 0.12, 0.0), ("contato", 0.065, 0.055, 0.018),
          ("salto", 0.12, 0.03, 0.0), ("contato", 0.05, 0.02, 0.006))
ASSENTA = sum(d for _, d, *_ in QUIQUE)  # ~0,53 s do toque até parar


def queda(t: float, inicio: float, toque: float, altura: float, distancia: float):
    """Deslocamento vertical da ponta do pino em relação ao lugar final (px; negativo = acima, positivo = passou do
    ponto) e o (esticar x, y): cai acelerando como gravidade (estica um pouco na vertical), toca, achata e afunda
    como mola, quica curto duas vezes e assenta. None antes do início."""
    if t < inicio:
        return None
    if t < toque:
        q = (t - inicio) / (toque - inicio)
        return -distancia * (1 - q * q), (1 - 0.05 * q * q, 1 + 0.10 * q * q)
    tau = t - toque
    for tipo, dur, a, afunda in QUIQUE:
        if tau < dur:
            f = tau / dur
            if tipo == "contato":
                s = math.sin(math.pi * f)
                return afunda * altura * s, (1 + a * s, 1 - a * s)
            estica = 0.25 * a * (1 - 2 * f) ** 2  # sai e chega esticado, no alto fica redondo
            return -a * altura * 4 * f * (1 - f), (1 - 0.6 * estica, 1 + estica)
        tau -= dur
    return 0.0, (1.0, 1.0)


def pino_caindo(t: float, p, b: dict, ox: float = 0.0):
    """Camadas do pino da Casa Veraneio caindo do topo (b["queda"] = início, toque) e o deslocamento atual da
    ponta (dy). A ponta começa um pouco acima do topo do quadro: o pino entra inteiro de fora."""
    (bx, by), pivo = base_do_simbolo(p)
    estado = queda(t, *b["queda"], p.simbolo_altura, by + 0.04 * p.altura)
    if estado is None:
        return [], None
    dy, esticar = estado
    return simbolo(t, p, b, bx + ox, by + dy, pivo=pivo, esticar=esticar, ox=ox, oy=dy), dy
