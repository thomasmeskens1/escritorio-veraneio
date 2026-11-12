"""Resumo do dia da Vera (12/11/2026): só contas no banco, por usuário; avisos de operação só para a Diretoria."""

import aprovacoes
import correcoes
import saude
import tarefas
import vera


def _tarefa(login, status, entregue=1):
    tid = tarefas.criar(login, "marketing", "gestor", "Post do Lodge 3", "media", "casa_veraneio")
    tarefas.atualizar(tid, status=status, entregue=entregue)
    return tid


def test_resumo_conta_os_pedidos_de_quem_fala(monkeypatch):
    monkeypatch.setattr(aprovacoes, "itens", lambda login: [{"id": 1}, {"id": 2}])
    login = "vera_teste@exemplo.com"
    _tarefa(login, "executando")
    _tarefa(login, "concluida", entregue=0)
    _tarefa(login, "falhou")
    _tarefa("outra_vera@exemplo.com", "executando")
    texto = vera.resumo(login, "Ana", diretoria=False)
    assert texto.startswith("Olá, Ana.")
    assert "1 pedido seu está em andamento" in texto and "1 resposta nova espera" in texto
    assert "1 pedido falhou" in texto and "2 itens esperam a sua aprovação" in texto
    assert "operação" not in texto and texto.endswith("Do que você precisa?")


def test_diretoria_ouve_os_avisos_de_operacao(monkeypatch):
    monkeypatch.setattr(aprovacoes, "itens", lambda login: [])
    monkeypatch.setattr(correcoes, "pendentes", lambda: 3)
    monkeypatch.setattr(saude, "avisos_da_operacao", lambda: ["Ollama fora do ar."])
    texto = vera.resumo("sem_pedidos@exemplo.com", "", diretoria=True)
    assert "Você não tem pedidos em andamento agora." in texto
    assert "3 observações esperam aprovação" in texto and "Ollama fora do ar." in texto
    monkeypatch.setattr(saude, "avisos_da_operacao", lambda: [])
    assert "A operação está em ordem." in vera.resumo("sem_pedidos@exemplo.com", "", diretoria=True)
