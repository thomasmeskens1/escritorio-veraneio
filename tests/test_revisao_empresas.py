"""Financeiro, regras e empresa "Todas" (revisão de 30/10/2026, itens 1.6, 1.7 e 1.8). Banco temporário
(tests/conftest.py).
"""

import asyncio

import pytest
from fastapi import HTTPException

import cerebro
import cerebro_base as base
import correcoes
import fichas
import tarefas

tarefas.iniciar()


def test_termos_financeiros_sem_marcar_preco_publico():
    for texto in ("O faturamento do trimestre subiu", "Segundo o CRM, temos 79 contas ativas", "ROAS de 4,2",
                  "ticket médio de R$ 18 mil", "vendas do mês caíram"):
        assert cerebro.TERMOS_FINANCEIROS.search(texto), texto
    for texto in ("Diária R$ 12.100, mínimo 3 noites", "Casa à venda em Itu", "Taxa de ativação de R$ 2.000"):
        assert not cerebro.TERMOS_FINANCEIROS.search(texto), texto


def _observacao(empresa: str, texto: str) -> int:
    tarefa = tarefas.criar("ana-regra", "marketing", "copywriter", "Legenda", "simples", empresa=empresa)
    with correcoes._db() as db:
        return db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, tipo) "
                          "VALUES (?, 'ana-regra', 'marketing', 'copywriter', ?, ?, 'correcao')",
                          (tarefas._agora(), tarefa, texto)).lastrowid


@pytest.fixture
def aprovar(monkeypatch):
    async def ensinar(*_a, **_k):
        return "ok"

    monkeypatch.setattr(correcoes, "_dono", lambda _a: {"sub": "thomas", "role": "diretoria"})
    monkeypatch.setattr(cerebro, "ensinar", ensinar)

    def _aprovar(obs_id, regra, todas=False):
        return asyncio.run(correcoes.aprovar(obs_id, correcoes.Decisao(regra=regra, todas_as_empresas=todas), ""))
    return _aprovar


def test_regra_vale_so_para_a_empresa_da_tarefa(aprovar):
    aprovar(_observacao("casa_vero", "nunca cite diária"), "Na Casa Vero, nunca cite diária: são imóveis à venda.")
    aprovar(_observacao("casa_veraneio", "sempre cite a diária"), "Sempre cite a diária da baixa temporada.", todas=True)
    vero, veraneio = correcoes.regras_para("copywriter", "casa_vero"), correcoes.regras_para("copywriter", "casa_veraneio")
    assert "nunca cite diária" in vero and "Sempre cite a diária" in vero  # a da Vero e a que vale para todas
    assert "nunca cite diária" not in veraneio and "Sempre cite a diária" in veraneio


def test_texto_cru_da_conversa_nao_vira_regra(aprovar):
    crua = "Uma casa a 300 metros da praia, com 7 suítes para 16 pessoas, piscina privativa, jacuzzi " * 3 + "adorei!"
    with pytest.raises(HTTPException):
        aprovar(_observacao("casa_veraneio", crua), f"Seguir este padrão aprovado por Ana: {crua}"[:500])


def test_todas_as_empresas_busca_nas_tres_com_etiqueta():
    base._inserir("dados", "teste/vero", "Receita de imóveis vendidos", "Imóveis vendidos no trimestre: 4", "casa_vero")
    base._inserir("dados", "teste/corp", "Receita de eventos", "Imóveis vendidos? Não, eventos: 12 no trimestre",
                  "cv_corporativo")
    base._mudou()
    trechos = base.buscar("imóveis vendidos trimestre", k=5, empresa="*")
    titulos = " ".join(t["titulo"] for t in trechos)
    assert "[Casa Vero" in titulos and "Corporativo" in titulos


def test_ficha_com_empresa_todas_nao_quebra():
    assert isinstance(fichas.fichas_citadas("Compare o Lodge 20 com o Lodge 3", "*"), str)


# --- Item 1.9: contexto velho e plano herdado de modelo fraco ---------------------------------------------------

def test_historico_das_ultimas_24h_mais_a_troca_mais_recente():
    import orquestrador

    velho = {"texto": "Legenda do Lodge 35", "criada_em": "2026-10-20T10:00:00Z"}
    ontem = {"texto": "Carrossel do feriado", "criada_em": "2026-10-21T10:00:00Z"}
    agora = {"texto": "Com estes Lodges", "criada_em": tarefas._agora()}
    assert orquestrador._recentes([velho, ontem, agora]) == [agora]
    assert orquestrador._recentes([velho, ontem]) == [ontem]  # trabalho de ontem: a última troca continua


def test_fichas_do_pedido_ou_da_ultima_troca_que_citou_imoveis(monkeypatch):
    from agents import perfis

    citados = []
    monkeypatch.setattr(fichas, "fichas_citadas", lambda texto, empresa: citados.append(texto) or "")
    historico = [{"texto": "Legenda do Lodge 35", "resposta": "...", "criada_em": tarefas._agora()},
                 {"texto": "Carrossel com Lodge 02 e Lodge 119", "resposta": "...", "criada_em": tarefas._agora()},
                 {"texto": "Respostas: data 20/11", "resposta": "...", "criada_em": tarefas._agora()}]
    perfis.contexto("gestor", historico, "agora monte o carrossel")
    assert "Lodge 119" in citados[-1] and "Lodge 35" not in citados[-1]
    perfis.contexto("gestor", historico, "post do Lodge 7")
    assert citados[-1] == "post do Lodge 7"


def test_modelo_forte_refaz_o_plano_do_fraco(tmp_path, monkeypatch):
    import threading

    from agents import projeto

    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = ('{"entendimento": "E", "duvida": "", "titulo": "T", "etapas": '
             '[{"agente": "copywriter", "instrucao": "Textos", "fase": 1}]}')
    chamadas = []

    def executar(agente, descricao, esperado, papel):
        chamadas.append(agente)
        if "JSON com o entendimento" in esperado:
            return plano
        return f"entrega de {agente}"

    pasta = tmp_path / "7"
    (pasta / "etapas").mkdir(parents=True)
    (pasta / "plano.json").write_text('[{"agente": "copywriter", "instrucao": "Lodge 35", "fase": 1}]', encoding="utf-8")
    (pasta / "plano_modelo.txt").write_text("openrouter/fraco:free", encoding="utf-8")
    (pasta / "etapas" / "1_copywriter.md").write_text("textos do Lodge 35", encoding="utf-8")
    projeto.executar_projeto(7, "agora monte", "CTX", executar, threading.Event(), modelo="claude-code/max")
    assert "Lodge 35" not in (pasta / "plano.json").read_text(encoding="utf-8")  # replanejado
    assert (pasta / "plano_modelo.txt").read_text(encoding="utf-8") == "claude-code/max"
    assert chamadas.count("copywriter") == 1  # a etapa do fraco foi refeita
