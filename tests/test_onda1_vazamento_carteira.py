"""Teste de vazamento (Onda 1, 11/11/2026; N2-estrategista-44 com o ajuste do crítico): carteira de clientes e
financeiro nunca vão para modelo gratuito de fora nem para a web. Em vez de selo e relatório por tarefa, este teste
falha se alguma rota passar a mandar esses dados para fora. Só dados fictícios; sem Monday, Max nem modelos.
"""

import pytest

import carteira
import cerebro
import comercial as c
import config
import estudos
import roteamento
import saude
import tarefas
from roteamento import Dificuldade

tarefas.iniciar()

EXTERNOS = ["openrouter/teste:free", "groq/teste", "mistral/teste", "gemini/teste", "cerebras/teste"]
CLIENTES = {
    "contas": [{"nome": "ZEPHYRA INVESTIMENTOS LTDA", "industry": "Serviços financeiros", "text_mkxj2284": "São Paulo",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "", "company_domain": "zephyra.exemplo.com"}],
    "ganhos": [{"nome": "77 - X7NOVA TECH", "dropdown_mm3b42sb": "PJ", "color_mm4pd1wc": "Evento Corporativo",
                "n_meros_mkmgpvds": "24", "local_mkmgy5nb": "Atibaia", "date_mkp5eds": ""}],
}
NOMES = ("Zephyra", "ZEPHYRA", "zephyra.exemplo.com", "X7NOVA", "X7nova", "X7")


@pytest.fixture
def carteira_ficticia(monkeypatch):
    monkeypatch.setattr(c, "clientes", lambda: CLIENTES)
    monkeypatch.setattr(carteira, "_nomes", None)
    yield
    carteira._nomes = None


def test_nenhum_modelo_externo_e_tratado_como_local():
    assert all(roteamento.externo_gratuito(m) for m in EXTERNOS)
    assert not any(roteamento.externo_gratuito(m) for m in ("claude-code/max", "ollama/teste", "anthropic/teste"))


@pytest.mark.parametrize("agente", sorted(roteamento.AGENTES_SIGILOSOS))
def test_agente_da_carteira_nunca_tem_gratuito_de_fora_na_rota(agente, monkeypatch):
    monkeypatch.setattr(config, "modelos_gratuitos", lambda: EXTERNOS)
    monkeypatch.setattr(config, "modelo_disponivel", lambda _m: True)
    monkeypatch.setattr(config, "MODELO_LOCAL", "ollama/teste")
    monkeypatch.setattr(saude, "disponivel", lambda _m: True)
    monkeypatch.setattr(tarefas, "chat_rapido_liberado", lambda *_a: False)
    for dificuldade in Dificuldade:
        modelos = [e.modelo for e in roteamento.etapas_imediatas(dificuldade, agente)]
        assert not any(roteamento.externo_gratuito(m) for m in modelos), (agente, dificuldade, modelos)


@pytest.mark.parametrize("modelo", EXTERNOS)
@pytest.mark.parametrize("agente", sorted(roteamento.AGENTES_SIGILOSOS))
def test_executor_barra_o_externo_antes_de_chamar_o_modelo(agente, modelo):
    from agents import executor

    with pytest.raises(executor.RotaSigilosa):
        executor._rodar(agente, "Pedido com a carteira.", "Resposta.", modelo, 60, executor.Resultado(texto=""), 0)


@pytest.mark.parametrize("referencia", ["tarefa:12:carteira", "tarefa:12:financeiro", "14_persona_corporativo.md",
                                        "analytics/painel/crm", "analytics/painel/meta-ads"])
def test_qualquer_agente_que_consultou_trecho_sigiloso_fica_na_rota_sigilosa(referencia, monkeypatch):
    monkeypatch.setattr(cerebro, "_refs_consultadas", lambda _t: ["05_marca.md", referencia])
    assert roteamento.sigilosa("copywriter", "Escreva a legenda do post", tarefa_id=99)
    monkeypatch.setattr(cerebro, "_refs_consultadas", lambda _t: ["05_marca.md"])
    assert not roteamento.sigilosa("copywriter", "Escreva a legenda do post", tarefa_id=99)


def test_financeiro_e_nome_de_cliente_no_pedido_ou_no_contexto_sao_sigilosos(carteira_ficticia):
    for pedido in ("Tivemos R$ 80 mil de faturamento em outubro", "Qual foi o ROAS?", "Me passe a carteira de clientes",
                   "Investimos R$ 5.000 em anúncios"):
        assert roteamento.sigilosa("copywriter", pedido), pedido
    assert roteamento.sigilosa("social_media", "Resuma", contexto="A Zephyra fechou o evento de junho.")
    assert roteamento.sigilosa("analista_metricas", "Resumo", financeiro=True)


def test_consulta_ao_cerebro_por_modelo_externo_nao_devolve_nome_de_cliente(carteira_ficticia, monkeypatch):
    from agents import executor

    monkeypatch.setattr(cerebro, "consultar", lambda *_a, **_k: "Trecho: a X7NOVA TECH fez evento em Atibaia.")
    ferramenta = executor.ConsultarCerebro(agente="copywriter", tarefa_id=0, externo=True)
    assert "sigiloso" in ferramenta._run("clientes de Atibaia") and "X7NOVA" not in ferramenta._run("x")


def test_pedido_que_vai_a_web_nunca_leva_nome_de_cliente(carteira_ficticia, monkeypatch):
    monkeypatch.setattr(c, "_rotulos", lambda: {"segmento": ["Indústria"]})
    monkeypatch.setattr(c, "_persona", lambda: "Persona: clientes como a Zephyra e a X7nova Tech.")
    monkeypatch.setattr(estudos, "_painel", lambda financeiro=True: "Painel: a Zephyra voltou em outubro.")
    monkeypatch.setattr(estudos, "_cerebro", lambda *_a, **_k: "Cérebro: evento da X7NOVA TECH em Atibaia.")
    historico = [{"texto": "E a Zephyra Investimentos?", "resposta": "A ZEPHYRA pediu proposta."}]
    pedidos_web = [
        c.prompt_prospeccao("Prospecte 5 empresas parecidas com a Zephyra", 5),
        estudos.prompt("estrategista", "Faça a Matriz BCG e compare com a Zephyra", "*", historico, True, web=True),
        estudos.prompt("estrategista", "Analise esta proposta da X7NOVA", "*", historico, True, web=False),
    ]
    for pedido in pedidos_web:
        for nome in NOMES:
            assert nome not in pedido, nome


def test_pedido_com_a_carteira_nominal_so_vai_ao_max_sem_web(carteira_ficticia, tmp_path, monkeypatch):
    import persona_corporativo

    chamadas = []
    monkeypatch.setattr(c, "pedir_ao_max", lambda prompt, *a, **k: chamadas.append((prompt, k)) or
                        "<<PERSONA>>\n# Persona\n<<FIM>>")
    monkeypatch.setattr(persona_corporativo, "PASTA", tmp_path)
    monkeypatch.setattr(c, "_evento", lambda *_a: None)
    c.atualizar_persona(0)
    prompt, argumentos = chamadas[0]
    assert "ZEPHYRA" in prompt and argumentos["web"] is False  # a lista nominal só sai sem nenhuma ferramenta
