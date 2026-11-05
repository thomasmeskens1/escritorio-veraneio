"""Trilha das vinhetas do logo (Thomas, 05/11/2026): a assinatura sonora aprovada de cada marca, no tempo validado,
mais pequenos efeitos a cada troca de quadro ("senti falta de pequenos efeitos conforme os frames trocam").

Os tempos vêm das BATIDAS de motion_roteiros (as mesmas que movem a animação), então som e imagem andam juntos se
o roteiro mudar. Os efeitos ficam bem abaixo da assinatura (picos de 0,1 a 0,35 contra ~1,0): são acabamento, e
só até a assinatura começar; dali em diante ela soa sozinha (efeitos depois dela ficam no roteiro, mas fora da
mixagem: `efeitos_antes_da_assinatura`).

Uso: python audio_vinhetas.py <empresa> <vinheta.mp4> <saida.mp4>   (ou só <empresa> <saida.mp3> para a trilha)
"""

import math
import random
import subprocess
import sys
from pathlib import Path

from audio_assinaturas import corp_talher_na_taca, veraneio_queda_do_topo, vero_chave_na_porta
from audio_sintese import (TAXA, batida, clique, mixar, nota, raspar, ressoar, salvar, sino_fm, sopro, toques,
                           vibrafone)
from motion_roteiros import BATIDAS_CORP, BATIDAS_VERANEIO, BATIDAS_VERO, ROTEIROS


def _pico(sinal: list, alvo: float) -> list:
    maior = max(abs(v) for v in sinal) or 1.0
    return [v * alvo / maior for v in sinal]


# ---------------------------------------------------------------- efeitos curtos (todos com pico 1,0)

def swish(dur: float = 0.35, sobe: bool = True, semente: int = 51) -> list:
    """Passagem de ar: algo entra ou sai de cena (filtro abrindo ao subir, fechando ao sair)."""
    return _pico(sopro(dur, 400 if sobe else 3500, 3500 if sobe else 400, pico=0.6, semente=semente), 1.0)


def suga(dur: float = 0.4) -> list:
    """Tudo converge para o centro: ar que cresce e corta seco no ponto (contrário do whoosh)."""
    return _pico(sopro(dur, 300, 5000, pico=0.97, semente=52), 1.0)


def pop(freq: float = 520.0) -> list:
    """Um ícone nasce: "plop" redondo (seno caindo rápido de tom) com um estalo levíssimo."""
    s = batida(freq, freq * 0.45, 0.16, 0.09)
    return _pico(mixar(s, clique(freq * 5, 0.01, 3, semente=53), 0, 0.15), 1.0)


def gota() -> list:
    """Água (a piscina): "bloop" que sobe de tom, como gota caindo na superfície."""
    som, fase = [], 0.0
    for k in range(int(0.12 * TAXA)):
        t = k / TAXA
        fase += 2 * math.pi * (350 + 900 * (1 - math.exp(-t / 0.03))) / TAXA
        som.append(math.sin(fase) * math.exp(-t / 0.035) * min(1.0, t / 0.002))
    return _pico(som, 1.0)


def brilhos(n: int = 5, dur: float = 0.45, semente: int = 54) -> list:
    """Faíscas: sininhos agudos e curtos espalhados (pentatônica, para nunca desafinar com o acorde)."""
    rnd = random.Random(semente)
    s = []
    for _ in range(n):
        mixar(s, sino_fm(nota(rnd.choice(("E6", "G#6", "B6", "C#7", "E7"))), 0.4, razao=3.5, indice=0.8, queda=0.3),
              rnd.uniform(0, dur), rnd.uniform(0.4, 1.0))
    return _pico(s, 1.0)


def tique(semente: int = 55) -> list:
    """Texto entrando: toque seco e macio, quase só sentido."""
    return _pico(clique(2200, 0.02, 4, semente=semente), 1.0)


def folha() -> list:
    """Página virando (o calendário): dois roçares rápidos de papel."""
    s = sopro(0.09, 5000, 1800, pico=0.3, semente=56)
    return _pico(mixar(s, sopro(0.07, 4000, 1500, pico=0.2, semente=57), 0.07, 0.7), 1.0)


def caneta(dur: float = 0.4) -> list:
    """O círculo sendo marcado no calendário: risco de caneta (atrito agudo e leve)."""
    return _pico(ressoar(raspar(dur + 0.05, 0.0, dur, 0.4, 0.003, 58), [(3200, 0.004, 1.0), (5200, 0.003, 0.6)]), 1.0)


def holofote() -> list:
    """Holofote acendendo: "clunk" do relé com um grave curto de metal."""
    s = batida(160, 90, 0.18, 0.1)
    return _pico(mixar(s, clique(1400, 0.05, 6, semente=59), 0, 0.8), 1.0)


def carro(dur: float = 0.5) -> list:
    """O carro chega: passagem de ar com motor grave e a freada assentando na suspensão no fim."""
    ar = sopro(dur, 300, 1400, pico=0.55, semente=60)
    motor, fase = [], 0.0
    for k in range(int(dur * TAXA)):
        f = k / (dur * TAXA)
        fase += 2 * math.pi * (95 - 35 * f) / TAXA
        motor.append(0.5 * math.sin(fase) * math.sin(math.pi * min(1.0, f * 1.1)))
    s = mixar(ar, motor, 0)
    return _pico(mixar(s, batida(110, 60, 0.15, 0.1), dur * 0.75, 0.5), 1.0)


def onda_mar(dur: float = 0.7) -> list:
    """O mar subindo do horizonte: uma onda pequena e macia."""
    return _pico(sopro(dur, 250, 1500, pico=0.65, semente=61), 1.0)


def nascer_do_sol(dur: float = 0.8) -> list:
    """O sol subindo: um vibrafone suave que sobe uma quinta (Mi → Si)."""
    s = vibrafone(nota("E5"), 0.9)
    return _pico(mixar(s, vibrafone(nota("B5"), 1.0), dur * 0.45, 0.8), 1.0)


def tilintar(semente: int = 62) -> list:
    """A chave balançando pendurada na argola: dois toques metálicos curtos."""
    s = ressoar(toques(0.3, [(0.0, 1.0, 0.001), (0.09, 0.6, 0.001)], semente),
                [(4100, 0.08, 1.0), (6300, 0.06, 0.7), (8800, 0.05, 0.5)])
    return _pico(s, 1.0)


# ---------------------------------------------------------------- roteiros sonoros

def _veraneio():
    b = BATIDAS_VERANEIO
    return veraneio_queda_do_topo, 3.005, [
        (0.0, swish(0.45), 0.18),                      # a linha do horizonte se desenha
        (0.1, onda_mar(0.7), 0.22),                    # o mar sobe
        (0.45, nascer_do_sol(), 0.2),                  # o sol nasce atrás do mar
        (1.2, pop(420), 0.3),                          # a casa de praia surge
        (1.48, gota(), 0.25),                          # a piscina aparece
        (b["carro"][0], carro(0.5), 0.3),              # o carro chega e freia
        (b["converge"][0] - 0.1, suga(0.4), 0.2),      # tudo converge para o centro
        (b["faiscas"][0], brilhos(), 0.18),            # faíscas no toque do pino
        (b["rastro"][0], swish(0.5), 0.15),            # a seta orbital se desenha
        (b["desliza"][0], swish(0.4, sobe=False), 0.15),
        (b["nome1"][0], tique(), 0.12), (b["nome2"][0], tique(63), 0.1),
    ]


def _corp():
    b = BATIDAS_CORP
    grade = [(0.15 + 0.47 * i / 20, tique(70 + i), 0.05) for i in range(0, 20, 2)]  # as casas do mês em cascata
    return corp_talher_na_taca, 2.54, [
        (0.04, pop(480), 0.28),                        # o calendário aparece
        *grade,
        (0.55, caneta(0.4), 0.18),                     # o dia marcado com o círculo
        (1.1, folha(), 0.25),                          # o calendário vira
        (1.2, swish(0.35), 0.18),                      # o palco se revela
        (1.5, holofote(), 0.3), (1.58, holofote(), 0.25),  # os dois holofotes acendem
        (b["tacas"][0], swish(0.45), 0.2),             # as taças entram pelos lados
        (b["converge"][0] - 0.05, suga(0.37), 0.18),
        (b["faiscas"][0], brilhos(semente=71), 0.18),
        (b["rastro"][0], swish(0.5), 0.15),
        (b["desliza"][0], swish(0.4, sobe=False), 0.15),
        (b["nome1"][0], tique(), 0.12), (b["nome2"][0], tique(72), 0.1), (b["nome3"][0], tique(73), 0.1),
    ]


def _vero():
    b = BATIDAS_VERO
    return vero_chave_na_porta, 2.91, [
        (0.0, swish(0.4), 0.18),                       # a lupa se desenha
        (0.15, pop(600), 0.22),                        # a casinha aparece dentro da lupa
        (0.98, pop(480), 0.28),                        # o pino surge
        (1.5, swish(0.35, semente=80), 0.18),          # o pino gira e vira chave
        (1.9, tilintar(), 0.2),                        # a chave balança pendurada
        (2.0, pop(380), 0.28),                         # a casa nasce
        (2.4, swish(0.45, semente=81), 0.16),          # a chave dá a volta até a porta
        (b["faiscas"][0], brilhos(semente=82), 0.18),  # as janelas acendem e soltam faíscas
        (b["anel"][0], swish(0.5, sobe=False), 0.12),
        (b["chave_logo"][0], tilintar(83), 0.15),      # a chave sobe para dentro do pino do logo
        (b["desliza"][0], swish(0.4, sobe=False), 0.15),
        (b["nome1"][0], tique(), 0.12), (b["nome2"][0], tique(84), 0.1), (b["nome3"][0], tique(85), 0.1),
    ]


TRILHAS = {"casa_veraneio": _veraneio, "cv_corporativo": _corp, "casa_vero": _vero}


def efeitos_antes_da_assinatura(empresa: str) -> list:
    """Só os efeitos que terminam antes de a assinatura começar: quando o som característico assume, os efeitos
    saem (Thomas, 05/11/2026: "a sobreposição não ficou agradável e poluiu o áudio")."""
    _compor, inicio, efeitos = TRILHAS[empresa]()
    return [(t, som, ganho) for t, som, ganho in efeitos if t + len(som) / TAXA <= inicio]


def trilha(empresa: str) -> tuple[list, float]:
    """A trilha mono da vinheta inteira (duração do roteiro) e o reverb da assinatura."""
    compor, inicio, _efeitos = TRILHAS[empresa]()
    assinatura, reverb = compor()
    s = [0.0] * int(ROTEIROS[empresa]["duracao"] * TAXA)
    for t, som, ganho in efeitos_antes_da_assinatura(empresa):
        mixar(s, som, t, ganho)
    mixar(s, _pico(assinatura, 1.0), inicio)
    return s[:int(ROTEIROS[empresa]["duracao"] * TAXA)], reverb


def montar(empresa: str, video: Path, saida: Path) -> Path:
    """Põe a trilha no MP4 da vinheta (vídeo copiado, áudio AAC 256k), do tamanho do vídeo."""
    sinal, reverb = trilha(empresa)
    saida = Path(saida)
    mp3 = salvar(sinal, saida.with_name(saida.stem + "_trilha"), reverb=reverb, cauda=0.0, manter_wav=False)
    from motion_video import achar_ffmpeg
    subprocess.run([achar_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(mp3),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-af", "apad", "-shortest", str(saida)], check=True)
    mp3.unlink()
    return saida


if __name__ == "__main__":
    if len(sys.argv) == 3:
        sinal, reverb = trilha(sys.argv[1])
        print(salvar(sinal, Path(sys.argv[2]).with_suffix(""), reverb=reverb, cauda=0.0, manter_wav=False))
    else:
        print(montar(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
