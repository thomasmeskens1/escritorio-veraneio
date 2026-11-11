"""Regras de marca num arquivo só (backend/marcas_regras.json; Onda 2 de novembro, gestor-19, designer-33,
editor_video-19, sonoplasta-07): o teste falha quando o código das peças (scripts/max) discorda do arquivo. O que
depende da decisão 1 fica "pendente_decisao_1" e não é conferido. Os manuais (fora do git) só são lidos onde existem.
"""

import json
import re
import sys
from pathlib import Path

import pytest

import conferente_motor as motor

REGRAS = motor.marcas()
EMPRESAS = ("casa_veraneio", "cv_corporativo", "casa_vero")
PENDENTE = "pendente_decisao_1"


def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "logos_empresas.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    return None


PASTA = _pasta_max()
precisa_max = pytest.mark.skipif(PASTA is None, reason="scripts/max não montado")


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def test_arquivo_tem_as_tres_marcas_e_pendencias_sem_valor_inventado():
    assert set(REGRAS["marcas"]) == set(EMPRESAS)
    assert REGRAS["pendente"] == PENDENTE
    # Decisão 1: 0,75x no Corp e na Vero e o fechamento/vinheta da Vero continuam em aberto.
    assert REGRAS["marcas"]["cv_corporativo"]["video"]["velocidade"] == PENDENTE
    assert REGRAS["marcas"]["casa_vero"]["video"]["velocidade"] == PENDENTE
    assert REGRAS["marcas"]["casa_vero"]["fechamento"]["fundo"] == PENDENTE
    assert motor.da_marca("casa_vero", "video", "velocidade") is None  # pendente não é conferido
    assert motor.da_marca("casa_veraneio", "video", "velocidade") == 0.75


def test_musicas_aprovadas_em_11_11():
    aprovadas = {e: [f["n"] for f in REGRAS["marcas"][e]["som"]["faixas"] if f["status"] == "aprovada"]
                 for e in EMPRESAS}
    assert aprovadas == {"casa_veraneio": [2, 3, 5], "cv_corporativo": [1, 2, 3, 4, 6], "casa_vero": [1, 3, 4, 5, 6]}


@precisa_max
def test_cores_do_motion_dos_moldes_e_da_conferencia_da_arte():
    paleta = {k: v for k, v in REGRAS["paleta"].items() if not k.startswith("_")}
    camadas = pytest.importorskip("motion_camadas")
    assert {k: _hex(v) for k, v in camadas.CORES.items() if k != "preto"} == paleta
    css = (PASTA / "moldes" / "casa_veraneio" / "base.css").read_text(encoding="utf-8")
    for nome, valor in paleta.items():
        assert re.search(rf"--{nome}:\s*{valor}\b", css, re.I), (nome, valor)
    import conferencia_arte

    lista = " ".join(conferencia_arte.COMUM)
    assert all(valor in lista for valor in paleta.values())


@precisa_max
def test_logos_de_cada_empresa():
    import logos_empresas

    for empresa in EMPRESAS:
        marca = REGRAS["marcas"][empresa]
        assert logos_empresas.LOGOS[empresa]["pasta"] == marca["pasta_marcas"]
        assert logos_empresas.SIGLAS[empresa] == marca["sigla"]
        for apelido in logos_empresas.APELIDOS:
            assert logos_empresas.LOGOS[empresa][apelido] == marca["logos"][apelido], (empresa, apelido)
        assert set(marca["logo_por_fundo"].values()) <= set(logos_empresas.APELIDOS)


@precisa_max
def test_ritmo_e_veu_do_motion():
    texto = (PASTA / "motion.py").read_text(encoding="utf-8")
    padrao = float(re.search(r"^VELOCIDADE_PADRAO\s*=\s*([\d.]+)", texto, re.M).group(1))
    assert padrao == REGRAS["marcas"]["casa_veraneio"]["video"]["velocidade"]
    assert f"velocidade < {REGRAS['video']['velocidade_min']}" in texto
    assert f"velocidade > {REGRAS['video']['velocidade_max']}" in texto
    # O exemplo do cabeçalho usa "preto" só como véu leve (nunca degradê de leitura).
    for opacidade in re.findall(r'"tipo": "degrade", "cor": "preto", "opacidade": ([\d.]+)', texto):
        assert float(opacidade) <= REGRAS["veu"]["opacidade_max"]


@precisa_max
def test_vinheta_e_fechamento():
    vinheta = pytest.importorskip("motion_vinheta")
    for empresa in EMPRESAS:
        marca = REGRAS["marcas"][empresa]
        pasta, logo, altura, fundo, _ = vinheta.VINHETAS[empresa]
        assert pasta == marca["pasta_marcas"] and altura == marca["vinheta"]["logo_916_px"]
        if marca["vinheta"]["logo"] != PENDENTE:
            assert logo == marca["logos"][marca["vinheta"]["logo"]], empresa
        if marca["vinheta"]["fundo"] != PENDENTE:
            assert fundo == marca["vinheta"]["fundo"], empresa


@precisa_max
def test_moldes_da_casa_veraneio():
    texto = (PASTA / "molde.py").read_text(encoding="utf-8")
    assert re.search(rf'^FORMATO_PADRAO = "{REGRAS["feed"]["formato_padrao"]}"', texto, re.M)
    logos = dict(re.findall(r'"(\w+)": "(logo_[\w]+\.png)"', re.search(r"^LOGOS = \{.*\}$", texto, re.M).group(0)))
    do_molde = dict(re.findall(r'"(\w+)": "(\w+)"', re.search(r"^LOGO_DO_MOLDE = \{.*\}$", texto, re.M).group(0)))
    veraneio = REGRAS["marcas"]["casa_veraneio"]
    assert logos[do_molde["fechamento"]] == veraneio["logos"][veraneio["fechamento"]["logo"]]
    assert logos[do_molde["capa"]] == veraneio["logos"][veraneio["logo_por_fundo"]["foto"]]
    css = (PASTA / "moldes" / "casa_veraneio" / "base.css").read_text(encoding="utf-8")
    assert f"--logo: {REGRAS['feed']['logo_feed_px']}px" in css
    assert f"--logo-fim: {REGRAS['feed']['logo_fechamento_px']}px" in css
    com_moldes = {e for e in EMPRESAS if REGRAS["marcas"][e]["moldes"]}
    assert set(re.findall(r'"(\w+)"', re.search(r"^EMPRESAS = \(([^)]*)\)", texto, re.M).group(1))) == com_moldes


@precisa_max
def test_ficha_sonora_do_sonoplasta_e_da_biblioteca():
    import audio_biblioteca
    import sonoplasta

    assert sonoplasta.LUFS == REGRAS["som_comum"]["lufs"]
    assert f"TP={REGRAS['som_comum']['true_peak_alvo_db']}" in (PASTA / "sonoplasta.py").read_text(encoding="utf-8")
    for empresa in EMPRESAS:
        som = REGRAS["marcas"][empresa]["som"]
        assert sonoplasta.MARCAS[empresa] == som["catalogo"]
        geradas = [(estilo, bpm) for estilo, bpm, *_ in audio_biblioteca.FAIXAS[som["catalogo"]]]
        assert geradas == [(f["estilo"], f["bpm"]) for f in som["faixas"]], empresa


def test_catalogo_do_drive_bate_com_o_arquivo():
    """Só onde o Drive está (o PC): o status de cada faixa no catalogo.json é o do arquivo de regras."""
    pasta = PASTA and __import__("sonoplasta").BIBLIOTECA
    if not pasta or not (pasta / "catalogo.json").is_file():
        pytest.skip("Drive fora deste ambiente")
    catalogo = {(f["marca"], f["estilo"]): f.get("status") for f in json.loads(
        (pasta / "catalogo.json").read_text(encoding="utf-8"))}
    for empresa in EMPRESAS:
        som = REGRAS["marcas"][empresa]["som"]
        for faixa in som["faixas"]:
            assert catalogo.get((som["catalogo"], faixa["estilo"])) == faixa["status"], faixa


def test_manuais_nao_desmentem_o_arquivo():
    """Onde os manuais existem (PC): cores do manual 01, 0,75x nos manuais 05 e 06, logo de ~112 px no 11 e no 12."""
    import config

    pasta = config.PASTA_CONHECIMENTO
    manuais = {p.name[:2]: p.read_text(encoding="utf-8") for p in sorted(Path(pasta).glob("[0-9][0-9]_*.md"))} \
        if Path(pasta).is_dir() else {}
    if not manuais:
        pytest.skip("manuais fora do git e fora deste ambiente")
    for valor in (v for k, v in REGRAS["paleta"].items() if not k.startswith("_")):
        assert valor in manuais["01"], valor
    for numero in ("05", "06"):
        assert "0,75x" in manuais[numero], numero
    for numero in ("11", "12"):
        assert f"~{REGRAS['feed']['logo_feed_px']} px" in manuais[numero], numero
