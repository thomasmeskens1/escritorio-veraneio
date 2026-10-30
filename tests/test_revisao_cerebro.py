"""Cérebro: Monday, contatos, aprovação pela Diretoria, 👎, reranker e consolidação (revisão de 30/10/2026, itens
2.12 a 2.16 e 2.20). Banco temporário (tests/conftest.py).
"""

import asyncio

import cerebro
import cerebro_base as base
import config
import correcoes
import tarefas

tarefas.iniciar()


def test_contatos_de_lead_nao_viram_conhecimento():
    texto = "Lead: Ana, ana.souza@empresa.com.br, (11) 98765-4321, CPF 123.456.789-09. Diária R$ 12.100."
    limpo = cerebro.sem_contatos(texto)
    assert "ana.souza" not in limpo and "98765" not in limpo and "123.456" not in limpo
    assert "R$ 12.100" in limpo  # preço continua


def test_prospectador_nao_vira_conhecimento():
    tarefa = tarefas.criar(config.DONO_MAX, "comercial", "prospectador", "Ache leads em SP", "simples",
                           empresa="cv_corporativo")
    tarefas.atualizar(tarefa, status="concluida", resposta="Lead X, contato@x.com")
    assert cerebro.aprender_tarefa(tarefa) is None


def test_diretoria_que_nao_e_o_thomas_aprova_e_o_cerebro_aprende(monkeypatch):
    ensinados = []

    async def ensinar(login, texto, empresa="*"):
        ensinados.append(login)
        return "ok"

    monkeypatch.setattr(correcoes, "_dono", lambda _a: {"sub": "lucca@casaveraneio.com", "nome": "Lucca",
                                                         "role": "diretoria"})
    monkeypatch.setattr(cerebro, "ensinar", ensinar)
    tarefa = tarefas.criar("ana", "marketing", "copywriter", "Legenda", "simples")
    with correcoes._db() as db:
        obs = db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, tipo) VALUES "
                         "(?, 'ana', 'marketing', 'copywriter', ?, 'nunca use emoji', 'correcao')",
                         (tarefas._agora(), tarefa)).lastrowid
    asyncio.run(correcoes.aprovar(obs, correcoes.Decisao(regra="Nunca use emoji nas legendas."), ""))
    assert ensinados == [config.DONO_MAX]


def test_joinha_para_baixo_tira_a_resposta_do_conhecimento():
    import avaliacoes

    tarefa = tarefas.criar(config.DONO_MAX, "marketing", "copywriter", "Legenda do Lodge 9", "simples")
    tarefas.atualizar(tarefa, status="concluida", resposta="Legenda ruim do Lodge 9")
    trecho = cerebro.aprender_tarefa(tarefa)
    ativo = lambda: base.db().execute("SELECT ativo FROM conhecimento WHERE id = ?", (trecho,)).fetchone()[0]
    avaliacoes.avaliar(tarefas.obter(tarefa), config.DONO_MAX, -1)
    assert ativo() == 0
    avaliacoes.avaliar(tarefas.obter(tarefa), config.DONO_MAX, 0)  # voto retirado: volta
    assert ativo() == 1
    assert base.PASSO_CONCLUSAO < base.PASSO_FALHA / 5  # conclusão sozinha não anula um 👎


def test_reranker_exige_tarefas_diferentes(monkeypatch):
    import numpy as np

    import reranker

    X = np.random.RandomState(0).rand(400, len(reranker.vetor({}))).astype(np.float32)
    y = np.array([0, 1] * 200)
    grupos = np.array([1, 2, 3] * 133 + [1])
    monkeypatch.setattr(reranker, "exemplos", lambda com_grupos=False: (X, y, grupos) if com_grupos else (X, y))
    assert "3 de 40 tarefas" in reranker.treinar()["observacao"]  # 400 linhas de só 3 tarefas: não treina


def test_consolidacao_tem_tolerancia_e_confere_na_subida():
    from apscheduler.schedulers.background import BackgroundScheduler

    import consolidacao_semanal

    agendador = BackgroundScheduler(timezone="America/Sao_Paulo")
    consolidacao_semanal.agendar(agendador)
    semanal = agendador.get_job("consolidacao_semanal")
    assert semanal.misfire_grace_time == 24 * 3600


def test_pasta_de_manuais_vazia_nao_desativa_os_oficiais(tmp_path, monkeypatch):
    trecho = base._inserir("oficial", "00_manual_teste.md", "Manual", "Regra de ouro do teste", "casa_veraneio")
    monkeypatch.setattr(cerebro, "PASTA_CONHECIMENTO", tmp_path)  # pasta vazia (Drive fora, renomeada)
    assert cerebro.indexar_oficiais() == 0
    assert base.db().execute("SELECT ativo FROM conhecimento WHERE id = ?", (trecho,)).fetchone()[0] == 1


def test_relatorio_libera_so_os_proprios_scripts_e_expira(tmp_path, monkeypatch):
    import os

    import pytest
    from fastapi import HTTPException

    import relatorios

    monkeypatch.setattr(relatorios, "PASTA", tmp_path)
    nome = "5-" + "a" * 24 + ".html"
    (tmp_path / nome).write_text("<html><script>const graficos = [];</script></html>", encoding="utf-8")
    politica = relatorios.abrir(nome).headers["content-security-policy"]
    assert "https://cdnjs.cloudflare.com" in politica and "'sha256-" in politica and "unsafe-inline" not in politica.split("style-src")[0]
    os.utime(tmp_path / nome, (1, 1))  # 1970: passou dos 30 dias
    with pytest.raises(HTTPException):
        relatorios.abrir(nome)
    assert not (tmp_path / nome).exists()
