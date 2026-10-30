"""Insatisfações, Log aglomerado e o caso do carrossel do Lodge 35 (30/10/2026). Banco temporário (tests/conftest.py).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_insatisfacoes_registro.py
"""

import api_painel
import insatisfacoes
import tarefas
from agents import perfis

tarefas.iniciar()


def _troca(texto: str, resposta: str = "") -> dict:
    return {"texto": texto, "resposta": resposta}


def test_pedido_sem_lodge_continua_os_lodges_da_conversa_recente():
    # Caso real (#232): "agora monte o carrossel" depois de pedir 6 Lodges virou carrossel do Lodge 35 (pedido antigo).
    historico = [_troca("Legenda nesse estilo para o Lodge 35", "Legenda do Lodge 35..."),
                 _troca("PERSONA | CASA VERANEIO ...", "Persona consolidada"),
                 _troca("Carrossel com as casas: Lodge 02, Lodge 119, Lodge 18", "Carrossel com os 3 Lodges")]
    relevante = perfis._historico_relevante(historico, "Peça final: agora monte o carrossel e venda essa casa")
    textos = [h["texto"] for h in relevante]
    assert not any("Lodge 35" in t for t in textos)
    assert any("Lodge 119" in t for t in textos) and any("PERSONA" in t for t in textos)


def test_sem_lodge_em_lugar_nenhum_mantem_tudo():
    historico = [_troca("Ideia de post"), _troca("Outra ideia")]
    assert perfis._historico_relevante(historico, "e agora?") == historico


def test_reacao_negativa():
    for texto in ("Não era isso que eu pedi", "ficou ruim", "pedi 6 casas e veio só uma", "Está errado"):
        assert insatisfacoes.e_negativa(texto), texto
    for texto in ("Gostei, pode seguir", "Agora monte o carrossel", "Ótimo"):
        assert not insatisfacoes.e_negativa(texto), texto


def test_registrar_e_analisar():
    tarefa_id = tarefas.criar("ana-insat", "marketing", "gestor", "Carrossel com 6 Lodges", "media")
    tarefas.atualizar(tarefa_id, status="concluida", resposta="Carrossel do Lodge 35")
    linha = tarefas.obter(tarefa_id)
    antes = insatisfacoes.novas()
    novo = insatisfacoes.registrar(linha, "ana-insat", "voto", "pedido", "Pedi 6 Lodges e veio 1")
    assert insatisfacoes.novas() == antes + 1
    gravado = insatisfacoes._db().execute("SELECT * FROM insatisfacoes WHERE id = ?", (novo,)).fetchone()
    assert gravado["pedido"] == "Carrossel com 6 Lodges" and gravado["resposta"] == "Carrossel do Lodge 35"
    assert insatisfacoes.registrar(linha, "ana-insat", "voto", "inexistente") and \
        insatisfacoes._db().execute("SELECT categoria FROM insatisfacoes ORDER BY id DESC").fetchone()[0] == "outro"


def _linha(id_, texto, criada, concluida=None, agente="gestor", usuario="ana"):
    return {"id": id_, "texto": texto, "usuario": usuario, "andar": "marketing", "agente": agente,
            "criada_em": criada, "concluida_em": concluida}


def test_log_aglomera_conversa_e_producao():
    linhas = [
        _linha(230, "Planejamento: post do feriado", "2026-10-30T18:01:24Z", "2026-10-30T18:05:00Z"),
        _linha(231, "Planejamento: com estas casas", "2026-10-30T18:10:05Z", "2026-10-30T18:14:00Z"),
        _linha(232, "Peça final: monte o carrossel", "2026-10-30T18:15:31Z", "2026-10-30T18:18:16Z"),
        _linha(233, "Produza a peça final do projeto #232, coordenado pelo Gestor.", "2026-10-30T18:19:01Z",
               agente="criador_imagens"),
        _linha(240, "Outro assunto, bem depois", "2026-10-30T22:00:00Z"),
        _linha(241, "Pedido de outra pessoa", "2026-10-30T18:16:00Z", usuario="bia"),
    ]
    grupos = api_painel._agrupar(linhas)
    assert grupos[230] == grupos[231] == grupos[232] == grupos[233] == 230
    assert grupos[240] == 240 and grupos[241] == 241
