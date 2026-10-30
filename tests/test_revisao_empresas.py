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
