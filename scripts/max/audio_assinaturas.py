"""Candidatas da assinatura sonora das três marcas (Thomas, 05/11/2026: "algo único e viral, como o Tu Dum da
Netflix"), para ele ouvir e escolher; ainda não entram na vinheta. Cada uma tem 1 a 3 s, nasce de um elemento da
história visual da marca e termina num acorde maior aberto (calor, chegada).

Uso: python audio_assinaturas.py <pasta>  →  <pasta>/<MARCA>/<Marca>_<letra>_<nome>.wav e .mp3
"""

import sys
from pathlib import Path

from audio_sintese import (batida, clique, colchao, corda, marimba, mixar, nota, rhodes, salvar, sino_fm, sopro,
                           vidro)


# ---------------------------------------------------------------- Casa Veraneio (praia; o pino cai e quica)

def veraneio_pino_na_areia():
    """"Tum-plim": o pino toca a areia (pancada grave e macia) e o quique vira duas notas de marimba subindo."""
    s = batida(120, 48, 0.8, 0.45)
    mixar(s, marimba(nota("G4")), 0.01, 0.55)
    mixar(s, marimba(nota("E5"), 1.6), 0.2, 0.6)
    return mixar(s, marimba(nota("B5"), 1.6), 0.2, 0.25), 0.35


def veraneio_violao_por_do_sol():
    """"Trrum-pling": um acorde de violão de nylon (Ré com 7ª e 9ª, bossa) e um harmônico de sino no alto."""
    s = []
    for i, n in enumerate(("D3", "A3", "C#4", "E4", "F#4")):
        mixar(s, corda(nota(n), 2.4, brilho=0.25, semente=i + 1), i * 0.022, 0.5)
    return mixar(s, sino_fm(nota("A5"), 1.8, razao=2.0, indice=1.0, queda=1.5), 0.38, 0.35), 0.3


def veraneio_quique_de_mola():
    """"Tum-ti-di-dim": a pancada e o quique em notas de steel drum que ficam mais curtas, como a mola assentando."""
    s = batida(110, 46, 0.7, 0.4)
    for t, n, g in ((0.0, "C5", 0.6), (0.22, "G5", 0.5), (0.36, "E5", 0.35), (0.46, "C6", 0.45)):
        mixar(s, sino_fm(nota(n), 1.4, razao=1.0, indice=2.2, queda=1.1, queda_indice=0.12), t, g)
    return s, 0.3


def veraneio_onda_que_chega():
    """"Shhh-plim": uma onda (ruído abrindo e fechando) quebra na praia e vira um acorde de marimba (Dó com 9ª)."""
    s = sopro(1.1, 250, 2200, pico=0.7)
    mixar(s, batida(100, 50, 0.5, 0.3), 0.76, 0.4)
    for i, n in enumerate(("C4", "E4", "G4", "B4", "D5")):
        mixar(s, marimba(nota(n), 1.8), 0.76 + i * 0.03, 0.4)
    return s, 0.4


# ---------------------------------------------------------------- Casa Veraneio CORP. (eventos; o brinde)

def corp_tim_tim():
    """"Tim-tim, aaah": duas taças se tocam (cristal afinado) e o acorde do salão abre por baixo."""
    s = vidro(nota("E6"), 1.8)
    mixar(s, vidro(nota("B6"), 1.8), 0.15, 0.8)
    for n in ("E3", "B3", "G#4", "D#5"):
        mixar(s, rhodes(nota(n), 2.0), 0.3, 0.3)
    return s, 0.35


def corp_abre_o_palco():
    """"Tu-dum, taaam": duas batidas de tímpano (a segunda mais alta) e um acorde de metais que se abre."""
    s = batida(85, 52, 1.0, 0.8)
    mixar(s, batida(110, 66, 1.2, 0.9), 0.26, 1.0)
    for n in ("C4", "G4", "E5"):
        mixar(s, sino_fm(nota(n), 1.6, razao=1.0, indice=3.5, queda=1.6, queda_indice=0.6, ataque=0.06), 0.27, 0.3)
    return s, 0.3


def corp_holofote():
    """"Fuuu-tchac-plim": a luz sobe (ruído subindo), o holofote acende (estalo) e a taça brilha sobre o acorde."""
    s = sopro(0.75, 200, 6000, pico=0.96)
    mixar(s, clique(1800, 0.06, 6), 0.72, 0.8)
    mixar(s, vidro(nota("G6"), 1.5), 0.74, 0.5)
    for n in ("G3", "D4", "B4"):
        mixar(s, rhodes(nota(n), 1.8), 0.74, 0.3)
    return s, 0.35


# ---------------------------------------------------------------- Casa Vero (a chave; a casa que acolhe)

def vero_chave_na_porta():
    """"Clic-clac, dum": a chave gira na fechadura (dois cliques) e a casa responde com um acorde quente de piano."""
    s = clique(3000, 0.04, 8, semente=4)
    mixar(s, clique(1700, 0.05, 7, semente=5), 0.09, 0.9)
    for n in ("A3", "E4", "C#5"):
        mixar(s, rhodes(nota(n), 2.2), 0.26, 0.4)
    return s, 0.3


def vero_toc_toc():
    """"Toc-toc, ta-dam": duas batidas de madeira na porta e duas notas de piano subindo (alguém abre)."""
    s = []
    for t in (0.0, 0.16):
        mixar(s, batida(320, 190, 0.15, 0.1), t, 0.7)
        mixar(s, clique(900, 0.03, 4, semente=6), t, 0.4)
    mixar(s, rhodes(nota("E4"), 1.0), 0.42, 0.45)
    mixar(s, rhodes(nota("A4"), 2.0), 0.6, 0.5)
    return mixar(s, rhodes(nota("C#5"), 2.0), 0.6, 0.25), 0.3


def vero_bem_vindo():
    """"Clic, ahhh": um clique leve e um acorde que acolhe crescendo, com um sininho de porta no meio."""
    s = clique(2600, 0.035, 8, semente=7)
    mixar(s, colchao([nota(n) for n in ("A3", "C#4", "E4", "A4")], 1.9, ataque=0.35, queda=1.0), 0.05, 0.9)
    return mixar(s, sino_fm(nota("E6"), 1.4, razao=3.5, indice=1.5, queda=1.2), 0.38, 0.25), 0.4


CANDIDATAS = {
    "CASA VERANEIO": [("Casa_Veraneio_A_pino_na_areia", veraneio_pino_na_areia),
                      ("Casa_Veraneio_B_violao_por_do_sol", veraneio_violao_por_do_sol),
                      ("Casa_Veraneio_C_quique_de_mola", veraneio_quique_de_mola),
                      ("Casa_Veraneio_D_onda_que_chega", veraneio_onda_que_chega)],
    "CASA VERANEIO CORP": [("Corp_A_tim_tim", corp_tim_tim), ("Corp_B_abre_o_palco", corp_abre_o_palco),
                           ("Corp_C_holofote", corp_holofote)],
    "CASA VERO": [("Casa_Vero_A_chave_na_porta", vero_chave_na_porta), ("Casa_Vero_B_toc_toc", vero_toc_toc),
                  ("Casa_Vero_C_bem_vindo", vero_bem_vindo)],
}


def gerar(pasta: Path) -> list[Path]:
    feitos = []
    for marca, lista in CANDIDATAS.items():
        for nome, compor in lista:
            sinal, reverb = compor()
            feitos.append(salvar(sinal, Path(pasta) / marca / nome, reverb=reverb))
            print(feitos[-1], flush=True)
    return feitos


if __name__ == "__main__":
    gerar(Path(sys.argv[1]))
