"""Onda 3, grupo N (31/10/2026): botão "Desdobrar" no chat (backend/desdobrar.py; designer-07, gestor_trafego-11).
Banco temporário (tests/conftest.py); o envio ao chat e a fila do Max são falsos. O render fica em test_onda3_moldes.py.
"""

import asyncio

import pytest

import desdobrar
import producao
import tarefas
from conexoes import gerenciador

tarefas.iniciar()

USUARIO = {"sub": "usuario.teste"}


def _peca_pronta(agente: str = "criador_imagens", status: str = "concluida", pasta: str | None = "MARKETING/P") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", agente, "Carrossel do Lodge 999", "complexa", "casa_veraneio")
    tarefas.atualizar(tarefa_id, status=status, modelo=producao.MODELO_MAX, resposta="✅ Pedido concluído")
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo, pasta) VALUES (?, 'Teste', ?)", (tarefa_id, pasta))
    return tarefa_id


@pytest.fixture
def sem_espera(monkeypatch):
    async def nada(*_a):
        return None
    monkeypatch.setattr(desdobrar, "_acompanhar", nada)


def test_pedir_poe_um_trabalho_na_fila_sem_duplicar(sem_espera):
    tarefa_id = _peca_pronta()
    resposta = asyncio.run(desdobrar.pedir(tarefa_id, USUARIO))
    trabalho = producao.obter_trabalho(resposta["trabalho_id"])
    assert trabalho["tipo"] == "desdobrar" and trabalho["status"] == "pendente"
    assert trabalho["payload"] == {"tarefa_id": tarefa_id, "raiz": tarefa_id, "pasta": "MARKETING/P",
                                   "formatos": ["1080x1350", "1080x1920"]}
    assert "desdobrar" in producao.TIPOS_TRABALHO  # o trabalhador consegue reservar
    de_novo = asyncio.run(desdobrar.pedir(tarefa_id, USUARIO))
    assert de_novo["trabalho_id"] == resposta["trabalho_id"] and "já está na fila" in de_novo["texto"]
    producao.cancelar_trabalho(resposta["trabalho_id"], "fim do teste")


@pytest.mark.parametrize("kwargs, usuario, codigo", [
    ({}, {"sub": "outra.pessoa"}, 404),
    ({"status": "producao"}, USUARIO, 409),
    ({"agente": "editor_video"}, USUARIO, 409),
    ({"pasta": None}, USUARIO, 409),
])
def test_pedir_recusa_peca_que_nao_serve(sem_espera, kwargs, usuario, codigo):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        asyncio.run(desdobrar.pedir(_peca_pronta(**kwargs), usuario))
    assert erro.value.status_code == codigo


def test_conclusao_avisa_no_chat_ou_manda_para_o_max(monkeypatch):
    enviados, fila = [], []

    async def enviar(login, mensagem):
        enviados.append((login, mensagem))
        return True

    async def enfileirar(login, andar, agente, texto, **kwargs):
        fila.append((agente.id, texto, kwargs))
        return 1

    monkeypatch.setattr(gerenciador, "enviar_para_usuario", enviar)
    monkeypatch.setattr(producao, "enfileirar", enfileirar)
    tarefa_id = _peca_pronta()
    texto = asyncio.run(desdobrar.concluir({"status": "concluido", "resultado": "Desdobrada: 6 arquivo(s)"}, tarefa_id))
    assert "Desdobrada: 6 arquivo(s)" in texto and not fila
    assert enviados[-1][0] == "usuario.teste" and enviados[-1][1]["titulo"] == "Desdobrar"
    asyncio.run(desdobrar.concluir({"status": "concluido", "resultado": "SEM_MOLDE: sem molde.json"}, tarefa_id))
    assert fila[-1][0] == "criador_imagens" and fila[-1][2]["base"] == tarefa_id
    assert fila[-1][1].startswith(f"Ajuste na peça #{tarefa_id}:") and "9:16" in fila[-1][1]
    falha = asyncio.run(desdobrar.concluir({"status": "falhou", "resultado": "Pasta da peça não encontrada"}, tarefa_id))
    assert "Não foi possível desdobrar" in falha
