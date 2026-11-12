"""Memória do que já foi usado (Onda 3; criador_imagens-06, editor_video-05, sonoplasta-17): origem de cada foto,
take e faixa gravada com a peça; capa ou take repetido só avisa; o Gestor e o Max veem o que saiu do mesmo Lodge;
o Sonoplasta evita a faixa das últimas produções da marca."""

import json
import sys
from pathlib import Path

import pytest

import uso_material


def _o(caminho, papel="capa", tipo="foto", imovel="lodge 12", de=None, dur=None, fonte="acervo"):
    return {"tipo": tipo, "papel": papel, "fonte": fonte, "caminho": caminho, "imovel": imovel, "de": de,
            "duracao_s": dur}


def test_capa_repetida_avisa_so_na_mesma_empresa_e_nunca_na_propria_peca():
    capa = _o("Lodges 1 - 50/Lodge 12/piscina_teste.jpg")
    assert uso_material.registrar(90001, "casa_veraneio", [capa, _o("Lodges 1 - 50/Lodge 12/sala.jpg", "foto")]) == 2
    assert uso_material.registrar(90001, "casa_veraneio", [capa]) == 0          # repetição do /concluir
    avisos = uso_material.avisos("casa_veraneio", [capa], 90002)
    assert len(avisos) == 1 and "esta capa (piscina_teste.jpg) já foi usada hoje na peça #90001" in avisos[0]
    assert uso_material.avisos("casa_vero", [capa], 90002) == []                 # empresas separadas
    assert uso_material.avisos("casa_veraneio", [capa], 90001) == []             # a própria peça
    assert uso_material.avisos("casa_veraneio", [_o("Lodges 1 - 50/Lodge 12/sala.jpg")], 90002) == []  # era foto


def test_take_avisa_so_quando_o_trecho_se_cruza():
    take = _o("LODGES PRAIA/Lodge 40/drone_teste.mp4", "take", "video", "lodge 40", 2.0, 4.0, "marketing_lodges")
    uso_material.registrar(90010, "casa_veraneio", [take])
    cruzado = dict(take, de=5.0)
    longe = dict(take, de=20.0)
    assert "este take (drone_teste.mp4, de 5 a 9 s) já saiu hoje na peça #90010" in \
        uso_material.avisos("casa_veraneio", [cruzado], 90011)[0]
    assert uso_material.avisos("casa_veraneio", [longe], 90011) == []
    assert uso_material.linha_do_resumo(["x"]).startswith("⚠ Material repetido (só aviso)")


def test_plano_do_gestor_e_briefing_veem_o_que_saiu_do_lodge(monkeypatch, tmp_path):
    uso_material.registrar(90020, "casa_veraneio", [_o("Lodges 1 - 50/Lodge 33/capa_teste.jpg", imovel="lodge 33")])
    bloco = uso_material.para_contexto("casa_veraneio", "carrossel do Lodge 33 para o verão")
    assert "JÁ USADO NO LODGE 33" in bloco and "capa_teste.jpg" in bloco and "#90020" in bloco
    assert uso_material.para_contexto("cv_corporativo", "Lodge 33") == ""
    assert uso_material.bloco("gestor", "casa_veraneio", "Lodge 33") == bloco
    assert uso_material.bloco("copywriter", "casa_veraneio", "Lodge 33") == ""
    monkeypatch.setattr(uso_material, "ARQUIVO_CONFIG", tmp_path / "uso.json")
    (tmp_path / "uso.json").write_text(json.dumps({"ativo": False}), encoding="utf-8")
    assert uso_material.para_contexto("casa_veraneio", "Lodge 33") == ""


def test_lista_vinda_do_trabalhador_e_conferida():
    limpas = uso_material.normalizar([{"tipo": "foto", "papel": "capa", "caminho": "a.jpg", "fonte": "x",
                                       "imovel": "drop table"}, {"tipo": "?", "papel": "capa", "caminho": "b"},
                                      "texto solto"])
    assert len(limpas) == 1 and limpas[0]["fonte"] == "desconhecida" and limpas[0]["imovel"] is None


def test_conclusao_aceita_as_origens():
    import producao
    assert producao.Conclusao(resumo="ok", pasta="x", origens=[_o("a.jpg")]).origens[0]["caminho"] == "a.jpg"


@pytest.fixture
def max_scripts():
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "origem_material.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    pytest.skip("scripts/max não montado")


def test_origens_saem_da_receita(max_scripts, tmp_path):
    import origem_material as mod
    acervo = tmp_path / "acervo"
    rascunho, final = tmp_path / "rascunho", tmp_path / "rascunho" / "entrega"
    (final / "EDITÁVEL").mkdir(parents=True)
    receita = {"versao": 1, "empresa": "casa_veraneio", "peca": "p", "tipo": "reels", "formato": "1080x1920",
               "cenas": [{"n": 1, "origem": "acervo/capa.jpg", "fonte": str(acervo / "Lodges 1 - 50" / "Lodge 12" / "capa.jpg")},
                         {"n": 2, "origem": "acervo/tour.mp4", "de": 1.5, "duracao_s": 4.0},
                         {"n": 3, "origem": "anexos/foto.png"}, {"n": 4, "origem": "fundo:verde"}],
               "fotos": [], "logo": None, "textos": [], "arquivos": ["p.mp4"],
               "faixa": {"arquivo": "CASA VERANEIO/bossa.mp3", "estilo": "bossa"}}
    (final / "EDITÁVEL" / "receita.json").write_text(json.dumps(receita), encoding="utf-8")
    lista = mod.origens(rascunho, final, "reels do Lodge 12", [("acervo", acervo)], buscar=False)
    assert lista[0] == {"tipo": "foto", "papel": "capa", "fonte": "acervo", "caminho": "Lodges 1 - 50/Lodge 12/capa.jpg",
                        "imovel": "lodge 12", "de": None, "duracao_s": None}
    assert lista[1]["papel"] == "take" and lista[1]["fonte"] == "desconhecida" and lista[1]["de"] == 1.5
    assert lista[2]["fonte"] == "anexo" and lista[3]["tipo"] == "faixa" and len(lista) == 4


def test_sonoplasta_evita_a_faixa_das_ultimas_producoes_da_marca(max_scripts, tmp_path, monkeypatch):
    import sonoplasta
    monkeypatch.setattr(sonoplasta, "USO", tmp_path / "uso.json")
    faixas = [{"marca": "CASA VERANEIO", "estilo": e, "bpm": 100, "clima": "", "legenda": "", "arquivo": f"{e}.mp3",
               "status": "aprovada"} for e in ("um", "dois")]
    primeira = sonoplasta.escolher("casa_veraneio", "", itens=faixas)[0]["arquivo"]
    sonoplasta._registrar_uso(primeira, "casa_veraneio", "peca-1")
    sonoplasta.registrar_uso("dois.mp3", "cv_corporativo", "peca-corp")  # outra empresa não conta
    assert sonoplasta.recentes("casa_veraneio") == {primeira}
    assert sonoplasta.escolher("casa_veraneio", "", itens=faixas)[0]["arquivo"] != primeira
    assert sonoplasta.escolher("casa_veraneio", f"quero {Path(primeira).stem}", itens=faixas)[0]["arquivo"] == primeira
    (tmp_path / "antigo.json").write_text(json.dumps({"um.mp3": 1.0}), encoding="utf-8")  # formato antigo
    monkeypatch.setattr(sonoplasta, "USO", tmp_path / "antigo.json")
    assert sonoplasta._usos() == {"um.mp3": 1.0} and sonoplasta.recentes("casa_veraneio") == set()
