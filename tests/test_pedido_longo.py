"""Pedido longo ao Gestor (até 30 mil caracteres): ficha de requisitos, âncora nas etapas e checagem final.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_pedido_longo.py
"""

import shutil
import threading

from agents import projeto

FICHA = ("OBJETIVO: Briefing em PowerPoint para a influenciadora no Lodge 149\n"
         "ENTREGÁVEIS: 1 PowerPoint editável com 6 slides\n"
         "REQUISITOS:\nR1. Capa com o título \"Briefing de Conteúdo\"\nR2. Slide com as ideias dos 9 stories\n"
         "DADOS FORNECIDOS: Lodge 149, Santana de Parnaíba\nTOM E RESTRIÇÕES: próximo e elegante\nA CONFIRMAR: datas")
PLANO = '{"titulo": "Briefing Lodge 149", "etapas": [{"agente": "copywriter", "instrucao": "R1 e R2", "fase": 1}]}'


def _executar_falso(chamadas: list):
    def executar(agente, descricao, esperado, papel):
        chamadas.append((agente, descricao))
        if "FICHA DE REQUISITOS fiel" in descricao:
            return FICHA
        if "Responda SOMENTE com um JSON" in descricao:
            return PLANO
        if "Entrega final" in esperado:
            return "Aqui está o briefing.\n<<CHECAGEM>>\nR1: ok\nR2: faltou - sem fotos reais do Lodge 149\n<<FIM>>"
        return "Textos da capa e dos stories."
    return executar


def _rodar(pedido: str):
    tarefa_id = 999901
    pasta = projeto.PASTA_PROJETOS / str(tarefa_id)
    shutil.rmtree(pasta, ignore_errors=True)
    chamadas = []
    try:
        final = projeto.executar_projeto(tarefa_id, pedido, "CONTEXTO", _executar_falso(chamadas), threading.Event())
        return final, chamadas, (pasta / "requisitos.md").exists(), projeto.entregaveis_do_projeto(tarefa_id)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def test_pedido_longo_vira_ficha_e_a_etapa_nao_recebe_o_texto_gigante():
    pedido = "Crie um PowerPoint de briefing. " + "Detalhe do briefing. " * 1500  # ~30 mil caracteres
    final, chamadas, tem_ficha, entregaveis = _rodar(pedido)
    assert tem_ficha and entregaveis == "1 PowerPoint editável com 6 slides"
    etapa = next(d for a, d in chamadas if a == "copywriter")
    assert pedido not in etapa and "R1. Capa" in etapa          # a etapa recebe a ficha, não o pedido inteiro
    assert etapa.rstrip().endswith("nem o formato.")             # âncora do objetivo no fim
    assert "<<CHECAGEM>>" not in final                           # o bloco de checagem não vai ao usuário
    assert "R2: faltou - sem fotos reais do Lodge 149" in final  # o que faltou aparece


def test_pedido_curto_continua_como_antes():
    final, chamadas, tem_ficha, _ = _rodar("Crie um carrossel de 3 slides do Lodge 1 sobre o Carnaval.")
    assert not tem_ficha
    assert not any("FICHA DE REQUISITOS fiel" in d for _, d in chamadas)
    etapa = next(d for a, d in chamadas if a == "copywriter")
    assert "Projeto: Crie um carrossel" in etapa
