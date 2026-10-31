"""Pauta da semana, fase 1 (Onda 2, item 15): o quadro do Monday (SIMULADO, nada de chamada real) comparado com a
grade do manual 15, por empresa, sem IA; a rotina não roda de madrugada.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_pauta_semana.py
"""

import asyncio
from datetime import date

import monday
import pauta_semana
import tarefas

SEGUNDA = date(2026, 11, 2)  # semana de 02/11 a 08/11/2026


def _item(n: int, nome: str, postagem: str = "", conta: str = "Casa Veraneio", status: str = "Aguardando",
          entrega: str = "", legenda: str = "") -> dict:
    return {"id": str(n), "name": nome, "column_values": [
        {"id": "data", "text": postagem}, {"id": monday.COL_STATUS, "text": status},
        {"id": monday.COL_CONTA, "text": conta}, {"id": pauta_semana.COL_ENTREGA, "text": entrega},
        {"id": monday.COL_LEGENDA, "text": legenda}]}


QUADRO = {
    "Novembro": [
        _item(1, "REELS | Lodge 239 à beira-mar", "2026-11-03", entrega="2026-11-03"),
        _item(2, "REELS | Réveillon Lodge 239 - 45 NOITES", "2026-11-20"),  # fora da semana
        _item(3, "REELS | Réveillon: faltam 60 noites", "2026-11-04", status="Revisão"),  # 57 com essa data
        _item(4, "CARROSSEL | Casas para o Réveillon", "2026-11-05"),
        _item(5, "CARROSSEL | Guia da Praia das Cigarras", "2026-11-06"),
        _item(6, "CARROSSEL | Feriado de 15/11", "2026-11-07"),  # 1 a mais
        _item(7, "STORIES | Bastidores", "2026-11-02"), _item(8, "STORIES | Enquete", "2026-11-02"),
        _item(9, "STORIES | Lodge 31", "2026-11-03"),
        _item(10, "REELS | Case de confraternização", "2026-11-04", conta="CV Corp"),
        _item(11, "CARROSSEL | Evento de fim de ano", "2026-11-05", conta="CV Corp"),
        _item(12, "Peça sem padrão no nome", "2026-11-05", conta="Casa Vero"),
        _item(13, "POST | Item sem conta", "2026-11-06", conta=""),
    ],
    "Definir Data": [_item(20, "REELS | Ideia sem data", conta="Casa Vero")],
}


def test_grade_por_empresa_aponta_buracos_e_excessos():
    a = pauta_semana.analisar(QUADRO, "casa_veraneio", SEGUNDA)
    assert a["grade"] == ["REELS: 2 de 3 (FALTAM 1)", "CARROSSEL: 3 de 2 (1 A MAIS)",
                          "STORIES: 2 de 5 a 7 dias com Stories (FALTAM 3)"]
    assert a["vencendo"] == ["REELS | Lodge 239 à beira-mar (entrega 03/11, Aguardando)"]
    assert a["contagens"] == ["REELS | Réveillon: faltam 60 noites: diz 60 noites, mas com a postagem em "
                              "04/11/2026 faltam 57 para o Réveillon"]
    assert a["sem_conta"] == ["POST | Item sem conta"]
    corp = pauta_semana.analisar(QUADRO, "cv_corporativo", SEGUNDA)
    assert corp["grade"] == ["REELS: 1 de 2 (FALTAM 1)", "CARROSSEL: 1 de 1 (ok)", "STORIES: 0 de 3 dias com Stories "
                                                                                  "(FALTAM 3)"]
    vero = pauta_semana.analisar(QUADRO, "casa_vero", SEGUNDA)
    assert vero["sem_tipo"] == ["Peça sem padrão no nome"] and vero["sem_data"] == 1
    assert all("Lodge 239" not in nome for _, i in vero["itens"] for nome in [i["name"]])  # nada da Casa Veraneio


def test_pauta_separa_as_empresas_e_nao_mexe_no_monday(monkeypatch):
    def proibido(*_a, **_k):
        raise AssertionError("a pauta com quadro simulado não chama o Monday")

    monkeypatch.setattr(monday, "_api", proibido)
    texto = pauta_semana.montar("*", SEGUNDA, QUADRO)
    assert texto.index("**Casa Veraneio**") < texto.index("**Casa Veraneio Corporativo**") < \
        texto.index("**Casa Vero Imóveis**")
    assert "nada foi criado, alterado ou enfileirado" in texto
    so_corp = pauta_semana.montar("cv_corporativo", SEGUNDA, QUADRO)
    assert "**Casa Veraneio Corporativo**" in so_corp and "Lodge 239" not in so_corp


def test_leitura_do_quadro_so_consulta(monkeypatch):
    consultas = []

    def api(consulta, variaveis=None, versao=None):
        consultas.append(consulta)
        return {"boards": [{"groups": [{"items_page": {"items": QUADRO["Novembro"]}}]}]}

    monkeypatch.setattr(monday, "grupo_por_nome", lambda nome, criar=False: None if criar else {"id": nome})
    monkeypatch.setattr(monday, "_api", api)
    quadro = pauta_semana.ler_quadro(*pauta_semana.semana(date(2026, 11, 30)))  # semana entre novembro e dezembro
    assert list(quadro) == ["Novembro", "Dezembro", "Definir Data"]
    assert consultas and all(c.lstrip().startswith("query") for c in consultas)


def test_rotina_da_pauta_nao_roda_de_madrugada():
    assert pauta_semana.horario_invalido({"tipo": "cron", "hora": "3", "minuto": 0, "dia_semana": "mon"})
    assert pauta_semana.horario_invalido({"tipo": "intervalo", "minutos": 60})
    assert pauta_semana.horario_invalido({"tipo": "data", "quando": "2026-11-02T05:30:00-03:00"})
    assert pauta_semana.horario_invalido({"tipo": "cron", "hora": "8", "minuto": 0, "dia_semana": "mon"}) is None
    assert pauta_semana.e_pedido("Pauta da semana") and not pauta_semana.e_pedido("Planeje a semana do Réveillon")


def test_rotina_entrega_a_pauta_no_chat_do_gestor(monkeypatch):
    import agendamentos
    import orquestrador

    entregues = []

    async def entregar(linha):
        entregues.append(linha)

    monkeypatch.setattr(orquestrador, "entregar", entregar)
    monkeypatch.setattr(pauta_semana, "montar", lambda empresa: f"PAUTA DA SEMANA de teste ({empresa})")
    monkeypatch.setattr(orquestrador, "nova_tarefa", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sem IA")))
    agente = type("A", (), {"id": "gestor"})()
    linha = {"usuario": "usuario.teste@exemplo.com", "andar": "marketing", "tarefa": "Pauta da semana",
             "empresa": "casa_vero"}
    asyncio.run(agendamentos._encaminhar(linha, agente))
    assert len(entregues) == 1 and entregues[0]["status"] == "concluida"
    assert entregues[0]["resposta"] == "PAUTA DA SEMANA de teste (casa_vero)" and entregues[0]["agente"] == "gestor"
    assert tarefas.obter(entregues[0]["id"])["modelo"] == "sistema (sem IA)"
