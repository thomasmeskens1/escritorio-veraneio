"""Motion graphics dos vídeos (scripts/max/motion.py; Thomas, 04/11/2026): curvas, cascata, conferência do
motion.json, quadros desenhados com Pillow (fonte padrão quando as da marca não estão, como no contêiner), vinheta
do logo de cada empresa e a instrução do Editor de Vídeo. O que precisa do ffmpeg só roda onde ele existe (PC).
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "motion.py").exists():
            return pasta
    return None


@pytest.fixture
def motion(monkeypatch, tmp_path):
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não montado")
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade nos testes
    import motion as modulo
    return modulo


def _texto(**extra):
    return {"tipo": "texto", "texto": "Onde o seu grupo", "fonte": "playfair", "tamanho": 80, "y": 700, **extra}


# ---------------------------------------------------------------- curvas

def test_curvas_comecam_em_0_terminam_em_1_e_so_crescem(motion):
    for nome, curva in motion.CURVAS.items():
        assert curva(0) == pytest.approx(0) and curva(1) == pytest.approx(1), nome
        assert curva(-1) == pytest.approx(0) and curva(2) == pytest.approx(1), nome  # sem passar do ponto (sem quique)
        valores = [curva(i / 50) for i in range(51)]
        assert all(b >= a - 1e-9 for a, b in zip(valores, valores[1:])), nome


def test_ease_out_desacelera(motion):
    assert motion.ease_out_cubic(0.3) > 0.6 > motion.linear(0.3)
    assert motion.ease_out_quint(0.3) > motion.ease_out_cubic(0.3)
    assert motion.ease_in_out_cubic(0.5) == pytest.approx(0.5)
    assert motion.ease_in_cubic(0.5) == pytest.approx(0.125)


def test_cores_da_marca(motion):
    assert motion.cor("verde") == (0, 54, 27, 255)
    assert motion.cor("Caramelo", 0.5) == (217, 161, 91, 128)
    assert motion.cor("#F0DBC3") == (240, 219, 195, 255)
    with pytest.raises(ValueError, match="Cor desconhecida"):
        motion.cor("roxo")


# ---------------------------------------------------------------- linha do tempo

def test_cascata_entre_elementos(motion):
    elementos = [{"tipo": "degrade", "opacidade": 0.2}, _texto(entrada="letras"), _texto(), {"tipo": "filete", "y": 900}]
    tempos = motion.linha_do_tempo(elementos, 5.0, cascata=0.15, inicio=0.3)
    assert tempos[0]["inicio"] == 0 and tempos[0]["saida"] is None  # degradê: desde o começo, sem saída
    assert [round(t["inicio"], 2) for t in tempos[1:]] == [0.3, 0.45, 0.6]
    assert tempos[3]["fim_entrada"] == pytest.approx(0.6 + 0.8)  # desenha: 0,8 s
    for t in tempos[1:]:  # saída suave terminando 0,1 s antes do corte
        assert t["saida"]["inicio"] == pytest.approx(5.0 - 0.1 - 0.5) and t["fim"] == pytest.approx(4.9)


def test_palavra_a_palavra_empurra_o_proximo(motion):
    elementos = [_texto(entrada={"efeito": "palavra", "intervalo": 0.12}), _texto()]
    tempos = motion.linha_do_tempo(elementos, 6.0, cascata=0.15, inicio=0.3)
    assert tempos[0]["fim_entrada"] == pytest.approx(0.3 + 3 * 0.12 + 0.6)  # 4 palavras
    assert tempos[1]["inicio"] == pytest.approx(0.3 + 3 * 0.12 + 0.15)


def test_inicio_explicito_e_sem_saida(motion):
    tempos = motion.linha_do_tempo([_texto(entrada={"efeito": "sobe", "inicio": 2.0}, sai=False)], 4.0)
    assert tempos[0]["inicio"] == 2.0 and tempos[0]["saida"] is None and tempos[0]["fim"] == 4.0


def test_cena_curta_demais_e_recusada(motion):
    with pytest.raises(ValueError, match="depois do início da saída"):
        motion.linha_do_tempo([_texto(entrada={"efeito": "sobe", "inicio": 1.2})], 1.6)
    with pytest.raises(ValueError, match="depois do fim da cena"):
        motion.linha_do_tempo([_texto(entrada={"efeito": "sobe", "inicio": 5})], 4.0, sai=False)


# ---------------------------------------------------------------- motion.json

def _spec(**cena):
    return {"formato": "1080x1920", "cenas": [{"video": "acervo/a.mp4", "duracao": 5, "saida": "trabalho/a.mp4",
                                               "elementos": [_texto()], **cena}]}


def test_spec_valido(motion):
    spec = _spec(elementos=[{"tipo": "degrade", "cor": "verde", "y0": 1100, "opacidade": [0, 0.85]},
                            _texto(entrada="palavra"), {"tipo": "filete", "y": 1500},
                            {"tipo": "caixa", "texto": "POV: chegou", "cor": "creme", "cor_texto": "verde", "y": 360},
                            {"tipo": "contagem", "valor": 45, "sufixo": " noites", "y": 800},
                            {"tipo": "imagem", "logo": "branca", "altura": 135, "y": 1500}])
    assert motion.validar(spec) is spec
    assert motion.validar({"cenas": [{"fundo": "verde", "duracao": 3, "saida": "f.mp4"}]})


@pytest.mark.parametrize("cena, erro", [
    ({"elementos": [{"tipo": "estrela", "y": 1}]}, "tipo desconhecido"),
    ({"elementos": [_texto(tamnho=80)]}, "campo\\(s\\) desconhecido"),
    ({"elementos": [_texto(entrada="gira")]}, "Entrada desconhecida"),
    ({"elementos": [_texto(entrada={"efeito": "sobe", "duracao": 5})]}, "duração da entrada"),
    ({"elementos": [_texto(entrada="desenha")]}, "é para filete"),
    ({"elementos": [{"tipo": "texto", "texto": "sem y"}]}, "falta a posição"),
    ({"elementos": [_texto(cor="roxo")]}, "Cor desconhecida"),
    ({"elementos": [{"tipo": "contagem", "y": 1}]}, "valor"),
    ({"elementos": [{"tipo": "imagem", "y": 1}]}, "sem \"arquivo\""),
    ({"velocidade": 1.5}, "nunca acelerar"),
    ({"velocidade": 0.3}, "lenta demais"),
    ({"saida": ""}, "falta \"saida\""),
    ({"elementos": [_texto(texto="R$ 2.000 a diária")]}, "com_valor"),
])
def test_spec_invalido(motion, cena, erro):
    with pytest.raises(ValueError, match=erro):
        motion.validar(_spec(**cena))


def test_valor_liberado_com_com_valor(motion):
    spec = {**_spec(elementos=[_texto(texto="R$ 2.000 a diária")]), "com_valor": True}
    assert motion.validar(spec)


def test_spec_sem_cenas_ou_formato_errado(motion):
    with pytest.raises(ValueError, match="sem \"cenas\""):
        motion.validar({})
    with pytest.raises(ValueError, match="Formato"):
        motion.validar({**_spec(), "formato": "720x1280"})
    with pytest.raises(ValueError, match="sem \"video\" nem \"fundo\""):
        motion.validar({"cenas": [{"saida": "a.mp4"}]})


def test_caminho_fora_da_pasta(motion, tmp_path):
    with pytest.raises(ValueError, match="fora da pasta"):
        motion._dentro(tmp_path, "../fora.mp4", "saida")


# ---------------------------------------------------------------- quadros (Pillow)

def _alfa(imagem: Image.Image) -> int:
    return sum(imagem.getchannel("A").histogram()[1:])


def _cena(motion, tmp_path, elementos, duracao=4.0, **extra):
    return motion.Cena(elementos, duracao, 1080, 1920, base=tmp_path, **extra)


def test_quadros_com_fonte_padrao(motion, tmp_path):
    cena = _cena(motion, tmp_path, [_texto(entrada="sobe")])
    assert any("não encontrada" in a for a in cena.avisos)  # sem as fontes da marca (contêiner): avisa
    assert _alfa(cena.quadro(0.0)) == 0  # antes da entrada: nada
    meio, cheio = cena.quadro(0.5), cena.quadro(1.5)
    assert 0 < _alfa(meio) and 0 < _alfa(cheio)
    assert meio.getchannel("A").getextrema()[1] < cheio.getchannel("A").getextrema()[1]  # ainda em fade
    caixa = cheio.getchannel("A").getbbox()
    assert caixa[1] >= 690 and caixa[3] <= 820  # no y pedido, sem cortar
    assert abs((caixa[0] + caixa[2]) / 2 - 540) < 6  # centralizado
    assert _alfa(cena.quadro(3.95)) == 0  # saiu antes do corte


def test_sobe_parte_de_baixo(motion, tmp_path):
    cena = _cena(motion, tmp_path, [_texto(entrada={"efeito": "sobe", "distancia": 60})])
    topo_meio = cena.quadro(0.35).getchannel("A").getbbox()[1]
    topo_fim = cena.quadro(1.5).getchannel("A").getbbox()[1]
    assert topo_meio > topo_fim


def test_palavra_a_palavra(motion, tmp_path):
    cena = _cena(motion, tmp_path, [_texto(entrada={"efeito": "palavra", "inicio": 0, "intervalo": 0.2})])
    cedo, tarde = cena.quadro(0.15).getchannel("A").getbbox(), cena.quadro(2.0).getchannel("A").getbbox()
    assert cedo[2] < tarde[2] - 100  # só a primeira palavra apareceu


def test_revela_desenha_escala_e_letras(motion, tmp_path):
    elementos = [_texto(entrada={"efeito": "revela", "inicio": 0}),
                 {"tipo": "filete", "largura": 400, "y": 1000, "entrada": {"efeito": "desenha", "inicio": 0}},
                 {"tipo": "caixa", "largura": 300, "altura": 100, "y": 1200,
                  "entrada": {"efeito": "escala", "inicio": 0}},
                 {"tipo": "texto", "texto": "KICKER", "espacamento": 9, "tamanho": 28, "y": 400,
                  "entrada": {"efeito": "letras", "inicio": 0}}]
    cena = _cena(motion, tmp_path, elementos, sai=False)
    largura = lambda q, y0, y1: (lambda b: b[2] - b[0])(q.crop((0, y0, 1080, y1)).getchannel("A").getbbox())  # noqa
    cedo, fim = cena.quadro(0.25), cena.quadro(2.0)
    assert largura(cedo, 690, 820) < largura(fim, 690, 820)          # revela da esquerda para a direita
    assert largura(cedo, 990, 1010) < largura(fim, 990, 1010) == 400  # filete se desenha até a largura toda
    assert largura(cedo, 1150, 1350) < largura(fim, 1150, 1350) == 300  # caixa assenta em 100%
    assert largura(cedo, 380, 460) > largura(fim, 380, 460)           # letras: espaçamento maior que assenta


def test_contagem_chega_ao_valor(motion, tmp_path):
    cena = _cena(motion, tmp_path, [{"tipo": "contagem", "valor": 1200, "tamanho": 120, "y": 600,
                                     "entrada": {"efeito": "contagem", "inicio": 0}}], sai=False)
    assert motion.numero_br(1200) == "1.200"
    cedo, fim = cena.quadro(0.05), cena.quadro(2.0)
    assert _alfa(cedo) < _alfa(fim)
    assert cena.quadro(2.0).tobytes() == cena.quadro(3.0).tobytes()  # parado no valor final


def test_quadros_parados_sao_reaproveitados(motion, tmp_path):
    cena = _cena(motion, tmp_path, [{"tipo": "degrade", "opacidade": 0.3}, _texto()], duracao=3.0)
    quadros = list(cena.quadros_crus())
    assert len(quadros) == 90 and all(len(q) == 1080 * 1920 * 4 for q in quadros)
    assert quadros[50] is quadros[60]  # tudo já entrou: o mesmo quadro, sem redesenhar
    fundo = next(cena.quadros_crus("verde"))
    assert fundo[:4] == bytes((0, 54, 27, 255))


def test_aviso_de_area_da_interface(motion, tmp_path):
    cena = _cena(motion, tmp_path, [_texto(y=1700)])
    assert any("área da interface" in a for a in cena.avisos)


def test_imagem_procura_logo_nas_referencias(motion, tmp_path):
    pasta = tmp_path / "_referencias" / "CASA_VERANEIO"
    pasta.mkdir(parents=True)
    Image.new("RGBA", (400, 120), (240, 219, 195, 255)).save(pasta / "logo_branca.png")
    cena = _cena(motion, tmp_path, [{"tipo": "imagem", "logo": "branca", "altura": 60, "y": 1500}], sai=False)
    assert cena.itens[0]["sprite"].altura == 60 and cena.itens[0]["sprite"].largura == 200
    with pytest.raises(ValueError, match="não encontrada"):
        _cena(motion, tmp_path, [{"tipo": "imagem", "arquivo": "nada.png", "y": 10}])


# ---------------------------------------------------------------- vinheta do logo

def _logo(pasta: Path, nome: str, cor_nome=(240, 219, 195, 255)) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    imagem = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
    imagem.paste((217, 161, 91, 255), (0, 0, 280, 300))   # "símbolo"
    imagem.paste(cor_nome, (320, 60, 900, 240))  # "nome"
    imagem.save(pasta / nome)
    return pasta / nome


def test_vinheta_de_cada_empresa_usa_so_o_proprio_logo(motion, tmp_path):
    import motion_vinheta
    for empresa, (pasta, nome, *_resto) in motion_vinheta.VINHETAS.items():
        _logo(tmp_path / "drive" / "CÉREBRO" / "MARCAS" / pasta, nome)
    assert set(motion_vinheta.VINHETAS) == {"casa_veraneio", "cv_corporativo", "casa_vero"}
    for empresa, (pasta, nome, *_resto) in motion_vinheta.VINHETAS.items():
        logo = motion_vinheta.arquivo_logo(empresa, tmp_path / "peca")
        assert logo.parent.name == pasta and logo.name == nome
    with pytest.raises(ValueError, match="sem vinheta"):
        motion_vinheta.arquivo_logo("outra", tmp_path)


def test_vinheta_prefere_a_copia_da_peca_e_monta_os_quadros(motion, tmp_path):
    import motion_vinheta
    from PIL import ImageChops
    peca = tmp_path / "peca"
    for empresa, (pasta, nome, _altura, fundo, _luz) in motion_vinheta.VINHETAS.items():
        logo = _logo(peca / "_referencias" / pasta, nome, (0, 54, 27, 255) if fundo == "creme" else (255,) * 4)
        assert motion_vinheta.arquivo_logo(empresa, peca) == logo
        duracao = motion_vinheta.duracao(empresa)
        for formato in motion_vinheta.FORMATOS:
            render = motion_vinheta.Renderizador(empresa, formato, logo)
            largura, altura = render.largura, render.altura
            fim = render.quadro(duracao - 0.05)
            caixa = ImageChops.difference(fim, render.fundo).convert("L").point(
                lambda v: 255 if v > 30 else 0).getbbox()  # o que não é fundo: o logo assentado
            assert abs((caixa[0] + caixa[2]) / 2 - largura / 2) < largura * 0.03, (empresa, formato)  # centrado
            assert caixa[1] > altura * 0.2 and caixa[3] < altura * 0.8
            assert fim.getpixel((2, 2)) == motion.cor(fundo)[:3]  # fundo da marca, opaco, nas bordas
            assert render.quadro(0.0).tobytes() == render.fundo.tobytes()  # começa vazio
            assert render.quadro(duracao - 0.6).tobytes() == fim.tobytes()  # ~1,2 s parado no fim


def test_logo_em_partes_refaz_o_png(motion, tmp_path):
    import motion_vinheta
    logo = _logo(tmp_path / "CASA_VERANEIO", "logo_caramelo_texto_creme.png")
    pecas = motion_vinheta.partes_do_logo("casa_veraneio", logo, 1080, 1920)
    assert {"corpo", "rastro", "nome1"} <= set(pecas)
    simbolo = sum(p.imagem.getchannel("A").histogram()[255] for n, p in pecas.items() if not n.startswith("nome"))
    assert simbolo > 0 and pecas["nome1"].x > pecas["corpo"].x  # o nome fica à direita do símbolo


def test_roteiros_tem_batidas_em_ordem_e_logo_parado_no_fim(motion):
    import motion_roteiros
    assert set(motion_roteiros.ROTEIROS) == {"casa_veraneio", "cv_corporativo", "casa_vero"}
    for empresa, roteiro in motion_roteiros.ROTEIROS.items():
        assert 5.5 <= roteiro["duracao"] <= 6.5, empresa
        batidas = roteiro["batidas"]
        assert all(0 <= a < b <= roteiro["duracao"] for a, b in batidas.values()), empresa
        assert roteiro["duracao"] - max(b for _, b in batidas.values()) >= 1.15, empresa  # ~1,2 s de logo parado
        assert batidas["surge"][0] < batidas["desliza"][0] < batidas["nome1"][0]  # símbolo, depois o nome


def test_ease_out_back_passa_pouco_do_ponto_e_assenta(motion):
    from motion_camadas import ease_out_back, mola, trecho
    assert ease_out_back(0) == pytest.approx(0) and ease_out_back(1) == pytest.approx(1)
    pico = max(ease_out_back(i / 100) for i in range(101))
    assert 1.0 < pico < 1.06  # elegante: passa ~4% e volta, sem quique de desenho animado
    assert max(ease_out_back(i / 100, 1.7) for i in range(101)) > pico
    assert mola(0) == 0 and abs(1 - mola(3.0)) < 0.01
    assert trecho(1.5, 1.0, 2.0) == pytest.approx(0.5) and trecho(0.5, 1.0, 2.0) == 0 and trecho(3, 1, 2) == 1


def test_icones_saem_rgba_no_tamanho_pedido(motion):
    import motion_icones
    for nome in motion_icones.DESENHOS:
        imagem = motion_icones.icone(nome, 96)
        assert imagem.mode == "RGBA" and imagem.size == (96, 96), nome
        assert imagem.getchannel("A").getbbox(), nome  # tem desenho
    assert motion_icones.icone("lupa", 64, aro=0.5).size == (64, 64)
    assert motion_icones.anel(40, 3, (217, 161, 91)).mode == "RGBA"
    with pytest.raises(ValueError):
        motion_icones.icone("outro", 64)


# ---------------------------------------------------------------- prompt do Editor de Vídeo

def test_instrucao_do_editor_de_video(motion):
    try:
        import trabalhador_max
    except Exception as erro:  # dependências do PC podem faltar no contêiner
        pytest.skip(f"trabalhador indisponível: {erro}")
    texto = trabalhador_max.instrucao_motion("editor_video", "casa_vero")
    assert "motion.py" in texto and "--empresa casa_vero" in texto and "outra empresa" in texto
    assert trabalhador_max.instrucao_motion("criador_imagens", "casa_vero") == ""
    ritmo = trabalhador_max.RITMO_VIDEO
    assert "3,5 a 6 s" in ritmo and "5 a 7 takes" in ritmo and "NUNCA acelerar" in ritmo and "0,75x" in ritmo  # 04/11/2026
    assert "batida" in ritmo


# ---------------------------------------------------------------- com ffmpeg (só no PC)

def test_aplicar_e_vinheta_com_ffmpeg(motion, tmp_path):
    if not motion.achar_ffmpeg() or not motion.achar_ffmpeg("ffprobe"):
        pytest.skip("ffmpeg ausente (contêiner)")
    saida = motion.aplicar(None, tmp_path / "fundo.mp4", [_texto()], "1080x1350", 2.0, fundo="verde",
                           base=tmp_path)
    assert saida["quadros"] == 60 and motion.duracao_do_video(saida["saida"]) == pytest.approx(2.0, abs=0.1)
    clipe = motion.aplicar(saida["saida"], tmp_path / "clipe.mp4", [_texto(entrada="palavra")], "1080x1920",
                           base=tmp_path, velocidade=0.85)
    assert motion.duracao_do_video(clipe["saida"]) == pytest.approx(2.0 / 0.85, abs=0.15)  # câmera lenta alonga
    junta = motion.juntar_cenas([saida["saida"], saida["saida"]], tmp_path / "junta.mp4")
    assert motion.duracao_do_video(junta) == pytest.approx(4.0, abs=0.2)
    previas = motion.previa(junta, [1.0], tmp_path / "previas", "p")
    assert Image.open(previas[0]).size == (1080, 1350)
    spec = tmp_path / "motion.json"
    spec.write_text(json.dumps({"formato": "1080x1080", "cenas": [
        {"fundo": "creme", "duracao": 2.5, "saida": "s.mp4", "elementos": [_texto(cor="verde", y=400)]}]}),
        encoding="utf-8")
    assert motion.renderizar(spec)[0]["saida"].is_file()
    shutil.rmtree(tmp_path / "previas", ignore_errors=True)
