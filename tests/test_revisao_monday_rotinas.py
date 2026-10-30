"""Conta do Monday pela empresa da tarefa, rotinas revalidadas e backup sem segredos (revisão de 30/10/2026, itens
2.17, 2.21 e 2.32). Banco temporário (tests/conftest.py); nada vai ao Monday de verdade.
"""

import asyncio

import agendamentos
import tarefas
from agents import ferramentas_monday

tarefas.iniciar()


def test_conta_do_item_e_a_empresa_da_tarefa(monkeypatch):
    import monday

    criados = []
    import monday_datas

    monkeypatch.setattr(monday, "grupo_por_nome", lambda *_a, **_k: {"id": "g", "title": "Novembro"})
    monkeypatch.setattr(monday, "criar_item",
                        lambda grupo, nome, valores: criados.append(valores) or {"id": 1, "name": nome, "url": "https://x"})
    monkeypatch.setattr(monday_datas, "reposicionar_seguro", lambda *_a, **_k: None)
    monkeypatch.setattr(ferramentas_monday, "_descrever_roteiro", lambda *_a, **_k: None)
    tarefa = tarefas.criar("ana", "marketing", "social_media", "Planeje", "simples", empresa="casa_vero")
    ferramentas_monday._criar(ferramentas_monday._Contador(), tarefa, "POST | Casa à venda em Itu",
                              conta="Casa Veraneio")  # o modelo escreveu a conta errada
    assert criados and criados[0][monday.COL_CONTA] == {"label": "Casa Vero"}


def test_rotina_de_usuario_desativado_para(monkeypatch):
    import auth

    rotina = agendamentos.criar("saiu@casaveraneio.com", "marketing", "copywriter", "Legenda semanal",
                                {"tipo": "intervalo", "minutos": 60}, "A cada hora", "casa_veraneio")["id"]
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: {"saiu@casaveraneio.com": {"ativo": False}})
    asyncio.run(agendamentos._executar(rotina))
    assert not agendamentos._obter(rotina)["ativo"]


def test_backup_nao_leva_tokens_nem_senhas():
    from pathlib import Path

    texto = Path("/repo/scripts/backup_dados.py").read_text(encoding="utf-8") if Path("/repo/scripts/backup_dados.py").exists() else ""
    if not texto:
        import pytest
        pytest.skip("scripts não montado")
    assert '"usuarios.json"' in texto and '"token"' in texto


def test_senha_trocada_ou_sair_derruba_o_token_antigo(monkeypatch):
    import auth

    usuarios = {"ana@x.com": {"nome": "Ana", "role": "funcionario", "senha": auth.gerar_hash("velha123")}}
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: usuarios)
    monkeypatch.setattr(auth, "_gravar", lambda novos: usuarios.update(novos))
    token = auth.criar_token({"login": "ana@x.com", "nome": "Ana", "role": "funcionario"})
    assert auth.validar_token(token)
    auth.atualizar_usuario("ana@x.com", senha="nova12345")
    assert auth.validar_token(token) is None  # senha nova: o token antigo cai
    novo = auth.criar_token({"login": "ana@x.com", "nome": "Ana", "role": "funcionario"})
    assert auth.validar_token(novo)
    auth.encerrar_sessoes("ana@x.com")  # "Sair"
    assert auth.validar_token(novo) is None
