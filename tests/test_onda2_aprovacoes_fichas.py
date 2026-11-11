"""Onda 2 de novembro (11/11/2026), agente L: uma fila só de aprovações (N2-construtor-12, N2-designer-20,
N2-estrategista-04), fichas de pedido do manual 16 na tela do agente (N2-professor-07, N2-analista_metricas-21,
N2-estrategista-25, N2-sonoplasta-23) e pedido de obra do Construtor (N2-construtor-01).
Banco temporário (tests/conftest.py), manual 16 fictício em pasta temporária, dados fictícios.
"""

import asyncio
import json

import pytest

import agentes_dinamicos as ad
import aprovacoes
import avaliacoes
import config
import fichas_pedido as fichas
import folha_aprovacao
import pedido_obra
import persona_corporativo as persona
import tarefas
from estado import andar_do_agente

tarefas.iniciar()
THOMAS = "usuario.teste@exemplo.com"
OUTRA = "outra.pessoa@exemplo.com"

PERSONA = ("Missão: organizar pacotes de hospedagem para grupos e famílias, com base nas fichas oficiais. "
           "Regras: regras de ouro da marca — nunca use WhatsApp como CTA, o site fica fora dos criativos e stories "
           "não têm legenda; nunca prometer disponibilidade; nunca inventar preço. "
           "Fluxo: 1) entende o pedido; 2) consulta o Cérebro e as fichas; 3) monta a proposta; 4) revisa. "
           "Entregáveis: roteiro do pacote em texto, com os Lodges e os serviços inclusos e à parte. "
           "Fala com: recebe do Gestor de Marketing e entrega para o Copywriter.")
APARENCIA = {"pele": "#e0ac69", "cabelo": {"estilo": "curto", "cor": "#222222"},
             "roupa": {"estilo": "camisa", "cor": "#335577"}, "calca": "#111111", "acessorio": "nenhum"}
EXEMPLOS = [{"pedido": f"Pedido de teste número {n} para o agente", "resposta_esperada":
             f"Resposta esperada número {n}, com o arquivo na pasta do andar"} for n in (1, 2, 3)]


def _spec(nome="Organizador de Pacotes", **extra):
    return {"nome": nome, "andar": "marketing", "setor": "performance", "funcao": "Monta pacotes de hospedagem",
            "descricao": "Organiza pacotes.", "exemplo": "Monte um pacote de Réveillon para 20 pessoas.",
            "role": nome, "goal": "Montar pacotes claros a partir das fichas oficiais.", "backstory": PERSONA,
            "aparencia": APARENCIA, **extra}


@pytest.fixture
def limpo(monkeypatch, tmp_path):
    monkeypatch.setattr(ad, "_role_de", lambda login: "diretoria")
    monkeypatch.setattr(config, "DONO_MAX", THOMAS)
    monkeypatch.setattr(persona, "PASTA", tmp_path / "persona")
    ad._db(), pedido_obra._db(), aprovacoes._db(), folha_aprovacao._db()  # tabelas criadas
    with tarefas._db() as db:  # banco de teste: cada teste começa com a fila vazia
        for tabela in ("agentes_criados", "pedidos_obra", "folhas_aprovacao"):
            db.execute(f"DELETE FROM {tabela}")
    yield
    for agente_id in list(ad.CRIADOS):
        asyncio.run(ad.desativar(agente_id))


def _tipos(login):
    return [(i["tipo"], i["informativo"]) for i in aprovacoes.itens(login)]


# --- N2-construtor-01: pedido de obra -----------------------------------------------------------------------------

def test_agente_com_ferramentas_vira_pedido_de_obra_e_nao_proposta(limpo):
    tarefa = tarefas.criar(OUTRA, "porao", "construtor", "Crie um agente que lance os posts no Monday", "media")
    with pytest.raises(ad.ErroValidacao, match="PEDIDO DE OBRA"):  # sem os 3 exemplos
        asyncio.run(ad.criar(_spec(), OUTRA, tarefa))
    registro = asyncio.run(ad.criar(_spec(ferramentas=["Monday"], nao_faz="Não publica sozinho.", exemplos=EXEMPLOS),
                                    OUTRA, tarefa))
    assert registro["obra"] and ad.propostas_pendentes() == 0 and not andar_do_agente("organizador_de_pacotes")
    texto = ad.conferir_resposta(tarefa, "Virou pedido de obra para o Thomas.")
    assert f"PEDIDO DE OBRA #{registro['id']}" in texto and "Resposta esperada: Resposta esperada número 3" in texto
    assert "Não publica sozinho" in texto and "Monday" in texto
    repetido = asyncio.run(ad.criar(_spec(exemplos=EXEMPLOS), OUTRA, tarefa))
    assert repetido["repetido"] and len(pedido_obra.pendentes()) == 1
    assert "Só o Thomas" in pedido_obra.decidir(registro["id"], OUTRA, "aprovar")
    assert "aceito" in pedido_obra.decidir(registro["id"], THOMAS, "aprovar") and not pedido_obra.pendentes()
    assert pedido_obra.da_tarefa(tarefa)["situacao"] == pedido_obra.ACEITO  # nada é apagado


def test_agente_leve_segue_como_proposta_e_comercial_continua_bloqueado(limpo):
    tarefa = tarefas.criar(OUTRA, "porao", "construtor", "Crie um organizador de pacotes", "media")
    assert asyncio.run(ad.criar(_spec(), OUTRA, tarefa))["situacao"] == ad.PROPOSTA
    outra = tarefas.criar(OUTRA, "porao", "construtor", "Crie um agente que lê o Drive do Comercial", "media")
    with pytest.raises(ad.ErroValidacao, match="não recebe agentes novos"):
        asyncio.run(ad.criar(_spec(nome="Leitor", andar="comercial", setor="corporativo", exemplos=EXEMPLOS),
                             OUTRA, outra))
    with pytest.raises(ad.ErroValidacao, match="não pode"):  # o texto vai para o Claude Code: sem link nem senha
        pedido_obra.montar(_spec(exemplos=EXEMPLOS, nao_faz="Veja https://exemplo.com e a senha"), OUTRA)


# --- N2-construtor-12, -designer-20, -estrategista-04: uma fila só ------------------------------------------------

def test_proposta_aparece_para_quem_pediu_com_botoes_e_para_o_thomas_so_informativa(limpo):
    tarefa = tarefas.criar(OUTRA, "porao", "construtor", "Crie um organizador de pacotes", "media")
    registro = asyncio.run(ad.criar(_spec(), OUTRA, tarefa))
    assert _tipos(OUTRA) == [("agente", False)] and _tipos(THOMAS) == [("agente", True)]
    item = aprovacoes.itens(OUTRA)[0]
    assert {a["acao"] for a in item["acoes"]} == {"aprovar", "ajustar", "descartar"} and not item["vencido"]
    with ad._db() as db:  # 8 dias parado: vence, mas continua lá e não é aprovado sozinho
        db.execute("UPDATE agentes_criados SET criado_em = '2026-01-01T10:00:00Z' WHERE id = ?", (registro["id"],))
    assert aprovacoes.itens(OUTRA)[0]["vencido"] and ad.propostas_pendentes() == 1
    assert "descartada" in asyncio.run(aprovacoes.decidir("agente", registro["id"], OUTRA, "descartar"))
    assert aprovacoes.itens(OUTRA) == [] and ad._db().execute("SELECT COUNT(*) FROM agentes_criados").fetchone()[0] == 1
    with pytest.raises(ValueError):
        asyncio.run(aprovacoes.decidir("agente", registro["id"], OUTRA, "apagar"))


def test_persona_e_obra_so_na_fila_do_thomas_e_recusar_guarda_o_rascunho(limpo):
    persona.PASTA.mkdir(parents=True)
    (persona.PASTA / f"{persona.PREFIXO_RASCUNHO}7.md").write_text("# Persona nova\n", encoding="utf-8")
    (persona.PASTA / f"{persona.PREFIXO_RASCUNHO}7.json").write_text(
        json.dumps({"tarefa_id": 7, "pedido_por": THOMAS, "criado_em": "2026-11-10T09:00:00-03:00"}), encoding="utf-8")
    assert ("persona", False) in _tipos(THOMAS) and not _tipos(OUTRA)
    assert "Só o Thomas" in asyncio.run(aprovacoes.decidir("persona", "7", OUTRA, "recusar"))
    assert "recusado" in asyncio.run(aprovacoes.decidir("persona", "7", THOMAS, "recusar"))
    assert not persona.rascunhos_pendentes() and any(a.name.startswith("14_persona_recusada_7_")
                                                     for a in persona.PASTA.iterdir())


def test_decisao_de_estudo_fica_ate_o_thomas_registrar(limpo):
    tarefa = tarefas.criar(OUTRA, "comercial", "estrategista", "Me ajude a decidir: abrir um novo canal?", "complexa")
    tarefas.atualizar(tarefa, status="concluida", resposta="Opções A e B. Decisão do Thomas: ___ em __/__")
    comum = tarefas.criar(OUTRA, "comercial", "estrategista", "SWOT da Casa Vero", "complexa")
    tarefas.atualizar(comum, status="concluida", resposta="SWOT")
    assert _tipos(THOMAS) == [("estudo", False)] and _tipos(OUTRA) == [("estudo", True)]
    assert "Escreva a decisão" in aprovacoes.registrar_decisao(tarefa, THOMAS, "decidir", "")
    assert "Só o Thomas" in aprovacoes.registrar_decisao(tarefa, OUTRA, "decidir", "Opção B")
    assert "registrada" in asyncio.run(aprovacoes.decidir("estudo", str(tarefa), THOMAS, "decidir", "Opção B"))
    assert aprovacoes.itens(THOMAS) == []
    assert aprovacoes._db().execute("SELECT decisao FROM decisoes_estudo WHERE tarefa_id = ?",
                                    (tarefa,)).fetchone()["decisao"] == "Opção B"


def test_folha_sem_joinha_fica_na_fila_de_quem_pediu_ate_aprovar(limpo, monkeypatch):
    monkeypatch.setattr(aprovacoes, "FOLHAS_DESDE", "2000-01-01")
    tarefa = tarefas.criar(OUTRA, "marketing", "gestor", "Peça final: POST do Lodge 1", "complexa")
    tarefas.atualizar(tarefa, status="concluida", resposta="Peça pronta.")
    with folha_aprovacao._db() as db:
        db.execute("INSERT INTO folhas_aprovacao (tarefa_id, anexo_id) VALUES (?, 'abc')", (tarefa,))
    assert _tipos(OUTRA) == [("folha", False)] and not _tipos(THOMAS)
    assert "Só quem pediu" in asyncio.run(aprovacoes.decidir("folha", str(tarefa), THOMAS, "aprovar"))
    assert "aprovada" in asyncio.run(aprovacoes.decidir("folha", str(tarefa), OUTRA, "aprovar"))
    assert avaliacoes.de(tarefa) == 1 and aprovacoes.itens(OUTRA) == []


# --- N2-professor-07 e cia.: ficha do manual 16 ------------------------------------------------------------------

MANUAL = """# Fichas de pedido (teste)

Regra geral: diga sempre a EMPRESA.

## Social Media (manuais 02, 15)
- Obrigatório: empresa; mês ou data; TIPO (STORIES; POST) ou "planejamento do mês".
- Opcional: Lodges pelo número; responsável no Monday (só o Thomas aloca; peça avulsa pede).
- Bom exemplo (Casa Veraneio): "Carrossel para 20/11 com os Lodges 34 e 202, responsável Fulana, sem valores."
- Bom exemplo (Casa Vero): "Reels do Vero 87 para 12/11, sem valor."

## Designer e Criador de Imagens (manuais 03, 04)
- Obrigatório: empresa; TIPO.
- Bom exemplo: "CARROSSEL F1 do Lodge 202, sem valor."

## Gestor de Tráfego (manual 02)
- Obrigatório: empresa; plataforma.

## Analista de Métricas (manuais 02, 15)
- Obrigatório:
  - a empresa, ou "todas as empresas";
  - período.
- Opcional:
  - rede ou formato.
- Sempre: compara com o período anterior.
- Bom exemplo: "Compare os Reels de outubro e novembro da Casa Veraneio."
"""


def test_manual_16_vira_ficha_por_agente_nos_dois_formatos(tmp_path, monkeypatch):
    (tmp_path / "16_fichas_de_pedido.md").write_text(MANUAL, encoding="utf-8")
    monkeypatch.setattr(config, "PASTA_CONHECIMENTO", tmp_path)
    social = fichas.de("social_media")
    assert social["obrigatorio"] == ["empresa", "mês ou data", 'TIPO (STORIES; POST) ou "planejamento do mês"']
    assert social["opcional"][1] == "responsável no Monday (só o Thomas aloca; peça avulsa pede)"
    assert [e["empresa"] for e in social["exemplos"]] == ["casa_veraneio", "casa_vero"]
    assert social["exemplos"][0]["modelo"] == ("Carrossel para [data] com os Lodges [nº] e [nº], responsável [nome], "
                                               "sem valores.")
    assert fichas.modelo("Lodges 03, 26 e 64; Lodge 20, 30 s") == "Lodges [nº], [nº] e [nº]; Lodge [nº], 30 s"
    assert social["geral"] =="Regra geral: diga sempre a EMPRESA."
    assert fichas.de("designer")["titulo"] == fichas.de("criador_imagens")["titulo"] == "Designer e Criador de Imagens"
    assert fichas.de("gestor_trafego") and fichas.de("gestor") is None  # "Gestor de Tráfego" não é o Gestor
    metricas = fichas.de("analista_metricas")
    assert metricas["obrigatorio"] == ['a empresa, ou "todas as empresas"', "período"]
    assert metricas["opcional"] == ["rede ou formato"] and metricas["notas"][0]["rotulo"] == "Sempre"
    assert fichas.de("sonoplasta") is None  # ficha ainda em rascunho: sem cartão
    (tmp_path / "16_fichas_de_pedido.md").write_text(MANUAL + "\n## Sonoplasta (manual 05)\n- Obrigatório: empresa.\n",
                                                     encoding="utf-8")
    assert fichas.de("sonoplasta")["obrigatorio"] == ["empresa"]  # o manual mudou: lido de novo
