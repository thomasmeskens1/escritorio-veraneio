"""Síntese de áudio do Sonoplasta (scripts/max/audio_sintese.py; Thomas, 05/11/2026): notas afinadas, som mixado
sem estalo no fim e as candidatas da assinatura sonora das três marcas com 1 a 3,5 s."""

import sys
import wave
from pathlib import Path

import pytest


@pytest.fixture
def audio():
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "audio_sintese.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            import audio_sintese
            return audio_sintese
    pytest.skip("scripts/max não montado")


def test_notas_afinadas(audio):
    assert audio.nota("A4") == pytest.approx(440.0)
    assert audio.nota("A3") == pytest.approx(220.0)
    assert audio.nota("C4") == pytest.approx(261.63, abs=0.01)
    assert audio.nota("F#4") == pytest.approx(369.99, abs=0.01)


def test_mixar_soma_no_tempo_e_fecha_sem_estalo(audio):
    base = audio.mixar([], [1.0] * audio.TAXA, 0.5)
    assert len(base) == int(1.5 * audio.TAXA)
    assert base[0] == 0.0 and base[int(0.5 * audio.TAXA)] == 1.0
    assert abs(base[-1]) < 0.001  # a saída suave leva o fim a zero


def test_candidatas_das_tres_marcas(audio, monkeypatch, tmp_path):
    import audio_assinaturas
    assert set(audio_assinaturas.CANDIDATAS) == {"CASA VERANEIO", "CASA VERANEIO CORP", "CASA VERO"}
    assert all(len(lista) >= 3 for lista in audio_assinaturas.CANDIDATAS.values())
    nome, compor = audio_assinaturas.CANDIDATAS["CASA VERANEIO"][0]
    sinal, reverb = compor()
    assert 1.0 <= len(sinal) / audio.TAXA <= 3.5 and 0 < reverb < 1
    monkeypatch.setattr(audio.subprocess, "run", lambda *a, **k: None)  # sem ffmpeg: só o WAV
    wav = audio.salvar(sinal[: audio.TAXA // 4], tmp_path / nome, reverb=reverb, cauda=0.2)
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 3, 48000)
        quadros = w.readframes(w.getnframes())
    amostras = [int.from_bytes(quadros[k:k + 3], "little", signed=True) for k in range(0, len(quadros), 3)]
    assert max(abs(a) for a in amostras) / 8388607 <= 0.9  # pico em -1 dBFS, sem distorção
