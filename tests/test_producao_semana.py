"""Produzir a semana (gestor-12, fase 2; decisões 4, 5 e 7 de 04/11/2026): comando, escolha dos itens (7 dias e
itens de fora), fila sem aprovação e espera (sem falhar) com o PC desligado. Monday SIMULADO, banco temporário."""

import asyncio
from datetime import date, datetime

import pytest

import max_texto
import monday
import orquestrador
import pauta_semana
import producao_semana
import tarefas
from agendamentos import FUSO
from estado import Status, buscar_agente

tarefas.iniciar()
HOJE = date(2026, 11, 4)  # janela: 04/11 a 10/11
NOITE = datetime(2026, 11, 4, 22, 0, tzinfo=FUSO)
DIA = datetime(2026, 11, 4, 14, 0, tzinfo=FUSO)


def _item(n: int, nome: str, postagem: str = "", conta: str = "Casa Veraneio", status: str = "Aguardando",
          entrega: str = "") -> dict:
    return {"id": str(n), "name": nome, "column_values": [
        {"id": "data", "text": postagem}, {"id": monday.COL_STATUS, "text": status},
        {"id": monday.COL_CONTA, "text": conta}, {"id": pauta_semana.COL_ENTREGA, "text": entrega},
        {"id": monday.COL_LEGENDA, "text": ""}]}


QUADRO = {
    "Novembro": [
        _item(9101, "REELS | Lodge 239 à beira-mar", "2026-11-06"),
        _item(9102, "CARROSSEL | Casas do Réveillon", "2026-11-20", entrega="2026-11-09"),  # entrega na janela
        _item(9103, "STORIES | Bastidores", "2026-11-12"),  # fora da janela
        _item(9104, "REELS | Já pronto", "2026-11-05", status="Revisão"),  # encerrado: nem aparece
        _item(9105, "Peça sem padrão", "2026-11-05"),  # sem TIPO
        _item(9106, "POST | Sem roteiro", "2026-11-07"),  # sem descrição
        _item(9107, "POST | Item sem conta", "2026-11-07", conta=""),
        _item(9108, "REELS | Evento corporativo", "2026-11-05", conta="CV Corp"),  # outra empresa
        _item(9109, "REELS | Em produção", "2026-11-05", status="Em produção"),
    ],
    "Definir Data": [_item(9110, "POST | Sem data mas com entrega", entrega="2026-11-10")],
}
ROTEIROS = {"9101": "1. Lodge 239 na praia", "9102": "Página 1...", "9110": "Arte única", "9108": "Case"}


def _ler(item):
    return ROTEIROS.get(item["id"], "")


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    def proibido(*_a, **_k):
        raise AssertionError("nada de chamada real ao Monday")

    monkeypatch.setattr(monday, "_api", proibido)
    with producao_semana._db() as db:
        db.execute("DELETE FROM producao_semana")
    monday._db()
    yield


def test_reconhece_o_comando_e_a_empresa():
    assert producao_semana.e_pedido("gestor", "Produzir a semana")
    assert producao_semana.e_pedido("gestor", "produzir a semana do Corp")
    assert not producao_semana.e_pedido("copywriter", "Produzir a semana")
    assert not producao_semana.e_pedido("gestor", "Planeje a semana do Réveillon")
    assert not producao_semana.e_pedido("gestor", "Produzir a semana " + "com um briefing enorme " * 10)
    e = producao_semana.empresa_do_pedido
    assert e("Produzir a semana da Casa Veraneio Corporativo", "casa_veraneio") == "cv_corporativo"
    assert e("Produzir a semana do Corp", "casa_vero") == "cv_corporativo"
    assert e("Produzir a semana da Vero", "casa_veraneio") == "casa_vero"
    assert e("Produzir a semana da Casa Vero Imóveis", None) == "casa_vero"
    assert e("Produzir a semana da Casa Veraneio", "casa_vero") == "casa_veraneio"
    assert e("Produzir a semana", "casa_vero") == "casa_vero"
    assert e("Produzir a semana", "") is None


def test_escolhe_os_itens_dos_proximos_7_dias_e_explica_os_de_fora():
    escolha = producao_semana.selecionar(QUADRO, "casa_veraneio", HOJE, _ler)
    assert [i["id"] for _, i in escolha["escolhidos"]] == ["9101", "9102", "9110"]  # ordem da data na janela
    pulados = dict(escolha["pulados"])
    assert "sem TIPO" in pulados["Peça sem padrão"]
    assert "roteiro" in pulados["POST | Sem roteiro"]
    assert "sem Conta" in pulados["POST | Item sem conta"]
    nomes = {n for n, _ in escolha["pulados"]} | {i["name"] for _, i in escolha["escolhidos"]}
    assert not nomes & {"STORIES | Bastidores", "REELS | Já pronto", "REELS | Evento corporativo", "REELS | Em produção"}
    corp = producao_semana.selecionar(QUADRO, "cv_corporativo", HOJE, _ler)
    assert [i["id"] for _, i in corp["escolhidos"]] == ["9108"]


def test_um_clique_enfileira_sem_aprovacao_e_responde_no_gestor(monkeypatch):
    entregues = []

    async def entregar(linha):
        entregues.append(linha)

    monkeypatch.setattr(orquestrador, "entregar", entregar)
    monkeypatch.setattr(orquestrador, "nova_tarefa", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sem IA")))
    monkeypatch.setattr(monday, "ativo", lambda: True)
    monkeypatch.setattr(pauta_semana, "ler_quadro", lambda inicio, fim: QUADRO)
    monkeypatch.setattr(producao_semana, "_descricao", _ler)
    monkeypatch.setattr(producao_semana, "_hoje", lambda: HOJE)
    agente = buscar_agente("marketing", "gestor")
    asyncio.run(producao_semana.iniciar("semana.teste@exemplo.com", "marketing", agente,
                                        "Produzir a semana da Casa Veraneio", "casa_vero"))
    assert len(entregues) == 1 and entregues[0]["status"] == "concluida" and entregues[0]["agente"] == "gestor"
    texto = entregues[0]["resposta"]
    assert "Na fila de produção (3)" in texto and "Ficaram de fora (3)" in texto and "20:00" in texto
    assert [p["item_id"] for p in producao_semana.pendentes()] == [9101, 9102, 9110]
    # O mesmo comando de novo não duplica: os itens já estão na fila.
    asyncio.run(producao_semana.iniciar("semana.teste@exemplo.com", "marketing", agente,
                                        "Produzir a semana da Casa Veraneio", "casa_vero"))
    assert len(producao_semana.pendentes()) == 3 and "já está na fila" in entregues[-1]["resposta"]


def _fila_com_um_item(monkeypatch):
    producao_semana.enfileirar(1, "casa_veraneio", [(HOJE, _item(9201, "REELS | Lodge 31"))])
    enviados = []

    async def enviar(item_id, usuario=None):
        enviados.append((item_id, usuario))

    monkeypatch.setattr(monday, "_enviar_ao_gestor", enviar)
    monkeypatch.setattr(monday, "autorizados", lambda: {555})
    gestor = buscar_agente("marketing", "gestor")
    monkeypatch.setattr(gestor, "status", Status.disponivel)
    return enviados


def test_pc_desligado_o_item_espera_sem_falhar(monkeypatch):
    enviados = _fila_com_um_item(monkeypatch)
    monkeypatch.setattr(max_texto, "online", lambda: False)
    for _ in range(3):
        assert asyncio.run(producao_semana.despachar_um(NOITE)) is None
    assert enviados == [] and [p["status"] for p in producao_semana.pendentes()] == ["na_fila"]
    monkeypatch.setattr(max_texto, "online", lambda: True)  # o PC ligou: segue pelo pipeline do Enviar
    monkeypatch.setattr(max_texto, "_ocupado", lambda: True)
    assert asyncio.run(producao_semana.despachar_um(NOITE)) == 9201
    assert enviados == [(9201, 555)] and producao_semana.pendentes() == []


def test_de_dia_so_sai_com_o_max_parado_e_o_gestor_livre(monkeypatch):
    enviados = _fila_com_um_item(monkeypatch)
    monkeypatch.setattr(max_texto, "online", lambda: True)
    monkeypatch.setattr(max_texto, "_ocupado", lambda: True)
    assert asyncio.run(producao_semana.despachar_um(DIA)) is None  # de dia, com o Max ocupado: espera a noite
    monkeypatch.setattr(max_texto, "_ocupado", lambda: False)
    monkeypatch.setattr(buscar_agente("marketing", "gestor"), "status", Status.trabalhando)
    assert asyncio.run(producao_semana.despachar_um(DIA)) is None  # Gestor ocupado: espera a vez
    monkeypatch.setattr(buscar_agente("marketing", "gestor"), "status", Status.disponivel)
    assert asyncio.run(producao_semana.despachar_um(DIA)) == 9201 and enviados == [(9201, 555)]


def test_janela_da_noite():
    assert producao_semana.de_noite(NOITE) and producao_semana.de_noite(datetime(2026, 11, 5, 6, 59, tzinfo=FUSO))
    assert not producao_semana.de_noite(DIA) and not producao_semana.de_noite(datetime(2026, 11, 5, 7, 0, tzinfo=FUSO))


def test_pauta_traz_os_botoes_de_produzir():
    texto = pauta_semana.montar("*", HOJE, QUADRO)
    assert texto.startswith("PAUTA DA SEMANA") and "Produzir a semana" in texto
    for nome in ("Casa Veraneio", "Casa Veraneio Corporativo", "Casa Vero Imóveis"):  # js/chat.js opcoesDaPauta
        assert f"**{nome}** —" in texto
