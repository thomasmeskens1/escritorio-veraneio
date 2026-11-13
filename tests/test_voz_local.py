"""Voz no PC (13/11/2026): WAV de ida e volta, vocabulário no Whisper, voz configurável e rotas protegidas.
Os modelos são simulados: o teste não carrega Whisper nem Kokoro."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

import voz_local


def test_wav_ida_e_volta():
    onda = np.sin(np.linspace(0, 50, 16000)).astype(np.float32) * 0.5
    volta = voz_local.pcm_do_wav(voz_local.wav_de_pcm(onda, 16000))
    assert len(volta) == 16000 and np.abs(volta - onda).max() < 1e-3
    assert len(voz_local.pcm_do_wav(voz_local.wav_de_pcm(onda, 8000))) == 32000  # reamostra para 16 kHz


def test_whisper_recebe_o_vocabulario(monkeypatch):
    chamada = {}

    class Falso:
        def transcribe(self, amostras, **opcoes):
            chamada.update(opcoes)
            return [SimpleNamespace(text=" Olá Vera, revise o marketing do Lodge 3.")], None

    monkeypatch.setattr(voz_local, "_whisper", Falso())
    texto = voz_local.transcrever(voz_local.wav_de_pcm(np.zeros(8000, dtype=np.float32), 16000))
    assert texto == "Olá Vera, revise o marketing do Lodge 3."
    assert "marketing" in chamada["initial_prompt"] and chamada["language"] == "pt"


def test_voz_configuravel_com_mistura(monkeypatch, tmp_path):
    arquivo = tmp_path / "voz.json"
    monkeypatch.setattr(voz_local, "ARQUIVO_VOZ", arquivo)
    assert voz_local.config_voz()["voz"] == "pf_dora"
    arquivo.write_text(json.dumps({"mistura": [["af_heart", 0.3]], "velocidade": 0.9}), encoding="utf-8")
    pedido = {}

    class Falso:
        def get_voice_style(self, nome):
            return np.full(4, 1.0 if nome == "pf_dora" else 0.0, dtype=np.float32)

        def create(self, texto, voice, speed, lang):
            pedido.update(voice=voice, speed=speed, lang=lang)
            return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr(voz_local, "_kokoro", Falso())
    wav = voz_local.falar("Olá, Thomas.")
    assert wav[:4] == b"RIFF" and pedido["speed"] == 0.9 and pedido["lang"] == "pt-br"
    assert np.allclose(pedido["voice"], 0.7)  # 70% Dora + 30% da outra voz


@pytest.fixture
def cliente():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(voz_local.rotas)
    return TestClient(app)


def test_rotas_exigem_login(cliente):
    assert cliente.post("/api/voz/transcrever", content=b"x").status_code == 401
    assert cliente.post("/api/voz/falar", json={"texto": "oi"}).status_code == 401
    assert cliente.get("/api/voz/disponivel").status_code == 401


def test_audio_vazio_ou_grande_recusado(cliente, monkeypatch):
    monkeypatch.setattr(voz_local, "validar_token", lambda token: {"sub": "teste@exemplo.com"})
    cabecalho = {"Authorization": "Bearer x"}
    assert cliente.post("/api/voz/transcrever", content=b"", headers=cabecalho).status_code == 413
    grande = b"0" * (voz_local.MAX_AUDIO_BYTES + 1)
    assert cliente.post("/api/voz/transcrever", content=grande, headers=cabecalho).status_code == 413
    assert cliente.post("/api/voz/transcrever", content=b"nao e wav", headers=cabecalho).status_code == 422
