"""Onda 3, grupo N (31/10/2026): moldes de produção da Casa Veraneio (scripts/max/molde.py; criador_imagens-02,
designer-02) e o "Desdobrar" em 4:5 e 9:16 no PC (scripts/max/desdobrar_formatos.py; designer-07, gestor_trafego-11).
Roda no contêiner (scripts em /repo/scripts) ou no PC (python -m pytest tests/test_onda3_moldes.py), onde o render de
verdade com o Chrome também roda. Fotos e logos fictícios gerados no teste; nada chama o Max.
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest


def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "molde.py").exists():
            return pasta
    return None


@pytest.fixture
def molde():
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não montado")
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    import molde as modulo
    return modulo


def _imagem(caminho: Path, tamanho=(1600, 1200), cor=(90, 140, 110), modo="RGB"):
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new(modo, tamanho, cor).save(caminho)


def _render_falso(chamadas: list):
    """No lugar do Chrome: grava um PNG do tamanho pedido e guarda o HTML usado."""
    def renderizar(html: Path, saida: Path, largura: int, altura: int, espera_ms: int = 0):
        chamadas.append({"html": Path(html).read_text(encoding="utf-8"), "saida": Path(saida), "medida": (largura, altura),
                         "pasta": sorted(p.name for p in Path(html).parent.iterdir())})
        _imagem(Path(saida), (largura, altura))
    return renderizar


SLIDES = [
    {"molde": "capa", "foto": "acervo/fachada.jpg", "kicker": "Casa em destaque", "titulo": "Lodge 999",
     "subtitulo": "Pé na areia", "lodge": 999, "local": "Cidade Fictícia, SP", "pessoas": 16,
     "saida": "entrega/01_capa.png"},
    {"molde": "ficha", "foto": "acervo/fachada.jpg", "lodge": "Lodge 999", "local": "Cidade Fictícia/SP",
     "titulo": "A casa inteira", "subtitulo": "só para o seu grupo", "suites": 8, "pessoas": 16,
     "cta": "Reserve a data do seu grupo", "saida": "entrega/02_ficha_v2.png"},
    {"molde": "fechamento", "kicker": "Réveillon", "titulo": "A virada", "subtitulo": "do seu grupo",
     "linhas": ["8 suítes · até 16 pessoas"], "cta": "Reserve a data", "saida": "entrega/03_fim.png"},
]


def _peca(pasta: Path, slides=SLIDES, formato="1080x1440") -> Path:
    _imagem(pasta / "acervo" / "fachada.jpg")
    (pasta / "molde.json").write_text(json.dumps({"empresa": "casa_veraneio", "formato": formato, "slides": slides},
                                                 ensure_ascii=False), encoding="utf-8")
    return pasta / "molde.json"


def _marcas(pasta: Path) -> Path:
    _imagem(pasta / "CASA_VERANEIO" / "logo_branca.png", (330, 100), (255, 255, 255, 255), "RGBA")
    _imagem(pasta / "CASA_VERANEIO" / "logo_caramelo_texto_creme.png", (330, 100), (217, 161, 91, 255), "RGBA")
    return pasta


# --- Moldes (molde.py) --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("entrada, esperado", [
    ("Morungaba, SP", "Morungaba / SP"), ("Morungaba/SP", "Morungaba / SP"), ("Jurerê Internacional - sc",
                                                                              "Jurerê Internacional / SC"),
    ("Morungaba / SP", "Morungaba / SP"), ("Litoral Norte", "Litoral Norte"),
])
def test_local_sempre_cidade_barra_uf(molde, entrada, esperado):
    assert molde.local_padrao(entrada) == esperado


def test_capa_com_marca_titulo_e_zona_do_formato(molde):
    pagina = molde.montar_html({**SLIDES[0], "titulo": "Lodge <b>999</b>"}, "1080x1920")
    assert 'class="f916 molde-capa"' in pagina and "width:1080px;height:1920px" in pagina
    assert "Lodge &lt;b&gt;999&lt;/b&gt;" in pagina  # texto escapado, nunca HTML do pedido
    assert "Cidade Fictícia / SP" in pagina and "LODGE 999" in pagina and "ATÉ 16 PESSOAS" in pagina
    assert 'src="logo_branca.png"' in pagina and "R$" not in pagina
    fim = molde.montar_html(SLIDES[2])
    assert 'src="logo_caramelo_texto_creme.png"' in fim and "<li>8 suítes · até 16 pessoas</li>" in fim
    css = (molde.PASTA_MOLDES / "casa_veraneio" / "base.css").read_text(encoding="utf-8")
    assert "#00361B" in css and "#D9A15B" in css and "--logo-fim: 135px" in css and "font-weight: 400 900" in css


def test_valor_so_com_pedido(molde):
    with pytest.raises(ValueError, match="com_valor"):
        molde.montar_html({**SLIDES[1], "valor": "R$ 9.000"})
    with pytest.raises(ValueError, match="com_valor"):
        molde.montar_html({**SLIDES[0], "subtitulo": "Réveillon R$ 19.000 a diária"})
    ficha = molde.montar_html({**SLIDES[1], "com_valor": True, "valor": "R$ 9.000", "minimo_noites": 5})
    assert "DIÁRIA" in ficha and "R$ 9.000" in ficha and "MÍNIMO DE 5 NOITES" in ficha
    assert "DIÁRIA" not in molde.montar_html(SLIDES[1])


def test_moldes_so_da_casa_veraneio_e_formatos_conhecidos(molde):
    with pytest.raises(ValueError, match="Casa Veraneio"):
        molde.montar_html(SLIDES[0], empresa="casa_vero")
    with pytest.raises(ValueError, match="Formato"):
        molde.montar_html(SLIDES[0], "1200x628")
    with pytest.raises(ValueError, match="Molde desconhecido"):
        molde.montar_html({"molde": "revista"})


def test_renderiza_todos_os_slides_com_foto_logo_e_saida_na_pasta(molde, tmp_path):
    pytest.importorskip("PIL")
    chamadas = []
    pngs = molde.renderizar(_peca(tmp_path / "peca"), marcas=_marcas(tmp_path / "MARCAS"),
                            renderizador=_render_falso(chamadas))
    assert [p.name for p in pngs] == ["01_capa.png", "02_ficha_v2.png", "03_fim.png"]
    assert all(p.parent == tmp_path / "peca" / "entrega" and p.is_file() for p in pngs)
    assert chamadas[0]["medida"] == (1080, 1440) and 'src="foto_01.jpg"' in chamadas[0]["html"]
    assert {"base.css", "foto_01.jpg", "logo_branca.png"} <= set(chamadas[0]["pasta"])
    assert not (tmp_path / "peca" / "_moldes").exists()  # pasta de trabalho apagada no fim


def test_foto_ou_saida_fora_da_pasta_e_recusada(molde, tmp_path):
    pytest.importorskip("PIL")
    _imagem(tmp_path / "fora.jpg")
    for slide in ({**SLIDES[0], "foto": "../fora.jpg"}, {**SLIDES[2], "saida": "../../roubo.png"}):
        with pytest.raises(ValueError, match="fora da pasta"):
            molde.renderizar(_peca(tmp_path / "peca", [slide]), marcas=tmp_path, renderizador=_render_falso([]))


def test_instrucao_so_para_artes_da_casa_veraneio(molde):
    texto = molde.instrucao("criador_imagens", "casa_veraneio", "visual")
    assert "molde.json" in texto and "Desdobrar" in texto and "com_valor" in texto and "Cidade / UF" in texto
    assert molde.instrucao("criador_imagens", "casa_vero") == ""  # identidade da Vero ainda em rascunho
    assert molde.instrucao("criador_imagens", "casa_veraneio", "texto") == ""
    assert molde.instrucao("editor_video", "casa_veraneio") == ""


def test_render_de_verdade_no_pc(molde, tmp_path):
    """Só no PC (Chrome instalado): os 3 moldes em 3:4 e 9:16 saem no tamanho certo, com o Verde da marca."""
    pytest.importorskip("PIL")
    import renderizar_png
    from PIL import Image

    if not any(Path(c).exists() for c in renderizar_png.CHROMES) and not shutil.which("chrome"):
        pytest.skip("sem Chrome (contêiner)")
    arquivo = _peca(tmp_path / "peca")
    for formato in ("1080x1440", "1080x1920"):
        for png in molde.renderizar(arquivo, formato, tmp_path / formato, marcas=_marcas(tmp_path / "MARCAS")):
            with Image.open(png) as imagem:
                assert imagem.size == tuple(int(v) for v in formato.split("x"))
                if "fim" in png.name:  # fechamento: fundo Verde #00361B no canto
                    assert imagem.convert("RGB").getpixel((5, 5)) == (0, 54, 27)


# --- Desdobrar no PC (scripts/max/desdobrar_formatos.py) ----------------------------------------------------------

@pytest.fixture
def formatos(molde, tmp_path, monkeypatch):
    import comum
    import desdobrar_formatos as modulo

    monkeypatch.setattr(modulo, "RASCUNHOS", tmp_path / "producoes")
    monkeypatch.setattr(comum, "DRIVE", tmp_path / "drive")
    monkeypatch.setattr(comum, "log", lambda *_a: None)
    (tmp_path / "drive" / "MARKETING" / "VERANEIO ｜ CARROSSEL - TESTE").mkdir(parents=True)
    return modulo


def test_desdobra_em_4x5_e_9x16_na_pasta_formatos(formatos, tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    import molde as modulo_molde

    monkeypatch.setattr(modulo_molde, "pasta_marcas", lambda: _marcas(tmp_path / "MARCAS"))
    _peca(tmp_path / "producoes" / "41")
    chamadas = []
    payload = {"raiz": 41, "pasta": "MARKETING/VERANEIO ｜ CARROSSEL - TESTE", "formatos": ["1080x1350", "1080x1920"]}
    texto = formatos.executar(payload, _render_falso(chamadas))
    pasta = tmp_path / "drive" / "MARKETING" / "VERANEIO ｜ CARROSSEL - TESTE" / "FORMATOS"
    assert sorted(p.name for p in pasta.iterdir()) == sorted(
        f"{n}_{r}.png" for n in ("01_capa", "02_ficha", "03_fim") for r in ("4x5", "9x16"))  # _v2 sai do nome
    assert {c["medida"] for c in chamadas} == {(1080, 1350), (1080, 1920)}
    assert "6 arquivo(s)" in texto and "FORMATOS/01_capa_9x16.png" in texto
    formatos.executar(payload, _render_falso([]))  # de novo: nunca troca o que já está no Drive
    assert (pasta / "01_capa_4x5_2.png").is_file()


def test_sem_molde_ou_pasta_fora_do_drive(formatos, tmp_path):
    assert formatos.executar({"raiz": 7, "pasta": "MARKETING/X"}).startswith(formatos.SEM_MOLDE)
    _peca(tmp_path / "producoes" / "8", [{"molde": "revista", "saida": "entrega/x.png"}])
    assert "Molde desconhecido" in formatos.executar({"raiz": 8, "pasta": "MARKETING/X"})
    _peca(tmp_path / "producoes" / "9")
    with pytest.raises(RuntimeError, match="não encontrada"):
        formatos.executar({"raiz": 9, "pasta": "../../fora"})


def test_trabalhador_conhece_o_trabalho_desdobrar(molde):
    import trabalhos_max

    assert "desdobrar" in trabalhos_max.EXECUTORES
