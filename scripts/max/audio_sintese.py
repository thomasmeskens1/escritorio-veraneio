"""Síntese de áudio do Sonoplasta (Thomas, 05/11/2026): assinaturas sonoras e efeitos compostos por código, sem
modelo de IA e sem biblioteca externa (só Python e o ffmpeg para o MP3). O som é 100% nosso: notas, ritmo e timbre
escolhidos aqui.

Sinais são listas de float em mono a 48 kHz; `mixar` soma um som no ponto do tempo; `salvar` normaliza, passa pelo
reverb (Freeverb: 8 filtros pente e 4 passa-tudo por canal, estéreo pelo desvio de atraso) e grava WAV 24 bits + MP3.
"""

import math
import random
import struct
import subprocess
import wave
from pathlib import Path

TAXA = 48000


def nota(nome: str) -> float:
    """Frequência de uma nota ("A4" = 440 Hz; sustenido com #, ex. "F#3")."""
    escala = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    semitom = escala[nome[0]] + (1 if "#" in nome else 0) + 12 * (int(nome[-1]) - 4)
    return 440.0 * 2 ** (semitom / 12)


def _n(segundos: float) -> int:
    return max(1, int(segundos * TAXA))


def mixar(base: list, som: list, inicio: float, ganho: float = 1.0) -> list:
    """Soma `som` em `base` a partir de `inicio` (s), com saída suave de 30 ms no fim (som cortado vira estalo)."""
    i0, n, fecha = int(inicio * TAXA), len(som), min(len(som), _n(0.03))
    if len(base) < i0 + n:
        base.extend([0.0] * (i0 + n - len(base)))
    for k, v in enumerate(som):
        base[i0 + k] += v * ganho * (1.0 if k < n - fecha else (n - k) / fecha)
    return base


def _queda(t: float, ataque: float, queda: float) -> float:
    """Envelope percussivo: sobe em `ataque` e cai 60 dB em `queda` segundos."""
    if t < ataque:
        return t / ataque
    return math.exp(-6.9 * (t - ataque) / queda)


def sino_fm(freq: float, dur: float, razao: float = 1.4, indice: float = 3.0, queda: float = 1.5,
            queda_indice: float = 0.5, ataque: float = 0.002) -> list:
    """Sino / metal por FM (Chowning): `razao` inteira soa afinada, quebrada soa sino; o brilho cai com o tempo."""
    w, wm = 2 * math.pi * freq / TAXA, 2 * math.pi * freq * razao / TAXA
    return [_queda(k / TAXA, ataque, queda) * math.sin(w * k + indice * math.exp(-k / TAXA / queda_indice)
                                                       * math.sin(wm * k)) for k in range(_n(dur))]


def marimba(freq: float, dur: float = 1.2) -> list:
    """Madeira afinada: fundamental redonda e o 4º harmônico curto (a batida da baqueta)."""
    corpo = sino_fm(freq, dur, razao=1.0, indice=0.6, queda=0.9, queda_indice=0.08)
    baqueta = sino_fm(freq * 4, 0.12, razao=1.0, indice=0.2, queda=0.08)
    return mixar(corpo, baqueta, 0, 0.25)


def rhodes(freq: float, dur: float = 2.0) -> list:
    """Piano elétrico quente: FM 1:1 suave e o "tine" agudo curto na entrada."""
    corpo = sino_fm(freq, dur, razao=1.0, indice=1.2, queda=dur, queda_indice=0.35, ataque=0.004)
    return mixar(corpo, sino_fm(freq * 14, 0.15, razao=1.0, indice=0.0, queda=0.12), 0, 0.06)


def vidro(freq: float, dur: float = 1.6) -> list:
    """Taça de cristal: parciais inarmônicos de vidro, cada um com a própria queda (o "tim" do brinde)."""
    som = [0.0] * _n(dur)
    for razao, ganho, queda in ((1.0, 1.0, 1.4), (2.32, 0.45, 0.9), (4.25, 0.25, 0.5), (6.63, 0.12, 0.3)):
        w = 2 * math.pi * freq * razao / TAXA
        for k in range(len(som)):
            som[k] += ganho * _queda(k / TAXA, 0.0008, queda) * math.sin(w * k)
    return som


def corda(freq: float, dur: float = 2.0, brilho: float = 0.5, semente: int = 1) -> list:
    """Corda dedilhada (Karplus-Strong): violão de nylon com `brilho` baixo, aço com alto."""
    rnd = random.Random(semente)
    tamanho = max(2, round(TAXA / freq))
    linha = [rnd.uniform(-1, 1) for _ in range(tamanho)]
    a = 0.5 + 0.49 * brilho
    som = []
    for k in range(_n(dur)):
        v = linha[k % tamanho]
        linha[k % tamanho] = 0.996 * (a * v + (1 - a) * linha[(k + 1) % tamanho])
        som.append(v * _queda(k / TAXA, 0.0, dur))  # a corda se cala dentro de `dur`, sem corte
    return som


def batida(f0: float = 140.0, f1: float = 45.0, dur: float = 0.7, queda: float = 0.5) -> list:
    """Pancada grave (o pino tocando o chão, o tímpano do palco): seno que desce de f0 a f1 e um clique de ataque."""
    som, fase = [], 0.0
    for k in range(_n(dur)):
        t = k / TAXA
        fase += 2 * math.pi * (f1 + (f0 - f1) * math.exp(-t / 0.045)) / TAXA
        som.append(_queda(t, 0.0015, queda) * math.sin(fase))
    return som


def _biquad_banda(sinal: list, freq: float, q: float) -> list:
    w = 2 * math.pi * freq / TAXA
    alfa = math.sin(w) / (2 * q)
    b0, b2, a0, a1, a2 = alfa, -alfa, 1 + alfa, -2 * math.cos(w), 1 - alfa
    x1 = x2 = y1 = y2 = 0.0
    saida = []
    for x in sinal:
        y = (b0 * x + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1, y2, y1 = x1, x, y1, y
        saida.append(y)
    return saida


def clique(ressonancia: float = 2400.0, dur: float = 0.05, q: float = 8.0, semente: int = 2) -> list:
    """Clique mecânico (chave na fechadura, trinco): estalo de ruído que ressoa numa frequência."""
    rnd = random.Random(semente)
    ruido = [rnd.uniform(-1, 1) * _queda(k / TAXA, 0.0003, dur) for k in range(_n(dur))]
    return [v * q * 0.6 for v in _biquad_banda(ruido, ressonancia, q)]


def sopro(dur: float, corte_ini: float, corte_fim: float, pico: float = 0.6, semente: int = 3) -> list:
    """Whoosh / onda do mar: ruído com o filtro abrindo (ou fechando) e o volume em arco até `pico` (fração)."""
    rnd = random.Random(semente)
    n, y, som = _n(dur), 0.0, []
    for k in range(n):
        f = k / n
        corte = corte_ini * (corte_fim / corte_ini) ** f
        y += (1 - math.exp(-2 * math.pi * corte / TAXA)) * (rnd.uniform(-1, 1) - y)
        volume = math.sin(math.pi / 2 * f / pico) if f < pico else math.cos(math.pi / 2 * (f - pico) / (1 - pico))
        som.append(y * volume * 2.2)
    return som


def colchao(freqs: list, dur: float, ataque: float = 0.25, queda: float = 1.2) -> list:
    """Acorde sustentado e quente (pad): senos levemente desafinados entre si, entrada e saída suaves."""
    som = [0.0] * _n(dur)
    for i, f in enumerate(freqs):
        for desvio in (-0.6, 0.6):
            w = 2 * math.pi * (f + desvio * (1 + i * 0.3)) / TAXA
            for k in range(len(som)):
                t = k / TAXA
                env = min(1.0, t / ataque) * min(1.0, max(0.0, (dur - t) / queda))
                som[k] += env * (math.sin(w * k) + 0.18 * math.sin(2 * w * k)) / len(freqs)
    return som


# ---------------------------------------------------------------- reverb e gravação

_PENTES = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)  # Freeverb (atrasos para 44,1 kHz, escalados)
_PASSA_TUDO = (556, 441, 341, 225)


def _freeverb(sinal: list, sala: float, abafar: float, desvio: int) -> list:
    escala = TAXA / 44100
    pentes = [[0.0] * int((d + desvio) * escala) for d in _PENTES]
    filtros = [0.0] * len(pentes)
    pts = [[0.0] * int((d + desvio) * escala) for d in _PASSA_TUDO]
    ip, ia = [0] * len(pentes), [0] * len(pts)
    saida = []
    for x in sinal:
        x *= 0.015
        acc = 0.0
        for j, buf in enumerate(pentes):
            y = buf[ip[j]]
            filtros[j] = y * (1 - abafar) + filtros[j] * abafar
            buf[ip[j]] = x + filtros[j] * sala
            ip[j] = (ip[j] + 1) % len(buf)
            acc += y
        for j, buf in enumerate(pts):
            b = buf[ia[j]]
            buf[ia[j]] = acc + b * 0.5
            acc = b - acc
            ia[j] = (ia[j] + 1) % len(buf)
        saida.append(acc)
    return saida


def salvar(sinal: list, destino: Path, reverb: float = 0.3, sala: float = 0.84, cauda: float = 1.8) -> Path:
    """Normaliza (pico -1 dBFS), soma o reverb estéreo e grava `destino`.wav (24 bits, 48 kHz) e .mp3 (320k)."""
    seco = list(sinal) + [0.0] * _n(cauda)
    pico = max(abs(v) for v in seco) or 1.0
    seco = [v / pico for v in seco]
    canais = []
    for desvio in (0, 23):
        molhado = _freeverb(seco, sala, 0.35, desvio)
        canais.append([s + reverb * m for s, m in zip(seco, molhado)])
    pico = max(abs(v) for c in canais for v in c) or 1.0
    ganho = 0.89 / pico
    fim = len(seco)
    for k in range(fim - 1, 0, -1):  # corta o silêncio do fim (abaixo de -70 dB)
        if abs(canais[0][k]) * ganho > 3e-4 or abs(canais[1][k]) * ganho > 3e-4:
            fim = min(len(seco), k + _n(0.05))
            break
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wav = destino.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(TAXA)
        quadros = bytearray()
        for k in range(fim):
            saida = 1.0 if k < fim - _n(0.04) else (fim - k) / _n(0.04)  # sem estalo no fim
            for c in canais:
                quadros += struct.pack("<i", int(max(-1.0, min(1.0, c[k] * ganho * saida)) * 8388607))[:3]
        w.writeframes(bytes(quadros))
    from motion_video import achar_ffmpeg
    subprocess.run([achar_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
                    "-b:a", "320k", str(destino.with_suffix(".mp3"))], check=True)
    return wav
