"""Onda 1, agente D (brainstorm de 11/11/2026): vigia da ocupação (despachante-02), rotas da NEWSLETTER, do "sem vídeo",
do TIKTOK e do YOUTUBE (email_marketing-05, editor_video-09) e modelo local sem raciocínio (despachante-26). Banco
temporário (tests/conftest.py)."""

import asyncio

import atividade
import monday
import orquestrador
import producao
import tarefas
import triagem
from estado import Status, buscar_agente
from roteamento import Etapa, sem_video_negado

tarefas.iniciar()


def _limpar(agente_id: str) -> None:
    with tarefas._db() as db:
        db.execute("UPDATE tarefas SET status = 'falhou' WHERE agente = ? AND status IN ('executando', 'adiada', "
                   "'producao', 'produzindo')", (agente_id,))
    atividade._ocupacao[agente_id] = 0
    atividade._etapas_abertas[agente_id] = 0
    buscar_agente("marketing", agente_id).status = Status.disponivel


# --- Ocupação (despachante-02) ------------------------------------------------------------------------------------

def test_tarefa_adiada_propria_nao_segura_o_agente():
    _limpar("designer")
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "designer", "Arte", "simples")
    tarefas.atualizar(tarefa_id, status="adiada")
    asyncio.run(atividade.ocupar("designer"))
    assert asyncio.run(atividade.destravar_se_ocioso("designer"))
    assert buscar_agente("marketing", "designer").status == Status.disponivel


def test_tarefa_do_gestor_so_ocupa_quem_esta_na_etapa():
    _limpar("copywriter")
    _limpar("gestor")
    tarefas.criar("usuario.teste@exemplo.com", "marketing", "gestor", "Projeto", "media")  # "executando"
    asyncio.run(atividade.ocupar("copywriter"))
    assert atividade._tem_tarefa_ativa("gestor")  # o Gestor segue ocupado pela própria tarefa
    assert asyncio.run(atividade.destravar_se_ocioso("copywriter"))  # antes: preso por qualquer tarefa do Gestor

    async def com_etapa():
        await atividade._abrir_etapa("copywriter")
        assert atividade._tem_tarefa_ativa("copywriter")
        assert not await atividade.destravar_se_ocioso("copywriter")
        await atividade._fechar_etapa("copywriter")
        assert buscar_agente("marketing", "copywriter").status == Status.disponivel

    asyncio.run(com_etapa())
    _limpar("gestor")


def test_plano_refeito_do_gestor_nao_soma_ocupacao(monkeypatch):
    chamadas = []
    monkeypatch.setattr(atividade, "_no_loop", lambda corrotina: (chamadas.append(corrotina), corrotina.close()))
    atividade.etapa_em_thread(1, "etapa_iniciada", "gestor", "Plano refeito: modelo assumiu o projeto")
    atividade.etapa_em_thread(1, "etapa_encerrada", "gestor", "fim")
    nomes = [c.__name__ for c in chamadas]
    assert "_abrir_etapa" not in nomes and "_fechar_etapa" not in nomes and "ocupar" not in nomes
    chamadas.clear()
    atividade.etapa_em_thread(1, "etapa_iniciada", "copywriter", "Etapa 1")
    atividade.etapa_em_thread(1, "etapa_encerrada", "copywriter", "Etapa 1")
    assert [c.__name__ for c in chamadas][:1] == ["_abrir_etapa"] and "_fechar_etapa" in [c.__name__ for c in chamadas]


def test_vigia_libera_todos_os_presos_sem_tarefa():
    _limpar("social_media")
    _limpar("designer")
    asyncio.run(atividade.ocupar("social_media"))
    asyncio.run(atividade.ocupar("social_media"))  # ocupação somada duas vezes (liberação perdida)
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "designer", "Arte", "simples")
    asyncio.run(atividade.ocupar("designer"))
    liberados = asyncio.run(atividade.destravar_todos())
    assert "social_media" in liberados and "designer" not in liberados
    assert buscar_agente("marketing", "designer").status == Status.trabalhando
    tarefas.atualizar(tarefa_id, status="concluida")
    _limpar("designer")


def test_fila_adiada_destrava_o_agente_preso(monkeypatch):
    _limpar("analista_tendencias")
    iniciadas = []

    async def rodar(linha, agente, etapas):
        iniciadas.append(linha["id"])

    monkeypatch.setattr(orquestrador, "_rodar_da_fila", rodar)
    monkeypatch.setattr(orquestrador, "_etapas_fila", lambda *_a: [Etapa("openrouter/x:free", 60)])
    with tarefas._db() as db:
        db.execute("UPDATE tarefas SET status = 'falhou' WHERE status = 'adiada'")
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "analista_tendencias", "Tendências", "simples")
    tarefas.atualizar(tarefa_id, status="adiada")
    asyncio.run(atividade.ocupar("analista_tendencias"))  # preso, sem nada rodando

    async def cenario():
        await orquestrador._processar_proxima()
        await asyncio.sleep(0.05)

    asyncio.run(cenario())
    assert iniciadas == [tarefa_id]  # antes: "continue" para sempre
    _limpar("analista_tendencias")


# --- Rotas (email_marketing-05, editor_video-09) ------------------------------------------------------------------

def _item(tipo: str, texto: str = "Peça de dezembro") -> str:
    return f"Produza a peça do item abaixo.\n\n{texto}\n- FORMATO DA PEÇA (obrigatório): {tipo} = {monday.TIPOS[tipo]}."


def test_newsletter_do_monday_vai_ao_email_marketing():
    gestor = buscar_agente("marketing", "gestor")
    email = orquestrador._newsletter_para_o_email("marketing", gestor, _item("NEWSLETTER"))
    assert email and email.id == "email_marketing"
    assert orquestrador._newsletter_para_o_email("marketing", gestor, _item("POST")) is None
    copy = buscar_agente("marketing", "copywriter")
    assert orquestrador._newsletter_para_o_email("marketing", copy, _item("NEWSLETTER")) is None


def test_tiktok_e_youtube_vao_ao_editor_de_video():
    assert producao.produtor_da_peca(_item("TIKTOK")) == "editor_video"
    assert producao.produtor_da_peca(_item("YOUTUBE")) == "editor_video"


def test_sem_video_nao_vai_ao_editor():
    pedido = "Capa e segundo slide do carrossel Janeiro no Nordeste, sem vídeo e sem nenhuma casa"
    gestor = (f"{pedido}\nPlano: o Designer faz a capa; o Editor de Vídeo não entra. Nenhum vídeo nesta peça.")
    assert producao.produtor_da_peca(gestor, pedido) == "criador_imagens"  # caso da tarefa 272
    assert producao.produtor_da_peca("Arte do Lodge 1, sem vídeo") == "criador_imagens"
    assert producao.produtor_da_peca("Um vídeo do Lodge 1") == "editor_video"
    pedido = _item("CARROSSEL", "Carrossel com páginas em vídeo")
    assert producao.produtor_da_peca(pedido, pedido) == "editor_video"
    assert "vídeo" not in sem_video_negado("carrossel sem vídeo").lower()


def test_triagem_ignora_video_negado():
    regras = triagem._pontos_regras("Faça o carrossel em PNG, sem mp4", ["editor_video", "criador_imagens"])
    assert "editor_video" not in regras and "criador_imagens" in regras


# --- Modelo local sem raciocínio (despachante-26) -----------------------------------------------------------------

def test_ollama_vai_com_no_think_e_sem_bloco_de_pensamento():
    from agents import executor

    recebidas = []

    class Falso:
        def call(self, mensagens, *args, **kwargs):
            recebidas.append(mensagens)
            return "<think>\n\n</think>\n\nResposta final."

    llm = executor._sem_raciocinio(Falso())
    mensagens = [{"role": "system", "content": "Você é o Copywriter."}, {"role": "user", "content": "Legenda"}]
    assert llm.call(mensagens) == "Resposta final."
    assert recebidas[0][-1]["content"].endswith("/no_think") and mensagens[-1]["content"] == "Legenda"
    assert recebidas[0][0]["content"] == "Você é o Copywriter."
    llm.call("Pedido direto")
    assert recebidas[1].endswith("/no_think")
    assert executor._sem_pensar([{"role": "user", "content": "x /no_think"}])[0]["content"].count("/no_think") == 1
