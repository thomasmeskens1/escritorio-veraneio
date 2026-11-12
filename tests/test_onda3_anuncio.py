"""Onda 3, agente O (12/11/2026): "Desdobrar para anúncio" (gestor_trafego-13, designer-21, email_marketing-06).
Backend (backend/desdobrar.py) com banco temporário e fila falsa; o render no PC (scripts/max/desdobrar_formatos.py e
molde.py) com renderizador falso. Nada chama o Max nem o Chrome (o render de verdade fica em test_onda3_moldes.py).
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

import desdobrar
import producao
import tarefas
from conexoes import gerenciador

tarefas.iniciar()

USUARIO = {"sub": "usuario.teste"}
REGRAS = json.loads((Path(desdobrar.__file__).with_name("marcas_regras.json")).read_text(encoding="utf-8"))


def _peca_pronta(empresa: str = "casa_veraneio") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", "criador_imagens", "Carrossel do Lodge 999", "complexa",
                              empresa)
    tarefas.atualizar(tarefa_id, status="concluida", modelo=producao.MODELO_MAX, resposta="✅ Pedido concluído")
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo, pasta) VALUES (?, 'Teste', 'MARKETING/P')",
                   (tarefa_id,))
    return tarefa_id


@pytest.fixture
def sem_espera(monkeypatch):
    async def nada(*_a, **_k):
        return None
    monkeypatch.setattr(desdobrar, "_acompanhar", nada)


def test_pedir_anuncio_enfileira_sem_misturar_com_o_desdobrar(sem_espera):
    tarefa_id = _peca_pronta()
    organico = asyncio.run(desdobrar.pedir(tarefa_id, USUARIO))
    resposta = asyncio.run(desdobrar.pedir_anuncio(tarefa_id, USUARIO))
    assert resposta["trabalho_id"] != organico["trabalho_id"] and "ANÚNCIO/" in resposta["texto"]
    trabalho = producao.obter_trabalho(resposta["trabalho_id"])
    assert trabalho["tipo"] == "desdobrar" and trabalho["payload"]["destino"] == "anuncio"
    assert trabalho["payload"]["formatos"] == ["1080x1080", "1200x628", "1080x1920", "1200x600"]
    assert "tarefa_id" not in trabalho["payload"]  # a trava do Desdobrar comum não enxerga o de anúncio
    de_novo = asyncio.run(desdobrar.pedir_anuncio(tarefa_id, USUARIO))
    assert de_novo["trabalho_id"] == resposta["trabalho_id"] and "já estão na fila" in de_novo["texto"]
    for t in (organico, resposta):
        producao.cancelar_trabalho(t["trabalho_id"], "fim do teste")


def test_anuncio_so_para_a_casa_veraneio(sem_espera):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        asyncio.run(desdobrar.pedir_anuncio(_peca_pronta("casa_vero"), USUARIO))
    assert erro.value.status_code == 409 and "Casa Veraneio" in erro.value.detail


def test_conclusao_do_anuncio_avisa_e_sem_molde_nao_vai_para_o_max(monkeypatch):
    enviados, fila = [], []

    async def enviar(login, mensagem):
        enviados.append(mensagem)
        return True

    async def enfileirar(*_a, **_k):
        fila.append(1)
        return 1

    monkeypatch.setattr(gerenciador, "enviar_para_usuario", enviar)
    monkeypatch.setattr(producao, "enfileirar", enfileirar)
    tarefa_id = _peca_pronta()
    texto = asyncio.run(desdobrar.concluir({"status": "concluido", "resultado": "8 arquivo(s)"}, tarefa_id, True))
    assert "anúncio e e-mail" in texto and enviados[-1]["titulo"] == "Desdobrar para anúncio"
    texto = asyncio.run(desdobrar.concluir({"status": "concluido", "resultado": "SEM_MOLDE: sem molde.json"}, tarefa_id,
                                           True))
    assert "só para peças de molde" in texto and not fila
    texto = asyncio.run(desdobrar.concluir({"status": "pendente", "resultado": ""}, tarefa_id, True))
    assert "ANÚNCIO/" in texto


# --- Render no PC (scripts/max) ------------------------------------------------------------------------------------

def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "molde.py").exists():
            return pasta
    return None


@pytest.fixture
def pc(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não montado")
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    import comum
    import desdobrar_formatos
    import molde

    monkeypatch.setattr(desdobrar_formatos, "RASCUNHOS", tmp_path / "producoes")
    monkeypatch.setattr(comum, "DRIVE", tmp_path / "drive")
    monkeypatch.setattr(comum, "log", lambda *_a: None)
    monkeypatch.setattr(molde, "pasta_marcas", lambda: tmp_path / "MARCAS")
    (tmp_path / "drive" / "MARKETING" / "PECA").mkdir(parents=True)
    return desdobrar_formatos, molde


def _imagem(caminho: Path, tamanho=(1600, 1200)):
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", tamanho, (90, 140, 110)).save(caminho)


def _render_falso(chamadas: list):
    def renderizar(html: Path, saida: Path, largura: int, altura: int, espera_ms: int = 0):
        chamadas.append({"html": Path(html).read_text(encoding="utf-8"), "medida": (largura, altura),
                         "pasta": sorted(p.name for p in Path(html).parent.iterdir())})
        _imagem(Path(saida), (largura, altura))
    return renderizar


SLIDES = [
    {"molde": "capa", "foto": "acervo/f.jpg", "titulo": "Lodge 999", "lodge": 999, "local": "Cidade Fictícia, SP",
     "saida": "entrega/01_capa.png"},
    {"molde": "fechamento", "titulo": "A virada", "cta": "Reserve a data", "saida": "entrega/02_fim_v2.png"},
]


def test_anuncio_gera_tres_formatos_cabecalho_de_email_e_o_guia(pc, tmp_path):
    formatos, _ = pc
    rascunho = tmp_path / "producoes" / "51"
    _imagem(rascunho / "acervo" / "f.jpg")
    (rascunho / "molde.json").write_text(json.dumps({"empresa": "casa_veraneio", "slides": SLIDES}), encoding="utf-8")
    chamadas = []
    texto = formatos.executar({"raiz": 51, "pasta": "MARKETING/PECA", "destino": "anuncio"}, _render_falso(chamadas))
    pasta = tmp_path / "drive" / "MARKETING" / "PECA" / "ANÚNCIO"
    esperado = {f"{n}_{r}.png" for n in ("01_capa", "02_fim") for r in ("1x1", "1.91x1", "9x16")}
    esperado |= {"email_cabecalho_1200x600.png", formatos.LEIA}
    assert {p.name for p in pasta.iterdir()} == esperado  # o e-mail leva só a capa
    assert {c["medida"] for c in chamadas} == {(1080, 1080), (1200, 628), (1080, 1920), (1200, 600)}
    assert all("anuncio.css" in c["html"] and "anuncio.css" in c["pasta"] for c in chamadas)
    assert any('class="f916 anuncio molde-capa"' in c["html"] for c in chamadas)
    guia = (pasta / formatos.LEIA).read_text(encoding="utf-8")
    assert "Reels e Stories" in guia and "600 px" in guia and "  - 01_capa_1.91x1.png" in guia
    assert "7 arquivo(s)" in texto and "ANÚNCIO" in texto
    assert not (tmp_path / "drive" / "MARKETING" / "PECA" / "FORMATOS").exists()


def test_formatos_de_anuncio_so_com_a_classe_de_anuncio(pc):
    _, molde = pc
    with pytest.raises(ValueError, match="Formato"):
        molde.montar_html(SLIDES[1], "1200x628")  # o orgânico continua sem 1,91:1
    pagina = molde.montar_html(SLIDES[1], "1200x628", anuncio=True)
    assert 'class="f191 anuncio molde-fechamento"' in pagina and "width:1200px;height:628px" in pagina


def test_anuncio_css_segue_marcas_regras(pc):
    _, molde = pc
    css = (molde.PASTA_MOLDES / "casa_veraneio" / "anuncio.css").read_text(encoding="utf-8")
    regra = REGRAS["anuncio"]
    zona = re.search(r"\.anuncio\.f916 \{([^}]*)\}", css).group(1)
    assert f"--topo: {regra['zonas_916']['topo_px']}px" in zona and f"--base: {regra['zonas_916']['base_px']}px" in zona
    assert 1920 - regra["zonas_916"]["base_px"] <= 1250  # regra prática do manual 08 §3
    assert set(regra["formatos"].values()) | {regra["email_cabecalho"]} == set(molde.FORMATOS_ANUNCIO)
    assert set(desdobrar.FORMATOS_ANUNCIO) == set(molde.FORMATOS_ANUNCIO)
    assert "preto" not in css.lower() and "#000" not in css  # degradê e cores seguem os do base.css
