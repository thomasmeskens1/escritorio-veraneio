"""'Lance no Monday' pedido ao Gestor (Thomas, 03/11/2026): o último planejamento dele vai ao Social Media, que registra
os itens sem mudar o plano. Banco temporário (tests/conftest.py)."""

import encaminhamento
import tarefas

tarefas.iniciar()


def test_reconhece_o_pedido_so_no_gestor():
    for texto in ("Lance no Monday o planejamento", "pode subir isso pro Monday?", "Cadastre tudo no Monday",
                  "coloca no monday por favor"):
        assert encaminhamento.lancar_no_monday("marketing", "gestor", texto), texto
    assert not encaminhamento.lancar_no_monday("marketing", "gestor", "Planejamento de dezembro com 3 Reels")
    assert not encaminhamento.lancar_no_monday("marketing", "copywriter", "Lance no Monday")


def test_pega_o_ultimo_planejamento_concluido_do_gestor():
    login = "teste.lanca@exemplo.com"
    assert encaminhamento.ultimo_planejamento(login) is None
    antigo = tarefas.criar(login, "marketing", "gestor", "Planejamento de novembro", "media")
    tarefas.atualizar(antigo, status="concluida", resposta="Plano antigo " * 30)
    novo = tarefas.criar(login, "marketing", "gestor", "Planejamento de dezembro", "media")
    tarefas.atualizar(novo, status="concluida", resposta="Semana 1: 3 Reels do Lodge 239 " * 20)
    tarefa_id, plano = encaminhamento.ultimo_planejamento(login)
    assert tarefa_id == novo and plano.startswith("Semana 1")
    pedido = encaminhamento.pedido_ao_social_media("Lance no Monday", tarefa_id, plano)
    assert "criar_itens_monday" in pedido and f"#{novo}" in pedido and "Não refaça" in pedido
