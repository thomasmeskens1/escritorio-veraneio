"""Onda 3 de novembro: edição rápida no PC, sem o Max (scripts/max/edicao_rapida_pc.py; criador_imagens-03,
designer-02, sonoplasta-02). Roda no contêiner (scripts em /repo/scripts) ou no PC. Render, ffmpeg, Drive e
biblioteca são falsos (pastas temporárias); nada chama o Max nem o backend.
"""

import json
import sys
from pathlib import Path

import pytest

PASTA_PECA = "MARKETING/VERANEIO ｜ CARROSSEL - TESTE"
SLIDES = [
    {"molde": "capa", "foto": "acervo/fachada.jpg", "kicker": "Casa em destaque", "titulo": "Lodge 999",
     "local": "Cidade Fictícia / SP", "lodge": 999, "saida": "entrega/01_capa.png"},
    {"molde": "foto", "foto": "acervo/fachada.jpg", "saida": "entrega/02_foto.png"},
    {"molde": "fechamento", "titulo": "A virada", "linhas": ["8 suítes"], "cta": "Reserve a data",
     "saida": "entrega/03_fim_v2.png"},
]


def _imagem(caminho: Path, tamanho=(200, 260)):
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", tamanho, (90, 140, 110)).save(caminho)


@pytest.fixture
def pc(tmp_path, monkeypatch):
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "edicao_rapida_pc.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts/max não montado")
    pytest.importorskip("PIL")
    import comum
    import edicao_rapida_pc as edicao_rapida
    import molde
    import sonoplasta

    enviados = []
    monkeypatch.setattr(edicao_rapida, "RASCUNHOS", tmp_path / "producoes")
    monkeypatch.setattr(comum, "DRIVE", tmp_path / "drive")
    monkeypatch.setattr(comum, "log", lambda *_a: None)
    monkeypatch.setattr(comum, "enviar_arquivo", lambda caminho, arquivo: enviados.append(caminho))
    monkeypatch.setattr(molde, "pasta_marcas", lambda: tmp_path / "MARCAS")
    monkeypatch.setattr(sonoplasta, "BIBLIOTECA", tmp_path / "biblioteca")
    monkeypatch.setattr(sonoplasta, "ESPELHO", tmp_path / "espelho.json")
    monkeypatch.setattr(sonoplasta, "USO", tmp_path / "uso.json")
    edicao_rapida.enviados = enviados
    return edicao_rapida


def _render_falso(chamadas: list):
    def renderizar(html: Path, saida: Path, largura: int, altura: int, espera_ms: int = 0):
        chamadas.append(Path(html).read_text(encoding="utf-8"))
        _imagem(Path(saida), (108, 144))
    return renderizar


def _peca(tmp_path: Path, raiz: int = 41) -> Path:
    rascunho = tmp_path / "producoes" / str(raiz)
    _imagem(rascunho / "acervo" / "fachada.jpg")
    (rascunho / "molde.json").write_text(json.dumps({"empresa": "casa_veraneio", "formato": "1080x1440",
                                                     "slides": SLIDES}, ensure_ascii=False), encoding="utf-8")
    (rascunho / ".versao").write_text("2")
    entrega = tmp_path / "drive" / PASTA_PECA
    for nome in ("01_capa.png", "02_foto.png", "03_fim.png", "03_fim_v2.png"):
        _imagem(entrega / nome)
    return entrega


def _payload(**extra):
    return {"acao": "textos", "raiz": 41, "pasta": PASTA_PECA, "tarefa_id": 41, **extra}


def test_le_os_campos_editaveis_de_cada_molde(pc, tmp_path):
    _peca(tmp_path)
    lido = json.loads(pc.executar({"acao": "ler", "raiz": 41}))
    capa, foto, fim = lido["slides"]
    assert capa["campos"]["titulo"] == "Lodge 999" and capa["campos"]["contagem"] == {"numero": "", "texto": ""}
    assert foto["campos"] == {} and fim["campos"]["linhas"] == ["8 suítes"] and "cta" in fim["campos"]
    assert pc.executar({"acao": "ler", "raiz": 7}).startswith(pc.SEM_MOLDE)


def test_troca_so_o_slide_alterado_como_nova_versao(pc, tmp_path):
    entrega = _peca(tmp_path)
    chamadas = []
    mudancas = [{"n": 1, "campo": "titulo", "antes": "Lodge 999", "depois": "Lodge 999 no verão"},
                {"n": 1, "campo": "contagem", "antes": {"numero": "", "texto": ""},
                 "depois": {"numero": "45", "texto": "noites para o Réveillon"}},
                {"n": 3, "campo": "cta", "antes": "Reserve a data", "depois": "Reserve a data"}]  # igual: nada muda
    texto = pc.executar(_payload(mudancas=mudancas), _render_falso(chamadas))
    assert len(chamadas) == 1 and "Lodge 999 no verão" in chamadas[0] and "45" in chamadas[0]  # só a capa
    assert (entrega / "01_capa_v3.png").is_file() and (entrega / "01_capa.png").is_file()  # a anterior fica
    assert (entrega / "EDITÁVEL" / "receita_v3.json").is_file()
    receita = json.loads((entrega / "EDITÁVEL" / "receita_v3.json").read_text(encoding="utf-8"))
    assert "Lodge 999 no verão" in receita["textos"] and receita["conferencia"]["origem"].startswith("edição rápida")
    rascunho = tmp_path / "producoes" / "41"
    novo = json.loads((rascunho / "molde.json").read_text(encoding="utf-8"))
    assert novo["slides"][0]["saida"] == "entrega/01_capa_v3.png" and novo["slides"][2]["saida"] == "entrega/03_fim_v2.png"
    assert json.loads((rascunho / "molde_anteriores" / "molde_v2.json").read_text(encoding="utf-8"))["slides"][0]["titulo"] == "Lodge 999"
    assert (rascunho / ".versao").read_text() == "3"
    final = entrega / "FINAL"
    assert sorted(p.name for p in final.glob("*.png")) == ["01_capa.png", "02_foto.png", "03_fim.png"]
    assert (final / "01_capa.png").stat().st_size == (entrega / "01_capa_v3.png").stat().st_size  # a vigente
    assert pc.enviados == ["/api/producao/41/folha"]  # folha de aprovação refeita e enviada ao chat
    assert "versão 3" in texto and "título" in texto and "PPTX" in texto


def test_texto_que_mudou_depois_ou_valor_na_arte_e_recusado(pc, tmp_path):
    _peca(tmp_path)
    with pytest.raises(ValueError, match="abra"):
        pc.executar(_payload(mudancas=[{"n": 1, "campo": "titulo", "antes": "Outro", "depois": "X"}]), _render_falso([]))
    with pytest.raises(ValueError, match="com_valor"):
        pc.executar(_payload(mudancas=[{"n": 1, "campo": "titulo", "antes": "Lodge 999", "depois": "R$ 900"}]),
                    _render_falso([]))
    with pytest.raises(ValueError, match="não tem o campo"):
        pc.executar(_payload(mudancas=[{"n": 2, "campo": "titulo", "antes": "", "depois": "X"}]), _render_falso([]))
    assert "Nada mudou" in pc.executar(_payload(mudancas=[]), _render_falso([]))
    assert pc.executar(_payload(raiz=7, mudancas=[])).startswith(pc.SEM_MOLDE)


# --- Outra música -------------------------------------------------------------------------------------------------

FAIXAS = [
    {"marca": "CASA VERANEIO", "estilo": "bossa", "bpm": 100, "arquivo": "CASA VERANEIO/bossa.mp3", "status": "aprovada"},
    {"marca": "CASA VERANEIO", "estilo": "samba", "bpm": 120, "arquivo": "CASA VERANEIO/samba.mp3", "status": "aprovada"},
    {"marca": "CASA VERANEIO", "estilo": "chill", "bpm": 90, "arquivo": "CASA VERANEIO/chill.mp3",
     "status": "para aprovação"},
    {"marca": "CASA VERO", "estilo": "jazz", "bpm": 88, "arquivo": "CASA VERO/jazz.mp3", "status": "aprovada"},
]


def _video(tmp_path: Path, faixa: str | None = "CASA VERANEIO/bossa.mp3", itens=FAIXAS) -> Path:
    entrega = tmp_path / "drive" / PASTA_PECA
    (entrega / "EDITÁVEL").mkdir(parents=True, exist_ok=True)
    for nome in ("Reels.mp4", "Reels_com_som.mp4", "vinheta.mp4"):
        (entrega / nome).write_bytes(b"video")
    (entrega / "EDITÁVEL" / "receita.json").write_text(json.dumps(
        {"versao": 1, "empresa": "casa_veraneio", "faixa": {"arquivo": faixa, "estilo": "bossa"} if faixa else None}),
        encoding="utf-8")
    biblioteca = tmp_path / "biblioteca"
    for f in itens:
        (biblioteca / f["arquivo"]).parent.mkdir(parents=True, exist_ok=True)
        (biblioteca / f["arquivo"]).write_bytes(b"mp3")
    (biblioteca / "catalogo.json").write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    return entrega


def _mixar_falso(chamadas: list):
    def mixar(video, faixa, saida, empresa, vinheta=None, desde=0.0):
        chamadas.append((Path(video).name, Path(faixa).name, empresa))
        Path(saida).write_bytes(b"com som")
        return saida
    return mixar


def test_outra_musica_usa_outra_faixa_aprovada_da_marca(pc, tmp_path):
    entrega = _video(tmp_path)
    chamadas = []
    texto = pc.executar_musica({"raiz": 41, "pasta": PASTA_PECA, "empresa": "casa_veraneio", "tarefa_id": 41},
                               _mixar_falso(chamadas))
    assert chamadas == [("Reels.mp4", "samba.mp3", "casa_veraneio")]  # nem a atual, nem a em aprovação, nem a vinheta
    assert (entrega / "Reels_com_som_v2.mp4").read_bytes() == b"com som"
    assert (entrega / "Reels_com_som.mp4").read_bytes() == b"video"  # a anterior fica
    receita = json.loads((entrega / "EDITÁVEL" / "receita_v2.json").read_text(encoding="utf-8"))
    assert receita["faixa"]["arquivo"] == "CASA VERANEIO/samba.mp3"
    assert (entrega / "FINAL" / "Reels_com_som.mp4").read_bytes() == b"com som"  # a FINAL fica com a nova
    assert "faixa aprovada" in texto and "versão 2" in texto


def test_sem_outra_aprovada_ou_sem_receita(pc, tmp_path):
    so_uma = [FAIXAS[0], FAIXAS[2]]
    _video(tmp_path, itens=so_uma)
    with pytest.raises(RuntimeError, match="APROVADA"):
        pc.executar_musica({"raiz": 41, "pasta": PASTA_PECA, "empresa": "casa_veraneio"}, _mixar_falso([]))
    (tmp_path / "drive" / PASTA_PECA / "EDITÁVEL" / "receita.json").unlink()
    assert pc.executar({"acao": "musica", "raiz": 41, "pasta": PASTA_PECA}).startswith(pc.SEM_RECEITA)


def test_trabalhador_conhece_a_edicao_rapida(pc):
    import trabalhos_max

    assert trabalhos_max.EXECUTORES["edicao_rapida"] is pc.executar
