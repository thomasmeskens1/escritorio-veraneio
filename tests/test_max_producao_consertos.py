"""Consertos da produção do Max (brainstorm de 31/10/2026, grupo B): tipo de entrega, correções aprovadas na
produção, falha com o texto do Max, entrega só de texto, aviso da caixa de areia, fila que não morre em 3 h, erro
interno passageiro, decisão em aberto e manual 02 para o Tráfego do Corporativo e da Casa Vero.
Banco temporário (tests/conftest.py).
"""

import asyncio

import pytest

import correcoes
import orquestrador
import producao
import saude
import tarefas
from estado import buscar_agente
from roteamento import Etapa

tarefas.iniciar()


# --- Tipo de entrega (despachante-02, criador_imagens-28) ---------------------------------------------------------

@pytest.mark.parametrize("pedido, esperado", [
    ("preciso criar uma legenda nesse estilo para o Lodge 35", "texto"),
    ("Crie a legenda do post do Lodge 35", "texto"),
    ("Crie um post do Lodge 35 com legenda", "visual"),
    ("Crie a arte e a legenda do post do Lodge 35", "visual"),
    ("Faça uma apresentação em PowerPoint dos Lodges de Ilhabela", "documento"),
    ("Reels do Lodge 90 com 3 cenas", "visual"),
    ("Monte o carrossel do Lodge 12", "visual"),
    ("FORMATO DA PEÇA (obrigatório): POST\nlegenda: x", "visual"),
])
def test_tipo_de_entrega(pedido, esperado):
    assert producao.tipo_de_entrega(pedido) == esperado


def test_briefing_do_gestor_ja_decidiu_produzir():
    briefing = ("Produza a peça final do projeto #9, coordenado pelo Gestor.\n\nPedido original: Persona da Casa "
                "Veraneio\n\nResultado consolidado do Gestor:\nfotografias e vídeos ...")
    assert producao.tipo_de_entrega(briefing) == "visual"  # o orquestrador já perguntou se era para produzir
    doc = briefing.replace("Persona da Casa Veraneio", "Apresentação pptx da persona")
    assert producao.tipo_de_entrega(doc) == "documento"


# --- Correções aprovadas na produção (editor_video-09, moviemaker-14) ---------------------------------------------

def _regra(agente: str, regra: str, empresa: str = "*") -> None:
    with correcoes._db() as db:
        db.execute("INSERT INTO regras_aprendidas (agente, regra, criada_em, empresa) VALUES (?, ?, ?, ?)",
                   (agente, regra, tarefas._agora(), empresa))


def test_regras_aprovadas_chegam_a_producao_de_video_e_arte():
    _regra("moviemaker", "Frames de cerca de 4 s, sem acelerar.", "casa_vero")
    _regra("editor_video", "Logo do fechamento com pelo menos 120 px.")
    _regra("designer", "Nada de bloco Verde forte sobre a foto.", "casa_veraneio")
    _regra("copywriter", "Regra só do Copywriter.")
    video = correcoes.regras_da_producao("editor_video", "casa_vero")
    assert "4 s" in video and "120 px" in video and "Verde forte" not in video and "Copywriter" not in video
    assert "Verde forte" in correcoes.regras_da_producao("criador_imagens", "casa_veraneio")
    assert "4 s" not in correcoes.regras_da_producao("editor_video", "casa_veraneio")  # regra de outra empresa
    assert correcoes.regras_da_producao("agente_sem_regra", "cv_corporativo") == ""


# --- Falha com o texto do Max e entrega só de texto (despachante-01) ----------------------------------------------

@pytest.fixture
def operador(monkeypatch):
    import atividade
    import monday

    async def nada(*_a):
        return None

    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(atividade, "liberar", nada)
    monkeypatch.setattr(monday, "andamento", lambda *_a, **_k: None)
    monkeypatch.setattr(orquestrador, "_entregar", nada)
    monkeypatch.setattr(orquestrador, "entregar_na_origem", nada)


def _producao(texto: str = "Produza a peça") -> int:
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "criador_imagens", texto, "complexa")
    tarefas.atualizar(tarefa_id, status="produzindo")
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo) VALUES (?, 'Teste')", (tarefa_id,))
    return tarefa_id


def test_falha_sem_arquivo_leva_o_texto_do_max(operador):
    tarefa_id = _producao()
    asyncio.run(producao.falhar(tarefa_id, producao.Falha(erro="Nenhum arquivo PNG/MP4/PDF foi gerado.",
                                                          texto="Faltou a foto da fachada do Lodge 35."), ""))
    motivo = tarefas.obter(tarefa_id)["motivo"]
    assert "Nenhum arquivo" in motivo and "Faltou a foto da fachada" in motivo


def test_entrega_so_de_texto_conclui_sem_pasta(operador):
    tarefa_id = _producao("Crie a legenda do Lodge 35")
    conclusao = producao.Conclusao(resumo="Legenda: Casa inteira para o seu grupo.", pasta="MARKETING/x",
                                   arquivos=[], so_texto=True)
    asyncio.run(producao.concluir(tarefa_id, conclusao, ""))
    linha = tarefas.obter(tarefa_id)
    assert linha["status"] == "concluida" and "entregue como texto" in linha["resposta"]
    assert "Arquivos em" not in linha["resposta"]
    pasta = producao._db().execute("SELECT pasta FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()[0]
    assert pasta is None  # não vira base de ajuste numa pasta que não existe


# --- Aviso da caixa de areia (despachante-27) ----------------------------------------------------------------------

def test_bloqueio_da_caixa_vira_aviso_no_painel(operador):
    tarefa_id = _producao()
    linhas = ["2026-10-31 10:00:00 | arquivo de segredo bloqueado (.env)", "2026-10-31 10:00:01 | rede bloqueada (x)"]
    asyncio.run(producao.registrar_bloqueios(tarefa_id, producao.Bloqueios(linhas=linhas), ""))
    avisos = [a for a in saude.avisos_da_caixa_de_areia() if f"tarefa {tarefa_id} " in a]
    assert avisos and "2 tentativa(s)" in avisos[0] and "usuario.teste@exemplo.com" in avisos[0]
    eventos = [e["tipo"] for e in tarefas.eventos_de([tarefa_id])[tarefa_id]]
    assert "bloqueio_caixa" in eventos


# --- Fila que não morre em 3 h (despachante-18) ---------------------------------------------------------------------

def test_reagendar_espera_crescente_e_prazo_de_24_horas():
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "copywriter", "Legenda", "simples")
    for _ in range(8):  # antes, a 6ª tentativa matava a tarefa
        assert tarefas.reagendar(tarefa_id)
    assert tarefas.obter(tarefa_id)["tentativas_fila"] == 8
    with tarefas._db() as db:
        db.execute("UPDATE tarefas SET criada_em = '2026-01-01T00:00:00Z' WHERE id = ?", (tarefa_id,))
    assert not tarefas.reagendar(tarefa_id)  # mais de 24 h e já tentou o bastante


def test_tentativa_sem_modelo_rodando_nao_conta():
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "copywriter", "Legenda", "simples")
    inicio = tarefas._agora()
    tarefas.registrar_evento(tarefa_id, "falha_modelo", "copywriter", "claude-code/max", "Max ocupado; seguindo")
    assert tarefas.falhas_de_modelo_desde(tarefa_id, inicio) == 0
    assert tarefas.reagendar(tarefa_id, rodou_modelo=False)
    assert tarefas.obter(tarefa_id)["tentativas_fila"] == 0
    tarefas.registrar_evento(tarefa_id, "falha_modelo", "copywriter", "openrouter/x:free", "erro 500")
    assert tarefas.falhas_de_modelo_desde(tarefa_id, inicio) == 1


# --- Erro interno passageiro (despachante-19) -----------------------------------------------------------------------

def test_erro_interno_passageiro_tenta_de_novo(monkeypatch):
    chamadas = []

    async def etapas(*_a):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise orquestrador.ErroInterno("cannot start a transaction within a transaction")
        return True

    async def sem_espera(_s):
        return None

    monkeypatch.setattr(orquestrador, "_executar_etapas", etapas)
    monkeypatch.setattr(orquestrador.asyncio, "sleep", sem_espera)
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "copywriter", "Legenda", "simples")
    agente = buscar_agente("marketing", "copywriter")
    assert asyncio.run(orquestrador._executar_com_retentativa(tarefas.obter(tarefa_id), agente, [Etapa("x", 1)]))
    assert len(chamadas) == 2
    assert "retentativa" in [e["tipo"] for e in tarefas.eventos_de([tarefa_id])[tarefa_id]]

    async def quebra(*_a):
        raise orquestrador.ErroInterno("invalid literal for int(): 'orlando'")

    monkeypatch.setattr(orquestrador, "_executar_etapas", quebra)
    with pytest.raises(orquestrador.ErroInterno):  # erro de código: falha na hora, como antes
        asyncio.run(orquestrador._executar_com_retentativa(tarefas.obter(tarefa_id), agente, [Etapa("x", 1)]))


# --- Decisão em aberto segura a produção (editor_video-24) ----------------------------------------------------------

def test_decisao_em_aberto():
    assert orquestrador._decisao_em_aberto("Plano pronto.\n\nFaltam duas decisões suas: casa A ou B?")
    assert orquestrador._decisao_em_aberto("Ainda não tenho o MP4; só sai depois de eu conferir.")
    assert orquestrador._decisao_em_aberto("Plano pronto. Legenda e arte definidas.") is None


# --- Manual 02 para o Tráfego do Corporativo e da Casa Vero (gestor_trafego-09) ------------------------------------

def test_trafego_de_corp_e_vero_recebe_o_metodo_do_manual_02(monkeypatch, tmp_path):
    import config
    from agents import diretrizes

    (tmp_path / "00_leia.md").write_text("# 00\n\n## REGRAS DE OURO\nouro\n\n## 2. Regras\ngerais", encoding="utf-8")
    (tmp_path / "02_social.md").write_text("# 02\n\n## 1. Missão\nmissão\n\n## 5. Exemplo real\ncalendário\n\n"
                                           "## 6. Playbook de campanha paga\nconjuntos A e B", encoding="utf-8")
    (tmp_path / "12_vero.md").write_text("# Casa Vero\n\n## 1. O que é\nimóveis", encoding="utf-8")
    monkeypatch.setattr(config, "PASTA_CONHECIMENTO", tmp_path)
    texto = diretrizes.para("gestor_trafego", empresa="casa_vero")
    assert "conjuntos A e B" in texto and "MÉTODO DE MÍDIA PAGA" in texto and "imóveis" in texto
    assert "calendário" not in texto  # só as seções da função
    assert texto.index("imóveis") < texto.index("conjuntos A e B")  # o documento da empresa vem antes
    assert "conjuntos A e B" not in diretrizes.para("copywriter", empresa="casa_vero")
