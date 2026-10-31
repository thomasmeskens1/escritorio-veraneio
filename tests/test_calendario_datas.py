"""Datas calculadas para quem planeja (Onda 2, item 4): contagem pela data da POSTAGEM, feriados móveis, regionais
das cidades de origem e datas próprias por empresa, sem misturar. Datas fixas: nada depende de hoje.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_calendario_datas.py
"""

import json
from datetime import date

import calendario
from agents import perfis

HOJE = date(2026, 10, 31)


def test_contagem_parte_da_postagem_e_nao_de_hoje():
    # Manual 07 §5: 01/10 → 91 noites, 15/10 → 77, 29/10 → 63; gestor.md: postagem de 16/11 → 45.
    reveillon = date(2026, 12, 31)
    assert [calendario.faltam(reveillon, date(2026, 10, d)) for d in (1, 15, 29)] == [91, 77, 63]
    assert calendario.faltam(calendario.data_do_alvo("Réveillon", date(2026, 11, 16)), date(2026, 11, 16)) == 45
    texto = calendario.bloco("copywriter", "casa_veraneio", "Item do Monday: REELS | Réveillon\n"
                             "- Data de postagem: 2026-11-16", hoje=HOJE)
    assert "DATA DA POSTAGEM deste trabalho: 16/11/2026" in texto
    assert "Réveillon (31/12/2026): faltam 45 noites" in texto
    assert "faltam 61 noites" not in texto  # 61 seria a conta pela data de hoje


def test_feriados_moveis_calculados_pela_pascoa():
    feriados = {e["nome"]: e for e in calendario.nacionais(2027)}
    assert feriados["Carnaval"]["data"] == date(2027, 2, 6) and feriados["Carnaval"]["fim"] == date(2027, 2, 10)
    assert feriados["Sexta-feira Santa"]["data"] == date(2027, 3, 26)
    assert feriados["Corpus Christi"]["data"] == date(2027, 5, 27)
    assert calendario.data_do_alvo("Carnaval", date(2026, 11, 16)) == date(2027, 2, 6)
    assert calendario.data_do_alvo("Carnaval", date(2027, 2, 7)) == date(2028, 2, 26)  # já passou: o do ano seguinte


def test_data_da_postagem_no_briefing_e_no_chat():
    assert calendario.data_postagem("- Data de postagem: 2026-11-16", HOJE) == date(2026, 11, 16)
    assert calendario.data_postagem("o reels com postagem em 20/11", HOJE) == date(2026, 11, 20)
    assert calendario.data_postagem("postagem em 05/01", HOJE) == date(2027, 1, 5)  # o próximo 05/01
    assert calendario.data_postagem("Data Postagem: 02/12/2026", HOJE) == date(2026, 12, 2)
    assert calendario.data_postagem("monte um carrossel do Lodge 239", HOJE) is None


def test_sem_postagem_a_contagem_fica_pendente_e_tabela_do_mes():
    texto = calendario.bloco("social_media", "casa_veraneio", "Planeje dezembro da Casa Veraneio", hoje=HOJE)
    assert "PENDENTE" in texto and "não use a data de hoje" in texto
    assert "01/12=30" in texto and "31/12=0" in texto  # tabela por dia do mês planejado
    assert "Carnaval (06/02/2027)" in texto and "01/12=67" in texto


def test_cada_empresa_so_com_as_suas_datas():
    veraneio = calendario.bloco("gestor", "casa_veraneio", "planejamento do mês", hoje=HOJE)
    corp = calendario.bloco("gestor", "cv_corporativo", "planejamento do mês", hoje=HOJE)
    vero = calendario.bloco("gestor", "casa_vero", "planejamento do mês", hoje=HOJE)
    assert "Férias de verão" in veraneio and "Confraternizações" not in veraneio and "13º" not in veraneio
    assert "Confraternizações de fim de ano" in corp and "Kick-off do ano" in corp
    assert "Férias de verão" not in corp and "Réveillon (" not in corp and "13º" not in corp
    assert "13º salário e bônus" in vero and "Confraternizações" not in vero and "Férias de verão" not in vero
    assert "a confirmar com a equipe" in corp and "a confirmar com a equipe" in vero
    # Os feriados nacionais valem para as três, com feriadão: 20/11/2026 é sexta.
    for texto in (veraneio, corp, vero):
        assert "20/11/2026 (sexta) · Consciência Negra (feriadão de 3 dias (sex a dom); feriado nacional" in texto


def test_feriados_da_cidade_de_origem_padrao_sp():
    texto = calendario.bloco("analista_tendencias", "casa_veraneio", "", hoje=HOJE)
    assert "25/01/2027 (segunda) · Aniversário de São Paulo (feriadão de 3 dias (sáb a seg); feriado municipal " \
           "(São Paulo / SP)" in texto
    assert "segmentado por região" in texto and "São Paulo / SP" in texto
    julho = calendario.eventos("casa_veraneio", date(2027, 7, 1), date(2027, 7, 31))
    assert any(e["nome"] == "Revolução Constitucionalista" and e["tipo"] == "feriado estadual (SP)" for e in julho)


def test_lista_configuravel_por_empresa(tmp_path, monkeypatch):
    arquivo = tmp_path / "calendario.json"
    arquivo.write_text(json.dumps({
        "cidades_origem": {"casa_veraneio": ["Salvador / BA"]},
        "feriados_regionais": {"Salvador / BA": [{"mes": 6, "dia": 24, "nome": "São João"}]},
        "datas_proprias": {"casa_vero": [{"nome": "Feira de imóveis", "mes": 6, "dia": 20, "obs": "teste"}]},
    }), encoding="utf-8")
    monkeypatch.setattr(calendario, "ARQUIVO", arquivo)
    junho = {e["nome"]: e for e in calendario.eventos("casa_veraneio", date(2027, 6, 1), date(2027, 7, 10))}
    assert junho["Independência da Bahia"]["tipo"] == "feriado estadual (BA)"
    assert junho["São João"]["tipo"] == "feriado municipal (Salvador / BA)"
    assert "Revolução Constitucionalista" not in junho  # SP saiu da lista da Casa Veraneio
    vero = {e["nome"] for e in calendario.eventos("casa_vero", date(2027, 6, 1), date(2027, 9, 30))}
    assert "Feira de imóveis" in vero and "Dia do Corretor" not in vero  # a lista configurada substitui a padrão
    assert "Revolução Constitucionalista" in vero  # a Vero continua com SP


def test_so_quem_planeja_e_so_quando_o_pedido_fala_de_data():
    assert calendario.bloco("designer", "casa_veraneio", "planeje dezembro", hoje=HOJE) == ""
    assert calendario.bloco("gestor", "*", "planeje dezembro", hoje=HOJE) == ""  # sem empresa: nada misturado
    assert calendario.bloco("copywriter", "casa_veraneio", "Melhore este texto, por favor", hoje=HOJE) == ""
    assert calendario.bloco("gestor_trafego", "casa_veraneio", "campanha do Carnaval", hoje=HOJE).count(
        "Calendário de verba") == 1


def test_bloco_entra_no_contexto_de_quem_planeja():
    pedido = "Planeje a campanha do Réveillon"
    assert "DATAS CALCULADAS PELO SISTEMA" in perfis.contexto("social_media", [], pedido, "casa_veraneio")
    assert "DATAS CALCULADAS PELO SISTEMA" not in perfis.contexto("designer", [], pedido, "casa_veraneio")
