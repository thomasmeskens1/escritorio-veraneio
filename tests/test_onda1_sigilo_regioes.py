"""Onda 1, conserto 17: sigilo por linha no Cérebro (N2-gestor-09, N2-cerebro-09) e pedido por região
(N2-gestor-01, primeira parte). Banco temporário (tests/conftest.py); dados e nomes fictícios.
"""

import json

import pytest

import carteira
import cerebro
import cerebro_base as base
import cerebro_imoveis as imoveis
import cerebro_sigilo as sigilo
from cerebro_texto import dividir
from agents import executor

CLIENTE = "Zephyra Fictícia"


@pytest.fixture
def carteira_ficticia(monkeypatch):
    monkeypatch.setattr(carteira, "_nomes_do_crm", lambda: carteira.chaves([CLIENTE]))
    eventos = []
    monkeypatch.setattr(cerebro.atividade, "evento_em_thread", lambda *a, **k: eventos.append((a, k)))
    return eventos


def _trecho(i: int, ref: str, conteudo: str, tipo: str = "oficial") -> dict:
    return {"id": i, "titulo": f"Trecho {i}", "conteudo": conteudo, "fonte_tipo": tipo, "fonte_ref": ref,
            "data": "10/11/2026", "sinais": {}}


def _busca(monkeypatch, trechos):
    monkeypatch.setattr(base, "buscar", lambda *a, **k: list(trechos))
    monkeypatch.setattr(cerebro.lacunas, "da_busca", lambda *a, **k: None)
    monkeypatch.setattr(cerebro.imoveis, "responder", lambda *a, **k: None)


# --- Sigilo por linha ----------------------------------------------------------------------------------

def test_linha_com_cliente_sai_e_o_resto_fica(carteira_ficticia, monkeypatch):
    _busca(monkeypatch, [_trecho(1, "01_regras.md", "O check-in é às 14h.\nNo ano passado a Zephyra Fictícia "
                                 "fechou um evento.\nO check-out é às 11h e o café vai até as 10h.")])
    resposta = cerebro.consultar("regras da casa", "gestor", 0, externo=True)
    assert "check-in é às 14h" in resposta and "check-out é às 11h" in resposta
    assert "zephyra" not in resposta.lower() and sigilo.AVISO.strip() in resposta and resposta != sigilo.BLOQUEIO
    # Pelo caminho completo da ferramenta (gratuito de fora): a resposta não é mais bloqueada inteira.
    ferramenta = executor.ConsultarCerebro(agente="gestor", tarefa_id=0, externo=True)
    assert "check-in é às 14h" in ferramenta._run("regras da casa")


def test_trecho_da_carteira_sai_inteiro_e_nao_conta_como_consultado(carteira_ficticia, monkeypatch):
    registros = []
    monkeypatch.setattr(base, "registrar_consulta", lambda t, a, p, ids, s: registros.append(ids))
    _busca(monkeypatch, [_trecho(1, "site/lodges/lodge-1", "Lodge com piscina e vista para o mar, para 12 pessoas."),
                         _trecho(2, "tarefa:9:carteira", "Contas ativas: lista de contas corporativas.", "tarefa"),
                         _trecho(3, "analytics/x/crm", "Faturamento do mês passado.", "dados")])
    resposta = cerebro.consultar("lodges com piscina", "gestor", 0, externo=True)
    assert "vista para o mar" in resposta
    assert "Contas ativas" not in resposta and "Faturamento" not in resposta
    assert registros == [[1]]  # o sigiloso não entra nas consultas da tarefa (a tarefa não vira sigilosa)


def test_sem_gratuito_de_fora_nada_muda(carteira_ficticia, monkeypatch):
    _busca(monkeypatch, [_trecho(1, "tarefa:9:carteira", "Cliente Zephyra Fictícia, contas ativas.", "tarefa")])
    assert "Zephyra" in cerebro.consultar("clientes", "gestor", 0)  # Max e local seguem vendo tudo


def test_sobrou_pouco_bloqueia_tudo_como_antes(carteira_ficticia, monkeypatch):
    _busca(monkeypatch, [_trecho(1, "14_persona_corporativo.md", "Persona longa " * 80),
                         _trecho(2, "01_regras.md", "Ok.")])
    assert cerebro.consultar("persona", "gestor", 0, externo=True) == sigilo.BLOQUEIO
    _busca(monkeypatch, [_trecho(1, "tarefa:3:financeiro", "Receita total do trimestre.", "tarefa")])
    assert cerebro.consultar("receita", "gestor", 0, externo=True) == sigilo.BLOQUEIO


def test_nenhum_campo_sigiloso_vaza(carteira_ficticia, monkeypatch):
    """Varredura: trechos sigilosos por referência e linhas com nome de cliente nunca chegam ao gratuito de fora."""
    sigilosos = [_trecho(10 + n, ref, f"SEGREDO-{n} conteúdo restrito.", "tarefa") for n, ref in enumerate(
        ["tarefa:1:carteira", "tarefa:2:financeiro", "14_persona_corporativo.md", "analytics/cv/google-ads",
         "analytics/cv/meta-ads", "analytics/cv/crm"])]
    publico = [_trecho(1, "02_marca.md", "Tom acolhedor e elegante, com frases curtas e convidativas.\n"
                       "Atende a Zephyra Fictícia desde 2020.\n" * 4)]
    _busca(monkeypatch, publico + sigilosos)
    resposta = cerebro.consultar("tom da marca", "gestor", 0, externo=True)
    assert "Tom acolhedor" in resposta
    assert "SEGREDO" not in resposta and not carteira.tem_nomes(resposta)
    assert not [a for a, _ in carteira_ficticia if a[1] == "cerebro_sigilo"]  # sem tarefa: nada registrado


def test_gatilho_vai_para_o_registro_sem_o_conteudo(carteira_ficticia, monkeypatch):
    _busca(monkeypatch, [_trecho(1, "01_regras.md", "Regra pública um.\nRegra pública dois.\nZephyra Fictícia aqui."),
                         _trecho(2, "tarefa:5:carteira", "Contas ativas.", "tarefa")])
    monkeypatch.setattr(cerebro.tarefas, "obter", lambda _id: None)
    monkeypatch.setattr(base, "registrar_consulta", lambda *a, **k: None)
    cerebro.consultar("regras", "gestor", 77, externo=True)
    detalhes = [k.get("detalhe", "") for a, k in carteira_ficticia if a[1] == "cerebro_sigilo"]
    assert detalhes and "1 trecho(s) financeiro/carteira" in detalhes[0] and "1 linha(s)" in detalhes[0]
    assert "Zephyra" not in detalhes[0] and "Contas ativas" not in detalhes[0]


# --- Regiões ---------------------------------------------------------------------------------------

def _documento(ref: str, conteudo: str) -> None:
    for t, c in dividir(conteudo.splitlines()[0].lstrip("# "), conteudo):
        base._inserir("site", ref, t, c, "casa_veraneio")


@pytest.fixture
def lodges_regioes():
    if not base.db().execute("SELECT 1 FROM conhecimento WHERE fonte_ref = 'site/lodges/lodge-801'").fetchone():
        for n, local, cat in ((801, "Praia Teste Norte - BA", "Praia"), (802, "Vila Teste Sol - CE", "Campo"),
                              (803, "Serra Teste - SC", "Campo"), (804, "Ubatuba - SP", "Praia"),
                              (805, "Gramado Teste - RS", "Campo"), (806, "Campo Teste - MS", "Campo")):
            _documento(f"site/lodges/lodge-{n}", f"# Lodge {n} — {local}\nFonte: https://exemplo.com/lodge-{n}\n"
                       f"Resumo: 4 quartos | até 10 pessoas | categoria: {cat}")
    imoveis.atualizar("casa_veraneio", forcar=True)


def _numeros(texto: str) -> set[int]:
    filtros = imoveis.interpretar(texto)
    chaves = ("cidade", "uf", "comodidade", "categoria")
    return {l["numero"] for l in imoveis.filtrar("casa_veraneio", **{k: filtros[k] for k in chaves})["linhas"]}


def test_casas_do_nordeste_saem_pela_tabela(lodges_regioes):
    resposta = imoveis.responder("as casas do Nordeste")
    assert resposta and "801" in resposta and "802" in resposta
    assert "803" not in resposta and "804" not in resposta and "região nordeste" in resposta
    assert _numeros("quais lodges temos no Nordeste?") >= {801, 802}
    assert not _numeros("quais lodges temos no Nordeste?") & {803, 804, 805, 806}


def test_sul_sudeste_litoral_e_estados_com_sul_no_nome(lodges_regioes):
    assert {803, 805} <= _numeros("casas na região Sul") and 806 not in _numeros("casas na região Sul")
    assert 804 in _numeros("lodges do Sudeste") and 801 not in _numeros("lodges do Sudeste")
    # "Mato Grosso do Sul" é o estado, não a região Sul.
    filtros = imoveis.interpretar("quais lodges em Mato Grosso do Sul")
    assert filtros["uf"] == "MS" and not filtros["regiao"]
    assert imoveis.interpretar("liste os lodges do sul de Minas")["regiao"] == ""
    litoral = _numeros("casas no litoral")
    assert {801, 804} <= litoral and not litoral & {802, 803, 805}
    assert _numeros("lodges do litoral norte") & {801, 802, 803, 805, 806} == set() and 804 in _numeros(
        "lodges do litoral norte")


def test_regiao_nao_reconhecida_avisa(lodges_regioes):
    assert "Não reconheci a região" in imoveis.responder("liste os lodges da região serrana")


def test_microrregiao_do_arquivo(lodges_regioes, monkeypatch, tmp_path):
    arquivo = tmp_path / "regioes.json"
    arquivo.write_text(json.dumps({"serra gaúcha": {"cidades": ["Gramado Teste"]}}), encoding="utf-8")
    monkeypatch.setattr(imoveis, "ARQUIVO_REGIOES", arquivo)
    assert _numeros("lodges da serra gaúcha") == {805}
    arquivo.write_text("{ quebrado", encoding="utf-8")  # arquivo ruim: só as fixas, sem erro
    assert "litoral norte" in imoveis._microrregioes()


def test_consulta_do_agente_por_regiao_sem_sigilo(lodges_regioes, monkeypatch):
    monkeypatch.setattr(carteira, "_nomes_do_crm", lambda: carteira.chaves([CLIENTE]))
    resposta = cerebro.consultar("as casas do Nordeste", "gestor", 0, externo=True)
    assert "Tabela de imóveis" in resposta and "801" in resposta and resposta != sigilo.BLOQUEIO
