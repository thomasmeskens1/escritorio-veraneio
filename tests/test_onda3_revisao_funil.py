"""Onda 3 (R): revisão de proposta (N2-estrategista-19) e mutirão do funil parado (N2-estrategista-20).
Só dados fictícios (empresas inventadas); Monday falso, sem Max, sem web.
"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

import agenda_clientes
import carteira
import comercial
import estudos
import funil_parado as f
import revisao_proposta as r
import tarefas

tarefas.iniciar()

HOJE = date(2026, 11, 12)
BASE = {"contas": [{"nome": "AURELIX SISTEMAS LTDA", "industry": "Tecnologia", "text_mkxj2284": "Campinas"}],
        "ganhos": []}
PROPOSTA = ("Revisar proposta antes de enviar: Proposta para a AURELIX SISTEMAS, confraternização de 120 pessoas, "
            "investimento de R$ 48.500,00, validade até 05/11/2026. O mercado de eventos cresce.")


@pytest.fixture
def carteira_falsa(monkeypatch):
    monkeypatch.setattr(comercial, "clientes", lambda: BASE)
    monkeypatch.setattr(carteira, "_nomes", None)
    monkeypatch.setattr(estudos, "_painel", lambda financeiro=True: "")
    monkeypatch.setattr(estudos, "_cerebro", lambda *a, **k: "")
    monkeypatch.setattr(comercial, "_persona", lambda: "Persona fictícia: RH de empresas médias.")
    monkeypatch.setattr(r, "_manual_corp", lambda: "## 1. O que é\nProdutora 360° de eventos corporativos.")


# --- N2-estrategista-19 ----------------------------------------------------------------------------------------

def test_revisao_e_reconhecida_e_vai_sem_web(carteira_falsa):
    assert r.e_pedido("estrategista", PROPOSTA) and not r.e_pedido("copywriter", PROPOSTA)
    assert not r.e_pedido("estrategista", "Faça a SWOT do Corporativo")
    assert estudos.e_estudo("estrategista", PROPOSTA)
    assert not estudos.e_estudo("estrategista", PROPOSTA, com_anexo=True)  # anexo: caminho normal (lê o arquivo)
    sem_web, motivo = estudos.analise_sem_web("estrategista", PROPOSTA)  # cita "mercado" e ainda assim sem web
    assert sem_web and "revis" in motivo
    assert "revisar a proposta" in estudos.aviso_inicio("estrategista", PROPOSTA)


def test_prompt_da_revisao_sem_nome_e_com_checklist(carteira_falsa):
    texto = estudos.prompt("estrategista", PROPOSTA, "cv_corporativo", web=False)
    assert "AURELIX" not in texto.upper() and carteira.OCULTO in texto
    assert "COMO REVISAR A PROPOSTA" in texto and "MANUAL DO CORPORATIVO" in texto and "Persona fictícia" in texto
    assert "COMO FAZER A ANÁLISE" not in texto and "[SUGESTÃO:" in texto


def test_valores_so_para_quem_ja_pode_ver(monkeypatch):
    resposta = "Investimento de R$ 48.500,00 (ou 48 mil reais) com [SUGESTÃO: incluir a validade]."
    monkeypatch.setattr(r, "ve_valores", lambda login: False)
    limpa = r.sem_valores(resposta, "usuario.teste@exemplo.com")
    assert "48" not in limpa and r.OCULTO_VALOR in limpa and "[SUGESTÃO:" in limpa
    monkeypatch.setattr(r, "ve_valores", lambda login: True)
    assert r.sem_valores(resposta, "usuario.teste@exemplo.com") == resposta


def test_executar_revisao_no_max_sem_web_e_sem_valor(monkeypatch, carteira_falsa):
    import auth

    pedidos = []

    def max_falso(prompt, limite_s, web=True, **_):
        pedidos.append((prompt, limite_s, web))
        return "Nota 7/10.\nPROPOSTA DEVOLVIDA: investimento de R$ 48.500,00 [SUGESTÃO: CTA com data]."

    monkeypatch.setattr(comercial, "pedir_ao_max", max_falso)
    monkeypatch.setattr(auth, "ve_financeiro", lambda login: False)
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "comercial", "estrategista", PROPOSTA, "complexa",
                              "cv_corporativo")
    resposta = estudos.executar(tarefa_id, "estrategista", PROPOSTA, "cv_corporativo", [])
    prompt, limite, web = pedidos[0]
    assert web is False and limite == estudos.LIMITE_ANALISE_S and "AURELIX" not in prompt.upper()
    assert "48.500" not in resposta and "[SUGESTÃO: CTA com data]" in resposta


def test_proposta_anexada_leva_o_checklist_no_contexto():
    assert "COMO REVISAR A PROPOSTA" in r.contexto_anexo("estrategista", "Revise esta proposta antes de enviar")
    assert r.contexto_anexo("estrategista", "Analise este anexo") == ""


# --- N2-estrategista-20 ----------------------------------------------------------------------------------------

COLUNAS = [{"id": "status", "title": "Etapa", "type": "status"},
           {"id": "date_ult", "title": "Último contato", "type": "date"},
           {"id": "num_tent", "title": "Tentativas", "type": "numbers"},
           {"id": "date_mkp5eds", "title": "Data do Evento", "type": "date"},
           {"id": "n_meros_mkmgpvds", "title": "Pax", "type": "numbers"},
           {"id": "text_dec", "title": "Decisor", "type": "text"},
           {"id": "dropdown_mm3b42sb", "title": "PF/PJ", "type": "dropdown"},
           {"id": "numeric_valor", "title": "Valor", "type": "numbers"}]


def _item(nome, contato, etapa="Aguardando Definição", tentativas="", evento="", pax="80", decisor="RH",
          pfpj="PJ", atualizado="2026-11-10T10:00:00Z"):
    valores = {"status": etapa, "date_ult": contato, "num_tent": tentativas, "date_mkp5eds": evento,
               "n_meros_mkmgpvds": pax, "text_dec": decisor, "dropdown_mm3b42sb": pfpj, "numeric_valor": "99999"}
    return {"name": nome, "updated_at": atualizado, "column_values": [{"id": k, "text": v} for k, v in valores.items()]}


ITENS = [_item("101 - BRONTAL LOGISTICA", "2026-10-28", evento="Aguardando Definição"),        # 15 dias: destravar
         _item("102 - CYRENE ALIMENTOS", "2026-09-01"),                                       # 72 dias: reaquecer
         _item("103 - DORVANA TECH", "2026-06-01"),                                           # 164 dias: encerrar
         _item("104 - ESKARA ENERGIA", "2026-10-01", tentativas="4"),                         # 42 dias, 4x: encerrar
         _item("105 - FALVORA", "2026-11-11", etapa="Proposta enviada"),                      # 1 dia: não está parada
         _item("106 - GALTRIS", "2026-10-30", evento="2026-10-20", decisor=""),               # evento passou
         _item("107 - PESSOA FISICA", "2026-01-01", pfpj="PF")]                               # PF fica fora


def _monday_falso(consultas):
    def api(query, variaveis=None):
        consultas.append(query)
        assert "mutation" not in query  # só leitura
        return {"boards": [{"columns": COLUNAS, "groups": [{"items_page": {"cursor": None, "items": ITENS}}]}]}
    return api


def test_pedido_do_mutirao():
    assert f.e_pedido("estrategista", "Estrategista, faça o mutirão do funil")
    assert agenda_clientes.e_pedido("estrategista", "Quais oportunidades paradas temos?")
    assert not f.e_pedido("copywriter", "mutirão do funil") and not f.e_pedido("estrategista", "Faça a SWOT")


def test_colunas_achadas_pelo_titulo_so_as_que_existem():
    usadas = f.colunas_usadas(COLUNAS)
    assert usadas == {"evento": "date_mkp5eds", "pax": "n_meros_mkmgpvds", "etapa": "status", "contato": "date_ult",
                      "tentativas": "num_tent", "decisor": "text_dec"}
    assert f.colunas_usadas([{"id": "x", "title": "Nome"}]) == {}


def test_separa_em_tres_listas_pelo_criterio(monkeypatch):
    import monday

    consultas = []
    monkeypatch.setattr(monday, "_api", _monday_falso(consultas))
    itens, usadas = f.ler()
    assert consultas and all("mutation" not in q for q in consultas)
    assert all("99999" not in str(i) for i in itens)  # valor não é lido
    listas = f.separar(itens, usadas, HOJE)
    nomes = {k: [x["nome"].split()[0] for x in v] for k, v in listas.items()}
    assert nomes["destravar"] == ["BRONTAL"]
    assert nomes["reaquecer"] == ["CYRENE"]
    assert set(nomes["encerrar"]) == {"DORVANA", "ESKARA", "GALTRIS"}
    brontal = listas["destravar"][0]
    assert brontal["falta"] == ["data do evento"] and "data" in brontal["sugestao"]
    assert "Perdido ou Pausado" in listas["encerrar"][0]["sugestao"]


def test_sem_coluna_de_contato_usa_a_atualizacao_do_item():
    item = {"nome": "201 - HELVORA", "atualizado": "2026-08-01T09:00:00Z", "etapa": "Aguardando Definição"}
    reg = f.classificar(item, {"etapa": "status"}, HOJE)
    assert reg["lista"] == "encerrar" and reg["dias"] == 103 and reg["falta"] == []


def test_lista_nominal_so_para_quem_ve_a_carteira(monkeypatch):
    import monday

    monkeypatch.setattr(monday, "_api", _monday_falso([]))
    itens, usadas = f.ler()
    monkeypatch.setattr(carteira, "ve_carteira", lambda login: True)
    com = f.executar("usuario.teste@exemplo.com", HOJE, itens, usadas)
    assert "BRONTAL" in com and "Uso interno" in com and "Nada foi mudado no Monday" in com
    monkeypatch.setattr(carteira, "ve_carteira", lambda login: False)
    sem = f.executar("", HOJE, itens, usadas)
    assert "BRONTAL" not in sem and "Uso interno" not in sem and "só as contagens" in sem


def test_mutirao_pelo_caminho_da_agenda_sem_ia(monkeypatch):
    import cerebro
    import monday
    import orquestrador

    entregues = []

    async def entregar(linha):
        entregues.append(linha)

    monkeypatch.setattr(monday, "_api", _monday_falso([]))
    monkeypatch.setattr(orquestrador, "entregar", entregar)
    monkeypatch.setattr(cerebro, "aprender_tarefa", lambda *_: pytest.fail("a lista não vira conhecimento"))
    agente = SimpleNamespace(id="estrategista")
    tarefa_id = asyncio.run(agenda_clientes.iniciar("usuario.teste@exemplo.com", "comercial", agente,
                                                    "Mutirão do funil parado"))
    linha = tarefas.obter(tarefa_id)
    assert linha["status"] == "concluida" and "Mutirão do funil parado" in linha["resposta"]
    assert entregues and entregues[0]["id"] == tarefa_id
