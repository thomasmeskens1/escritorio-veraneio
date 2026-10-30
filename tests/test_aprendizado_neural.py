"""👍/👎, rede neural do Cérebro e consolidação semanal (Thomas, 29/10/2026), num banco temporário (conftest).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_aprendizado_neural.py
"""

import json
import random
import tempfile
from pathlib import Path

import avaliacoes  # banco temporário: tests/conftest.py
import cerebro_base as base
import consolidacao_semanal
import correcoes
import reranker
import tarefas

_PASTA = Path(tempfile.mkdtemp())

reranker.PASTA = _PASTA / "aprendizado"
reranker.ARQUIVO_MODELO = reranker.PASTA / "reranker.joblib"
reranker.ARQUIVO_META = reranker.PASTA / "reranker.json"
tarefas.iniciar()


def _trecho(titulo: str) -> int:
    with base.db() as db:
        return db.execute("INSERT INTO conhecimento (fonte_tipo, titulo, conteudo, peso_fonte, criado_em, "
                          "atualizado_em) VALUES ('oficial', ?, 'x', 1.0, ?, ?)",
                          (titulo, base.agora(), base.agora())).lastrowid


def _tarefa(agente: str = "copywriter") -> int:
    tarefa_id = tarefas.criar("francielle", "marketing", agente, "Legenda para o Lodge 28", "simples")
    tarefas.atualizar(tarefa_id, status="concluida", resposta="Legenda pronta.")
    return tarefa_id


def _pontuacao(i: int) -> float:
    return base.db().execute("SELECT pontuacao FROM conhecimento WHERE id = ?", (i,)).fetchone()[0]


def test_voto_ajusta_trechos_e_troca_desfaz():
    a, b = _trecho("A"), _trecho("B")
    tarefa_id = _tarefa()
    base.registrar_consulta(tarefa_id, "copywriter", "legenda", [a, b], [{"cosseno": 0.8}, {"cosseno": 0.4}])
    linha = tarefas.obter(tarefa_id)
    assert avaliacoes.avaliar(linha, "francielle", 1) == 2
    assert round(_pontuacao(a), 2) == base.PASSO_SUCESSO and avaliacoes.de(tarefa_id) == 1
    avaliacoes.avaliar(linha, "francielle", -1)  # troca: desfaz o 👍 e aplica o 👎
    assert round(_pontuacao(a), 2) == -base.PASSO_FALHA
    avaliacoes.avaliar(linha, "francielle", 0)  # retira o voto
    assert round(_pontuacao(b), 2) == 0 and avaliacoes.de(tarefa_id) == 0


def test_comentario_no_negativo_vira_correcao_para_a_diretoria():
    tarefa_id = _tarefa()
    avaliacoes.avaliar(tarefas.obter(tarefa_id), "francielle", -1, "Faltou o nome do Lodge")
    obs = correcoes._db().execute("SELECT tipo, correcao FROM observacoes WHERE tarefa_anterior = ?",
                                  (tarefa_id,)).fetchone()
    assert obs["tipo"] == "correcao" and "Lodge" in obs["correcao"]


def test_rede_espera_exemplos_e_depois_so_ativa_se_superar_a_ordem():
    assert reranker.prever([{"cosseno": 0.5}]) is None
    assert "Ainda aprendendo" in reranker.treinar()["observacao"]
    random.seed(1)
    for _ in range(80):  # trechos de cosseno alto ajudam; posição não diz nada (a rede tem de superar a ordem)
        tarefa_id = _tarefa()
        sinais = [{"cosseno": random.random(), "posicao": p, "fonte": "oficial"} for p in range(4)]
        util = max(sinais, key=lambda s: s["cosseno"])["cosseno"] > 0.7
        base.registrar_consulta(tarefa_id, "copywriter", "q", [_trecho("t") for _ in sinais], sinais)
        avaliacoes.avaliar(tarefas.obter(tarefa_id), "francielle", 1 if util else -1)
    status = reranker.treinar()
    assert status["exemplos"] >= reranker.MINIMO_EXEMPLOS and status["auc"] is not None
    assert json.loads(reranker.ARQUIVO_META.read_text(encoding="utf-8"))["exemplos"] == status["exemplos"]
    if status["ativo"]:
        assert len(reranker.prever([{"cosseno": 0.9}, {"cosseno": 0.1}])) == 2


def test_consolidacao_grava_aprendizados_para_aprovar(monkeypatch):
    import comercial

    _tarefa("copywriter")
    resposta = ('<<APRENDIZADOS>>[{"agente": "copywriter", "empresa": "Casa Veraneio", "aprendizado": '
                '"Sempre citar o número do Lodge na legenda.", "porque": "3 👎 sem o Lodge"}, '
                '{"agente": "inexistente", "empresa": "Todas", "aprendizado": "Regra geral.", "porque": "x"}]<<FIM>>')
    monkeypatch.setattr(comercial, "pedir_ao_max", lambda prompt: resposta)
    resultado = consolidacao_semanal.consolidar(forcar=True)
    assert resultado["ok"] and resultado["itens"] == 2
    linhas = correcoes._db().execute("SELECT agente, correcao FROM observacoes WHERE tipo = 'aprendizado' "
                                     "ORDER BY id").fetchall()
    assert [l["agente"] for l in linhas] == ["copywriter", "*"]  # agente inválido vira "todos"
    assert linhas[0]["correcao"].startswith("[Casa Veraneio]")
    assert not consolidacao_semanal.consolidar()["ok"]  # uma vez por semana
