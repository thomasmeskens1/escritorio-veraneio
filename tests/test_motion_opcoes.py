"""Opções B, C e D da vinheta do logo (scripts/max/motion_opcoes*.py; Thomas, 04/11/2026): a A segue a aprovada e é
o padrão; todas as opções montam nos três formatos, duram 5,5 a 7 s, terminam com o logo parado e centrado; na
Casa Veraneio o pino cai de fora do quadro e quica curto (passa do ponto e volta) antes de assentar.
"""

import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageChops  # noqa: E402


def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "motion_opcoes.py").exists():
            return pasta
    return None


@pytest.fixture
def mv(monkeypatch, tmp_path):
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não montado")
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade nos testes
    import motion_vinheta
    return motion_vinheta


def _logo(pasta: Path, nome: str, fundo: str) -> Path:
    """Logo de mentira: símbolo Caramelo (com uma "chave" Verde dentro, para a Vero) e o nome em duas linhas."""
    pasta.mkdir(parents=True, exist_ok=True)
    imagem = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
    imagem.paste((217, 161, 91, 255), (0, 0, 280, 300))
    imagem.paste((0, 54, 27, 255), (120, 60, 160, 260))
    cor_nome = (0, 54, 27, 255) if fundo == "creme" else (255, 255, 255, 255)
    imagem.paste(cor_nome, (320, 40, 900, 130))
    imagem.paste(cor_nome, (320, 160, 900, 250))
    imagem.save(pasta / nome)
    return pasta / nome


@pytest.fixture
def logos(mv, tmp_path):
    return {empresa: _logo(tmp_path / pasta, nome, fundo)
            for empresa, (pasta, nome, _altura, fundo, _luz) in mv.VINHETAS.items()}


def test_opcoes_de_cada_empresa_e_a_a_continua_a_aprovada(mv):
    import motion_opcoes
    import motion_roteiros
    assert set(motion_opcoes.OPCOES) == set(mv.VINHETAS)
    for empresa, opcoes in motion_opcoes.OPCOES.items():
        assert list(opcoes) == ["A", "B", "C", "D"], empresa
        assert opcoes["A"]["camadas"] is motion_roteiros.ROTEIROS[empresa]["camadas"]
        assert mv.duracao(empresa) == motion_roteiros.ROTEIROS[empresa]["duracao"]  # padrão: A
        for variante, roteiro in opcoes.items():
            assert 5.5 <= roteiro["duracao"] <= 7.0, (empresa, variante)
            batidas = roteiro["batidas"]
            assert all(0 <= a < b <= roteiro["duracao"] for a, b in batidas.values()), (empresa, variante)
            assert roteiro["duracao"] - max(b for _, b in batidas.values()) >= 1.15, (empresa, variante)
    assert motion_opcoes.roteiro("casa_vero", "b") is motion_opcoes.OPCOES["casa_vero"]["B"]
    with pytest.raises(ValueError, match="Opção da vinheta"):
        motion_opcoes.roteiro("casa_vero", "E")


def test_renderizador_sem_variante_e_a_opcao_a(mv, logos):
    import motion_roteiros
    render = mv.Renderizador("casa_veraneio", "1080x1920", logos["casa_veraneio"])
    assert render.roteiro["camadas"] is motion_roteiros.ROTEIROS["casa_veraneio"]["camadas"]


@pytest.mark.parametrize("variante", ["B", "C", "D"])
def test_cada_opcao_monta_nos_tres_formatos_e_termina_parada(mv, logos, variante):
    for empresa, logo in logos.items():
        fundo = mv.VINHETAS[empresa][3]
        for formato in mv.FORMATOS:
            render = mv.Renderizador(empresa, formato, logo, variante)
            duracao = render.duracao
            for k in range(0, 61):  # quadros-chave de toda a história (uma amostra só: rápido)
                t = duracao * k / 60
                quadro = render._amostra(render.camadas(t))
                assert quadro.size == (render.largura, render.altura), (empresa, variante, formato, t)
            fim = render.quadro(duracao - 0.05)
            caixa = ImageChops.difference(fim, render.fundo).convert("L").point(
                lambda v: 255 if v > 30 else 0).getbbox()
            assert caixa, (empresa, variante, formato)
            largura, altura = render.largura, render.altura
            assert abs((caixa[0] + caixa[2]) / 2 - largura / 2) < largura * 0.03, (empresa, variante, formato)
            assert caixa[1] > altura * 0.2 and caixa[3] < altura * 0.8, (empresa, variante, formato)
            assert fim.getpixel((2, 2)) == mv.cor(fundo)[:3], (empresa, variante, formato)
            assert render.quadro(duracao - 1.0).tobytes() == fim.tobytes(), (empresa, variante, formato)  # ~1 s parado


def _corpo(render, t):
    return next(c for c in render.camadas(t) if getattr(c, "nome", "") == "corpo")


@pytest.mark.parametrize("variante", ["B", "C", "D"])
def test_veraneio_pino_cai_de_fora_e_quica_curto(mv, logos, variante):
    import motion_opcoes_comum
    for formato in mv.FORMATOS:
        render = mv.Renderizador("casa_veraneio", formato, logos["casa_veraneio"], variante)
        inicio, toque = render.roteiro["batidas"]["queda"]
        (_, final), _ = motion_opcoes_comum.base_do_simbolo(render.palco)
        assert not [c for c in render.camadas(inicio - 0.02) if getattr(c, "nome", "") == "corpo"]
        assert _corpo(render, inicio + 0.001).y < 0  # a ponta (pé do pino) acima do topo: entra inteiro de fora
        alturas = [_corpo(render, inicio + k / 120).y for k in range(round((toque - inicio) * 120))]
        assert all(b > a for a, b in zip(alturas, alturas[1:]))  # só desce, acelerando
        assert alturas[-1] - alturas[-2] > 3 * (alturas[1] - alturas[0])
        assenta = [_corpo(render, toque + k / 240) for k in range(round(motion_opcoes_comum.ASSENTA * 240) + 1)]
        assert max(c.y for c in assenta) > final + 2  # passa do ponto (afunda como mola)...
        assert min(c.y for c in assenta) < final - 0.05 * render.palco.simbolo_altura  # ...e quica para cima
        assert max(c.esticar[0] for c in assenta) > 1.08  # achata no toque (squash)
        assert motion_opcoes_comum.ASSENTA <= 0.6
        parado = _corpo(render, toque + motion_opcoes_comum.ASSENTA + 0.01)
        assert parado.y == pytest.approx(final) and parado.esticar == (1.0, 1.0)
        rastro = render.roteiro["batidas"]["rastro"][0]
        assert rastro >= toque + motion_opcoes_comum.ASSENTA - 0.05  # a seta e o nome só depois do quique
        assert render.roteiro["batidas"]["nome1"][0] > rastro


def test_opcoes_de_cada_empresa_sao_historias_diferentes(mv):
    import motion_opcoes
    for empresa, opcoes in motion_opcoes.OPCOES.items():
        funcoes = {opcao["camadas"] for opcao in opcoes.values()}
        assert len(funcoes) == 4, empresa
        assert len({opcao["titulo"] for opcao in opcoes.values()}) == 4, empresa
