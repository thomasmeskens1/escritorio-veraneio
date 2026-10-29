"""Rotinas agendadas: só pelo botão "Agendar tarefa" (formulário estruturado), nunca pelo texto do chat.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_agendamentos.py
"""

from datetime import datetime
from pathlib import Path

import agendamentos
from agendamentos import FUSO, Pedido, regra_do_formulario

AGORA = datetime(2026, 10, 29, 10, 0, tzinfo=FUSO)


def _pedido(**campos) -> Pedido:
    return Pedido(andar="marketing", agente="social_media", tarefa="Monte o resumo da semana", **campos)


def test_chat_nunca_agenda():
    # Testes reais (28 e 29/10/2026): briefings com "todos os dias" no conteúdo viraram rotina.
    assert not hasattr(agendamentos, "e_agendamento") and not hasattr(agendamentos, "interpretar")
    main = (Path(agendamentos.__file__).parent / "main.py").read_text(encoding="utf-8")
    assert "agendamentos.criar" not in main


def test_frequencias_do_formulario():
    regra, desc = regra_do_formulario(_pedido(frequencia="Todos os dias", horario="08:30"), AGORA)
    assert regra == {"tipo": "cron", "hora": "8", "minuto": 30} and desc == "Todos os dias às 08:30"
    regra, desc = regra_do_formulario(_pedido(frequencia="Toda semana", horario="09:00", dia_semana="Segunda"), AGORA)
    assert regra["dia_semana"] == "mon" and desc == "Toda segunda às 09:00"
    regra, desc = regra_do_formulario(_pedido(frequencia="Todo mês", horario="07:00", dia_mes=5), AGORA)
    assert regra["dia"] == 5 and desc == "Todo dia 5 do mês às 07:00"
    regra, desc = regra_do_formulario(_pedido(frequencia="A cada X horas", intervalo_horas=2), AGORA)
    assert regra == {"tipo": "intervalo", "minutos": 120} and desc == "A cada 2 horas"
    regra, desc = regra_do_formulario(_pedido(frequencia="Uma vez", horario="14:00", data="2026-10-30"), AGORA)
    assert regra["tipo"] == "data" and desc == "Em 30/10/2026 às 14:00"
    assert agendamentos.proxima_execucao(regra, AGORA).day == 30


def test_formulario_incompleto_explica_o_que_falta():
    casos = [(_pedido(frequencia="Todos os dias"), "horário"),
             (_pedido(frequencia="Uma vez", horario="08:00", data="2026-10-01"), "já passaram"),
             (_pedido(frequencia="Toda semana", horario="08:00"), "dia da semana"),
             (_pedido(frequencia="A cada X horas"), "quantas em quantas"),
             (_pedido(frequencia="Sempre", horario="08:00"), "frequência")]
    for pedido, trecho in casos:
        try:
            regra_do_formulario(pedido, AGORA)
        except ValueError as erro:
            assert trecho in str(erro), (pedido.frequencia, str(erro))
        else:
            raise AssertionError(f"{pedido.frequencia} deveria pedir {trecho}")
