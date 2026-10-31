"""Conferente automático, só avisando (Onda 2, item 2; 31/10/2026): regras duras por empresa na legenda, no
roteiro do item do Monday e na resposta final; lista fixa de conferência das artes no prompt do Max.
Banco temporário (tests/conftest.py); o Monday é simulado, nada sai daqui.
"""

import sys
from pathlib import Path

import pytest

import conferente
import tarefas
from agents import ferramentas_monday

tarefas.iniciar()

LEGENDA_OK = ("A Praia do Patacho tem selo Bandeira Azul. Nossa casa fica à beira dela.\n\n"
              "Lodge 189 · São Miguel dos Milagres / AL\n6 suítes · até 18 pessoas\n"
              "Réveillon: diária R$ 27.500, mínimo de 7 noites\n\n"
              "Casa Veraneio. A casa inteira é de vocês. O resto, a gente cuida.\n"
              "Reserve a data do seu grupo pelo link da bio.\n\n#casaveraneio #reveillon2027 #alagoas")


def _tem(avisos, trecho):
    return any(trecho.lower() in a.lower() for a in avisos)


def test_legenda_no_padrao_nao_gera_aviso():
    assert conferente.conferir(LEGENDA_OK, "casa_veraneio", "legenda") == []


@pytest.mark.parametrize("texto, trecho", [
    ("Chama no WhatsApp e reserve", "WhatsApp"),
    ("Ligue (11) 98765-4321", "telefone"),
    ("Lodge 34 · Maresias, SP", "Cidade / UF"),
    ("Lodge 34 · Maresias/SP", "Cidade / UF"),
    ("Lodge 34 em Maresias (SP)", "Cidade / UF"),
    ("A Vera preparou tudo", "nome interno"),
    ("Ainda temos casas livres para a virada", "disponibilidade"),
])
def test_regras_comuns(texto, trecho):
    assert _tem(conferente.conferir(texto, "casa_veraneio", "roteiro"), trecho)


def test_mencao_negada_e_uf_solta_nao_avisam():
    texto = "CTA pelo direct, nunca WhatsApp. Casas no litoral de SP, RJ e BA. Lodge 03 · Igaratá / SP"
    assert conferente.conferir(texto, "casa_veraneio", "resposta") == []


def test_formato_da_legenda():
    texto = ("Um refúgio — perfeito; para o grupo 😍🌊 #casaveraneio #a #b #c #d #e #maresiasé\n"
             "Casa Veraneio. A casa inteira é de vocês. O resto, a gente cuida. Link da bio.")
    avisos = conferente.conferir(texto, "casa_veraneio", "legenda")
    for trecho in ("travessão", "ponto e vírgula", "2 emojis", "7 hashtags", "acento"):
        assert _tem(avisos, trecho), (trecho, avisos)


def test_falta_hashtag_assinatura_e_cta():
    avisos = conferente.conferir("Uma casa à beira-mar para o grupo. Manda mensagem! #maresias", "casa_veraneio")
    assert _tem(avisos, "#casaveraneio") and _tem(avisos, "assinatura") and _tem(avisos, "CTA")


def test_palavras_vetadas_e_a_dosar():
    avisos = conferente.conferir("Pousada para casal, exclusivo e mais exclusivo", "casa_veraneio", "roteiro")
    assert _tem(avisos, "palavra vetada") and _tem(avisos, "2 vezes")


def test_valor_na_arte_so_com_pedido():
    roteiro = "Capa: Lodge 34 · Maresias / SP, diária R$ 14.500"
    assert _tem(conferente.conferir(roteiro, "casa_veraneio", "roteiro", "post do Lodge 34"), "sem valores")
    assert not _tem(conferente.conferir(roteiro, "casa_veraneio", "roteiro", "post com o valor da diária"), "valor")
    # Na legenda da Casa Veraneio a ficha leva a diária (manual 07 §4).
    assert not _tem(conferente.conferir(LEGENDA_OK, "casa_veraneio", "legenda", "post"), "valor")


def test_casa_vero_valor_lodge_e_marca():
    texto = "O Lodge 87 no Haras Larissa, por R$ 4.500.000. #casaveraneio Fale com um especialista agora!"
    avisos = conferente.conferir(texto, "casa_vero", "legenda", "post do Vero 87")
    assert _tem(avisos, "autorização") and _tem(avisos, "outra empresa") and _tem(avisos, "hashtag de outra")
    autorizado = conferente.conferir("Vero 87 por R$ 4.500.000", "casa_vero", "roteiro", "mostre o valor de venda")
    assert not _tem(autorizado, "valor")


def test_corporativo_sem_hospedagem_e_sem_a_outra_marca():
    texto = "Off-site no Lodge 31 da Casa Veraneio com diária especial e aluguel de espaço"
    avisos = conferente.conferir(texto, "cv_corporativo", "roteiro", "post de off-site")
    assert _tem(avisos, "hospedagem") and _tem(avisos, "outra empresa") and _tem(avisos, "vetada")
    ok = "Casa Veraneio Corporativo. Do orçamento ao último convidado, a gente produz. Converse com nossos especialistas."
    assert conferente.conferir(ok, "cv_corporativo", "legenda") == []


def test_casa_veraneio_nao_cita_as_outras():
    assert _tem(conferente.conferir("Conheça também a Casa Vero", "casa_veraneio", "roteiro"), "outra empresa")
    # Pedido do grupo (as três empresas): sem aviso de marca.
    assert not _tem(conferente.conferir("Casa Vero e Casa Veraneio", "casa_veraneio", "resposta",
                                        "post das 3 empresas"), "outra empresa")


def test_contagem_regressiva_do_reveillon():
    avisos = conferente.conferir("Faltam 30 noites para o Réveillon", "casa_veraneio", "roteiro",
                                 data_postagem="2026-12-02")
    assert _tem(avisos, "são 29")
    assert not conferente.conferir("Faltam 29 noites para o Réveillon", "casa_veraneio", "roteiro",
                                   data_postagem="2026-12-02")


def test_stories_com_legenda():
    assert _tem(conferente.conferir("Legenda qualquer", "casa_veraneio", "legenda", tipo="STORIES"), "STORIES")


def test_anotar_resposta_e_itens_do_monday():
    conferente.registrar(9001, "POST | Lodge 34", ["WhatsApp citado"])
    texto = conferente.anotar("Legenda: chama no WhatsApp", "copywriter", "casa_veraneio", "legenda", 9001)
    assert "Conferência automática" in texto and "POST | Lodge 34: WhatsApp citado" in texto
    assert conferente.anotar("Ok", "gestor", "casa_veraneio", "", 9001) == "Ok"  # já foi mostrado
    # Agente fora da lista (ex.: Analista) não tem a resposta conferida.
    assert conferente.anotar("Chama no WhatsApp", "analista_metricas", "casa_veraneio") == "Chama no WhatsApp"


def test_monday_grava_mesmo_com_aviso(monkeypatch):
    """Só avisa: o item é criado, e o aviso volta à ferramenta e ao rodapé da resposta."""
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "social_media", "post do Lodge 34",
                              "media", empresa="casa_veraneio")
    criados = []
    monkeypatch.setattr(ferramentas_monday.monday, "grupo_por_nome", lambda nome, criar=False: {"id": "g", "title": nome})
    monkeypatch.setattr(ferramentas_monday.monday, "criar_item",
                        lambda grupo, nome, valores: criados.append(valores) or {"id": "1", "name": nome, "url": "u"})
    monkeypatch.setattr(ferramentas_monday.monday_datas, "reposicionar_seguro", lambda item_id: None)
    monkeypatch.setattr(ferramentas_monday, "_descrever_roteiro", lambda item_id, roteiro: None)
    resultado = ferramentas_monday._criar(ferramentas_monday._Contador(), tarefa_id, "POST | Lodge 34",
                                          legenda="Chama no WhatsApp", roteiro="Maresias, SP")
    assert resultado.startswith("Criado") and criados
    assert "CONFERÊNCIA" in resultado and "WhatsApp" in resultado and "Cidade / UF" in resultado
    assert "Conferência dos itens gravados no Monday" in conferente.anotar("Pronto.", "social_media",
                                                                           "casa_veraneio", "", tarefa_id)


def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "conferencia_arte.py").exists():
            return pasta
    return None


@pytest.mark.skipif(_pasta_max() is None, reason="scripts/max não encontrado (monte em /repo/scripts)")
def test_lista_do_max_por_empresa():
    if str(_pasta_max()) not in sys.path:
        sys.path.insert(0, str(_pasta_max()))
    import conferencia_arte

    vero = conferencia_arte.instrucao("casa_vero")
    assert "CONFERÊNCIA FINAL" in vero and "Lodge" in vero and "Cidade / UF" in vero and "sem rodada extra" in vero
    assert "Corporativo" in conferencia_arte.instrucao("casa_veraneio")
    assert conferencia_arte.instrucao("casa_veraneio", "texto") == ""
