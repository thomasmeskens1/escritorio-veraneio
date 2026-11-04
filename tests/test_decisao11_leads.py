"""Decisão 11 (Thomas, 04/11/2026): todos os usuários veem tudo de leads e projetos (clientes, contatos, orçamento de
cada um); só a visão somada (vendas do mês, receita, ROAS, "como estamos financeiramente") fica com a Diretoria.
O que não muda: nome de cliente e financeiro seguem fora dos gratuitos de fora (rota sigilosa, decisão 12).
Só dados fictícios; banco temporário (tests/conftest.py)."""

from datetime import date

import pytest

import acesso
import agenda_clientes as a
import auth
import cerebro
import cerebro_base as base
import roteamento
import tarefas

tarefas.iniciar()

FUNCIONARIO = "funcionario.teste@exemplo.com"
HOJE = date(2026, 10, 30)
BASE = {"contas": [{"nome": "1 - QUELVIRA EVENTOS LTDA", "industry": "Serviços", "data_mknc1nvw": "2024-12-10"}],
        "ganhos": [{"nome": "2 - QUELVIRA EVENTOS LTDA", "color_mm4pd1wc": "Confraternização",
                    "n_meros_mkmgpvds": "90", "local_mkmgy5nb": "Jundiaí", "date_mkp5eds": "2024-12-10"}]}


@pytest.fixture
def sem_diretoria(monkeypatch):
    monkeypatch.setattr(auth, "ve_financeiro", lambda login: False)
    monkeypatch.setattr(acesso, "ve_financeiro", lambda login: False)


def test_funcionario_usa_prospectador_e_estrategista(monkeypatch, sem_diretoria):
    monkeypatch.setattr(acesso, "carregar_usuarios", lambda: {FUNCIONARIO: {"role": "funcionario", "agentes": "*"}})
    monkeypatch.setattr(acesso, "e_master", lambda login: False)
    assert acesso.pode_usar({"sub": FUNCIONARIO}, "comercial", "prospectador")
    assert acesso.pode_usar({"sub": FUNCIONARIO}, "comercial", "estrategista")


def test_funcionario_ve_os_nomes_mas_nao_a_receita_somada(sem_diretoria):
    texto = a.executar(FUNCIONARIO, "agenda de clientes", hoje=HOJE, base=BASE, em_prospeccao=set(),
                       vendas=[("Corp", "2 - QUELVIRA EVENTOS", date(2024, 12, 10), 48000.0),
                               ("Corp", "3 - QUELVIRA EVENTOS", date(2025, 12, 10), 52000.0)])
    assert "QUELVIRA" in texto and "só as contagens" not in texto
    assert "R$" not in texto and "Receita (Diretoria)" not in texto  # receita somada de período: só a Diretoria
    assert a.ve_nomes(FUNCIONARIO) and not a.ve_valores(FUNCIONARIO)


def _trecho(ref: str, texto: str) -> int:
    return base._inserir("oficial", ref, f"Trecho {ref}", texto, "cv_corporativo")


def test_cerebro_abre_a_carteira_e_segura_os_totais():
    persona = _trecho("14_persona_corporativo.md", "xilofrena orçamento do evento da Quelvira: R$ 48 mil")
    crm = _trecho("analytics/cv_corporativo/crm", "xilofrena vendas do mês: 12, receita total R$ 900 mil")
    base._mudou()
    base.indice_atual(fresco=True)
    try:
        aberto = {t["id"] for t in base.buscar("xilofrena", k=5, empresa="cv_corporativo", financeiro=False)}
        diretoria = {t["id"] for t in base.buscar("xilofrena", k=5, empresa="cv_corporativo", financeiro=True)}
    finally:
        base._indice = None
    assert persona in aberto and crm not in aberto  # lead um a um: todos; total do período: Diretoria
    assert {persona, crm} <= diretoria


def test_carteira_aberta_continua_sigilosa_para_gratuito_de_fora():
    tarefa = tarefas.criar(FUNCIONARIO, "marketing", "copywriter", "Resuma o lead", "simples", "cv_corporativo")
    persona = _trecho("14_persona_corporativo.md", "persona com clientes fictícios")
    base.registrar_consulta(tarefa, "copywriter", "lead", [persona])
    assert not cerebro._consultou_financeiro(tarefa)  # não é mais trava da Diretoria
    assert cerebro._consultou_sigiloso(tarefa) and roteamento.sigilosa("copywriter", "Resuma", tarefa_id=tarefa)


def test_resposta_com_a_carteira_vira_trecho_aberto_e_sigiloso(sem_diretoria):
    tarefa = tarefas.criar(FUNCIONARIO, "marketing", "copywriter", "Quem são os clientes?", "simples",
                           "cv_corporativo")
    tarefas.atualizar(tarefa, status="concluida", resposta="Na carteira de clientes estão a Quelvira e outras.")
    trecho = cerebro.aprender_tarefa(tarefa)
    ref = base.db().execute("SELECT fonte_ref FROM conhecimento WHERE id = ?", (trecho,)).fetchone()[0]
    assert ref == f"tarefa:{tarefa}:carteira"
    assert not base.FINANCEIRO_REF.search(ref) and base.SIGILOSO_REF.search(ref)
