"""Sonoplasta (scripts/max/sonoplasta.py; Thomas, 05/11/2026): todo vídeo sai sem som e com som; a faixa vem da
biblioteca da marca, pelo clima do pedido e em rodízio; aprovada ganha das que aguardam; reprovada nunca entra; a
música sai quando a vinheta começa; e o agente tem mesa no setor Vídeo com a biblioteca da marca no contexto."""

import json
import sys
from pathlib import Path

import pytest

FAIXAS = [
    {"marca": "CASA VERANEIO", "estilo": "bossa_nova_praia", "bpm": 100, "clima": "tarde de praia, relaxado",
     "legenda": "bossa nova, nylon guitar", "arquivo": "CASA VERANEIO/bossa.mp3", "status": "para aprovação"},
    {"marca": "CASA VERANEIO", "estilo": "samba_jazz_leve", "bpm": 120, "clima": "verão, festa leve",
     "legenda": "samba jazz, pandeiro", "arquivo": "CASA VERANEIO/samba.mp3", "status": "para aprovação"},
    {"marca": "CASA VERANEIO", "estilo": "balearic_chill", "bpm": 95, "clima": "golden hour, brisa do mar",
     "legenda": "balearic chillout", "arquivo": "CASA VERANEIO/balearic.mp3", "status": "para aprovação"},
    {"marca": "CASA VERO", "estilo": "lofi_groove", "bpm": 90, "clima": "casa aconchegante",
     "legenda": "lofi", "arquivo": "CASA VERO/lofi.mp3", "status": "reprovada"},
    {"marca": "CASA VERO", "estilo": "jazz_hop", "bpm": 88, "clima": "sofisticado",
     "legenda": "jazz hop", "arquivo": "CASA VERO/jazz.mp3", "status": "para aprovação"},
]


@pytest.fixture
def sono(tmp_path, monkeypatch):
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "sonoplasta.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            import sonoplasta
            # nada de Drive, espelho ou rodízio de verdade nos testes
            monkeypatch.setattr(sonoplasta, "BIBLIOTECA", tmp_path / "biblioteca")
            monkeypatch.setattr(sonoplasta, "ESPELHO", tmp_path / "espelho.json")
            monkeypatch.setattr(sonoplasta, "USO", tmp_path / "uso.json")
            return sonoplasta
    pytest.skip("scripts/max não montado")


def test_clima_do_pedido_escolhe_a_faixa(sono):
    assert sono.escolher("casa_veraneio", "reels de réveillon bem animado", itens=FAIXAS)[0]["estilo"] == "samba_jazz_leve"
    assert sono.escolher("casa_veraneio", "Clima da música: Mais calma", itens=FAIXAS)[0]["estilo"] == "balearic_chill"
    assert sono.escolher("casa_veraneio", "quero bossa nova na piscina", itens=FAIXAS)[0]["estilo"] == "bossa_nova_praia"


def test_cada_marca_so_usa_a_propria_biblioteca_e_reprovada_nunca_entra(sono):
    faixas, aprovadas = sono.faixas_da_marca("casa_vero", FAIXAS)
    assert [f["estilo"] for f in faixas] == ["jazz_hop"] and not aprovadas
    assert sono.faixas_da_marca("cv_corporativo", FAIXAS) == ([], False)


def test_aprovada_ganha_das_que_aguardam(sono):
    itens = [dict(f) for f in FAIXAS]
    itens[0]["status"] = "aprovada"
    faixa, aprovada = sono.escolher("casa_veraneio", "reels animado de festa", itens=itens)
    assert faixa["estilo"] == "bossa_nova_praia" and aprovada


def test_rodizio_e_troca_de_musica(sono):
    sono._registrar_uso("CASA VERANEIO/bossa.mp3")
    neutras = [f for f in FAIXAS if f["marca"] == "CASA VERANEIO"]
    assert sono.escolher("casa_veraneio", "", itens=neutras)[0]["arquivo"] != "CASA VERANEIO/bossa.mp3"
    evitar = {"CASA VERANEIO/samba.mp3"}
    assert sono.escolher("casa_veraneio", "bem animado", evitar, itens=FAIXAS)[0]["arquivo"] not in evitar
    assert sono.e_troca_de_musica("Troque a música por uma mais animada")
    assert sono.e_troca_de_musica("pode colocar outra trilha?")
    assert not sono.e_troca_de_musica("aumente o texto da cena 2")


def test_catalogo_do_drive_e_espelhado_e_vale_o_espelho_sem_drive(sono):
    (sono.BIBLIOTECA).mkdir()
    (sono.BIBLIOTECA / "catalogo.json").write_text(json.dumps(FAIXAS), encoding="utf-8")
    assert len(sono.catalogo()) == len(FAIXAS)
    (sono.BIBLIOTECA / "catalogo.json").unlink()  # Drive fora
    assert len(sono.catalogo()) == len(FAIXAS)


def test_musica_sai_quando_a_vinheta_comeca(sono):
    grafo = sono.filtro(30.0, 33.0, 1, 24.0, False)
    assert "adelay=24000" in grafo                    # a trilha da vinheta entra no segundo anotado pelo Editor
    fim = 24.0 + sono.SAI_ANTES_DA_VINHETA_S * 0.3
    assert f"atrim=0:{fim:.3f}" in grafo              # a música para logo depois que a vinheta começa
    assert "loudnorm=I=-14" in grafo
    assert "sidechaincompress" not in grafo           # vídeo sem som próprio: só a música
    assert "sidechaincompress" in sono.filtro(30.0, 33.0, 1, None, True)


def test_video_maior_que_a_faixa_emenda_com_crossfade(sono):
    grafo = sono.filtro(75.0, 33.0, 3, None, False)
    assert grafo.count("acrossfade") == 2 and "[3:a]atrim=0:33.000" in grafo


def test_na_producao_gera_a_versao_com_som_e_nunca_derruba(sono, tmp_path, monkeypatch):
    final = tmp_path / "entrega"
    final.mkdir()
    (final / "reels.mp4").write_bytes(b"x")

    def falso(video, empresa, pedido, rascunho, evitar):
        saida = video.with_name(f"{video.stem}{sono.SUFIXO}{video.suffix}")
        saida.write_bytes(b"y")
        return saida, FAIXAS[0], False

    monkeypatch.setattr(sono, "versao_com_som", falso)
    gerados, linha = sono.na_producao(tmp_path, final, ["reels.mp4", "capa.png"], "casa_veraneio", "reels")
    assert gerados == ["reels_com_som.mp4"] and "ainda em aprovação" in linha
    # ajuste que só troca a música, sem vídeo novo: refaz a versão com som do vídeo que já existe
    gerados, _ = sono.na_producao(tmp_path, final, [], "casa_veraneio", "troque a música", ajuste=True)
    assert gerados == ["reels_com_som.mp4"]

    def quebra(*_args):
        raise RuntimeError("sem faixa")

    monkeypatch.setattr(sono, "versao_com_som", quebra)
    gerados, linha = sono.na_producao(tmp_path, final, ["reels.mp4"], "casa_veraneio", "reels")
    assert gerados == [] and "O vídeo sem som segue normal" in linha


def test_sonoplasta_tem_mesa_no_video_e_ve_a_biblioteca_da_marca(monkeypatch, tmp_path):
    import config
    from agents import perfis
    from estado import ANDARES

    assert ANDARES["marketing"]["sonoplasta"].setor == "video"
    assert "sonoplasta" in perfis.PERFIS
    monkeypatch.setattr(config, "DADOS_DIR", tmp_path)
    (tmp_path / "biblioteca_musicas.json").write_text(json.dumps(FAIXAS), encoding="utf-8")
    texto = perfis._biblioteca_de_musicas("casa_vero")
    assert "jazz hop" in texto and "lofi" not in texto and "bossa" not in texto
    (tmp_path / "biblioteca_musicas.json").unlink()
    assert "Não invente" in perfis._biblioteca_de_musicas("casa_vero")
