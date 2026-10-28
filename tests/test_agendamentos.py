"""Quando um texto vira rotina agendada (e quando é só uma tarefa para já).

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_agendamentos.py
"""

import agendamentos

BRIEFING = (
    "Crie um PowerPoint editável como briefing de marketing de influência para uma influenciadora. CONTEXTO DA "
    "PARCERIA: hospedagem no Lodge 149. Entregas: 3 stories por dia durante 3 dias e 1 carrossel. Serviços "
    "previstos: chef de cozinha, arrumadeira todos os dias e churrasqueiro no sábado. TOM: escreva direto para "
    "ela, com linguagem próxima e elegante. ESTRUTURA: 6 slides, capa, proposta, ideias para os stories, "
    "diferenciais, sugestão de carrossel e combinados da entrega.")


def test_briefing_longo_nao_vira_rotina():
    # Teste real (28/10/2026): "arrumadeira todos os dias" no briefing virou rotina diária às 9h.
    assert len(BRIEFING) > agendamentos.LIMITE_SEM_PEDIDO
    assert not agendamentos.e_agendamento(BRIEFING)


def test_texto_longo_com_pedido_explicito_vira_rotina():
    assert agendamentos.e_agendamento(f"Agende esta rotina: {BRIEFING} Rode todos os dias às 08:00.")


def test_pedidos_curtos_de_rotina_continuam():
    for texto in ("Analise as campanhas todos os dias às 08:00",
                  "Toda segunda às 9h, monte o resumo da semana",
                  "A cada 2 horas confira os comentários"):
        assert agendamentos.e_agendamento(texto), texto


def test_tarefa_para_ja_nao_vira_rotina():
    assert not agendamentos.e_agendamento("Escreva 3 legendas para o post do Lodge 20")
