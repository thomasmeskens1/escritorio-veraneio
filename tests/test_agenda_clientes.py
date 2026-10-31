"""Agenda de clientes sob pedido (Onda 2, item 14): reativação, recompra, pré-reserva de fim de ano e recorrência,
calculadas em código, sem IA. Só dados fictícios (empresas inventadas, exemplo.com); sem Monday, Max nem painel real.
"""

import asyncio
import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

import agenda_clientes as a
import carteira
import comercial
import tarefas

tarefas.iniciar()

HOJE = date(2026, 10, 31)
NOMES = ("AURELIX", "BRONTAL", "CYRENE", "DORVANA", "ESKARA")


def _ganho(nome, tipo, pax, quando, local="Jundiaí"):
    return {"nome": nome, "dropdown_mm3b42sb": "PJ", "color_mm4pd1wc": tipo, "n_meros_mkmgpvds": str(pax),
            "local_mkmgy5nb": local, "date_mkp5eds": quando}


BASE = {
    "contas": [{"nome": "AURELIX SISTEMAS LTDA", "industry": "Tecnologia", "text_mkxj2284": "Campinas",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "2024-12-10", "company_domain": "aurelix.exemplo.com"},
               {"nome": "Brontal Logistica", "industry": "Logística", "text_mkxj2284": "Barueri",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "Aguardando Definição", "company_domain": ""},
               {"nome": "Cyrene Alimentos", "industry": "Alimentos", "text_mkxj2284": "Jundiaí",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "2026-03-15", "company_domain": ""}],
    "ganhos": [_ganho("10 - AURELIX SISTEMAS", "Confraternização", 120, "2024-12-10"),
               _ganho("11 - AURELIX SISTEMAS Extras", "Confraternização", 10, "2024-12-20"),  # a mesma compra
               _ganho("12 - DORVANA TECH", "Evento Corporativo", 40, "2026-01-20"),
               _ganho("13 - DORVANA TECH", "Evento Corporativo", 40, "2026-04-20"),
               _ganho("14 - DORVANA TECH copy", "Evento Corporativo", 40, "2026-07-20"),
               _ganho("15 - CYRENE ALIMENTOS", "Confraternização", 200, "2025-12-05"),
               _ganho("16 - CYRENE ALIMENTOS", "Workshop", 30, "2026-03-15"),
               _ganho("17 - ESKARA ENERGIA", "Confraternização", 80, "2025-11-28"),
               _ganho("18 - ESKARA ENERGIA", "Confraternização", 85, "2026-12-12")],  # já fechou este ano
}


@pytest.fixture
def sem_diretoria(monkeypatch):
    monkeypatch.setattr(a, "ve_nomes", lambda login: False)
    monkeypatch.setattr(a, "ve_valores", lambda login: False)


@pytest.fixture
def diretoria(monkeypatch):
    monkeypatch.setattr(a, "ve_nomes", lambda login: True)
    monkeypatch.setattr(a, "ve_valores", lambda login: True)


def _por_nome(lista):
    return {r["nome"].split()[0].upper(): r for r in lista}


def test_pedidos_que_viram_agenda_e_os_que_nao():
    assert a.secoes("prospectador", "Prospectador, quem devo reativar?") == ["reativacao"]
    assert a.secoes("estrategista", "Me mostra a agenda de clientes") == list(a.PEDE)
    assert a.secoes("prospectador", "Quais clientes estão na hora da recompra?") == ["recompra"]
    assert a.secoes("prospectador", "Lista da pré-reserva de dezembro") == ["fim_de_ano"]
    assert a.secoes("estrategista", "Qual a recorrência dos clientes?") == ["recorrencia"]
    # Prospecção, estudo, criação de leads e outros agentes seguem o caminho de antes.
    assert not a.e_pedido("prospectador", "Prospecte 10 empresas para eventos de fim de ano")
    assert not a.e_pedido("estrategista", "Faça a Matriz BCG com a recorrência dos clientes")
    assert not a.e_pedido("prospectador", "Crie os leads da prévia #12 de reativação")
    assert not a.e_pedido("copywriter", "Quem devo reativar?")


def test_datas_e_chave_do_cliente():
    assert a.data("2024-12-10") == date(2024, 12, 10) and a.data("10/12/2024") == date(2024, 12, 10)
    assert a.data("Aguardando Definição") is None and a.data("") is None and a.data("2024-13-40") is None
    assert a.cliente("11 - AURELIX SISTEMAS Extras") == a.cliente("AURELIX SISTEMAS LTDA")
    assert a.cliente("14 - DORVANA TECH copy") == a.cliente("12 - DORVANA TECH")


def test_reativacao_mais_de_12_meses_com_a_epoca_de_procurar():
    registros = a.montar(BASE, HOJE)
    dados = a.reativacao(registros, HOJE, em_prospeccao={a.cliente("AURELIX SISTEMAS")})
    lista = _por_nome(dados["lista"])
    assert set(lista) == {"AURELIX"}  # Cyrene e Dorvana voltaram há pouco; Eskara já tem evento marcado
    assert lista["AURELIX"]["ultimo"] == date(2024, 12, 10) and lista["AURELIX"]["tipo"] == "Confraternização"
    assert lista["AURELIX"]["sugestao"].startswith("procurar já")  # dezembro chega em 2 meses
    assert lista["AURELIX"]["aviso"] == "já está na Prospecção Ativa"
    assert [r["nome"].upper() for r in dados["sem_data"]] == ["BRONTAL LOGISTICA"]  # sem deduzir a data


def test_sugestao_quatro_a_tres_meses_antes():
    assert a.sugestao(12, date(2026, 3, 1)) == "procurar entre ago e set"
    assert a.sugestao(1, date(2026, 3, 1)) == "procurar entre set e out"
    assert a.sugestao(5, date(2026, 3, 1)).startswith("procurar já")


def test_recompra_pelo_ritmo_com_grau_de_confianca():
    lista = _por_nome(a.recompra(a.montar(BASE, HOJE), HOJE))
    dorvana = lista["DORVANA"]
    assert dorvana["ritmo"] == 90 and dorvana["confianca"].startswith("3 eventos")
    assert dorvana["proxima"] == date(2027, 1, 16) and dorvana["oferecer"] == "oferecer a data até 17/11/2026"
    assert "ESKARA" not in lista  # já fechou o próximo
    assert lista["AURELIX"]["confianca"].startswith("1 evento")  # aniversário da data (dez/2026)


def test_pre_reserva_de_fim_de_ano():
    dados = a.fim_de_ano(a.montar(BASE, HOJE), HOJE)
    assert [r["nome"].split()[0].upper() for r in dados["lista"]] == ["CYRENE", "AURELIX"]  # maiores primeiro
    cyrene = dados["lista"][0]  # o evento de dezembro (200 pax), não o último (workshop de março)
    assert (cyrene["tipo"], cyrene["pax"], cyrene["fim_de_ano"]) == ("Confraternização", "200", date(2025, 12, 5))
    assert dados["lista"][1]["pax"] == "120"  # o "Extras" de 10 pax não conta como tamanho do evento
    assert dados["fechados"] == 1 and dados["ultima_chamada"]


def test_quem_nao_e_da_diretoria_so_ve_contagens(sem_diretoria):
    texto = a.executar("usuario.teste@exemplo.com", "agenda de clientes", hoje=HOJE, base=BASE,
                       vendas=[("Corp", "10 - AURELIX", date(2024, 12, 10), 5000.0)])
    assert not any(nome in texto.upper() for nome in NOMES)
    assert "R$" not in texto and "só as contagens" in texto
    assert "1. Reativação: 1 cliente(s)" in texto and "Sem data de último evento no CRM: 1" in texto
    assert "3. Pré-reserva de fim de ano: 2 cliente(s)" in texto and "Já fecharam nov/dez de 2026: 1" in texto


def test_diretoria_ve_nomes_e_valores(diretoria):
    texto = a.executar("usuario.teste@exemplo.com", "agenda de clientes", hoje=HOJE, base=BASE,
                       vendas=[("Corp", "10 - AURELIX", date(2024, 12, 10), 5000.0),
                               ("Corp", "12 - DORVANA", date(2026, 1, 20), 3000.0),
                               ("Corp", "13 - DORVANA", date(2026, 4, 20), 3000.0)],
                       em_prospeccao=set())
    assert "**AURELIX SISTEMAS LTDA**" in texto and "**DORVANA TECH**" in texto and "BRONTAL" in texto.upper()
    assert "quem volta R$ 6.000 (55%), uma compra R$ 5.000" in texto


def test_lista_nominal_configuravel_sem_ser_diretoria(tmp_path, monkeypatch):
    import auth

    monkeypatch.setattr(auth, "ve_financeiro", lambda login: False)
    monkeypatch.setattr(a, "ARQUIVO_CONFIG", tmp_path / "agenda_clientes.json")
    assert not a.ve_nomes("usuario.teste@exemplo.com")  # sem arquivo: ninguém além da Diretoria
    a.ARQUIVO_CONFIG.write_text(json.dumps({"veem_nomes": ["usuario.teste@exemplo.com"]}), encoding="utf-8")
    assert a.ve_nomes("usuario.teste@exemplo.com") and not a.ve_nomes("outro.teste@exemplo.com")
    assert not a.ve_valores("usuario.teste@exemplo.com")  # valores continuam só da Diretoria
    a.ARQUIVO_CONFIG.write_text("{quebrado", encoding="utf-8")
    assert not a.ve_nomes("usuario.teste@exemplo.com")


def test_recorrencia_junta_aditivos_e_conta_quem_sumiu():
    vendas = [("Corp", "1 - ALFA", date(2024, 1, 10), 100.0), ("Corp", "2 - ALFA Aditivo", date(2024, 1, 20), 10.0),
              ("Corp", "3 - BETA", date(2025, 1, 10), 100.0), ("Corp", "4 - BETA", date(2026, 1, 10), 100.0),
              ("Corp", "5 - BETA", date(2026, 7, 10), 100.0), ("Hospedagem", "GAMA", date(2026, 9, 1), 50.0)]
    dados = a.recorrencia(vendas, HOJE)
    corp = dados["Corp"]
    assert corp["clientes"] == 2 and corp["faixas"]["1"] == 1 and corp["faixas"]["3+"] == 1
    assert corp["juntadas"] == 1 and corp["sumidos"] == 1 and corp["intervalo_medio"] == round((365 + 181) / 2)
    sem_valores = a.texto_recorrencia(dados, valores=False)
    assert "R$" not in sem_valores and "ALFA" not in sem_valores and "Casa Veraneio Corporativo: 2 clientes" in sem_valores
    assert "R$ 300" in a.texto_recorrencia(dados, valores=True)


def test_recorrencia_le_o_banco_do_painel_temporario(tmp_path, monkeypatch):
    import relatorios

    banco = tmp_path / "analytics.db"
    with sqlite3.connect(banco) as db:
        db.execute("CREATE TABLE crm_vendas (venda_id TEXT, negocio TEXT, nome TEXT, valor REAL, data DATE)")
        db.executemany("INSERT INTO crm_vendas VALUES (?, ?, ?, ?, ?)",
                       [("1", "Corp", "1 - ALFA", 100, "2025-05-01"), ("2", "Corp", "2 - ALFA", 100, "2026-05-01")])
    monkeypatch.setattr(relatorios, "BANCO", banco)
    assert len(a.vendas_do_painel()) == 2
    texto = a.recorrencia_para_estudo(financeiro=False)
    assert texto.startswith("### Clientes que voltam") and "2 compras 1 (100%)" in texto and "R$" not in texto


def test_iniciar_responde_sem_ia_e_sem_cerebro(monkeypatch, sem_diretoria):
    import cerebro
    import orquestrador

    entregues = []

    async def entregar(linha):
        entregues.append(linha)

    monkeypatch.setattr(comercial, "clientes", lambda: BASE)
    monkeypatch.setattr(a, "vendas_do_painel", lambda: [])
    monkeypatch.setattr(orquestrador, "entregar", entregar)
    monkeypatch.setattr(cerebro, "aprender_tarefa", lambda *_: pytest.fail("a agenda não vira conhecimento"))
    agente = SimpleNamespace(id="prospectador")
    tarefa_id = asyncio.run(a.iniciar("usuario.teste@exemplo.com", "comercial", agente, "Quem devo reativar?"))
    linha = tarefas.obter(tarefa_id)
    assert linha["status"] == "concluida" and linha["modelo"] == a.MODELO
    assert "Reativação" in linha["resposta"] and "AURELIX" not in linha["resposta"]
    assert entregues and entregues[0]["id"] == tarefa_id


def test_historico_do_estudo_nao_leva_nomes_para_a_web(monkeypatch):
    import estudos

    monkeypatch.setattr(comercial, "clientes", lambda: BASE)
    monkeypatch.setattr(carteira, "_nomes", None)
    monkeypatch.setattr(estudos, "_painel", lambda financeiro=True: "")
    monkeypatch.setattr(estudos, "_cerebro", lambda *a, **k: "")
    historico = [{"texto": "agenda de clientes", "resposta": "1. **AURELIX SISTEMAS** · Confraternização"}]
    texto = estudos.prompt("estrategista", "Faça a SWOT do Corporativo", "cv_corporativo", historico)
    assert "AURELIX" not in texto.upper() and carteira.OCULTO in texto
