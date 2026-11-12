"""Material do MARKETING da Casa Veraneio (12/11/2026): LODGES por categoria e SABORES CV viram fonte das peças e do
Cérebro, só leitura. Pastas fictícias em tmp_path; nada toca o Drive de verdade."""

import sys
from pathlib import Path

import pytest


def _modulo(monkeypatch, tmp_path):
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "acervo_marketing.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts/max não montado")
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade
    import acervo_marketing

    return acervo_marketing


def _arquivo(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"x")


@pytest.fixture
def pastas(tmp_path):
    lodges, sabores = tmp_path / "LODGES", tmp_path / "SABORES CV"
    _arquivo(lodges / "LODGES PRAIA" / "LODGE 112" / "drone.mp4")
    _arquivo(lodges / "LODGES PRAIA" / "LODGE 112" / "sala.jpg")
    _arquivo(lodges / "LODGES CAMPO" / "LODGE 10" / "VIDEOS" / "a.mov")
    _arquivo(lodges / "LODGE 35" / "piscina.jpg")
    _arquivo(lodges / "FORA DO PORTIFOLIO" / "LODGE 46" / "x.jpg")
    _arquivo(lodges / "LODGE 5 - ORLANDO" / "y.jpg")
    _arquivo(sabores / "2025" / "CHEF ANA" / "prato.jpg")
    _arquivo(sabores / "2025" / "CHEF ANA" / "receita.mp4")
    _arquivo(sabores / "A. LOGO ANIMADO" / "Logo Animado Story.mp4")
    return lodges, sabores


def test_lodges_por_categoria_sem_fora_do_portfolio_nem_orlando(monkeypatch, tmp_path, pastas):
    am = _modulo(monkeypatch, tmp_path)
    entradas = {e["lodge"]: e for e in am.catalogar_lodges(pastas[0])}
    assert set(entradas) == {"LODGE 112", "LODGE 10", "LODGE 35"}
    assert entradas["LODGE 112"]["categoria"] == "Praia" and entradas["LODGE 112"]["fotos"] == 1
    assert entradas["LODGE 10"]["categoria"] == "Campo" and entradas["LODGE 10"]["videos"] == 1
    assert entradas["LODGE 35"]["categoria"] == ""
    doc = am.documento_lodge(entradas["LODGE 112"])
    assert "Categoria: Praia" in doc["conteudo"] and doc["fonte_ref"].startswith("drive/marketing/lodges/")
    assert [p.name for p in am.pastas_do_lodge(112, pastas[0])] == ["LODGE 112"]
    assert am.pastas_do_lodge(46, pastas[0]) == [] and am.pastas_do_lodge(5, pastas[0]) == []


def test_sabores_cv_por_episodio_e_envio_so_do_que_mudou(monkeypatch, tmp_path, pastas):
    am = _modulo(monkeypatch, tmp_path)
    episodios = {e["lodge"]: e for e in am.catalogar_sabores(pastas[1])}
    assert episodios["CHEF ANA"]["ano"] == "2025" and episodios["CHEF ANA"]["videos"] == 1
    assert "A. LOGO ANIMADO" in episodios
    assert "gastronomia" in am.documento_sabores(episodios["CHEF ANA"])["conteudo"]
    enviados = []
    args = dict(lodges_raiz=pastas[0], sabores_raiz=pastas[1], arquivo_indice=tmp_path / "indice.md",
                arquivo_hashes=tmp_path / "hashes.json", enviar=lambda docs: enviados.extend(docs) or True)
    r = am.sincronizar(**args)
    assert r["lodges"] == 3 and r["sabores"] == 2 and r["enviados"] == 5
    assert "SABORES CV" in (tmp_path / "indice.md").read_text(encoding="utf-8")
    assert am.sincronizar(**args)["enviados"] == 0  # nada mudou: nada vai de novo ao Cérebro
    _arquivo(pastas[1] / "2025" / "CHEF ANA" / "nova.jpg")
    assert am.sincronizar(**args)["enviados"] == 1
