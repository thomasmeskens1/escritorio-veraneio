"""Plano do Gestor (tarefa 287, 12/11/2026): o JSON com "opcoes": [] antes das etapas dava "JSON inválido" em todos
os modelos; plano sem etapas (só um direcionamento) responde em vez de cair na fila; o direcionamento vira
observação."""

import pytest

import correcoes
import saude
from agents import projeto

COM_OPCOES = ('{"entendimento": "Post do Lodge 3", "duvida": "", "opcoes": [], "pode_decidir": true, '
              '"titulo": "Post Lodge 3", "etapas": [{"agente": "copywriter", "instrucao": "Legenda [cliente]", '
              '"fase": 1}]}\nObservação: use o tom [leve].')
VAZIO = ('{"entendimento": "Só considerar as imagens como referência para as próximas peças", "duvida": "", '
         '"opcoes": [], "pode_decidir": true, "titulo": "Referências", "etapas": []}')


def test_plano_com_opcoes_vazias_antes_das_etapas():
    plano, titulo = projeto._extrair_plano(COM_OPCOES)
    assert [p["agente"] for p in plano] == ["copywriter"] and titulo == "Post Lodge 3"


def test_lista_solta_antiga_ainda_vale_e_json_quebrado_falha():
    plano, _ = projeto._extrair_plano('Plano: [{"agente": "copywriter", "instrucao": "x", "fase": 1}]')
    assert plano[0]["agente"] == "copywriter"
    with pytest.raises(saude.FalhaDoModelo):
        projeto._extrair_plano('{"etapas": [{"agente": "copywriter",]}')


def test_plano_vazio_so_com_entendimento():
    assert projeto.plano_vazio(VAZIO)
    assert not projeto.plano_vazio(COM_OPCOES)
    assert not projeto.plano_vazio(VAZIO.replace("Só considerar as imagens como referência para as próximas peças", ""))


def test_plano_vazio_responde_sem_acionar_a_equipe(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto.pergunta_gestor, "pedir_plano", lambda pasta, executar, descricao: VAZIO)
    assert projeto._plano(tmp_path, "Só considerem as imagens nos próximos pedidos", "", lambda *a: "") == []
    assert (tmp_path / "sem_etapas.txt").exists()


def test_direcionamento_para_as_proximas_vira_observacao():
    texto = ("As imagens que eu enviei para o copy eram só para ensinar. Não precisa produzir, apenas quero que "
             "considerem os direcionamentos para quando forem produzir outros pedidos futuros.")
    assert correcoes.DIRECIONAMENTO.search(texto)
    assert not correcoes.DIRECIONAMENTO.search("Faça o post do Lodge 3 para o próximo sábado.")
