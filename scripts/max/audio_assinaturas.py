"""Candidatas da assinatura sonora das três marcas (Thomas, 05/11/2026: "algo único e viral, como o Tu Dum da
Netflix"), para ele ouvir e escolher; ainda não entram na vinheta. Cada uma tem 1 a 3 s, nasce de um elemento da
história visual da marca e termina num acorde maior aberto (calor, chegada).

Rodada 2 (05/11/2026): Vero aprovou a "chave na porta" pedindo a chave mais realista (síntese modal: pinos do
cilindro, giro com atrito, trinco na porta de madeira); Veraneio parte do "pino na areia" (a menos pior) com timbres
mais nobres; Corporativo recomeça em quatro direções novas. A rodada 1 está no histórico do git.

Uso: python audio_assinaturas.py <pasta>  →  <pasta>/<MARCA>/<Marca>_<letra>_<nome>.mp3
"""

import random
import sys
from pathlib import Path

from audio_sintese import (TAXA, batida, colchao, marimba, mixar, nota, raspar, ressoar, rhodes, salvar, saturar,
                           sino_fm, sopro, toques, vibrafone)

# Modos (freq Hz, tau s, ganho) medidos de objetos típicos: chave de latão pequena, trinco de aço, porta de madeira,
# taça de cristal (dois modos quase iguais: o batimento do cristal).
CHAVE = [(2350, 0.035, 1.0), (3780, 0.03, 0.8), (5210, 0.025, 0.6), (7130, 0.02, 0.4), (9400, 0.015, 0.25)]
TRINCO = [(820, 0.06, 1.0), (1460, 0.05, 0.7), (2680, 0.04, 0.5), (4300, 0.03, 0.3)]
MADEIRA = [(110, 0.09, 1.6), (185, 0.07, 1.2), (310, 0.05, 0.8), (520, 0.03, 0.4)]
CHAVEIRO = [(4100, 0.12, 1.0), (6300, 0.1, 0.7), (8800, 0.08, 0.5), (3600, 0.11, 0.8), (5900, 0.09, 0.6)]


def _cristal(freq: float) -> list:
    return [(freq, 0.9, 1.0), (freq + 1.7, 0.9, 0.8), (freq * 2.71, 0.45, 0.45), (freq * 5.13, 0.2, 0.2)]


# ---------------------------------------------------------------- Casa Vero (aprovada: a chave na porta)

def _pico(sinal: list, alvo: float) -> list:
    """Leva o pico de uma parte a `alvo`: ressonadores saem com volumes muito diferentes conforme a excitação."""
    maior = max(abs(v) for v in sinal) or 1.0
    return [v * alvo / maior for v in sinal]


def _fechadura(chaveiro: bool) -> list:
    """Chave de verdade: (chaveiro balançando), a chave entra passando pelos pinos, gira raspando e o trinco
    bate na porta de madeira (com o assentamento do ferrolho logo depois). Picos relativos ao acorde (~1,0)."""
    dur = 1.0
    rnd = random.Random(21)
    s = [0.0] * int(dur * TAXA)
    if chaveiro:
        tilin = toques(dur, [(rnd.uniform(0.0, 0.12), rnd.uniform(0.2, 0.5), 0.001) for _ in range(6)], 22)
        mixar(s, _pico(ressoar(tilin, CHAVEIRO), 0.2), 0)
    entra = [0.0] * int(dur * TAXA)
    for i, t in enumerate((0.14, 0.19, 0.245, 0.29, 0.33)):  # cada pino bate num ponto: modos levemente diferentes
        pino = toques(0.12, [(0.0, rnd.uniform(0.6, 1.0), 0.0015)], 23 + i)
        mixar(entra, ressoar(pino, [(f * rnd.uniform(0.9, 1.1), tau * 0.5, g) for f, tau, g in CHAVE]), t)
    mixar(s, _pico(entra, 0.4), 0)
    mixar(s, _pico(ressoar(raspar(dur, 0.13, 0.35, 0.05, 0.004, 24), [(f * 1.07, tau * 0.4, g) for f, tau, g in CHAVE]),
                   0.1), 0)
    mixar(s, _pico(ressoar(raspar(dur, 0.45, 0.58, 0.3, 0.005, 25), TRINCO), 0.3), 0)
    bate = toques(dur, [(0.60, 1.0, 0.003), (0.625, 0.35, 0.002)], 26)
    mixar(s, _pico(ressoar(bate, TRINCO), 0.7), 0)
    return mixar(s, _pico(ressoar(bate, MADEIRA), 0.6), 0)


def _acorde_vero(s: list, inicio: float) -> list:
    for n in ("A3", "E4", "C#5"):
        mixar(s, rhodes(nota(n), 2.2), inicio, 0.33)
    return s


def vero_chave_com_chaveiro():
    """A aprovada com chave realista: o chaveiro tilinta, a chave entra, gira, o trinco abre, e o acorde quente."""
    return _acorde_vero(_fechadura(True), 0.78), 0.22


def vero_chave_sem_chaveiro():
    """A mesma fechadura sem o chaveiro: mais seca e direta, o trinco fica em evidência."""
    return _acorde_vero(_fechadura(False), 0.78), 0.22


# ---------------------------------------------------------------- Casa Veraneio (a partir do "pino na areia")

def _areia(s: list, inicio: float, ganho: float = 0.35) -> list:
    """O "puf" de areia quando o pino toca o chão: ruído grave abafando rápido."""
    return mixar(s, sopro(0.18, 1200, 250, pico=0.08, semente=31), inicio, ganho)


def veraneio_pino_na_areia_ii():
    """"Tum-plim" refinado: pancada mais funda com o "puf" da areia, e o quique vira um par de vibrafone (Mi e Si)
    sobre um acorde quente que fica no ar."""
    s = saturar(batida(95, 40, 0.9, 0.55), 1.6)
    _areia(s, 0.0)
    mixar(s, vibrafone(nota("E5"), 2.2), 0.2, 0.55)
    mixar(s, vibrafone(nota("B5"), 2.2), 0.2, 0.3)
    return mixar(s, colchao([nota(n) for n in ("E3", "B3", "G#4", "F#4")], 2.0, ataque=0.2, queda=1.2), 0.2, 0.45), 0.4


def veraneio_tu_dum_da_praia():
    """"Tu-DUM": duas pancadas graves (o pino toca e quica) e a segunda abre num acorde de praia (Fá com 9ª) com
    vibrafone; a estrutura do "Tu Dum", com o timbre do sol e do mar."""
    s = saturar(batida(80, 38, 0.6, 0.4), 1.8)
    _areia(s, 0.0, 0.25)
    mixar(s, saturar(batida(100, 42, 1.0, 0.8), 1.8), 0.24, 1.0)
    mixar(s, colchao([nota(n) for n in ("F3", "A3", "C4", "E4", "G4")], 2.4, ataque=0.1, queda=1.4), 0.24, 0.6)
    for n in ("C5", "G5"):
        mixar(s, vibrafone(nota(n), 2.2), 0.25, 0.35)
    return s, 0.45


def veraneio_queda_do_topo():
    """"Dlin-dlin-dlin-tum-plim": o pino desce do topo em cascata de vibrafone (pentatônica descendo), toca a areia
    e quica para cima numa nota que abre o acorde: a vinheta inteira em som."""
    s = []
    for i, n in enumerate(("E6", "C#6", "B5", "G#5", "E5")):
        mixar(s, vibrafone(nota(n), 0.9), i * 0.055, 0.22 + 0.04 * i)
    toque = 5 * 0.055
    mixar(s, saturar(batida(95, 40, 0.8, 0.5), 1.6), toque, 1.0)
    _areia(s, toque)
    mixar(s, vibrafone(nota("B5"), 2.2), toque + 0.19, 0.5)
    return mixar(s, colchao([nota(n) for n in ("E3", "B3", "G#4")], 2.0, ataque=0.15), toque + 0.19, 0.4), 0.4


# ---------------------------------------------------------------- Casa Veraneio CORP. (rodada 2: direções novas)

def corp_rolha_de_espumante():
    """"Pop! fsss, aaah": a rolha do espumante estoura, as bolhas sobem e o acorde da festa abre (Sol com 9ª)."""
    dur = 1.8
    rnd = random.Random(41)
    pop = toques(dur, [(0.0, 1.0, 0.004)], 42)
    s = _pico(ressoar(pop, [(520, 0.014, 1.0), (1150, 0.009, 0.6), (240, 0.02, 0.8)]), 0.9)
    bolhas = []
    for _ in range(140):  # bolhas: estalinhos agudos que rareiam
        t = 0.08 + 1.4 * rnd.random() ** 2
        bolha = toques(0.03, [(0.0, rnd.uniform(0.2, 0.6), 0.0006)], rnd.randrange(10 ** 6))
        mixar(bolhas, ressoar(bolha, [(rnd.uniform(3000, 9000), 0.006, 1.0)]), t, 1 - t / 1.6)
    mixar(s, _pico(bolhas, 0.22), 0)
    for n in ("G3", "D4", "A4", "B4"):
        mixar(s, rhodes(nota(n), 2.2), 0.22, 0.35)
    return mixar(s, colchao([nota(n) for n in ("G2", "D3")], 2.2, ataque=0.3), 0.22, 0.4), 0.3


def corp_talher_na_taca():
    """"Tin-tin-tin": o talher na taça pedindo a palavra para o brinde, e o salão responde com um acorde que cresce."""
    dur = 2.6
    batidas = toques(dur, [(t, a, 0.0007) for t, a in ((0.0, 0.8), (0.17, 0.9), (0.34, 1.0))], 43)
    s = _pico(ressoar(batidas, _cristal(nota("D6"))), 0.75)
    mixar(s, colchao([nota(n) for n in ("D3", "A3", "F#4", "E4")], 2.0, ataque=0.45, queda=1.0), 0.5, 0.7)
    for n in ("D4", "A4", "F#5"):
        mixar(s, rhodes(nota(n), 2.0), 0.55, 0.25)
    return s, 0.35


def corp_assinatura_melodica():
    """Quatro notas para lembrar (como as grandes assinaturas melódicas): Sol, Ré, Si e o Sol de cima longo, em
    piano elétrico dobrado por vibrafone, com o grave entrando na última."""
    s = []
    for t, n, d in ((0.0, "G4", 0.6), (0.14, "D5", 0.6), (0.28, "B4", 0.6), (0.46, "G5", 2.0)):
        mixar(s, rhodes(nota(n), d + 0.3), t, 0.5)
        mixar(s, vibrafone(nota(n), d + 0.3), t, 0.3)
    mixar(s, saturar(batida(90, 45, 0.8, 0.6), 1.5), 0.46, 0.6)
    return mixar(s, colchao([nota(n) for n in ("G2", "D3", "B3")], 1.8, ataque=0.1), 0.46, 0.45), 0.35


def corp_tu_dum_profundo():
    """"Tu-DUM" de cinema: duas pancadas graves e encorpadas e um acorde de ar que se abre largo, com brilho."""
    s = saturar(batida(70, 36, 0.7, 0.5), 2.2)
    mixar(s, saturar(batida(78, 38, 1.4, 1.1), 2.2), 0.22, 1.1)
    mixar(s, colchao([nota(n) for n in ("C3", "G3", "D4", "E4", "B4")], 2.6, ataque=0.06, queda=1.6), 0.22, 0.7)
    mixar(s, sopro(1.2, 6000, 2500, pico=0.1, semente=44), 0.22, 0.035)
    return mixar(s, sino_fm(nota("G6"), 2.0, razao=3.5, indice=1.2, queda=1.8), 0.24, 0.12), 0.5


CANDIDATAS = {
    "CASA VERANEIO": [("Casa_Veraneio_E_pino_na_areia_II", veraneio_pino_na_areia_ii),
                      ("Casa_Veraneio_F_tu_dum_da_praia", veraneio_tu_dum_da_praia),
                      ("Casa_Veraneio_G_queda_do_topo", veraneio_queda_do_topo)],
    "CASA VERANEIO CORP": [("Corp_D_rolha_de_espumante", corp_rolha_de_espumante),
                           ("Corp_E_talher_na_taca", corp_talher_na_taca),
                           ("Corp_F_assinatura_melodica", corp_assinatura_melodica),
                           ("Corp_G_tu_dum_profundo", corp_tu_dum_profundo)],
    "CASA VERO": [("Casa_Vero_A2_chave_com_chaveiro", vero_chave_com_chaveiro),
                  ("Casa_Vero_A3_chave_sem_chaveiro", vero_chave_sem_chaveiro)],
}


def gerar(pasta: Path) -> list[Path]:
    feitos = []
    for marca, lista in CANDIDATAS.items():
        for nome, compor in lista:
            sinal, reverb = compor()
            feitos.append(salvar(sinal, Path(pasta) / marca / nome, reverb=reverb, manter_wav=False))
            print(feitos[-1], flush=True)
    return feitos


if __name__ == "__main__":
    gerar(Path(sys.argv[1]))
