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
