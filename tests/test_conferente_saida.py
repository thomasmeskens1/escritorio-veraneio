"""Conferente em todo ponto de saída (Onda 2 de novembro; copywriter-03, cerebro-03, email_marketing-03,
moviemaker-21, sonoplasta-04, designer-06): um motor só (backend/conferente_motor.py) no chat, no Monday, no e-mail,
no vídeo, no áudio e na legenda final; tudo só AVISA, e a única correção é a mecânica, no clique.
Banco temporário (tests/conftest.py); fichas simuladas, dados fictícios.
"""

import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

import cerebro_conferir
import conferente
import conferente_motor as motor
import conferente_rotas
import fichas

ASSINATURA = "Casa Veraneio. A casa inteira é de vocês. O resto, a gente cuida."
LEGENDA = ("Uma casa de verdade — no mesmo lugar, o grupo inteiro.\n\n"
           "Lodge 189 · São Miguel dos Milagres, AL\n6 suítes · até 18 pessoas\n\n"
           f"{ASSINATURA}\nReserve a data do seu grupo pelo link da bio.\n\n#réveillon2027 #alagoas #casavero")
RESPOSTA = f"Aqui está a legenda que combinamos, no tom da marca:\n\n{LEGENDA}\n\nSe quiser, ajusto o gancho."


def _tem(avisos, trecho):
    return any(trecho.lower() in a.lower() for a in avisos)


# ---------------------------------------------------------------- legenda no chat e "Corrigir o mecânico"

def test_acha_a_legenda_dentro_da_resposta():
    legenda = motor.legenda_do_texto(RESPOSTA)
    assert legenda.startswith("Uma casa de verdade") and legenda.endswith("#casavero")
    com_titulo = "Pronto!\n\n**Legenda:**\nPé na areia em Maresias / SP.\n#casaveraneio\n\n---\nObservação interna"
    assert motor.legenda_do_texto(com_titulo) == "Pé na areia em Maresias / SP.\n#casaveraneio"
    assert motor.legenda_do_texto("Resumo do plano de mídia: dois públicos e verba no vencedor.") == ""


def test_corrigir_o_mecanico_so_troca_o_que_nao_muda_o_sentido():
    novo, trocas = motor.corrigir_mecanico(LEGENDA, "casa_veraneio")
    assert "de verdade, no mesmo lugar" in novo and "—" not in novo
    assert "São Miguel dos Milagres / AL" in novo
    assert "#reveillon2027" in novo and "#casavero" not in novo and "#casaveraneio" in novo
    assert len(trocas) == 5
    assert motor.corrigir_mecanico("Lodge 3 em Maresias (SP), de 10–12 pessoas", "")[0] == \
        "Lodge 3 em Maresias / SP, de 10 a 12 pessoas"
    assert motor.corrigir_mecanico("Tudo certo. Lodge 3 · Maresias / SP", "")[1] == []


def test_resposta_do_chat_ganha_a_conferencia_da_legenda():
    texto = conferente.anotar(RESPOSTA, "copywriter", "casa_veraneio", "legenda do Lodge 189")
    assert conferente.TITULO_LEGENDA in texto
    rodape = texto.split(conferente.TITULO_LEGENDA, 1)[1]
    assert _tem([rodape], "travessão") and _tem([rodape], "hashtag")
    # Sem legenda na resposta, sem o bloco da legenda.
    assert conferente.TITULO_LEGENDA not in conferente.anotar("Plano pronto.", "copywriter", "casa_veraneio")


def test_botao_corrigir_o_mecanico():
    resultado = conferente_rotas.corrigir(conferente.anotar(RESPOSTA, "copywriter", "casa_veraneio"))
    assert resultado["antes"].startswith("Uma casa") and "Conferência" not in resultado["antes"]
    assert "—" not in resultado["depois"] and resultado["trocas"]
    assert not _tem(resultado["avisos"], "travessão")  # o que sobra não é mecânico
    assert conferente_rotas.corrigir("Sem legenda aqui.") == {"antes": "", "depois": "", "trocas": [], "avisos": []}
    with pytest.raises(HTTPException):
        conferente_rotas.mecanico(conferente_rotas.PedidoMecanico(texto=RESPOSTA), authorization="Bearer x")


# ---------------------------------------------------------------- ficha, grafia e fotos do Corp

@pytest.fixture
def ficha_189(monkeypatch):
    linha = {"numero": 189, "cidade": "São Miguel dos Milagres", "uf": "AL", "suites": 6, "quartos": None,
             "pessoas": 18, "fonte": "site", "coletado_em": "2026-11-01T10:00:00"}
    monkeypatch.setattr(cerebro_conferir, "_ficha", lambda numero, empresa: linha if numero == "189" else None)
    monkeypatch.setattr(fichas, "ficha", lambda numero, empresa="casa_veraneio", limite=0: (
        "- Lodge 189 — São Miguel dos Milagres - AL (dados de 01/11/2026)\n  - Réveillon: R$ 27.500 a diária")
        if str(numero) == "189" else None)


def test_legenda_final_contra_a_ficha_com_diaria(ficha_189):
    texto = "Lodge 189 · São Miguel dos Milagres / AL\n8 suítes · até 18 pessoas\nRéveillon: diária R$ 30.000"
    avisos = cerebro_conferir.divergencias_da_legenda(texto, "casa_veraneio", hoje=date(2026, 11, 11))
    assert _tem(avisos, "8 suítes") and _tem(avisos, "diária citada") and _tem(avisos, "mais de 7 dias")
    certo = "Lodge 189 · São Miguel dos Milagres / AL\n6 suítes\nRéveillon: diária R$ 27.500"
    assert cerebro_conferir.divergencias_da_legenda(certo, "casa_veraneio", hoje=date(2026, 11, 5)) == []
    # Na Casa Vero nenhum valor vai para a conferência; e o conferente da legenda do Monday já chama a ficha.
    assert not _tem(cerebro_conferir.divergencias_da_legenda("Vero 189 por R$ 1", "casa_vero"), "diária")
    assert _tem(conferente.conferir(texto, "casa_veraneio", "legenda"), "8 suítes")


def test_imovel_sem_ficha_nao_repete_o_aviso_do_pedido():
    assert conferente.conferir("Lodge 998 · Maresias / SP. " + ASSINATURA + " Link da bio. #casaveraneio",
                               "casa_veraneio", "legenda") == []


def test_grafia_e_vetos_de_foto_do_corp():
    assert _tem(conferente.conferir("Féria de janiero: já escolheu?", "casa_veraneio", "email"), "janeiro")
    roteiro = "Slide 2: foto com os convidados no palco e a logo do cliente no telão"
    assert _tem(conferente.conferir(roteiro, "cv_corporativo", "roteiro"), "autorização de imagem")
    assert not _tem(conferente.conferir(roteiro, "casa_veraneio", "roteiro"), "autorização de imagem")
    avisos = motor.fotos(["acervo/Confraternizacao Cliente 2021/foto1.jpg", "acervo/salao.jpg"], "cv_corporativo",
                         2026)
    assert _tem(avisos, "foto antiga") and _tem(avisos, "foto de evento")
    assert motor.fotos(["acervo/Confraternizacao 2021.jpg"], "casa_veraneio", 2026) == []


# ---------------------------------------------------------------- vídeo e áudio

def _cena(duracao, velocidade=None, texto="", **extra):
    cena = {"video": "acervo/x.mp4", "duracao": duracao, "elementos": [{"tipo": "texto", "texto": texto}], **extra}
    if velocidade is not None:
        cena["velocidade"] = velocidade
    return cena


def test_ritmo_premium_do_motion():
    picotado = {"cenas": [_cena(2.6, 1.0) for _ in range(10)]}
    avisos = motor.ritmo_do_video(picotado, "casa_veraneio", "reels do Lodge 32")
    assert _tem(avisos, "take de 2,6 s") and _tem(avisos, "velocidade 1x") and _tem(avisos, "10 takes")
    assert _tem(avisos, "mesma duração")
    assert not _tem(motor.ritmo_do_video(picotado, "casa_veraneio", "reels em 1x"), "velocidade")
    assert not _tem(motor.ritmo_do_video(picotado, "cv_corporativo"), "velocidade")  # decisão 1 em aberto
    calmo = {"cenas": [_cena(5.0), _cena(4.5), _cena(5.5, texto="uma frase curta"), {"fundo": "verde", "duracao": 4}]}
    assert motor.ritmo_do_video(calmo, "casa_veraneio") == []
    muito_texto = {"cenas": [_cena(4.0, texto=" ".join(["palavra"] * 20))]}
    assert _tem(motor.ritmo_do_video(muito_texto, "casa_veraneio"), "20 palavras")


def test_trava_de_paleta_do_video():
    spec = {"cenas": [{"duracao": 4, "elementos": [
        {"tipo": "degrade", "cor": "preto", "opacidade": [0, 0.8]}, {"tipo": "degrade", "cor": "preto", "opacidade": 0.25},
        {"tipo": "degrade", "cor": "preto", "opacidade": 0.5}, {"tipo": "texto", "texto": "Oi", "cor": "#123456"},
        {"tipo": "caixa", "cor": "preto"}, {"tipo": "texto", "texto": "Ok", "cor": "caramelo"}]}]}
    avisos = motor.cores_do_video(spec)
    assert len(avisos) == 4 and _tem(avisos, "degradê de leitura preto") and _tem(avisos, "véu preto em 50%")
    assert _tem(avisos, "#123456") and _tem(avisos, "caixa preto")


FFMPEG = """  Duration: 00:00:42.00, start: 0.000000, bitrate: 256 kb/s
[silencedetect @ 0x1] silence_start: 34.1
[silencedetect @ 0x1] silence_end: 35.6 | silence_duration: 1.5
[silencedetect @ 0x1] silence_start: 40.5
[Parsed_ebur128_0 @ 0x2] Summary:

  Integrated loudness:
    I:         -17.6 LUFS
    Threshold: -27.9 LUFS

  True peak:
    Peak:       -0.4 dBFS
"""


def _saida():
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "conferencia_saida.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            import conferencia_saida

            return conferencia_saida
    pytest.skip("scripts/max não montado")


def test_audio_da_versao_com_som():
    medidas = _saida().ler_medidas(FFMPEG)
    assert medidas["lufs"] == -17.6 and medidas["true_peak"] == -0.4 and medidas["duracao"] == 42.0
    assert medidas["silencios"] == [(34.1, 35.6), (40.5, 42.0)]
    avisos = motor.audio({**medidas, "vinheta_em": 38.0})
    assert _tem(avisos, "-17,6 LUFS") and _tem(avisos, "pico") and _tem(avisos, "no segundo 34")
    assert len(avisos) == 3  # o silêncio depois da vinheta é de propósito
    assert motor.audio({"lufs": -14.3, "true_peak": -1.6, "silencios": [], "duracao": 20}) == []


def _docx(arquivo: Path, texto: str) -> None:
    paragrafos = "".join(f"<w:p><w:r><w:t>{linha}</w:t></w:r></w:p>" for linha in texto.splitlines())
    with zipfile.ZipFile(arquivo, "w") as pacote:
        pacote.writestr("word/document.xml", f"<w:document><w:body>{paragrafos}</w:body></w:document>")


def test_conferencia_da_entrega_no_pc(tmp_path):
    saida = _saida()
    rascunho, entrega = tmp_path / "rascunho", tmp_path / "entrega"
    (rascunho / "acervo").mkdir(parents=True)
    entrega.mkdir()
    (rascunho / "motion.json").write_text(json.dumps({"cenas": [_cena(2.0, 1.0) for _ in range(3)]}), encoding="utf-8")
    (rascunho / "acervo" / "Festa Cliente 2021.jpg").write_bytes(b"x")
    _docx(entrega / "Legenda - Reels.docx", "Casa — de verdade\n" + ASSINATURA)
    linha = saida.conferir(entrega, ["Reels.mp4", "Legenda - Reels.docx"], rascunho, "casa_veraneio", "reels")
    assert linha.startswith("⚠ Conferência da entrega") and "travessão" in linha and "take de 2,0 s" in linha
    assert "foto de evento" not in linha  # só no Corp
    corp = saida.conferir(entrega, ["Reels.mp4"], rascunho, "cv_corporativo", "reels")
    assert "foto de evento" in corp and "velocidade" not in corp
    assert saida.conferir(entrega, [], None, "casa_veraneio") == ""
