"""Térreo (escola), Onda 1 de 31/10/2026: empresa da tarefa segue o pedido, a escola só indica o que a pessoa abre
(recepcionista-09) e o Professor responde curto (professor-06). Banco temporário (tests/conftest.py)."""

import acesso
import auth
import empresas
import tarefas
from agents import perfis

tarefas.iniciar()
LOGIN = "usuario.teste@exemplo.com"
USUARIOS = {LOGIN: {"nome": "Usuário Teste", "role": "funcionario",
                    "andares": ["terreo", "marketing", "comercial", "cobertura"]}}


def _troca(login, agente, texto, empresa=empresas.COMUM):
    tarefa_id = tarefas.criar(login, "terreo", agente, texto, "simples", empresa=empresa)
    tarefas.atualizar(tarefa_id, status="concluida", resposta="ok")
    return tarefa_id


def _usuarios(monkeypatch):
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: USUARIOS)
    monkeypatch.setattr(acesso, "carregar_usuarios", lambda: USUARIOS)


def test_empresa_do_terreo_segue_o_pedido_ou_fica_neutra():
    login = "escola.empresa@exemplo.com"
    assert perfis.empresa_da_escola(login, "professor", "Como peço uma legenda?") == empresas.COMUM
    assert perfis.empresa_da_escola(login, "professor", "Como peço um post para a Casa Vero?") == "casa_vero"
    _troca(login, "professor", "Quero ajuda com um pedido da Casa Veraneio Corporativo")
    assert perfis.empresa_da_escola(login, "professor", "e o formato?") == "cv_corporativo"
    assert perfis.empresa_da_escola(login, "recepcionista", "e o formato?") == empresas.COMUM  # outro chat


def test_resposta_ao_formulario_nao_esconde_o_pedido_original(monkeypatch):
    _usuarios(monkeypatch)
    _troca(LOGIN, "professor", "Me ajuda a pedir um carrossel de fim de ano")  # empresa neutra: "*"
    atual = tarefas.criar(LOGIN, "terreo", "professor", "Para qual empresa é o pedido?: Casa Vero", "simples",
                          empresa="casa_vero")
    descricao = perfis.descricao_tarefa("professor", "Para qual empresa é o pedido?: Casa Vero", [], atual)
    assert "carrossel de fim de ano" in descricao
    assert "EMPRESA DESTE TRABALHO: Casa Vero" in descricao


def test_escola_so_indica_o_que_a_pessoa_abre(monkeypatch):
    _usuarios(monkeypatch)
    texto = perfis._o_que_a_pessoa_abre(LOGIN)
    assert "QUEM ESTÁ PERGUNTANDO: Usuário" in texto
    assert "Andares fechados para ela: Porão" in texto
    abertos = texto.split("Andares fechados")[0]
    assert "Despachante" not in abertos and "Construtor" not in abertos and "Professor" in abertos
    atual = _troca(LOGIN, "recepcionista", "Onde vejo a fila das minhas tarefas?")
    descricao = perfis.descricao_tarefa("recepcionista", "Onde vejo a fila das minhas tarefas?", [], atual)
    assert "Andares fechados para ela: Porão" in descricao
    assert "QUEM ESTÁ PERGUNTANDO" not in perfis.contexto("copywriter", [], "legenda", "casa_veraneio", LOGIN)


def test_professor_responde_curto_com_o_pedido_pronto():
    persona = perfis.PERFIS["professor"]["backstory"]
    for trecho in ("Seu pedido, pronto para enviar", "O que faltava", "Mande para", "[PENDENTE", "me explica mais",
                   "incluído"):
        assert trecho in persona
    assert "Não sei com quem falar" in perfis.MANUAL_ESCOLA
