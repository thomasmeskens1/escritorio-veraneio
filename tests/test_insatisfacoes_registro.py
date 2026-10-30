"""Insatisfações, Log aglomerado e o caso do carrossel do Lodge 35 (30/10/2026). Banco temporário (tests/conftest.py).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_insatisfacoes_registro.py
"""

import api_painel
import insatisfacoes
import tarefas
from agents import perfis

tarefas.iniciar()


def _troca(texto: str, resposta: str = "", criada_em: str = "") -> dict:
    return {"texto": texto, "resposta": resposta, "criada_em": criada_em}


def test_conversa_em_ordem_com_a_troca_mais_recente_marcada():
    # Caso real (#232): o agente precisa ver qual troca está em andamento, não só uma lista solta.
    historico = [_troca("Legenda nesse estilo para o Lodge 35", "Legenda...", "2026-10-29T17:36:08Z"),
                 _troca("Carrossel com as casas: Lodge 02, Lodge 119, Lodge 18", "Carrossel...", "2026-10-30T18:10:05Z")]
    texto = perfis._resumo_historico(historico)
    assert "Troca 1 (29/10 17:36)" in texto and "Troca 2 (30/10 18:10) (A MAIS RECENTE)" in texto
    assert texto.index("Lodge 35") < texto.index("Lodge 119")  # da mais antiga para a mais recente
    assert "continua a troca MAIS RECENTE" in texto


def _gestor_falso(resposta_plano: str, descricoes: list):
    def executar(agente, descricao, esperado, papel):
        descricoes.append((agente, descricao))
        if "JSON com o entendimento" in esperado:
            return resposta_plano
        return f"entrega de {agente}"
    return executar


def test_gestor_interpreta_antes_e_as_etapas_recebem_o_entendimento(tmp_path, monkeypatch):
    import threading

    from agents import projeto

    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    descricoes = []
    plano = ('{"entendimento": "Continua o carrossel de 20/11 com os Lodges 02, 119 e 18 (troca mais recente).", '
             '"duvida": "", "titulo": "Carrossel 20/11", "etapas": [{"agente": "copywriter", '
             '"instrucao": "Textos dos 3 Lodges", "fase": 1}]}')
    final = projeto.executar_projeto(1, "agora monte o carrossel", "CTX", _gestor_falso(plano, descricoes),
                                     threading.Event())
    assert "INTERPRETE" in descricoes[0][1].upper() or "interprete o pedido" in descricoes[0][1]
    etapa = next(d for a, d in descricoes if a == "copywriter")
    assert "ENTENDIMENTO DO GESTOR" in etapa and "Lodges 02, 119 e 18" in etapa
    assert "Lodges 02, 119 e 18" in descricoes[-1][1]  # a consolidação confere contra o entendimento
    assert final == "entrega de gestor"


def test_gestor_pergunta_quando_nao_da_para_saber(tmp_path, monkeypatch):
    import threading

    from agents import projeto

    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    descricoes = []
    plano = ('{"entendimento": "O pedido fala em essa casa, mas a conversa tem dois carrosséis.", '
             '"duvida": "O carrossel é o dos 6 Lodges do feriado ou o do Lodge 35?", "titulo": "", "etapas": []}')
    final = projeto.executar_projeto(2, "monte essa casa", "CTX", _gestor_falso(plano, descricoes), threading.Event())
    assert final.endswith("PERGUNTA: O carrossel é o dos 6 Lodges do feriado ou o do Lodge 35?")
    assert len(descricoes) == 1  # ninguém da equipe trabalhou num palpite


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
