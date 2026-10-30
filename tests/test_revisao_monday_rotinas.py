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


def test_reenvio_de_mensagem_ja_recebida_e_ignorado():
    import main

    assert not main._ja_recebida("ana", "envio-1")
    assert main._ja_recebida("ana", "envio-1")  # mesmo envio de novo: só confirma
    assert not main._ja_recebida("bia", "envio-1")  # outro usuário, outro envio


def test_fila_do_monday_sobrevive_ao_reinicio(monkeypatch):
    import monday

    chamados = []

    async def unico(item_id, usuario):
        chamados.append(item_id)

    monkeypatch.setattr(monday, "_enviar_ao_gestor_unico", unico)
    with monday._db() as db:
        db.execute("INSERT OR REPLACE INTO monday_fila (item_id, usuario, em) VALUES (777, 5, '2026-10-30T10:00:00Z')")

    async def subida():
        assert monday.retomar_fila() == 1
        await asyncio.sleep(0.05)

    asyncio.run(subida())
    assert chamados == [777]
    assert not monday._db().execute("SELECT 1 FROM monday_fila WHERE item_id = 777").fetchone()  # tratado: saiu


def test_atualizacao_do_monday_tenta_de_novo_so_em_falha_passageira(monkeypatch):
    import urllib.error

    import monday

    monkeypatch.setattr(monday, "ESPERAS_NOVA_TENTATIVA_S", (0, 0, 0))
    chamadas = []

    def instavel(item_id):
        chamadas.append(item_id)
        if len(chamadas) < 3:
            raise urllib.error.URLError("rede caiu")

    asyncio.run(monday._seguro(instavel, 1))
    assert len(chamadas) == 3  # duas falhas de rede e o sucesso
    chamadas.clear()

    def recusa(item_id):
        chamadas.append(item_id)
        raise RuntimeError("Monday: [coluna inválida]")

    asyncio.run(monday._seguro(recusa, 1))
    assert len(chamadas) == 1  # erro de validação não adianta repetir


def test_previa_de_outra_pessoa_nao_e_usada(tmp_path, monkeypatch):
    import json

    import comercial

    monkeypatch.setattr(comercial, "PASTA_PREVIAS", tmp_path)
    (tmp_path / "50.json").write_text(json.dumps({"usuario": "bia", "leads": [], "criados": []}), encoding="utf-8")
    assert comercial._qual_previa("Crie os leads da prévia #50", "ana") is None
    assert comercial._qual_previa("Crie os leads da prévia #50", "bia") == 50


def test_busca_de_item_ambigua_nao_escolhe_o_primeiro(monkeypatch):
    import monday

    itens = [{"name": "POST | Lodge 10 Réveillon"}, {"name": "POST | Lodge 10 Carnaval"}]
    monkeypatch.setattr(monday, "_api", lambda *_a, **_k: {"boards": [{"items_page": {"items": itens}}]})
    monkeypatch.setattr(monday, "_com_descricao", lambda item: item)
    assert monday.buscar_item("Lodge 10") is None  # dois parecidos: o agente pergunta qual
    assert monday.buscar_item("POST | Lodge 10 Carnaval")["name"] == "POST | Lodge 10 Carnaval"


def test_anexos_tem_cota_diaria_e_os_antigos_saem_do_disco(tmp_path, monkeypatch):
    import io

    import pytest
    from fastapi import HTTPException, UploadFile

    import anexos

    monkeypatch.setattr(anexos, "_usuario", lambda _a: {"sub": "ana-cota"})
    monkeypatch.setattr(anexos, "COTA_DIARIA", 100)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 200
    with pytest.raises(HTTPException) as erro:
        asyncio.run(anexos.enviar_anexos([UploadFile(io.BytesIO(png), filename="a.png")], ""))
    assert erro.value.status_code == 413
    antigo = tmp_path / "velho.png"
    antigo.write_bytes(b"x")
    monkeypatch.setattr(anexos, "_absoluto", lambda caminho: antigo)
    with anexos._db() as db:
        db.execute("INSERT INTO anexos (id, usuario, nome_original, mime, tamanho, caminho, status, criado_em) VALUES "
                   "('velho1', 'ana', 'v.png', 'image/png', 1, 'dados/anexos/velho1.png', 'pronto', '2025-01-01T00:00:00Z')")
    assert anexos.limpar_antigos() >= 1 and not antigo.exists()
