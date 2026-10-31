"""Onda 2, grupo J: catálogo de imóveis em tabela (cerebro-01), conferência dos dados do imóvel antes do Max
(despachante-05, criador_imagens-06, cerebro-09, social_media-03), selo de estudo com validade (estrategista-27) e
perguntas da semana (cerebro-02). Banco temporário (tests/conftest.py); dados fictícios.
"""

import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import cerebro
import cerebro_base as base
import cerebro_conferir as conferir
import cerebro_imoveis as imoveis
import cerebro_lacunas as lacunas
import config
import correcoes
import tarefas
from cerebro_texto import dividir

tarefas.iniciar()


def _documento(ref: str, conteudo: str, empresa: str = "casa_veraneio", fonte: str = "site") -> None:
    titulo = conteudo.splitlines()[0].lstrip("# ")
    for t, c in dividir(titulo, conteudo):
        base._inserir(fonte, ref, t, c, empresa)


def _lodges_de_teste() -> None:
    if base.db().execute("SELECT 1 FROM conhecimento WHERE fonte_ref = 'site/lodges/lodge-701'").fetchone():
        return
    _documento("site/lodges/lodge-701", "# Lodge 701 — Cidade Teste Um - SP\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-701 (dados oficiais do site, atualizados em 2026-10-20)\nResumo: 5 quartos | 4 banheiros | até 12 "
               "pessoas | categoria: Campo\nBairro: Bairro Fictício\n\n## Acomodações\nSuíte 1 = 1 cama king\nSuíte 2 = 1 "
               "cama queen\nSuíte 3 = 2 camas de solteiro\n\n## Valores por época\n- Baixa temporada: diária R$ 3.000"
               "\n\n## Comodidades\nPiscina, Churrasqueira, Wi-Fi")
    _documento("site/lodges/lodge-702", "# Lodge 702 — Cidade Teste Um - SP\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-702 (dados oficiais do site)\nResumo: 8 quartos | até 16 pessoas | categoria: Praia\n\n## Acomodações"
               "\n7 suítes com ar-condicionado.\n\n## Comodidades\nSauna, Lareira")
    _documento("site/lodges/lodge-703", "# Lodge 703 — Vila Teste Dois - RJ\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-703\nResumo: 3 quartos | até 8 pessoas | categoria: Praia")
    _documento("drive/planilha/info-lodges/lodge-704", "# Lodge 704 — planilha Info Lodges\nFonte: planilha interna\n"
               "Endereço: Rua Fictícia, 100, Vila Teste Dois - RJ, 00000-000\nCasa com 4 suítes para até 10 hóspedes.",
               fonte="drive")
    _documento("site/resumo-lodges", "# Resumo dos lodges no site\n\nLodges: 257\n\n| Lodge | Local |")


# --- cerebro-01: catálogo em tabela -----------------------------------------------------------------

def test_tabela_sai_dos_documentos_do_site_sem_preco():
    _lodges_de_teste()
    imoveis.atualizar("casa_veraneio", forcar=True)
    l701 = imoveis.linha(701)
    assert (l701["cidade"], l701["uf"], l701["quartos"], l701["suites"], l701["pessoas"]) == (
        "Cidade Teste Um", "SP", 5, 3, 12)
    assert l701["bairro"] == "Bairro Fictício" and "Piscina" in l701["comodidades"] and l701["fonte"] == "site"
    assert imoveis.linha(702)["suites"] == 7
    fora = imoveis.linha(704)
    assert fora["fonte"] == "planilha" and fora["cidade"] == "Vila Teste Dois" and fora["pessoas"] == 10
    colunas = {c[1] for c in base.db().execute("PRAGMA table_info(imoveis)")}
    assert not {c for c in colunas if "preco" in c or "diaria" in c or "valor" in c}


def test_filtros_e_total_conferido():
    _lodges_de_teste()
    r = imoveis.filtrar(cidade="Cidade Teste Um", pessoas_min=14)
    assert [l["numero"] for l in r["linhas"]] == [702] and r["total_no_site"] == 257
    assert [l["numero"] for l in imoveis.filtrar(uf="RJ", categoria="praia")["linhas"] if l["numero"] > 700] == [703]
    assert imoveis.filtrar("cv_corporativo") is None  # Corp e Vero: tabela fica para depois


def test_pedido_de_lista_responde_pela_tabela():
    _lodges_de_teste()
    resposta = imoveis.responder("Liste todos os Lodges em Cidade Teste Um para 12 ou mais pessoas")
    assert "**2 Lodges da Casa Veraneio**" in resposta and "| 701 |" in resposta and "| 702 |" in resposta
    assert "coleta de" in resposta and "Sem preços" in resposta and "R$" not in resposta
    assert imoveis.responder("Quantas suítes tem o Lodge 701?") is None  # um imóvel: é da ficha
    assert imoveis.responder("Escreva uma legenda para o Lodge de praia") is None
    agrupado = imoveis.responder("Quantos Lodges tenho por cidade?")
    assert "| Cidade Teste Um / SP | 2 |" in agrupado
    tool = cerebro.consultar("Quais são os lodges em Vila Teste Dois?", "social_media")
    assert tool.startswith("Tabela de imóveis do Cérebro") and "fora do site" in tool


# --- Item 5: conferência dos dados do imóvel antes do Max ---------------------------------------------

def test_plano_que_diverge_da_ficha_pergunta_antes_do_max():
    _lodges_de_teste()
    plano = "Carrossel do Lodge 701 — Orlândia Fictícia / MG, com 8 suítes para 20 pessoas."
    achados = conferir.divergencias(plano, "casa_veraneio", "o plano")
    assert any("8 suítes" in a and "diz 3" in a for a in achados)
    assert any("20 pessoas" in a and "até 12" in a for a in achados)
    assert any("Orlândia Fictícia / MG" in a and "Cidade Teste Um / SP" in a for a in achados)
    assert conferir.divergencias("Lodge 701 para 10 pessoas, 3 suítes, Cidade Teste Um / SP", "casa_veraneio") == []
    trocado = conferir.pergunta_do_plano("Post do Lodge 702", "Plano: post do Lodge 701.", "casa_veraneio")
    assert "O plano fala do Lodge 701, mas o pedido cita o Lodge 702" in trocado
    assert conferir.pergunta_do_plano("Post do Lodge 702", "Plano: Lodge 702 com 7 suítes.", "casa_veraneio") is None
    assert "não está na ficha" in " ".join(conferir.divergencias("Post do Lodge 799", "casa_veraneio"))


def test_pedido_direto_tem_seguir_mesmo_assim():
    _lodges_de_teste()
    aviso = conferir.aviso_do_pedido("Arte do Lodge 701 com 9 suítes", "casa_veraneio")
    assert [o["rotulo"] for o in aviso["opcoes"]] == ["Usar a ficha", "Seguir mesmo assim"]
    reenviado = aviso["opcoes"][1]["texto"]
    assert conferir.aviso_do_pedido(reenviado, "casa_veraneio") is None  # a pessoa já decidiu
    assert "CONFERÊNCIA DE DADOS" in conferir.nota_no_briefing("Arte do Lodge 701 com 9 suítes", "casa_veraneio")


def test_formulario_da_vero_sem_campos_de_valor_e_com_dado_suspeito():
    _documento("vero/imoveis/vero-7701", "# Vero 7701 — Cidade Teste Um - SP\nÁrea construída: 2,6 m²\n4 suítes.",
               empresa="casa_vero")
    formulario = {"titulo": "Post", "campos": [
        {"nome": "valor_venda", "rotulo": "Valor de venda", "tipo": "texto"},
        {"nome": "condominio", "rotulo": "Condomínio e IPTU", "tipo": "texto"},
        {"nome": "destaque", "rotulo": "Qual o destaque do imóvel?", "tipo": "texto"}]}
    resposta = f"Preciso de dois dados.\n<<FORMULARIO>>{json.dumps(formulario)}<<FIM DO FORMULARIO>>"
    limpo = conferir.formulario_seguro(resposta, "casa_vero", "Post do Vero 7701")
    campos = json.loads(limpo.split("<<FORMULARIO>>")[1].split("<<FIM DO FORMULARIO>>")[0])["campos"]
    assert [c["nome"] for c in campos] == ["destaque"]
    assert "Tirei do formulário os campos de valor" in limpo and "área de 2,6 m²" in limpo
    assert conferir.formulario_seguro(resposta, "casa_veraneio", "x") == resposta
    com_valor = conferir.formulario_seguro(resposta, "casa_vero", "Post do Vero 7701 com o valor de venda")
    assert "valor_venda" in com_valor  # o usuário pediu valor (decisão 3)


# --- estrategista-27: selo de estudo com validade ------------------------------------------------------

def test_estudo_entra_com_selo_peso_menor_e_validade():
    tarefa = tarefas.criar(config.DONO_MAX, "comercial", "estrategista", "Matriz BCG fictícia das empresas", "complexa")
    tarefas.atualizar(tarefa, status="concluida", resposta="Estimativa: a empresa teste seria Interrogação na BCG.")
    trecho = cerebro.aprender_tarefa(tarefa)
    linha = base.db().execute("SELECT * FROM conhecimento WHERE id = ?", (trecho,)).fetchone()
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
    assert linha["fonte_tipo"] == "estudo" and linha["peso_fonte"] < base.PESOS_FONTE["tarefa"]
    assert linha["titulo"].startswith(f"ESTUDO de {hoje}") and "não usar como fato em peça pública" in linha["conteudo"]
    assert "ESTUDO" in cerebro._formatar([{"titulo": "x", "conteudo": "y", "fonte_tipo": "estudo",
                                           "fonte_ref": "tarefa:1", "data": "2026-10-31"}], 500)
    velho = base._inserir("estudo", "tarefa:999991", "ESTUDO antigo zebrafictícia", "zebrafictícia quadrante estrela")
    novo = base._inserir("estudo", "tarefa:999992", "ESTUDO novo zebrafictícia", "zebrafictícia quadrante vaca leiteira")
    with base._trava, base.db() as conexao:
        conexao.execute("UPDATE conhecimento SET atualizado_em = ? WHERE id = ?",
                        (base.agora(-timedelta(days=91)), velho))
    base._mudou()
    base.indice_atual(fresco=True)  # a busca aceita um índice de até 15 s: aqui ele precisa ver os dois estudos
    ids ={t["id"] for t in base.buscar("zebrafictícia quadrante", k=5)}
    assert novo in ids and velho not in ids
    base._indice = None  # os testes seguintes inserem e buscam em menos de 15 s: não herdam este índice


# --- cerebro-02: perguntas da semana ------------------------------------------------------------------

def test_lacunas_se_juntam_e_viram_perguntas_da_semana(monkeypatch):
    primeira = lacunas.registrar("Quais Lodges aceitam animais de estimação?", "casa_veraneio", "social_media")
    assert lacunas.registrar("Quais Lodges aceitam animais de estimação", "casa_veraneio", "copywriter") == primeira
    assert lacunas.registrar("Qual o faturamento de outubro?", "casa_veraneio", "estrategista") is None
    fora = lacunas.registrar("Qual a disponibilidade em dezembro de 2027 do Lodge 5?", "casa_veraneio", "gestor")
    assert base.db().execute("SELECT status FROM lacunas WHERE id = ?", (fora,)).fetchone()[0] == "fora_do_alcance"
    tarefa = tarefas.criar("usuario.teste@exemplo.com", "marketing", "email_marketing", "Newsletter", "simples")
    tarefas.atualizar(tarefa, status="concluida",
                      resposta="Texto pronto.\n- Imóveis em destaque de janeiro de 2027: PENDENTE (lista não enviada)")
    assert lacunas.da_resposta(tarefas.obter(tarefa)) == 1

    r = lacunas.perguntas_da_semana(forcar=True)
    assert r["ok"] and r["itens"] >= 1
    obs = correcoes._db().execute("SELECT * FROM observacoes WHERE tipo = 'pergunta' AND correcao LIKE "
                                  "'%animais de estima%' ORDER BY id DESC").fetchone()
    assert "não soube 2 vezes" in obs["correcao"] and "Casa Veraneio" in obs["correcao"]
    assert not correcoes._db().execute("SELECT 1 FROM observacoes WHERE tipo = 'pergunta' AND correcao LIKE "
                                       "'%disponibilidade%'").fetchone()
    assert lacunas.perguntas_da_semana()["ok"] is False  # uma vez por semana

    ensinados = []

    async def ensinar(login, texto, empresa="*"):
        ensinados.append((login, texto, empresa))
        return "ok"

    monkeypatch.setattr(cerebro, "ensinar", ensinar)
    monkeypatch.setattr(correcoes, "_dono", lambda _a: {"sub": "usuario.teste@exemplo.com", "role": "diretoria"})
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):  # só o Thomas ensina fatos (decisão 16)
        asyncio.run(lacunas.responder(obs["id"], lacunas.Resposta(resposta="Os Lodges 1 e 2 aceitam pet."), ""))
    monkeypatch.setattr(correcoes, "_dono", lambda _a: {"sub": config.DONO_MAX, "role": "diretoria"})
    asyncio.run(lacunas.responder(obs["id"], lacunas.Resposta(resposta="Os Lodges 1 e 2 aceitam pet."), ""))
    assert ensinados and ensinados[0][2] == "casa_veraneio" and "aceitam pet" in ensinados[0][1]
    assert correcoes._db().execute("SELECT status FROM observacoes WHERE id = ?", (obs["id"],)).fetchone()[0] == "aprovada"


def test_perguntas_da_semana_agendadas_de_dia():
    class Agendador:
        timezone = ZoneInfo("America/Sao_Paulo")
        jobs: list = []

        def add_job(self, funcao, gatilho, **kw):
            self.jobs.append((kw["id"], str(gatilho)))

    agendador = Agendador()
    lacunas.agendar(agendador)
    gatilho = dict(agendador.jobs)["perguntas_da_semana"]
    assert "day_of_week='mon'" in gatilho and "hour='10'" in gatilho
