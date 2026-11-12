"""Onda 3 de novembro: edição rápida sem o Max (backend/edicao_rapida.py; criador_imagens-03, designer-02,
sonoplasta-02) e trocar só o assunto/pré-header no Brevo (agents/brevo_assunto.py; email_marketing-02).
Banco temporário (tests/conftest.py); a fila do PC, o chat e a API do Brevo são falsos (só mock: nada vai ao Brevo).
"""

import asyncio
import json

import pytest
from fastapi import HTTPException

import edicao_rapida as er
import producao
import tarefas
from conexoes import gerenciador

tarefas.iniciar()

USUARIO = {"sub": "usuario.teste"}
LIDO = {"empresa": "casa_veraneio", "slides": [
    {"n": 1, "molde": "capa", "campos": {"kicker": "Casa em destaque", "titulo": "Lodge 999", "subtitulo": "",
                                         "local": "Cidade Fictícia / SP", "contagem": {"numero": "", "texto": ""}}},
    {"n": 2, "molde": "foto", "campos": {}}]}


def _peca(agente="criador_imagens", empresa="casa_veraneio", status="concluida", pasta="MARKETING/P",
          resposta="✅ Pedido concluído\n- 01_capa.png") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", agente, "Carrossel do Lodge 999", "complexa", empresa)
    tarefas.atualizar(tarefa_id, status=status, modelo=producao.MODELO_MAX, resposta=resposta)
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo, pasta) VALUES (?, 'Teste', ?)", (tarefa_id, pasta))
    return tarefa_id


def _mudanca(depois="Lodge 999 no verão", campo="titulo", antes="Lodge 999"):
    return er.Mudanca(n=1, campo=campo, antes=antes, depois=depois)


@pytest.fixture
def sem_espera(monkeypatch):
    async def nada(*_a):
        return None
    monkeypatch.setattr(er, "_acompanhar", nada)


def _limpar():
    with producao._db() as db:
        db.execute("UPDATE trabalhos_max SET status = 'cancelado' WHERE tipo = ? AND status IN ('pendente', "
                   "'executando')", (er.TIPO,))


def test_tipo_entra_na_fila_e_passa_na_frente_das_pecas():
    assert er.TIPO in producao.TIPOS_TRABALHO and er.TIPO in producao.TIPOS_RAPIDOS


def test_editar_textos_poe_o_trabalho_na_fila_sem_duplicar(sem_espera):
    _limpar()
    tarefa_id = _peca()
    resposta = asyncio.run(er.pedir_textos(tarefa_id, er.PedidoTextos(mudancas=[_mudanca()]), USUARIO))
    trabalho = producao.obter_trabalho(resposta["trabalho_id"])
    assert trabalho["tipo"] == "edicao_rapida" and trabalho["payload"]["acao"] == "textos"
    assert trabalho["payload"]["raiz"] == tarefa_id and trabalho["payload"]["pasta"] == "MARKETING/P"
    assert trabalho["payload"]["mudancas"][0] == {"n": 1, "campo": "titulo", "antes": "Lodge 999",
                                                   "depois": "Lodge 999 no verão"}
    de_novo = asyncio.run(er.pedir_musica(_ajuste_de(tarefa_id), er.PedidoMusica(), USUARIO))
    assert de_novo["trabalho_id"] == resposta["trabalho_id"] and "Já há uma edição" in de_novo["texto"]
    _limpar()


def _ajuste_de(base: int) -> int:
    """Ajuste da peça (mesma raiz, mesmo rascunho), com vídeo na resposta."""
    tarefa_id = _peca(resposta="✅ Pedido concluído\n- Reels.mp4")
    with producao._db() as db:
        db.execute("UPDATE producao_info SET base_tarefa_id = ? WHERE tarefa_id = ?", (base, tarefa_id))
    return tarefa_id


@pytest.mark.parametrize("kwargs, usuario, codigo", [
    ({}, {"sub": "outra.pessoa"}, 404),
    ({"status": "producao"}, USUARIO, 409),
    ({"agente": "editor_video"}, USUARIO, 409),
    ({"empresa": "casa_vero"}, USUARIO, 409),   # moldes do Corp e da Vero dependem da decisão 1
    ({"pasta": None}, USUARIO, 409),
])
def test_editar_textos_recusa_peca_que_nao_serve(sem_espera, kwargs, usuario, codigo):
    with pytest.raises(HTTPException) as erro:
        asyncio.run(er.pedir_textos(_peca(**kwargs), er.PedidoTextos(mudancas=[_mudanca()]), usuario))
    assert erro.value.status_code == codigo


def test_conferente_barra_whatsapp_e_valor_e_pede_confirmacao_no_resto(sem_espera):
    _limpar()
    tarefa_id = _peca()
    for ruim in ("Chama no WhatsApp", "Diária de R$ 9.000"):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(er.pedir_textos(tarefa_id, er.PedidoTextos(mudancas=[_mudanca(ruim)]), USUARIO))
        assert erro.value.status_code == 422 and "conferente barrou" in erro.value.detail
    duvida = er.PedidoTextos(mudancas=[_mudanca("Datas livres no verão")])
    resposta = asyncio.run(er.pedir_textos(tarefa_id, duvida, USUARIO))
    assert resposta["confirmar"] and "disponibilidade" in resposta["avisos"][0] and "trabalho_id" not in resposta
    duvida.confirmar = True
    assert asyncio.run(er.pedir_textos(tarefa_id, duvida, USUARIO))["trabalho_id"]
    _limpar()


def test_limite_de_caracteres_e_campo_desconhecido(sem_espera):
    tarefa_id = _peca()
    for mudanca in (_mudanca("x" * 60), er.Mudanca(n=1, campo="lodge", depois="1"),
                    er.Mudanca(n=1, campo="linhas", depois=["a"] * 9)):
        with pytest.raises(HTTPException) as erro:
            asyncio.run(er.pedir_textos(tarefa_id, er.PedidoTextos(mudancas=[mudanca]), USUARIO))
        assert erro.value.status_code == 422


def test_formulario_le_o_molde_no_pc_e_guarda_a_leitura(monkeypatch):
    _limpar()
    tarefa_id = _peca()
    chamadas = []

    async def aguardar(trabalho_id, _timeout):
        chamadas.append(trabalho_id)
        with producao._db() as db:
            db.execute("UPDATE trabalhos_max SET status = 'concluido', resultado = ?, concluido_em = ? WHERE id = ?",
                       (json.dumps(LIDO), producao._agora(), trabalho_id))
        return producao.obter_trabalho(trabalho_id)

    monkeypatch.setattr(producao, "aguardar_trabalho", aguardar)
    dados = asyncio.run(er.campos(tarefa_id, USUARIO))
    assert dados["ok"] and dados["slides"][0]["campos"]["titulo"] == "Lodge 999" and dados["limites"]["cta"]
    assert producao.obter_trabalho(chamadas[0])["payload"]["acao"] == "ler"
    asyncio.run(er.campos(tarefa_id, USUARIO))
    assert len(chamadas) == 1  # a leitura recente vale: sem ir de novo ao PC


def test_formulario_sem_molde_ou_pc_ocupado(monkeypatch):
    _limpar()
    tarefa_id = _peca()

    async def ocupado(trabalho_id, _timeout):
        return producao.obter_trabalho(trabalho_id)

    monkeypatch.setattr(producao, "aguardar_trabalho", ocupado)
    assert not asyncio.run(er.campos(tarefa_id, USUARIO))["ok"]  # fica na fila; o clique seguinte aproveita

    async def sem_molde(trabalho_id, _timeout):
        with producao._db() as db:
            db.execute("UPDATE trabalhos_max SET status = 'concluido', resultado = 'SEM_MOLDE: sem molde.json', "
                       "concluido_em = ? WHERE id = ?", (producao._agora(), trabalho_id))
        return producao.obter_trabalho(trabalho_id)

    monkeypatch.setattr(producao, "aguardar_trabalho", sem_molde)
    with pytest.raises(HTTPException) as erro:
        asyncio.run(er.campos(tarefa_id, USUARIO))
    assert erro.value.status_code == 409 and "Pedir ajuste" in erro.value.detail
    _limpar()


def test_outra_musica_so_para_video_e_com_a_empresa_da_peca(sem_espera):
    _limpar()
    with pytest.raises(HTTPException) as erro:
        asyncio.run(er.pedir_musica(_peca(), er.PedidoMusica(), USUARIO))  # só PNG
    assert erro.value.status_code == 409
    tarefa_id = _peca(agente="editor_video", empresa="cv_corporativo", resposta="✅ Pedido concluído\n- Reels.mp4")
    with pytest.raises(HTTPException):
        asyncio.run(er.pedir_musica(tarefa_id, er.PedidoMusica(clima="rock"), USUARIO))
    resposta = asyncio.run(er.pedir_musica(tarefa_id, er.PedidoMusica(clima="calma"), USUARIO))
    payload = producao.obter_trabalho(resposta["trabalho_id"])["payload"]
    assert payload["acao"] == "musica" and payload["empresa"] == "cv_corporativo" and "calma" in payload["pedido"]
    _limpar()


def test_conclusao_avisa_no_chat_e_nunca_manda_ao_max(monkeypatch):
    enviados, fila = [], []

    async def enviar(login, mensagem):
        enviados.append(mensagem)
        return True

    async def enfileirar(*_a, **_k):
        fila.append(1)

    monkeypatch.setattr(gerenciador, "enviar_para_usuario", enviar)
    monkeypatch.setattr(producao, "enfileirar", enfileirar)
    tarefa_id = _peca()
    texto = asyncio.run(er.concluir({"status": "concluido", "resultado": "Textos trocados sem o Max (versão 2)"},
                                    tarefa_id, "textos"))
    assert "versão 2" in texto and enviados[-1]["titulo"] == "Editar textos"
    texto = asyncio.run(er.concluir({"status": "concluido", "resultado": "SEM_RECEITA: sem receita"}, tarefa_id,
                                    "musica"))
    assert "Pedir ajuste" in texto and "troque a música" in texto and not fila  # o Max só com pedido da pessoa
    assert "Não foi possível" in asyncio.run(er.concluir({"status": "falhou", "resultado": "sem faixa"}, tarefa_id,
                                                         "musica"))
    eventos = [e["tipo"] for e in tarefas._db().execute("SELECT tipo FROM eventos WHERE tarefa_id = ?", (tarefa_id,))]
    assert eventos.count("edicao_textos") == 1 and eventos.count("edicao_musica") == 2


# --- Brevo: trocar só o assunto/pré-header (email_marketing-02) -------------------------------------------------

@pytest.fixture
def brevo(monkeypatch):
    from agents import ferramentas_brevo as fb

    estado = {"status": "draft", "modifiedAt": "2026-11-12T10:00:00Z", "name": "[Rascunho Escritório] VERANEIO | "
              "2027-01 | Férias", "subject": "Assunto antigo do e-mail de janeiro", "sender": {"name": "Casa Veraneio"}}
    chamadas = []

    def api(metodo, caminho, chave, corpo=None):
        fb._conferir(metodo, caminho, corpo)  # a mesma trava da ferramenta de verdade
        chamadas.append((metodo, caminho, corpo))
        if metodo == "PUT":
            estado.update(corpo, modifiedAt="2026-11-12T11:00:00Z")
        return dict(estado, id=int(caminho.rsplit("/", 1)[1]))

    monkeypatch.setattr(fb, "_chave", lambda: "chave-falsa")
    monkeypatch.setattr(fb, "_api", api)
    return estado, chamadas


def _conversa_com_rascunho(alterada="2026-11-12T10:00:00Z") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", "email_marketing", "E-mail de janeiro", "complexa",
                              "casa_veraneio")
    tarefas.registrar_evento(tarefa_id, "rascunho_brevo", "email_marketing",
                             detalhe=f"campanha 57 (alterada {alterada}) 2027-01: Assunto antigo")
    return tarefa_id


def test_troca_so_assunto_sem_html_e_sem_novo_rascunho(brevo):
    from agents.brevo_assunto import TrocarAssuntoBrevo

    _estado, chamadas = brevo
    tarefa_id = _conversa_com_rascunho()
    texto = TrocarAssuntoBrevo(empresa="casa_veraneio", tarefa_id=tarefa_id)._run(assunto="Janeiro com a casa só sua")
    puts = [c for c in chamadas if c[0] == "PUT"]
    assert puts == [("PUT", "/emailCampaigns/57", {"subject": "Janeiro com a casa só sua"})]  # nem HTML nem lista
    assert not [c for c in chamadas if c[0] == "POST"] and "sem criar outro" in texto and "nada foi enviado" in texto
    from agents import ferramentas_brevo as fb
    assert fb._rascunho_da_conversa(tarefa_id, "2027-01")[1] == "2026-11-12T11:00:00Z"  # a conversa segue dona


def test_rascunho_editado_a_mao_continua_protegido(brevo):
    from agents import ferramentas_brevo as fb
    from agents.brevo_assunto import TrocarAssuntoBrevo

    tarefa_id = _conversa_com_rascunho("2026-11-12T09:00:00Z")  # o Thomas mexeu depois do registro
    TrocarAssuntoBrevo(empresa="casa_veraneio", tarefa_id=tarefa_id)._run(numero=57, pre_header="Casas inteiras")
    assert fb._rascunho_da_conversa(tarefa_id, "2027-01")[1] == "2026-11-12T09:00:00Z"  # o corpo não é regravado


def test_outra_empresa_ou_campanha_enviada_nao_e_tocada(brevo):
    from agents.brevo_assunto import TrocarAssuntoBrevo

    estado, chamadas = brevo
    assert "não mexi" in TrocarAssuntoBrevo(empresa="casa_vero")._run(numero=57, assunto="Outro assunto qualquer")
    estado["status"] = "sent"
    assert "não é mais rascunho" in TrocarAssuntoBrevo(empresa="casa_veraneio")._run(numero=57, assunto="Outro")
    assert not [c for c in chamadas if c[0] != "GET"]
    assert "diga o número" in TrocarAssuntoBrevo(empresa="casa_veraneio")._run(assunto="Sem conversa")
