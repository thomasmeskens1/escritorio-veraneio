"""Onda 3 de novembro (12/11/2026): PPTX do editável gerado pelo código a partir da receita (moviemaker-35,
criador_imagens-04, designer-31) e leitura do PPTX que volta da equipe (editor_video-02). Sem Drive real e sem Max;
textos fictícios. A ida e volta com python-pptx só roda onde ele está instalado (PC do Max); o plano e a
comparação rodam em qualquer lugar.
"""

import copy
import json
import sys
from pathlib import Path

import pytest


def _pasta_max() -> Path:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "pptx_receita.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    pytest.skip("scripts/max não montado")


@pytest.fixture
def mods(monkeypatch, tmp_path):
    _pasta_max()
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade
    import pptx_diferenca
    import pptx_receita
    return pptx_receita, pptx_diferenca


MOTION = {"formato": "1080x1920", "empresa": "cv_corporativo", "cenas": [
    {"fundo": "verde", "duracao": 2.6, "elementos": [
        {"tipo": "texto", "texto": "Chamada", "fonte": "muli", "peso": 700, "tamanho": 24, "cor": "caramelo",
         "maiusculas": True, "espacamento": 9, "y": 673},
        {"tipo": "texto", "linhas": ["Frase de teste", "segunda linha"], "italico_ultima": True, "fonte": "playfair",
         "tamanho": 88, "entrelinha": 106, "cor": "branco", "y": 763},
        {"tipo": "filete", "cor": "caramelo", "largura": 120, "espessura": 4, "y": 1003}]},
    {"fundo": "verde", "duracao": 2.5, "elementos": [
        {"tipo": "texto", "linhas": ["Peça já", "o orçamento"], "fonte": "playfair", "italico": True, "tamanho": 58,
         "cor": "creme", "y": 700},
        {"tipo": "imagem", "logo": "caramelo", "altura": 135, "y": 1010}]}],
    "juntar": "entrega/Reels_Teste.mp4"}


def _receita(pr):
    import receita
    return receita.de_motion(MOTION, "Reels de teste", "reels")


def test_plano_um_slide_por_cena_com_estilo_da_marca(mods):
    pr, _ = mods
    plano = pr.planejar(_receita(pr), MOTION)
    assert (plano["largura"], plano["altura"], plano["fonte"]) == (1080, 1920, "motion.json")
    assert len(plano["slides"]) == 2
    chamada, frase = plano["slides"][0]["textos"]
    assert chamada["chave"] == "texto|c1|t1" and chamada["maiusculas"] and chamada["linhas"][0]["negrito"]
    assert frase["y"] == 763 and frase["entrelinha"] == 106
    assert [l["italico"] for l in frase["linhas"]] == [False, True]  # itálico só na última linha
    logo = plano["slides"][1]["logo"]
    assert logo["altura"] == 135 and logo["arquivo"] == "logo_corp_caramelo_texto_branco.png"
    assert pr.hex_da_cor("caramelo", pr.paleta()) == "#D9A15B"


def test_plano_sem_motion_usa_os_textos_da_receita(mods):
    pr, _ = mods
    receita = _receita(pr)
    plano = pr.planejar(receita)
    assert plano["fonte"] == "receita.json"
    assert [l["texto"] for c in plano["slides"][1]["textos"] for l in c["linhas"]] == receita["cenas"][1]["textos"]
    # motion com número de cenas diferente da receita não vale
    assert pr.planejar(receita, {"cenas": MOTION["cenas"][:1]})["fonte"] == "receita.json"


def test_plano_do_molde_com_papeis(mods):
    pr, _ = mods
    import receita
    dados = {"empresa": "casa_veraneio", "slides": [
        {"molde": "capa", "foto": "acervo/fachada.jpg", "titulo": "Lodge de teste", "local": "Cidade / UF"},
        {"molde": "fechamento", "titulo": "Fim", "cta": "Reserve"}]}
    plano = pr.planejar(receita.de_molde(dados, "Carrossel"), None, dados)
    assert plano["fonte"] == "molde.json" and plano["altura"] == 1440
    assert [c["papel"] for c in plano["slides"][0]["textos"]] == ["titulo", "local"]
    assert plano["slides"][0]["midia"] == "acervo/fachada.jpg" and plano["slides"][0]["midia_tipo"] == "foto"
    assert plano["slides"][1]["logo"]["apelido"] == "caramelo"


def _lido_do_plano(plano):
    """O que o leitor devolveria de um PPTX sem mudança (para testar a comparação sem python-pptx)."""
    slides = []
    for s in plano["slides"]:
        textos = {c["chave"]: {"x": c["x"], "y": c["y"], "largura": c["largura"], "altura": c["altura"],
                               "linhas": [l["texto"] for l in c["linhas"]], "tamanho": c["linhas"][0]["tamanho"]}
                  for c in s["textos"]}
        logos = {s["logo"]["chave"]: {"x": 400, "y": s["logo"]["y"], "altura": s["logo"]["altura"], "hash": "a",
                                      "hash_original": "a"}} if s.get("logo") else {}
        slides.append({"n": s["n"], "cena": s["cena"], "textos": textos, "fotos": {}, "logos": logos,
                       "novos_textos": [], "novas_imagens": 0})
    return {"largura": plano["largura"], "altura": plano["altura"], "slides": slides}


def test_comparar_mostra_texto_tamanho_logo_e_ordem(mods):
    pr, pd = mods
    plano = pr.planejar(_receita(pr), MOTION)
    lido = _lido_do_plano(plano)
    assert pd.comparar(plano, lido) == []
    mudado = copy.deepcopy(lido)
    mudado["slides"][0]["textos"]["texto|c1|t2"]["linhas"][1] = "outra linha"
    mudado["slides"][0]["textos"]["texto|c1|t2"]["tamanho"] = 100
    mudado["slides"][1]["logos"]["logo|c2"]["altura"] = 180
    mudado["slides"][1]["novos_textos"].append("Texto acrescentado")
    mudado["slides"].reverse()
    for n, s in enumerate(mudado["slides"], 1):
        s["n"] = n
    linhas = pd.comparar(plano, mudado)
    assert "slide 2: texto 2 “Frase de teste / segunda linha” → “Frase de teste / outra linha”" in linhas
    assert "slide 2: texto 2 com letra 88 → 100 px" in linhas
    assert "slide 1: logo com altura 135 → 180 px" in linhas
    assert "slide 1: texto novo “Texto acrescentado”" in linhas
    assert any(l.startswith("ordem: a cena 1") for l in linhas)


def test_comparar_cena_apagada_e_logo_removido(mods):
    pr, pd = mods
    plano = pr.planejar(_receita(pr), MOTION)
    lido = _lido_do_plano(plano)
    lido["slides"] = lido["slides"][1:]
    lido["slides"][0]["logos"] = {}
    linhas = pd.comparar(plano, lido)
    assert any("cena 1 apagada" in l for l in linhas) and "slide 2: logo removido" in linhas


def test_instrucao_sem_pptx_nos_anexos_fica_vazia(mods, tmp_path):
    _, pd = mods
    assert pd.instrucao(tmp_path, [tmp_path / "anexos" / "foto.jpg"]) == ""


def test_ida_e_volta_com_python_pptx(mods, tmp_path):
    pytest.importorskip("pptx")
    pr, pd = mods
    import receita
    rascunho = tmp_path / "peca"
    (rascunho / "entrega" / "EDITÁVEL").mkdir(parents=True)
    (rascunho / "motion.json").write_text(json.dumps(MOTION), encoding="utf-8")
    conferida = receita.de_motion(MOTION, "Reels de teste")
    (rascunho / "entrega" / receita.DESTINO).write_text(json.dumps(conferida), encoding="utf-8")
    nome, linha = pr.na_producao(rascunho, rascunho / "entrega", tmp_path / "sem_marcas")
    assert nome == "EDITÁVEL/Reels_Teste_editavel.pptx" and "2 slide(s)" in linha
    assert "logo" in linha  # sem a pasta de marcas o logo falta, com aviso
    arquivo = rascunho / "entrega" / nome
    assert arquivo.stat().st_size < 200_000
    assert pd.diferencas(rascunho, arquivo) == []
    from pptx import Presentation
    apresentacao = Presentation(str(arquivo))
    forma = next(f for f in apresentacao.slides[1].shapes if f.name == "texto|c2|t1")
    assert forma.text_frame.paragraphs[0].runs[0].font.name == "Playfair Display"
    forma.text_frame.paragraphs[0].runs[0].text = "Peça hoje"
    devolvido = tmp_path / "anexos" / "devolvido.pptx"
    devolvido.parent.mkdir()
    apresentacao.save(str(devolvido))
    assert pd.diferencas(rascunho, devolvido) == ["slide 2: texto 1 “Peça já / o orçamento” → “Peça hoje / o orçamento”"]
    assert "Aplique EXATAMENTE" in pd.instrucao(rascunho, [devolvido])


def test_na_producao_sem_receita_nao_faz_nada(mods, tmp_path):
    pr, _ = mods
    assert pr.na_producao(tmp_path, tmp_path / "entrega") == (None, "")
