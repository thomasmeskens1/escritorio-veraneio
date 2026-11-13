"""Voz no próprio PC, sem custo e sem serviço de terceiros (Thomas, 13/11/2026).

- POST /api/voz/transcrever: o navegador detecta o "Olá Vera" e manda o trecho falado (WAV 16 kHz, mono) para o
  Whisper local, que recebe o vocabulário do escritório (marketing, Lodge, Gestor, Brevo...). O reconhecimento do
  Chrome ouvia "máquina" no lugar de "marketing".
- POST /api/voz/falar: a resposta da Vera na voz Kokoro "Dora" (a escolhida nas amostras), em WAV.

Os modelos ficam em backend/dados/modelos (fora do git): whisper-small (faster-whisper) e kokoro (kokoro-onnx).
A voz e a mistura de timbre ficam em backend/dados/voz.json (sem reiniciar). Um áudio por vez em cada modelo.
"""

import asyncio
import io
import json
import logging
import threading
import wave

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import config
from auth import validar_token

log = logging.getLogger(__name__)
rotas = APIRouter(prefix="/api/voz")

PASTA = config.DADOS_DIR / "modelos"
ARQUIVO_VOZ = config.DADOS_DIR / "voz.json"
MAX_AUDIO_BYTES = 2_500_000      # ~75 s de WAV 16 kHz mono 16 bits
MAX_TEXTO_FALA = 600
TAXA = 16000
# Vocabulário do escritório: o Whisper usa como contexto e acerta os termos da casa.
VOCABULARIO = ("Olá Vera. Escritório Veraneio, Casa Veraneio, Casa Veraneio Corporativo, Casa Vero, Lodge, Lodges, "
               "marketing, Gestor, Gestor de Tráfego, Copywriter, Designer, Criador de Imagens, Social Media, "
               "E-mail Marketing, Brevo, Moviemaker, Editor de Vídeo, Sonoplasta, Analista de Métricas, "
               "Analista de Tendências, Prospectador, Estrategista, Recepcionista, Professor, Despachante, Construtor, "
               "Cérebro, estagiário, Monday, Drive, Reels, stories, carrossel, post, legenda, briefing, check-in, "
               "enxoval, hotel privativo, proposta, funil, lead, campanha, Instagram.")
VOZ_PADRAO = {"voz": "pf_dora", "mistura": [], "velocidade": 1.0, "tom": 0}

_whisper = None
_kokoro = None
_trava_whisper = threading.Lock()
_trava_kokoro = threading.Lock()


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def pcm_do_wav(dados: bytes):
    """WAV PCM 16 bits mono -> float32 em [-1, 1] a 16 kHz (o navegador já manda assim)."""
    import numpy as np

    with wave.open(io.BytesIO(dados)) as arquivo:
        if arquivo.getsampwidth() != 2 or arquivo.getnchannels() != 1:
            raise ValueError("áudio precisa ser WAV PCM 16 bits mono")
        taxa = arquivo.getframerate()
        amostras = np.frombuffer(arquivo.readframes(arquivo.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if taxa != TAXA:  # reamostragem simples (o navegador manda 16 kHz; isto é só uma garantia)
        posicoes = np.linspace(0, len(amostras) - 1, int(len(amostras) * TAXA / taxa))
        amostras = np.interp(posicoes, np.arange(len(amostras)), amostras).astype(np.float32)
    return amostras


def wav_de_pcm(amostras, taxa: int) -> bytes:
    import numpy as np

    saida = io.BytesIO()
    with wave.open(saida, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(taxa)
        arquivo.writeframes((np.clip(amostras, -1, 1) * 32767).astype(np.int16).tobytes())
    return saida.getvalue()


def transcrever(dados: bytes) -> str:
    global _whisper
    amostras = pcm_do_wav(dados)
    with _trava_whisper:
        if _whisper is None:
            from faster_whisper import WhisperModel

            _whisper = WhisperModel(str(PASTA / "whisper-small"), device="cpu", compute_type="int8")
        trechos, _ = _whisper.transcribe(amostras, language="pt", initial_prompt=VOCABULARIO, vad_filter=True,
                                         beam_size=5, condition_on_previous_text=False)
        return " ".join(t.text.strip() for t in trechos).strip()


def config_voz() -> dict:
    try:
        return {**VOZ_PADRAO, **json.loads(ARQUIVO_VOZ.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(VOZ_PADRAO)


def falar(texto: str) -> bytes:
    """Kokoro: a voz base e, se configurada, a mistura de timbre (ex.: [["af_heart", 0.6]]) e o tom em semitons.

    Tom sem perder a naturalidade: gera com a velocidade dividida por r e grava o WAV com a taxa multiplicada por r,
    então a voz sobe (ou desce) r vezes e o ritmo volta ao normal (opções de 13/11/2026)."""
    global _kokoro
    voz = config_voz()
    with _trava_kokoro:
        if _kokoro is None:
            from kokoro_onnx import Kokoro

            _kokoro = Kokoro(str(PASTA / "kokoro" / "kokoro-v1.0.onnx"), str(PASTA / "kokoro" / "voices-v1.0.bin"))
        estilo = _kokoro.get_voice_style(voz["voz"])
        resto = 1 - sum(peso for _, peso in voz["mistura"])
        estilo = estilo * resto + sum(_kokoro.get_voice_style(nome) * peso for nome, peso in voz["mistura"])
        fator = 2 ** (float(voz["tom"]) / 12)
        amostras, taxa = _kokoro.create(texto, voice=estilo, speed=float(voz["velocidade"]) / fator, lang="pt-br")
    return wav_de_pcm(amostras, int(round(taxa * fator)))


@rotas.post("/transcrever")
async def rota_transcrever(request: Request, authorization: str = Header("")):
    _usuario(authorization)
    dados = await request.body()
    if not dados or len(dados) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Áudio vazio ou longo demais (até 75 s).")
    try:
        texto = await asyncio.to_thread(transcrever, dados)
    except (ValueError, wave.Error, EOFError) as erro:
        raise HTTPException(status_code=422, detail=f"Áudio inválido: {erro}") from erro
    return {"texto": texto}


class Fala(BaseModel):
    texto: str = Field(min_length=1, max_length=MAX_TEXTO_FALA)


@rotas.post("/falar")
async def rota_falar(fala: Fala, authorization: str = Header("")):
    _usuario(authorization)
    wav = await asyncio.to_thread(falar, fala.texto.strip())
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@rotas.get("/disponivel")
async def disponivel(authorization: str = Header("")):
    """O navegador só usa a voz local quando os modelos estão no PC (senão fica a voz do navegador)."""
    _usuario(authorization)
    estado = {"transcrever": (PASTA / "whisper-small" / "model.bin").exists(),
              "falar": (PASTA / "kokoro" / "kokoro-v1.0.onnx").exists()}
    if (estado["transcrever"] and _whisper is None) or (estado["falar"] and _kokoro is None):
        # Microfone ligado: carrega os modelos já (a 1ª transcrição levava ~10 s; depois, ~3 s)
        threading.Thread(target=_aquecer, args=(estado,), daemon=True).start()
    return estado


def _aquecer(estado: dict) -> None:
    import numpy as np

    try:
        if estado["transcrever"] and _whisper is None:
            transcrever(wav_de_pcm(np.zeros(TAXA // 2, dtype=np.float32), TAXA))
        if estado["falar"] and _kokoro is None:
            falar("Olá.")
    except Exception:  # noqa: BLE001 - aquecer nunca derruba nada; o pedido real mostra o erro
        log.exception("aquecimento da voz local falhou")
