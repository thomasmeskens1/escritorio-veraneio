"""Onda 1 de novembro, agente F (11/11/2026): plano do Gestor e regras de conteúdo. Pauta com o papel das peças
(gestor-13), Analista antes de quem escreve (analista_tendencias-30), direção visual no roteiro (social_media-18),
pedido de vídeo fora do manual (moviemaker-02), prazo "fechar até" com validade (copywriter-01, analista_tendencias-01,
gestor-03), checklist da Meta (gestor_trafego-03), rápida ou completa (analista_tendencias-32) e CRECI da Casa Vero
(estrategista-38). Banco temporário (tests/conftest.py); Monday e Brevo simulados, nada sai para a internet.
"""

import json
import threading
from datetime import date

import pytest

import calendario
import conferente
import direcao_visual
import estudos
import pauta_papeis
import pauta_semana
import pedido_video
import prazos_comerciais
import producao
import tarefas
from agents import projeto, projeto_regras
from conferente_regras import CHECKLIST_META_TITULO

tarefas.iniciar()
HOJE = date(2026, 11, 11)
USUARIO = "usuario.teste@exemplo.com"


@pytest.fixture
def calendario_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(calendario, "ARQUIVO", tmp_path / "calendario.json")
    return tmp_path / "calendario.json"


# --- gestor-13: pauta confere o papel ------------------------------------------------------------------------------

def _item(n, nome, postagem, legenda="", conta="Casa Veraneio"):
    from pauta_semana import COL_ENTREGA, monday

    return {"id": str(n), "name": nome, "column_values": [
        {"id": "data", "text": postagem}, {"id": monday.COL_STATUS, "text": "Aguardando"},
        {"id": monday.COL_CONTA, "text": conta}, {"id": COL_ENTREGA, "text": ""},
        {"id": monday.COL_LEGENDA, "text": legenda}]}


def test_papel_explicito_vale_mais_que_a_palavra_solta():
    assert pauta_papeis.papel("REELS | Lodge 3\nPapel: Conversão. Descoberta do litoral") == "Conversão"
    assert pauta_papeis.papel("CARROSSEL | Consideração: guia da praia") == "Consideração"
    assert pauta_papeis.papel("STORIES | Bastidores") == ""


def test_semana_sem_conversao_perto_da_black_friday_avisa_e_sugere_o_carrossel(calendario_vazio):
    segunda = date(2026, 11, 16)  # Black Friday em 27/11: daqui a 11 dias
    quadro = {"Novembro": [
        _item(1, "REELS | Lodge 3 (Descoberta)", "2026-11-17"),
        _item(2, "CARROSSEL | Guia de Ubatuba", "2026-11-18", "Papel: Descoberta"),
        _item(3, "REELS | Lodge 9", "2026-11-19", "Papel: Consideração"),
        _item(4, "STORIES | Bastidores", "2026-11-20"),
    ]}
    a = pauta_semana.analisar(quadro, "casa_veraneio", segunda)
    assert a["mistura"] == "2 Descoberta, 1 Consideração, 0 Conversão"
    aviso = next(x for x in a["avisos_papel"] if "nenhuma peça de Conversão" in x)
    assert "Black Friday em 27/11" in aviso and "CARROSSEL | Guia de Ubatuba" in aviso
    assert any("sem papel" in x and "STORIES | Bastidores" in x for x in a["avisos_papel"])
    texto = pauta_semana.montar("casa_veraneio", segunda, quadro)
    assert "Papel das peças (manual 15 §5): 2 Descoberta" in texto and "Aviso de papel" in texto


def test_semana_com_conversao_demais_avisa(calendario_vazio):
    quadro = {"Novembro": [_item(n, f"REELS | Lodge {n}", "2026-11-17", "Papel: Conversão") for n in (1, 2, 3)]
              + [_item(4, "CARROSSEL | Guia", "2026-11-18", "Papel: Descoberta")]}
    avisos = pauta_semana.analisar(quadro, "casa_veraneio", date(2026, 11, 16))["avisos_papel"]
    assert any("mais da metade da semana é Conversão (3 de 4)" in x and "para Descoberta" in x for x in avisos)
    assert not any("nenhuma peça de Conversão" in x for x in avisos)


def test_prazo_fechar_ate_perto_pede_conversao(calendario_vazio):
    prazos_comerciais.registrar("cv_corporativo", "Confraternizações de fim de ano", "2026-11-20", "thomas",
                                hoje=HOJE)
    datas = pauta_papeis.datas_comerciais("cv_corporativo", HOJE)
    assert any("fechamento de Confraternizações de fim de ano até 20/11 (faltam 9 dias)" in d for d in datas)


# --- analista_tendencias-30: ângulos antes de quem escreve ----------------------------------------------------------

def test_analista_vai_para_antes_da_primeira_escrita():
    plano = [{"agente": "copywriter", "instrucao": "Texto", "fase": 1},
             {"agente": "analista_tendencias", "instrucao": "Ângulos", "fase": 1},
             {"agente": "criador_imagens", "instrucao": "Fotos", "fase": 1},
             {"agente": "designer", "instrucao": "Layout", "fase": 2}]
    novo, nota = projeto_regras.analista_antes(plano)
    assert [(p["agente"], p["fase"]) for p in novo] == [("copywriter", 2), ("analista_tendencias", 1),
                                                        ("criador_imagens", 2), ("designer", 3)]
    assert "fase 1, antes de quem escreve" in nota
    certo = [{"agente": "analista_tendencias", "instrucao": "A", "fase": 1},
             {"agente": "copywriter", "instrucao": "T", "fase": 2}]
    assert projeto_regras.analista_antes(certo) == (certo, "")


def _executar(resposta_plano, chamadas):
    def executar(agente, descricao, esperado, papel):
        chamadas.append((agente, descricao))
        if "JSON com o entendimento" in esperado:
            return resposta_plano
        return "Entrega final." if agente == "gestor" else f"entrega de {agente}"
    return executar


def test_projeto_reordena_o_analista_e_lembra_quem_escreve(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = ('{"entendimento": "Post de Réveillon", "duvida": "", "titulo": "Post Réveillon", "papel": "Descoberta", '
             '"cta": "link da bio", "metrica": "salvamentos", "hipotese": "h", "etapas": ['
             '{"agente": "copywriter", "instrucao": "Legenda", "fase": 1}, '
             '{"agente": "analista_tendencias", "instrucao": "Ângulos", "fase": 1}]}')
    chamadas = []
    projeto.executar_projeto(901, "Post de Réveillon", "CTX", _executar(plano, chamadas), threading.Event())
    salvo = json.loads((tmp_path / "901" / "plano.json").read_text(encoding="utf-8"))
    assert [(p["agente"], p["fase"]) for p in salvo] == [("copywriter", 2), ("analista_tendencias", 1)]
    assert "antes de quem escreve" in (tmp_path / "901" / "plano.md").read_text(encoding="utf-8")
    ordem = [a for a, _ in chamadas if a != "gestor"]
    assert ordem == ["analista_tendencias", "copywriter"]
    texto_copy = next(d for a, d in chamadas if a == "copywriter")
    assert "Use os ângulos do Analista de Tendências (etapa 2" in texto_copy and "entrega de analista" in texto_copy


def test_plano_com_trafego_fecha_com_o_checklist_da_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = ('{"entendimento": "E", "duvida": "", "titulo": "Campanha", "etapas": '
             '[{"agente": "gestor_trafego", "instrucao": "Plano de mídia", "fase": 1}]}')
    final = projeto.executar_projeto(902, "Plano de mídia do Carnaval", "CTX", _executar(plano, []),
                                     threading.Event())
    assert final.count(CHECKLIST_META_TITULO) == 1 and "Melhorias automáticas da Meta desligadas" in final


def test_resposta_do_trafego_ganha_o_checklist_uma_vez():
    plano = "Campanha do Carnaval: dois públicos, verba concentrada no vencedor e criativos em rodadas."
    texto = conferente.anotar(plano, "gestor_trafego", "casa_veraneio", "plano de mídia")
    assert texto.count(CHECKLIST_META_TITULO) == 1
    assert conferente.anotar(texto, "gestor_trafego", "casa_veraneio", "").count(CHECKLIST_META_TITULO) == 1
    assert CHECKLIST_META_TITULO not in conferente.anotar("O CPC subiu 10%.", "gestor_trafego", "casa_veraneio")


# --- moviemaker-02: pedido fora do manual vira pergunta --------------------------------------------------------------

def test_conflitos_do_pedido_com_o_manual_05():
    achados = pedido_video.conflitos("Reels do Lodge 32: cada espaço tem 2 takes de 2 s, 10 cenas, em 1x",
                                     "casa_veraneio")
    assert any("take de 2 s" in a for a in achados) and any("10 takes" in a for a in achados)
    assert any("0,75x" in a for a in achados)
    assert pedido_video.conflitos("Reels com 6 takes de 4 s cada", "casa_veraneio") == []
    assert pedido_video.conflitos("Reels com takes de 2 s", "cv_corporativo") == []  # decisão 1 em aberto
    assert pedido_video.conflitos("Post de 1x por semana", "casa_veraneio") == []  # não é vídeo


def test_formulario_de_um_clique_e_a_escolha_volta_no_contexto():
    bloco = pedido_video.formulario(["take de 2 s"])
    dados = json.loads(bloco.removeprefix("<<FORMULARIO>>").removesuffix("<<FIM DO FORMULARIO>>"))
    assert dados["campos"][0]["opcoes"] == [pedido_video.SEGUIR_PEDIDO, pedido_video.SEGUIR_PADRAO]
    resposta = f"Respostas — {pedido_video.TITULO}:\n- O pedido contraria: {pedido_video.SEGUIR_PEDIDO}"
    assert pedido_video.conflitos(resposta + " takes de 2 s reels", "casa_veraneio") == []
    assert "seguir o PEDIDO" in pedido_video.bloco("moviemaker", "casa_veraneio", resposta)
    assert "PEDIDO FORA DO PADRÃO" in pedido_video.bloco("moviemaker", "casa_veraneio", "Reels com takes de 2 s")


def test_gestor_pergunta_antes_de_planejar(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    tarefa = tarefas.criar(USUARIO, "marketing", "gestor", "Reels do Lodge 32 com takes de 2 s", "media",
                           empresa="casa_veraneio")
    chamadas = []
    final = projeto.executar_projeto(tarefa, "Reels do Lodge 32 com takes de 2 s", "CTX", _executar("[]", chamadas),
                                     threading.Event())
    assert not chamadas and "<<FORMULARIO>>" in final and pedido_video.SEGUIR_PADRAO in final
    assert not (tmp_path / str(tarefa) / "plano.json").exists()  # nada vai para a produção


def test_moviemaker_que_esquece_o_formulario_ganha_o_bloco():
    texto = conferente.anotar("Roteiro pronto.", "moviemaker", "casa_veraneio", "Reels com takes de 2 s")
    assert "<<FORMULARIO>>" in texto and pedido_video.TITULO in texto


# --- copywriter-01 / analista_tendencias-01 / gestor-03: prazo "fechar até" com validade ------------------------------

def test_prazo_valida_a_entrada_e_vence_em_7_dias(calendario_vazio):
    with pytest.raises(ValueError):
        prazos_comerciais.registrar("casa_veraneio", "Réveillon", "2026-11-01", "thomas", hoje=HOJE)  # passou
    with pytest.raises(ValueError):
        prazos_comerciais.registrar("outra", "Réveillon", "2026-12-10", "thomas", hoje=HOJE)
    prazos_comerciais.registrar("casa_veraneio", "Réveillon", "2026-12-10", "thomas", "poucas datas", hoje=HOJE)
    prazos_comerciais.registrar("casa_veraneio", "réveillon", "2026-12-12", "thomas", hoje=HOJE)  # reconfirma
    lista = prazos_comerciais.prazos("casa_veraneio", HOJE)
    assert len(lista) == 1 and lista[0]["fechar_ate"] == date(2026, 12, 12) and lista[0]["valido"]
    assert not prazos_comerciais.prazos("casa_veraneio", date(2026, 11, 19))[0]["valido"]  # 8 dias depois
    assert prazos_comerciais.prazos("casa_vero", HOJE) == []  # empresas separadas
    bloco = calendario.bloco("copywriter", "casa_veraneio", "legenda do Réveillon", hoje=HOJE)
    assert "fechar até 12/12/2026, faltam 31 dias" in bloco


def test_prazo_sem_confirmacao_nunca_vale(calendario_vazio):
    calendario_vazio.write_text(json.dumps({"prazos_comerciais": {"casa_veraneio": [
        {"momento": "Carnaval", "fechar_ate": "2027-01-20"}]}}), encoding="utf-8")
    assert not prazos_comerciais.prazos("casa_veraneio", HOJE)[0]["valido"]
    assert "sem confirmação válida" in prazos_comerciais.bloco("casa_veraneio", HOJE)


def test_conferente_avisa_urgencia_sem_prazo(calendario_vazio):
    texto = "Últimos dias para escolher a casa do Réveillon. Não perca!"
    assert any("sem prazo de fechamento válido" in a for a in conferente.conferir(texto, "casa_veraneio", "roteiro"))
    prazos_comerciais.registrar("casa_veraneio", "Réveillon", (date.today().replace(year=date.today().year + 1)
                                                              ).isoformat(), "thomas")
    assert not any("urgência" in a for a in conferente.conferir(texto, "casa_veraneio", "roteiro"))
    assert any("urgência" in a for a in conferente.conferir(texto, "casa_vero", "roteiro"))  # outra empresa
    assert not any("urgência" in a for a in conferente.conferir("Nunca diga corra.", "casa_vero", "roteiro"))


def test_sugestao_de_disponibilidade_nao_repete_a_frase_gasta():
    aviso = next(a for a in conferente.conferir("Casas livres para a virada", "casa_veraneio", "roteiro")
                 if "disponibilidade" in a)
    assert "ainda dá tempo" not in aviso


# --- estrategista-38: CRECI da Casa Vero (só aviso) -----------------------------------------------------------------

def test_creci_falta_na_legenda_da_vero(monkeypatch):
    monkeypatch.setenv("CRECI_VERO", "000-000-J")  # número fictício: o real vem do ambiente ou do manual 12
    avisos = conferente.conferir("Vero 12 em Atibaia / SP. Fale com um especialista agora!", "casa_vero", "legenda")
    assert any("falta o CRECI (000-000-J)" in a for a in avisos)
    com = conferente.conferir("Vero 12. CRECI 000-000-J. Fale com um especialista agora!", "casa_vero", "legenda")
    assert not any("CRECI" in a for a in com)
    assert not any("CRECI" in a for a in conferente.conferir("Lodge 3", "casa_veraneio", "legenda"))
    assert not any("CRECI" in a for a in conferente.conferir("Vero 12", "casa_vero", "legenda", tipo="STORIES"))


# --- social_media-18: direção visual no roteiro ---------------------------------------------------------------------

def _peca(empresa, link="https://drive.google.com/drive/folders/abcdefghij12", gostei=True):
    tarefa = tarefas.criar(USUARIO, "marketing", "criador_imagens", "Carrossel", "media", empresa=empresa)
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo, link) VALUES (?, ?, ?)", (tarefa, "Carrossel X", link))
    if gostei:
        import avaliacoes

        with avaliacoes._db() as db:
            db.execute("INSERT INTO avaliacoes (tarefa_id, usuario, valor, em) VALUES (?, ?, 1, '2026-11-01')",
                       (tarefa, USUARIO))
    return tarefa


ROTEIRO = "Capa: Vero 12 com a vista da serra. Página 2: sala. Página 3: suíte. Página 4: ficha e CTA.\n"


def test_direcao_visual_confere_a_referencia():
    da_vero, da_veraneio = _peca("casa_vero"), _peca("casa_veraneio")
    sem_drive = _peca("casa_vero", link=None)
    assert any("sem o bloco" in a for a in direcao_visual.conferir(ROTEIRO * 2, "casa_vero"))

    def com(ref):
        return direcao_visual.conferir(f"{ROTEIRO}DIREÇÃO VISUAL\nReferência: {ref}\nFormato: F1\nEvitar: caixa preta",
                                       "casa_vero")

    assert com(f"peça #{da_vero}") == []
    assert com("sem referência aprovada") == []
    assert "Casa Veraneio" in com(f"peça #{da_veraneio}")[0]
    assert "não tem pasta FINAL" in com(f"peça #{sem_drive}")[0]
    assert "outra empresa" in com("pasta VERANEIO | 2026-11 | Carrossel")[0]
    bloco = direcao_visual.bloco("social_media", "casa_vero", "roteiro do carrossel")
    assert f"peça #{da_vero}" in bloco and f"#{da_veraneio}" not in bloco and f"#{sem_drive}" not in bloco
    assert direcao_visual.bloco("copywriter", "casa_vero", "roteiro") == ""


# --- analista_tendencias-32: rápida ou completa ---------------------------------------------------------------------

def test_estudo_pergunta_antes_e_a_rapida_oferece_aprofundar():
    pedido = "Quais as tendências do mercado para o verão?"
    assert estudos.precisa_escolher("analista_tendencias", pedido)
    opcoes = estudos.opcoes_de_escolha(pedido)["opcoes"]
    assert [o["rotulo"] for o in opcoes] == ["Resposta rápida agora", "Estudo completo"]
    rapida, completo = (o["texto"] for o in opcoes)
    assert not estudos.e_estudo("analista_tendencias", rapida)  # vai ao agente, sem web
    assert estudos.e_estudo("analista_tendencias", completo) and not estudos.precisa_escolher(
        "analista_tendencias", completo)
    assert not estudos.precisa_escolher("estrategista", "Matriz BCG das empresas")  # só o Analista por enquanto
    final = conferente.anotar("Datas e ganchos.", "analista_tendencias", "casa_veraneio", rapida)
    assert f"Estudo completo: {pedido}" in final
