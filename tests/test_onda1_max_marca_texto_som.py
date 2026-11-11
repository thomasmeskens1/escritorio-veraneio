"""Onda 1 de novembro (11/11/2026), produção do Max: logo certo de cada empresa no motion e aviso de logo/pasta de
outra empresa (moviemaker-18, editor_video-18, gestor_trafego-04); texto aprovado do Copywriter como TEXTO FIXO e
conferência dos números antes da FINAL (copywriter-02); versão com som para todo vídeo, de qualquer agente, com a
mesma faixa em sequência no carrossel em MP4 (sonoplasta-06). Banco temporário (conftest); nada de Drive real.
"""

import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import avaliacoes
import tarefas
import texto_aprovado

tarefas.iniciar()


def _pasta_max() -> Path:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "logos_empresas.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    pytest.skip("scripts/max não montado")


@pytest.fixture
def max_(monkeypatch, tmp_path):
    _pasta_max()
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade
    monkeypatch.delenv("VERANEIO_EMPRESA", raising=False)
    import logos_empresas
    return logos_empresas


# --- Logo certo de cada empresa --------------------------------------------------------------------------------

def test_apelidos_do_logo_saem_da_empresa_da_peca(max_):
    assert max_.arquivo_do_apelido("cv_corporativo", "clara") == ("logo_corp_branca.png", "")
    assert max_.arquivo_do_apelido("cv_corporativo", "branca")[0] == "logo_corp_branca.png"  # nome antigo
    assert max_.arquivo_do_apelido("casa_vero", "escura")[0] == "logo_vero_verde_caramelo.png"
    assert max_.arquivo_do_apelido("casa_veraneio", "caramelo")[0] == "logo_caramelo_texto_creme.png"
    nome, aviso = max_.arquivo_do_apelido("casa_veraneio", "escura")  # não há logo completo em Verde
    assert nome == "logo_preta.png" and "Verde" in aviso
    with pytest.raises(ValueError):
        max_.arquivo_do_apelido("casa_vero", "dourada")


def test_logo_de_outra_empresa_pelo_nome_ou_pela_pasta(max_):
    assert max_.logo_de_outra("casa_vero", "_referencias/CASA_VERANEIO/logo_branca.png") == "casa_veraneio"
    assert max_.logo_de_outra("casa_veraneio", "logos/logo_corp_verde.png") == "cv_corporativo"
    assert max_.logo_de_outra("casa_veraneio", "CASA_VERO/qualquer.png") == "casa_vero"
    assert max_.logo_de_outra("casa_vero", "_referencias/CASA_VERO/logo_vero_verde_caramelo.png") is None
    assert max_.logo_de_outra("casa_veraneio", "acervo/piscina.png") is None


def test_empresa_do_trabalhador_manda_no_motion(max_, monkeypatch):
    assert max_.empresa_do_ambiente(None) == "casa_veraneio"
    monkeypatch.setenv(max_.VARIAVEL, "casa_vero")
    assert max_.empresa_do_ambiente(None) == "casa_vero" and max_.empresa_do_ambiente("casa_vero") == "casa_vero"
    with pytest.raises(ValueError, match="outra empresa"):
        max_.empresa_do_ambiente("casa_veraneio")


def test_motion_usa_o_logo_da_empresa_e_recusa_o_de_outra(max_, tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    import motion
    corp = tmp_path / "_referencias" / "CORPORATIVO"
    corp.mkdir(parents=True)
    Image.new("RGBA", (300, 100), (255, 255, 255, 255)).save(corp / "logo_corp_branca.png")
    elemento = {"tipo": "imagem", "logo": "branca", "altura": 50, "y": 1500}
    cena = motion.Cena([elemento], 3.0, base=tmp_path, empresa="cv_corporativo", sai=False)
    assert cena.itens[0]["sprite"].largura == 150  # achou o logo do Corporativo (antes: só o da Casa Veraneio)
    with pytest.raises(ValueError, match="não encontrada"):  # Casa Vero não acha o do Corporativo
        motion.Cena([elemento], 3.0, base=tmp_path, empresa="casa_vero")
    outro = {"tipo": "imagem", "arquivo": "_referencias/CORPORATIVO/logo_corp_branca.png", "altura": 50, "y": 1500}
    with pytest.raises(ValueError, match="logo de Corporativo"):
        motion.Cena([outro], 3.0, base=tmp_path, empresa="casa_veraneio")
    monkeypatch.setenv(max_.VARIAVEL, "casa_vero")
    with pytest.raises(ValueError, match="outra empresa"):
        motion.Cena([elemento], 3.0, base=tmp_path, empresa="cv_corporativo")
    with pytest.raises(ValueError, match="empresa desconhecida"):
        motion.validar({"empresa": "outra", "cenas": [{"fundo": "verde", "duracao": 2, "saida": "a.mp4"}]})


def test_conferencia_de_marca_avisa_logo_e_pasta_de_outra_empresa(max_, tmp_path):
    marcas = tmp_path / "MARCAS"
    (marcas / "CASA_VERANEIO").mkdir(parents=True)
    (marcas / "CASA_VERANEIO" / "logo_branca.png").write_bytes(b"logo-veraneio")
    rascunho = tmp_path / "rascunho"
    (rascunho / "entrega").mkdir(parents=True)
    (rascunho / "_referencias" / "CASA_VERO").mkdir(parents=True)
    (rascunho / "_referencias" / "CASA_VERO" / "logo_vero_verde_caramelo.png").write_bytes(b"ok")  # a própria
    (rascunho / "marca.png").write_bytes(b"logo-veraneio")  # cópia renomeada do logo da Casa Veraneio (hash)
    (rascunho / "arte.html").write_text('<img src="logo_corp_branca.png">', encoding="utf-8")
    avisos = max_.conferir(rascunho, "casa_vero", "VERO ｜ CARROSSEL - CARNAVAL LODGE 1", marcas)
    assert any("marca.png" in a and "Casa Veraneio" in a for a in avisos)
    assert any("arte.html" in a and "Corporativo" in a for a in avisos)
    assert not any("_referencias" in a for a in avisos)
    pasta = max_.conferir(tmp_path / "vazio", "casa_veraneio", "VERO ｜ CARROSSEL - CARNAVAL LODGE 1", marcas)
    assert pasta and "prefixo de Casa Vero" in pasta[0]
    assert max_.conferir(tmp_path / "vazio", "casa_vero", "VERO ｜ CARROSSEL - X", marcas) == []
    assert max_.linha_do_resumo(pasta, "casa_veraneio").startswith("🔴 Marca")


# --- Texto aprovado: copie, não reescreva -------------------------------------------------------------------------

APROVADO = ("Legenda: Lodge 32 beira-mar, 4 suítes para até 8 pessoas. Réveillon em 31/12.\n"
            "Observação: troque \"2 meses\" por \"oito semanas\" e tire \"ainda dá tempo\".")


def _docx(caminho: Path, texto: str) -> Path:
    paragrafos = "".join(f"<w:p><w:r><w:t>{linha}</w:t></w:r></w:p>" for linha in texto.split("\n"))
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("word/document.xml", f"<w:document><w:body>{paragrafos}</w:body></w:document>")
    return caminho


def test_divergencias_de_numeros_e_frases(max_):
    import conferencia_texto as ct
    problemas = ct.divergencias(APROVADO, "Quatro quartos, seis banheiros. Faltam dois meses! Ainda dá tempo.")
    assert any("4 quartos" in p for p in problemas) and any("6 banheiros" in p for p in problemas)
    assert any("2 meses" in p for p in problemas) and any("ainda dá tempo" in p for p in problemas)
    # números por extenso e datas escritas de outro jeito batem com o aprovado
    assert ct.divergencias(APROVADO, "Lodge 32: quatro suítes para até oito pessoas no Réveillon (31 de dezembro).") == []
    assert ct.divergencias("", "qualquer coisa") == []
    assert any("Lodge" in p for p in ct.divergencias("Casa com 3 suítes.", "Lodge com 3 suítes", "casa_vero"))


def test_instrucao_do_texto_fixo(max_):
    import conferencia_texto as ct
    bloco = ct.instrucao({"texto": APROVADO, "origem": "resposta #9 do Copywriter, com 👍"})
    assert "COPIE, NÃO REESCREVA" in bloco and "4 suítes para até 8 pessoas" in bloco and "#9" in bloco
    assert ct.instrucao(None) == "" and ct.instrucao({"texto": "  "}) == ""


def test_legenda_divergente_fica_fora_da_final(max_, tmp_path):
    import conferencia_texto as ct
    import pasta_final
    entrega = tmp_path / "VERANEIO ｜ REELS - LODGE 32"
    entrega.mkdir()
    (entrega / "reels.mp4").write_bytes(b"v")
    _docx(entrega / "Legenda - Reels Lodge 32.docx", "Quatro quartos, seis banheiros.")
    novos = ["reels.mp4", "Legenda - Reels Lodge 32.docx"]
    barradas, linha = ct.conferir(entrega, novos, {"texto": APROVADO}, "casa_veraneio")
    assert barradas == ["Legenda - Reels Lodge 32.docx"] and "FORA da pasta FINAL" in linha and "6 banheiros" in linha
    vigentes = pasta_final.atualizar(entrega, barradas)
    assert vigentes == ["reels.mp4"] and not (entrega / "FINAL" / "Legenda - Reels Lodge 32.docx").exists()
    _docx(entrega / "Legenda - Reels Lodge 32_v2.docx", "Lodge 32: 4 suítes para até 8 pessoas. Réveillon em 31/12.")
    barradas, linha = ct.conferir(entrega, ["Legenda - Reels Lodge 32_v2.docx"], {"texto": APROVADO})
    assert barradas == [] and "confere" in linha
    assert "Legenda - Reels Lodge 32.docx" in pasta_final.atualizar(entrega, barradas)
    # sem texto aprovado, nada muda (só o "Lodge" na legenda da Casa Vero)
    assert ct.conferir(entrega, novos, None, "casa_veraneio") == ([], "")


def _copywriter(texto: str, resposta: str, empresa: str = "casa_veraneio", andar: str = "marketing") -> int:
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", andar, "copywriter", texto, "simples", empresa)
    tarefas.atualizar(tarefa_id, status="concluida", resposta=resposta)
    return tarefa_id


def _producao(texto: str, empresa: str = "casa_veraneio") -> dict:
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "editor_video", texto, "complexa", empresa)
    return tarefas.obter(tarefa_id)


def _votar(tarefa_id: int, valor: int) -> None:
    with avaliacoes._db() as db:
        db.execute("INSERT OR REPLACE INTO avaliacoes VALUES (?, ?, ?, ?, ?)",
                   (tarefa_id, "usuario.teste@exemplo.com", valor, None,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))


def test_texto_aprovado_da_conversa_prefere_o_joinha_e_ignora_outra_empresa():
    boa = _copywriter("Legenda do reels do Lodge 77", "Legenda: Lodge 77 com 5 suítes para até 10 pessoas.")
    _copywriter("Legenda do reels do Lodge 77, versão 2", "Legenda: Lodge 77, 5 suítes, até 12 pessoas.")
    _copywriter("Legenda do Lodge 77", "Legenda da Vero", empresa="casa_vero")  # outra empresa: nunca entra
    ruim = _copywriter("Legenda do reels do Lodge 77, versão 3", "Versão recusada do Lodge 77.")
    _votar(ruim, -1)
    linha = _producao("Reels do Lodge 77 com a legenda aprovada")
    escolhido = texto_aprovado.da_producao(linha)
    assert "a mais recente" in escolhido["origem"] and "12 pessoas" in escolhido["texto"]  # 👎 nunca vale
    _votar(boa, 1)
    escolhido = texto_aprovado.da_producao(linha)
    assert escolhido["tarefa_id"] == boa and "👍" in escolhido["origem"]
    assert texto_aprovado.da_producao(_producao("Reels do Lodge 78 na piscina")) is None  # outro Lodge


def test_texto_aprovado_do_projeto_do_gestor(tmp_path, monkeypatch):
    monkeypatch.setattr(texto_aprovado, "PASTA_PROJETOS", tmp_path)
    (tmp_path / "501" / "etapas").mkdir(parents=True)
    (tmp_path / "501" / "etapas" / "01-copywriter.md").write_text("Legenda antiga", encoding="utf-8")
    (tmp_path / "501" / "etapas" / "03-copywriter.md").write_text("Legenda final: 4 suítes.", encoding="utf-8")
    (tmp_path / "501" / "etapas" / "02-designer.md").write_text("Layout", encoding="utf-8")
    linha = _producao("Produza a peça final do projeto #501, coordenado pelo Gestor. Siga o plano.")
    escolhido = texto_aprovado.da_producao(linha)
    assert escolhido["texto"] == "Legenda final: 4 suítes." and "#501" in escolhido["origem"]
    ajuste = _producao("Ajuste na peça #9: troque a foto")  # ajuste: o projeto está no pedido original
    assert texto_aprovado.da_producao(ajuste, linha["texto"])["texto"] == "Legenda final: 4 suítes."


# --- Versão com som para todo vídeo -------------------------------------------------------------------------------

@pytest.fixture
def sono(max_, tmp_path, monkeypatch):
    import sonoplasta
    monkeypatch.setattr(sonoplasta, "BIBLIOTECA", tmp_path / "biblioteca")
    monkeypatch.setattr(sonoplasta, "ESPELHO", tmp_path / "espelho.json")
    monkeypatch.setattr(sonoplasta, "USO", tmp_path / "uso.json")
    return sonoplasta


def test_carrossel_em_mp4_usa_a_mesma_faixa_em_sequencia(sono, tmp_path, monkeypatch):
    assert sono.conjuntos(["slide_2.mp4", "slide_10.mp4", "slide_1.mp4", "reels.mp4"]) == [
        ["slide_1.mp4", "slide_2.mp4", "slide_10.mp4"], ["reels.mp4"]]
    final = tmp_path / "entrega"
    (final / "EDITÁVEL" / "CENAS").mkdir(parents=True)
    faixa = {"arquivo": "CASA VERANEIO/bossa.mp3", "estilo": "bossa_nova_praia", "bpm": 100}
    monkeypatch.setattr(sono, "escolher", lambda *a, **k: (faixa, True))
    monkeypatch.setattr(sono, "duracao", lambda _v: 5.0)
    chamadas = []

    def falso(video, empresa, pedido, rascunho, evitar, escolhida=None, desde=0.0):
        chamadas.append((video.name, escolhida, desde))
        saida = video.with_name(f"{video.stem}{sono.SUFIXO}{video.suffix}")
        return saida, faixa, True

    monkeypatch.setattr(sono, "versao_com_som", falso)
    novos = ["carrossel_1.mp4", "carrossel_2.mp4", "carrossel_3.mp4", "EDITÁVEL/CENAS/cena01.mp4"]
    gerados, linha = sono.na_producao(tmp_path, final, novos, "casa_veraneio", "carrossel em vídeo")
    assert gerados == ["carrossel_1_com_som.mp4", "carrossel_2_com_som.mp4", "carrossel_3_com_som.mp4"]
    assert [c[2] for c in chamadas] == [0.0, 5.0, 10.0] and all(c[1] == (faixa, True) for c in chamadas)
    assert linha.count("bossa nova praia") == 1 and "em sequência" in linha
    assert "[1:a]atrim=12.000:33.000" in sono.filtro(5.0, 33.0, 1, None, False, 12.0)  # continua de onde parou
    assert sono.ponto_de_inicio(10.0, 33.0) == 10.0 and sono.ponto_de_inicio(30.0, 33.0) == 0.0


def test_trabalhador_gera_som_para_qualquer_agente_e_manda_o_texto_fixo(max_):
    try:
        import trabalhador_max
    except Exception as erro:  # dependências do PC podem faltar no contêiner
        pytest.skip(f"trabalhador indisponível: {erro}")
    import inspect
    fonte = inspect.getsource(trabalhador_max.produzir)
    assert 'if producao["agente"] == "editor_video":' not in fonte and "versoes_com_som(" in fonte
    producao = {"agente": "criador_imagens", "texto": "Carrossel em vídeo do Lodge 32", "empresa": "casa_veraneio",
                "texto_aprovado": {"texto": APROVADO, "origem": "resposta #9 do Copywriter"}}
    prompt = trabalhador_max.montar_prompt(producao, Path("."))
    assert "COPIE, NÃO REESCREVA" in prompt and "_com_som" in prompt
    editor = trabalhador_max.instrucao_motion("editor_video", "cv_corporativo")
    assert '"empresa": "cv_corporativo"' in editor and '"clara"' in editor
