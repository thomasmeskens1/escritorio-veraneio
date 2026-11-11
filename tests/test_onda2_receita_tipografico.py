"""Onda 2 de novembro (11/11/2026): receita fixa da peça, conferida quando a produção do Max volta (editor_video-04 e
criador_imagens-08), e Reels tipográfico do Corporativo no motion, com a contagem regressiva só com prazo "fechar
até" válido (gestor-27 e designer-13). Sem Drive real, sem ffmpeg e sem Max; frases fictícias.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest


def _pasta_max() -> Path:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "receita.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    pytest.skip("scripts/max não montado")


@pytest.fixture
def rc(monkeypatch, tmp_path):
    _pasta_max()
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade
    monkeypatch.delenv("VERANEIO_EMPRESA", raising=False)
    import receita
    return receita


@pytest.fixture
def tp(rc):
    pytest.importorskip("PIL")  # o roteiro confere a linha do tempo do motion.py (que usa o Pillow)
    import motion_tipografico
    return motion_tipografico


HOJE = date(2026, 11, 11)
FRASES = ["O ano está chegando ao fim", "Seu time merece | uma noite à altura", "Espaço, cenografia e gastronomia",
          "Do orçamento ao último convidado"]


def _spec_motion() -> dict:
    return {"formato": "1080x1920", "empresa": "cv_corporativo", "juntar": "entrega/Reels.mp4", "cenas": [
        {"video": "acervo/salao.mp4", "de": 1.0, "duracao": 4.5, "velocidade": 0.75, "saida": "trabalho/c1.mp4",
         "elementos": [{"tipo": "texto", "linhas": ["Seu time", "merece celebrar"], "y": 800}]},
        {"fundo": "verde", "duracao": 3.0, "saida": "trabalho/c2.mp4",
         "elementos": [{"tipo": "texto", "texto": "Converse com nossos especialistas", "y": 700},
                       {"tipo": "imagem", "logo": "caramelo", "altura": 135, "y": 1000}]}]}


# ---------------------------------------------------------------- receita: formato

def test_receita_nova_esta_no_formato_fixo(rc):
    r = rc.nova("cv_corporativo", "Peça", "reels", "1080x1920", [{"n": 1, "origem": "fundo:verde", "textos": ["Oi"]}])
    assert rc.validar(r) == []
    assert r["textos"] == ["Oi"] and r["fotos"] == [] and r["faixa"] is None and r["versao"] == rc.VERSAO
    json.dumps(r)  # JSON simples


def test_validar_aponta_campo_faltando_e_tipos_errados(rc):
    problemas = rc.validar({"versao": 1, "empresa": "outra", "tipo": "banner", "formato": "grande",
                            "cenas": [{"velocidade": "1x"}], "textos": "x"})
    texto = " | ".join(problemas)
    for trecho in ("falta \"peca\"", "falta \"logo\"", "empresa desconhecida", "tipo 'banner'", "formato 'grande'",
                   "velocidade precisa ser número", "\"textos\" precisa ser lista"):
        assert trecho in texto
    assert rc.validar("x") == ["a receita não é um objeto JSON"]


def test_receita_montada_do_motion_json(rc):
    r = rc.de_motion(_spec_motion(), "Reels teste")
    assert rc.validar(r) == []
    assert len(r["cenas"]) == 2 and r["duracao_s"] == 7.5
    assert r["cenas"][0]["origem"] == "acervo/salao.mp4" and r["cenas"][0]["velocidade"] == 0.75
    assert r["cenas"][1]["origem"] == "fundo:verde" and r["cenas"][1]["velocidade"] is None
    assert r["fotos"] == ["acervo/salao.mp4"] and r["arquivos"] == ["Reels.mp4"]
    assert r["logo"] == {"apelido": "caramelo", "arquivo": "logo_corp_caramelo_texto_branco.png"}
    assert "Converse com nossos especialistas" in r["textos"]


def test_receita_montada_do_molde_json(rc):
    dados = {"empresa": "casa_veraneio", "formato": "1080x1440", "slides": [
        {"molde": "capa", "foto": "acervo/a.jpg", "titulo": "Lodge 1", "saida": "entrega/01_capa.png"},
        {"molde": "foto", "foto": "acervo/b.jpg", "saida": "entrega/02_foto.png"},
        {"molde": "fechamento", "titulo": "Fim", "linhas": ["8 suítes"], "saida": "entrega/03_fim.png"}]}
    r = rc.de_molde(dados, "Carrossel")
    assert rc.validar(r) == [] and r["tipo"] == "carrossel" and r["formato"] == "1080x1440"
    assert r["arquivos"] == ["01_capa.png", "02_foto.png", "03_fim.png"]
    assert r["fotos"] == ["acervo/a.jpg", "acervo/b.jpg"] and "8 suítes" in r["textos"]


# ---------------------------------------------------------------- receita: conferência na volta

def _medir(tabela: dict):
    return lambda caminho: tabela.get(Path(caminho).name)


def test_conferencia_avisa_formato_duracao_e_arquivo_que_nao_voltou(rc, tmp_path):
    r = rc.de_motion(_spec_motion(), "Reels")
    r["arquivos"].append("Extra.mp4")
    _, avisos = rc.conferir(r, tmp_path, ["Reels.mp4"], "cv_corporativo", _medir({"Reels.mp4": (1080, 1350, 12.0)}))
    texto = " | ".join(avisos)
    assert "formato da receita 1080x1920" in texto and "1080x1350" in texto
    assert "duração da receita 7.5 s" in texto and "Extra.mp4" in texto


def test_conferencia_bate_quando_tudo_confere(rc, tmp_path):
    r = rc.de_motion(_spec_motion(), "Reels")
    medido, avisos = rc.conferir(r, tmp_path, ["Reels.mp4", "Reels_com_som.mp4"], "cv_corporativo",
                                 _medir({"Reels.mp4": (1080, 1920, 7.6)}))
    assert avisos == [] and medido == {"Reels.mp4": {"formato": "1080x1920", "duracao_s": 7.6}}


def test_conferencia_de_slides_logo_texto_contagem_e_empresa(rc, tmp_path):
    rascunho = tmp_path / "rascunho"
    rascunho.mkdir()
    (rascunho / "motion.json").write_text(json.dumps(_spec_motion()), encoding="utf-8")
    r = rc.nova("casa_veraneio", "Carrossel", "carrossel", "1080x1440",
                [{"n": 1, "origem": "acervo/a.jpg", "textos": ["Texto que sumiu"]}],
                logo={"apelido": "clara", "arquivo": "logo_corp_branca.png"}, contagem={"momento": "Réveillon"})
    _, avisos = rc.conferir(r, tmp_path, ["01.png", "02.png"], "cv_corporativo",
                            _medir({"01.png": (1080, 1440, None), "02.png": (1080, 1440, None)}), rascunho)
    texto = " | ".join(avisos)
    assert "receita com 1 slide(s), entregues 2" in texto
    assert "empresa casa_veraneio" in texto
    assert "Texto que sumiu" in texto
    assert "contagem regressiva sem prazo" in texto
    # logo do Corp numa peça do Corp não é aviso; na Casa Veraneio é
    _, avisos_cv = rc.conferir(r, tmp_path, [], "casa_veraneio")
    assert any("logo da receita" in a for a in avisos_cv)
    assert not any("logo da receita" in a for a in avisos)


def test_aviso_de_ritmo_respeita_o_pedido(rc, tmp_path):
    r = rc.nova("casa_veraneio", "Reels", "reels", "1080x1920", [
        {"n": 1, "origem": "acervo/a.mp4", "duracao_s": 2.5, "velocidade": 0.75, "textos": []},
        {"n": 2, "origem": "acervo/b.mp4", "duracao_s": 4.0, "velocidade": 1, "textos": []},
        {"n": 3, "origem": "fundo:verde", "duracao_s": 1.5, "velocidade": None, "textos": []}])
    _, avisos = rc.conferir(r, tmp_path, [], "casa_veraneio", pedido="Reels do Lodge 1")
    assert any("cena 1 com 2.5 s" in a for a in avisos) and any("cena 2 em 1x" in a for a in avisos)
    assert not any("cena 3" in a for a in avisos)  # cena de fundo não é take
    _, avisos = rc.conferir(r, tmp_path, [], "casa_veraneio", pedido="Reels em 1x, velocidade normal")
    assert not any("1x" in a for a in avisos)


def test_na_producao_grava_a_receita_conferida_com_a_faixa(rc, tmp_path):
    rascunho, final = tmp_path / "r", tmp_path / "r" / "entrega"
    final.mkdir(parents=True)
    (rascunho / "motion.json").write_text(json.dumps(_spec_motion()), encoding="utf-8")
    (rascunho / ".trilhas.json").write_text(json.dumps(
        {"Reels.mp4": ["CASA VERANEIO CORP/Casa_Veraneio_Corp_nu_disco.mp3"]}), encoding="utf-8")
    nome, linha = rc.na_producao(rascunho, final, ["Reels.mp4", "Reels_com_som.mp4"], "cv_corporativo", "CORP ｜ REELS",
                                 medir=_medir({"Reels.mp4": (1080, 1920, 7.5)}))
    assert nome == rc.DESTINO and "confere" in linha and "montada pelo sistema a partir do motion.json" in linha
    gravada = json.loads((final / rc.DESTINO).read_text(encoding="utf-8"))
    assert gravada["faixa"] == {"arquivo": "CASA VERANEIO CORP/Casa_Veraneio_Corp_nu_disco.mp3", "estilo": "nu_disco"}
    assert gravada["conferencia"]["origem"] == "motion.json" and gravada["conferencia"]["avisos"] == []


def test_na_producao_usa_a_receita_do_max_e_avisa_divergencia(rc, tmp_path):
    rascunho, final = tmp_path / "r", tmp_path / "r" / "entrega"
    final.mkdir(parents=True)
    r = rc.nova("cv_corporativo", "Post", "post", "1080x1440", [{"n": 1, "origem": "acervo/a.jpg", "textos": []}],
                arquivos=["Post.png"])
    (rascunho / rc.ARQUIVO).write_text(json.dumps(r), encoding="utf-8")
    nome, linha = rc.na_producao(rascunho, final, ["Post.png"], "cv_corporativo",
                                 medir=_medir({"Post.png": (1080, 1920, None)}))
    assert nome == rc.DESTINO and linha.startswith("⚠ Receita da peça:") and "1080x1920" in linha
    assert "montada pelo sistema" not in linha


def test_na_producao_sem_arte_sem_receita_ou_json_quebrado(rc, tmp_path):
    rascunho, final = tmp_path / "r", tmp_path / "r" / "entrega"
    final.mkdir(parents=True)
    assert rc.na_producao(rascunho, final, ["Legenda - X.docx"], "casa_veraneio") == (None, "")
    nome, linha = rc.na_producao(rascunho, final, ["Arte.png"], "casa_veraneio")
    assert nome is None and "sem receita.json" in linha
    (rascunho / rc.ARQUIVO).write_text("{quebrado", encoding="utf-8")
    nome, linha = rc.na_producao(rascunho, final, ["Arte.png"], "casa_veraneio")
    assert nome is None and "não é um JSON válido" in linha


def test_instrucao_da_receita_so_nas_pecas_visuais(rc):
    assert rc.ARQUIVO in rc.instrucao("editor_video") and "duracao_s" in rc.instrucao("criador_imagens")
    assert rc.instrucao("editor_video", "texto") == "" and rc.instrucao("copywriter") == ""


# ---------------------------------------------------------------- Reels tipográfico do Corp

def test_quebra_de_linha_e_palavra_curta_nao_fica_pendurada(tp):
    assert tp.quebrar("Realize agora mesmo o seu orçamento", 20) == ["Realize agora mesmo", "o seu orçamento"]
    assert tp.quebrar("Seu time merece | uma noite à altura", 40) == ["Seu time merece", "uma noite à altura"]
    assert tp.quebrar("palavra", 3) == ["palavra"]


@pytest.mark.parametrize("frases", [FRASES[:3], FRASES + FRASES[:3]])
def test_de_4_a_6_frases(tp, frases):
    with pytest.raises(ValueError, match="de 4 a 6 frases"):
        tp.conferir_frases(frases)


@pytest.mark.parametrize("ruim", ["Chame no WhatsApp", "Escreva para usuario.teste@exemplo.com",
                                  "Ligue 11 99999-0000", "Pacote por R$ 100", "uma frase " * 6])
def test_frases_sem_contato_valor_ou_texto_demais(tp, ruim):
    with pytest.raises(ValueError):
        tp.conferir_frases(FRASES[:3] + [ruim])


def test_prazo_valido_so_com_confirmacao_e_data_futura(tp):
    bom = {"momento": "Confraternizações de fim de ano", "fechar_ate": "2026-11-30", "vale_ate": "2026-11-15",
           "valido": True}
    assert tp.prazo_valido(bom, HOJE) == {"momento": bom["momento"], "fechar_ate": "2026-11-30", "faltam": 19}
    assert tp.prazo_valido({**bom, "valido": False}, HOJE) is None
    assert tp.prazo_valido({**bom, "fechar_ate": "2026-11-10"}, HOJE) is None
    assert tp.prazo_valido({**bom, "vale_ate": "2026-11-10"}, HOJE) is None
    assert tp.prazo_valido(None, HOJE) is None and tp.prazo_valido({"valido": True}, HOJE) is None


def test_prazo_gravado_pelo_trabalhador_e_lido_pelo_gerador(tp, tmp_path):
    prazo = {"momento": "Réveillon", "fechar_ate": "2026-12-01", "vale_ate": "2026-11-18", "valido": True}
    tp.gravar_prazo(tmp_path, prazo)
    assert tp.ler_prazo(tmp_path, HOJE)["faltam"] == 20
    tp.gravar_prazo(tmp_path, None)  # sem prazo válido nesta versão: o arquivo antigo sai
    assert tp.ler_prazo(tmp_path, HOJE) is None and not (tmp_path / tp.ARQUIVO_PRAZO).exists()


def _tipos(cena: dict) -> list[str]:
    return [e["tipo"] for e in cena["elementos"]]


def test_roteiro_sem_prazo_nao_tem_contagem(tp, rc):
    import motion
    spec, ficha, avisos = tp.roteiro({"frases": FRASES, "kicker": "Confraternização", "vinheta": False}, None, HOJE)
    motion.validar(spec)
    assert spec["empresa"] == "cv_corporativo" and len(spec["cenas"]) == 5  # 4 frases + fechamento
    assert all(c["fundo"] == "verde" for c in spec["cenas"])
    assert not any("contagem" in _tipos(c) for c in spec["cenas"])
    fechamento = spec["cenas"][-1]["elementos"]
    assert {"tipo": "imagem", "logo": "caramelo"}.items() <= fechamento[-1].items()
    assert fechamento[0]["linhas"] == ["Realize agora mesmo", "o seu orçamento"]
    assert ficha["contagem"] is None and ficha["molde"] == "tipografico" and rc.validar(ficha) == []
    assert ficha["logo"]["arquivo"] == "logo_corp_caramelo_texto_branco.png"
    assert "O ano está" in " ".join(ficha["textos"]) and ficha["arquivos"] == ["Reels_Tipografico.mp4"]
    assert 8 <= ficha["duracao_s"] <= 15 and avisos == []


def test_roteiro_com_prazo_valido_tem_contagem_regressiva(tp):
    prazo = {"momento": "Confraternizações de fim de ano", "fechar_ate": "2026-11-30", "vale_ate": "2026-11-15",
             "valido": True}
    spec, ficha, _ = tp.roteiro({"frases": FRASES}, prazo, HOJE)
    contagem = [e for c in spec["cenas"] for e in c["elementos"] if e["tipo"] == "contagem"]
    assert len(contagem) == 1 and contagem[0]["valor"] == 19 and contagem[0]["de"] > contagem[0]["valor"]
    assert ficha["contagem"] == {"momento": prazo["momento"], "fechar_ate": "2026-11-30"}


def test_roteiro_com_prazo_vencido_avisa_e_sai_sem_contagem(tp):
    vencido = {"momento": "Réveillon", "fechar_ate": "2026-12-01", "vale_ate": "2026-11-01", "valido": True}
    spec, ficha, avisos = tp.roteiro({"frases": FRASES}, vencido, HOJE)
    assert not any(e["tipo"] == "contagem" for c in spec["cenas"] for e in c["elementos"])
    assert ficha["contagem"] is None and any("sem contagem" in a for a in avisos)


def test_roteiro_so_do_corp_e_formatos(tp, monkeypatch):
    with pytest.raises(ValueError, match="só do Corporativo"):
        tp.roteiro({"empresa": "casa_veraneio", "frases": FRASES}, None, HOJE)
    monkeypatch.setenv("VERANEIO_EMPRESA", "casa_vero")  # a empresa da peça (trabalhador) manda
    with pytest.raises(ValueError):
        tp.roteiro({"frases": FRASES}, None, HOJE)
    monkeypatch.delenv("VERANEIO_EMPRESA")
    spec, _, _ = tp.roteiro({"frases": FRASES, "formato": "1080x1080", "saida": "entrega/Linkedin.mp4"}, None, HOJE)
    assert spec["formato"] == "1080x1080" and spec["juntar"] == "entrega/Linkedin.mp4"
    with pytest.raises(ValueError, match="vinheta"):
        tp.roteiro({"frases": FRASES, "formato": "1080x1080", "vinheta": True}, None, HOJE)
    spec, ficha, _ = tp.roteiro({"frases": FRASES, "vinheta": True}, None, HOJE)
    assert "juntar" not in spec and ficha["vinheta_em"] and not any(
        e["tipo"] == "imagem" for e in spec["cenas"][-1]["elementos"])  # a vinheta termina no logo


def test_instrucao_do_tipografico_so_no_editor_do_corp(tp):
    texto = tp.instrucao("editor_video", "cv_corporativo")
    assert "tipografico.json" in texto and tp.ARQUIVO_PRAZO in texto
    assert tp.instrucao("editor_video", "casa_veraneio") == "" and tp.instrucao("criador_imagens", "cv_corporativo") == ""
    assert tp.instrucao("editor_video", "cv_corporativo", "texto") == ""


# ---------------------------------------------------------------- backend: prazo vai com a produção

def test_prazo_comercial_da_producao(monkeypatch):
    import prazos_comerciais
    import producao
    vigente = {"momento": "Réveillon", "fechar_ate": date(2026, 12, 1), "vale_ate": date(2026, 11, 18),
               "faltam": 20, "valido": True, "confirmado_por": "login"}
    monkeypatch.setattr(prazos_comerciais, "vigente", lambda empresa, texto: vigente)
    assert producao._prazo_comercial("cv_corporativo", "Reels") == {
        "momento": "Réveillon", "fechar_ate": "2026-12-01", "vale_ate": "2026-11-18", "faltam": 20, "valido": True}
    monkeypatch.setattr(prazos_comerciais, "vigente", lambda empresa, texto: None)
    assert producao._prazo_comercial("cv_corporativo", "Reels") is None

    def quebra(empresa, texto):
        raise OSError("sem calendário")
    monkeypatch.setattr(prazos_comerciais, "vigente", quebra)
    assert producao._prazo_comercial("cv_corporativo", "Reels") is None


def test_vinheta_entra_por_padrao_so_no_9x16(tp):
    """Thomas, 11/11/2026: a vinheta do logo entra por padrão no Reels; no 1:1 o fechamento leva o logo."""
    assert tp.com_vinheta({"frases": FRASES}) and tp.com_vinheta({"formato": "1080x1920"})
    assert not tp.com_vinheta({"formato": "1080x1080"}) and not tp.com_vinheta({"vinheta": False})
    spec, ficha, _ = tp.roteiro({"frases": FRASES}, None, HOJE)
    assert ficha["vinheta_em"] and "juntar" not in spec


def test_tipografico_so_quando_pedido(tp):
    assert "SÓ quando o pedido disser" in tp.instrucao("editor_video", "cv_corporativo")
