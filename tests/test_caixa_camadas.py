"""Caixa de entrada, Cérebro pré-consultado (ideia do Code Mode) e resumos em camadas (ideia do OpenViking),
30/10/2026. Banco temporário (tests/conftest.py).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_caixa_camadas.py
"""

import caixa
import cerebro
import tarefas
from agents import executor

tarefas.iniciar()


def _trecho(n: int, conteudo: str) -> dict:
    return {"titulo": f"Documento {n}", "fonte_tipo": "oficial", "fonte_ref": f"doc{n}.md", "data": "2026-10-30",
            "conteudo": conteudo}


def test_camadas_cabem_mais_fontes_no_mesmo_espaco():
    trechos = [_trecho(n, f"Primeira frase do documento {n}. " + "detalhe " * 200) for n in range(1, 10)]
    texto = cerebro._formatar_em_camadas(trechos, 3000)
    assert len(texto) <= 3000
    assert "Mapa de outras fontes" in texto
    assert texto.count("[") >= 7                                     # 3 completas + pelo menos 4 no mapa
    assert "Primeira frase do documento 4." in texto                 # a camada resumo é a primeira frase
    mapa = texto.split("Mapa de outras fontes")[1]
    assert all(l.endswith((".", "…")) for l in mapa.strip().splitlines()[1:])  # só linhas inteiras


def test_poucas_fontes_ficam_como_antes():
    trechos = [_trecho(1, "Só um documento.")]
    assert cerebro._formatar_em_camadas(trechos, 3000) == cerebro._formatar(trechos, 3000)


def test_cerebro_pre_consultado_uma_vez_por_tarefa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cerebro, "consultar", lambda pergunta, agente, tarefa_id: chamadas.append(pergunta) or "SABER")
    tarefa_id = tarefas.criar("ana", "marketing", "copywriter", "Legenda do Lodge 28", "simples")
    d1 = executor._com_cerebro_pre_consultado("copywriter", "Descrição do pedido", tarefa_id)
    d2 = executor._com_cerebro_pre_consultado("copywriter", "Descrição do pedido", tarefa_id)  # outra tentativa
    assert "CONHECIMENTO DO CÉREBRO JÁ CONSULTADO" in d1 and "SABER" in d1 and d1 == d2
    assert chamadas == ["Legenda do Lodge 28"]  # a segunda tentativa reaproveita a busca
    etapa = executor._com_cerebro_pre_consultado("designer", "...\n\nSua etapa (2): Definir a paleta do post\n\nSeja "
                                                 "objetivo", tarefa_id)
    assert chamadas[-1] == "Definir a paleta do post" and "SABER" in etapa  # etapa do Gestor: busca pela etapa


def test_caixa_concluidos_e_lidos():
    ana = "ana-caixa"
    feita = tarefas.criar(ana, "marketing", "copywriter", "Legenda do Lodge 1", "simples")
    tarefas.atualizar(feita, status="concluida", resposta="Pronto.", concluida_em=tarefas._agora())
    falhou = tarefas.criar(ana, "marketing", "copywriter", "Outra legenda", "simples")
    tarefas.atualizar(falhou, status="falhou", motivo="erro", concluida_em=tarefas._agora())
    dados = caixa.caixa(ana)
    assert {c["tarefa_id"] for c in dados["concluidos"]} == {feita, falhou}
    assert dados["concluidos"][0]["agente_nome"]
    caixa.marcar_lidos(ana, [feita])
    assert {c["tarefa_id"] for c in caixa.caixa(ana)["concluidos"]} == {falhou}
    assert caixa.caixa("outra-pessoa")["concluidos"] == []  # cada um vê só a própria caixa
