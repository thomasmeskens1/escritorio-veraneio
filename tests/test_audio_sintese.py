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


def test_ressoar_vibra_na_frequencia_do_modo(audio):
    """Síntese modal: um toque num modo de 1 kHz vibra a 1 kHz (cruzamentos por zero) e vai se calando."""
    som = audio.ressoar(audio.toques(0.2, [(0.0, 1.0, 0.0005)]), [(1000.0, 0.05, 1.0)])
    trecho = som[int(0.02 * audio.TAXA):int(0.06 * audio.TAXA)]
    cruzamentos = sum(1 for a, b in zip(trecho, trecho[1:]) if a < 0 <= b)
    assert 36 <= cruzamentos <= 44  # ~40 ciclos em 40 ms
    assert max(map(abs, som[-1000:])) < 0.05 * max(map(abs, som))


def test_trilha_das_vinhetas_segue_o_roteiro(audio):
    """A trilha tem a duração da vinheta, os efeitos caem dentro dela e a assinatura entra no tempo validado."""
    import audio_vinhetas
    from motion_roteiros import ROTEIROS
    assert set(audio_vinhetas.TRILHAS) == set(ROTEIROS)
    for empresa, montar in audio_vinhetas.TRILHAS.items():
        _compor, inicio, efeitos = montar()
        duracao = ROTEIROS[empresa]["duracao"]
        assert all(0 <= t < duracao and 0 < g <= 0.35 for t, _som, g in efeitos), empresa
        assert 2.0 < inicio < 3.5, empresa
    sinal, _ = audio_vinhetas.trilha("casa_vero")
    assert len(sinal) == int(ROTEIROS["casa_vero"]["duracao"] * audio.TAXA)
    antes = max(map(abs, sinal[int(2.85 * audio.TAXA):int(2.9 * audio.TAXA)]))
    clique = max(map(abs, sinal[int(2.91 * audio.TAXA):int(2.95 * audio.TAXA)]))
    assert clique > 2 * antes  # o clique da chave cai em 2,91 s, no giro


def test_candidatas_das_tres_marcas(audio, monkeypatch, tmp_path):
    import audio_assinaturas
    assert set(audio_assinaturas.CANDIDATAS) == {"CASA VERANEIO", "CASA VERANEIO CORP", "CASA VERO"}
    assert all(len(lista) >= 2 for lista in audio_assinaturas.CANDIDATAS.values())
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
