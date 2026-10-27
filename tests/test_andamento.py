"""Painel de andamento sem linhas repetidas, para qualquer agente (auditoria de 27/10/2026).

Rodar no container: docker exec -w /app -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest /tests
(ou: python tests/test_andamento.py com backend/ no PYTHONPATH).
"""

import andamento
import producao


def _ev(tipo, modelo=None, detalhe=None):
    return {"tipo": tipo, "modelo": modelo, "detalhe": detalhe, "em": "2026-10-27T18:00:00Z"}


def _etapas(status, eventos, progresso=()):
    producao.progresso_de = lambda _t: list(progresso)
    return andamento._etapas_por_eventos({"id": 0, "status": status, "agente": "qualquer"}, eventos)


def _textos(etapas):
    return [e["texto"] for e in etapas if e["status"] != "pendente"]


def test_modelo_tentado_de_novo_vira_uma_linha():
    etapas = _etapas("executando", [_ev("tentativa", "groq/llama"), _ev("tentativa", "openrouter/x:free"),
                                    _ev("tentativa", "groq/llama")])
    assert _textos(etapas) == ["Pedido recebido", "Trabalhando com x", "Trabalhando com llama (2 vezes)"]
    assert etapas[2]["status"] == "andamento"


def test_mesma_consulta_ao_cerebro_vira_uma_linha():
    etapas = _etapas("executando", [_ev("consulta_cerebro", detalhe="Lodge 30")] * 2)
    assert _textos(etapas) == ["Pedido recebido", "Consultou o Cérebro: Lodge 30 (2 vezes)"]


def test_producao_sem_fase_conta_passadas():
    linhas = ["1/1 | Ajuste"] + ["- 1/2 | Slide 1", "- 8/2 | Slide 8"] * 3  # caso real da #68
    textos = _textos(_etapas("produzindo", [_ev("tentativa", "claude-code/max")], linhas))
    assert textos == ["Pedido recebido", "Ajuste", "Slide 1 · 3ª passada", "Slide 8 · 3ª passada"]


def test_producao_com_fases_mantem_partes_por_fase():
    linhas = ["1/1 | Carrossel", "> Montagem", "- 1/3 | Slide 1", "- 2/3 | Slide 2", "> Vídeos", "- 1/3 | Slide 1"]
    etapas = _etapas("produzindo", [_ev("tentativa", "claude-code/max")], linhas)
    assert [e["texto"] for e in etapas if e["status"] == "pendente"] == ["2 de 3", "3 de 3",
                                                                          "Entregar a resposta no chat"]
    assert [e["texto"] for e in etapas if e["status"] == "andamento"] == ["Carrossel", "Vídeos", "Slide 1"]


if __name__ == "__main__":
    for nome, teste in list(globals().items()):
        if nome.startswith("test_"):
            teste()
            print("ok", nome)
