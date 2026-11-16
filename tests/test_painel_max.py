"""Rota do Max do Gestor de Tráfego (tarefa 297, 16/11/2026): o sistema consulta os anúncios no painel antes e manda
os números junto com o pedido, porque o Claude Code do PC não tem as ferramentas do painel."""

from agents import ferramentas_painel as fp

RESUMO = ("Google Ads por campanha, últimos 30 dias (dados de 2023-10-15 até 2026-11-13):\n"
          "- [AM] [S] Feriados e Férias (SEARCH, ativa, orçamento R$ 80.00/dia, lance —): R$ 2,295.46\n"
          "- [AM] [S] Ano Novo (SEARCH, ativa, lance —): R$ 1,406.46\n"
          "- [AM] [S] Casa Veraneio - Termo genérico (SEARCH, ativa, lance —): R$ 1,297.37\n")


def test_campanha_citada_em_qualquer_ordem_e_sem_acento():
    assert fp.campanhas_citadas("Análise da campanha Ferias e Feriados do Google Ads", RESUMO) == [
        "[AM] [S] Feriados e Férias"]
    assert fp.campanhas_citadas("como vai o ano novo?", RESUMO) == ["[AM] [S] Ano Novo"]
    assert fp.campanhas_citadas("como estão os anúncios?", RESUMO) == []


def test_numeros_so_para_o_gestor_da_diretoria(monkeypatch):
    monkeypatch.setattr(fp, "disponivel", lambda: True)
    assert fp.dados_para_max("gestor_trafego", 0, "Férias e Feriados", financeiro=False) == ""
    assert fp.dados_para_max("social_media", 0, "Férias e Feriados", financeiro=True) == ""


def test_consulta_campanha_citada_e_periodo_do_pedido(monkeypatch):
    feitas = []

    def consultar(nome, argumentos, tarefa_id, agente_id, limite=fp.MAX_SAIDA):
        feitas.append((nome, argumentos))
        return RESUMO if nome == "analisar_google_ads" and not argumentos.get("campanha") else f"[{nome}]"

    monkeypatch.setattr(fp, "disponivel", lambda: True)
    monkeypatch.setattr(fp, "_consultar", consultar)
    texto = fp.dados_para_max("gestor_trafego", 0, "Férias e Feriados nos últimos 60 dias", financeiro=True)
    assert ("analisar_google_ads", {"dias": 60, "campanha": "[AM] [S] Feriados e Férias"}) in feitas
    assert {n for n, _ in feitas} == {"analisar_trafego_pago", "analisar_google_ads", "analisar_impulsionamentos",
                                      "analisar_crm"}
    assert "últimos 60 dias" in texto and "[analisar_crm]" in texto


def test_id_do_anuncio_no_pedido():  # tarefa 298: anúncio citado pelo ID que o Google Ads mostra
    pedido = "conjunto Feriados\nAnúncio responsivo 200890088544~804132974582 e o ID 804018350145, tel 48999998888"
    assert fp.ids_citados(pedido) == ["200890088544~804132974582", "804018350145"]
    assert fp.ids_citados("como vai a campanha de Ano Novo nos últimos 30 dias?") == []


def test_consulta_pelo_id_sem_repetir_a_campanha(monkeypatch):
    feitas = []

    def consultar(nome, argumentos, tarefa_id, agente_id, limite=fp.MAX_SAIDA):
        feitas.append((nome, argumentos))
        if nome == "analisar_google_ads" and not argumentos.get("campanha"):
            return RESUMO
        if nome == "analisar_google_ads":
            return "ANÚNCIO PEDIDO: ...\n\nGoogle Ads · [AM] [S] Feriados e Férias (SEARCH, ativa) ..."
        return f"[{nome}]"

    monkeypatch.setattr(fp, "disponivel", lambda: True)
    monkeypatch.setattr(fp, "_consultar", consultar)
    fp.dados_para_max("gestor_trafego", 0, "Feriados e Férias, anúncio 200890088544~804132974582", financeiro=True)
    google = [a["campanha"] for n, a in feitas if n == "analisar_google_ads"]
    assert google == ["", "200890088544~804132974582"]


def test_id_do_meta_no_pedido():  # anúncio do Meta pelo ID do Gerenciador (15 a 18 dígitos)
    pedido = "Analise o anúncio 120251443202050431 (id 120251443202050431) e o 200890088544~804132974582; tel 11999998888"
    assert fp.ids_meta_citados(pedido) == ["120251443202050431"]
    assert fp.ids_citados(pedido) == ["200890088544~804132974582"]


def test_consulta_o_anuncio_do_meta(monkeypatch):
    feitas = []
    monkeypatch.setattr(fp, "disponivel", lambda: True)
    monkeypatch.setattr(fp, "_consultar", lambda nome, argumentos, *_a, **_k: feitas.append((nome, argumentos)) or "")
    fp.dados_para_max("gestor_trafego", 0, "anúncio 120251443202050431 nos últimos 14 dias", financeiro=True)
    assert ("analisar_anuncio_meta", {"ad_id": "120251443202050431", "dias": 14}) in feitas
    assert "analisar_anuncio_meta" in fp.FINANCEIRAS
