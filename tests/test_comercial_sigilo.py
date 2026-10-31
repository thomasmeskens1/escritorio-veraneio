"""Comercial e sigilo (consertos 1 e 2, 31/10/2026): e-mail nominal fora da prospecção, carteira de clientes fora
do pedido que vai à web e da persona de quem não é da Diretoria, e a rota sigilosa (nada de CRM, carteira ou
financeiro em modelo gratuito de fora). Só dados fictícios (exemplo.com, empresas inventadas); sem Monday nem Max.
"""

import json
import sys
import types
from pathlib import Path

import pytest

import acesso
import carteira
import comercial as c
import config
import roteamento
import saude
import tarefas
from roteamento import Dificuldade

tarefas.iniciar()

# Carteira fictícia (nomes inventados para o teste).
CLIENTES = {
    "contas": [{"nome": "ZEPHYRA INVESTIMENTOS LTDA", "industry": "Serviços financeiros", "text_mkxj2284": "São Paulo",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "", "company_domain": "zephyra.exemplo.com"},
               {"nome": "Grupo Quorvex do Brasil", "industry": "Bens de consumo", "text_mkxj2284": "Barueri",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "", "company_domain": ""}],
    "ganhos": [{"nome": "1124 - TALMIRA FOODS copy", "dropdown_mm3b42sb": "PJ", "color_mm4pd1wc": "Evento",
                "n_meros_mkmgpvds": "120", "local_mkmgy5nb": "Jundiaí", "date_mkp5eds": "2026-11-20"},
               {"nome": "77 - X7NOVA TECH", "dropdown_mm3b42sb": "PJ", "color_mm4pd1wc": "Evento Corporativo",
                "n_meros_mkmgpvds": "24", "local_mkmgy5nb": "Atibaia", "date_mkp5eds": ""}],
}


@pytest.fixture
def carteira_ficticia(monkeypatch):
    monkeypatch.setattr(c, "clientes", lambda: CLIENTES)
    monkeypatch.setattr(carteira, "_nomes", None)
    yield
    carteira._nomes = None


# --- Conserto 1: e-mail nominal ----------------------------------------------------------------------------

def test_caixa_generica_pura_ou_com_complemento_neutro():
    for email in ("eventos@exemplo.com", "rh2@exemplo.com", "contato.campinas@exemplo.com", "comercial-br@exemplo.com",
                  "eventos.corporativos@exemplo.com", "fale-conosco@exemplo.com", "contatos@exemplo.com",
                  "rh_sp@exemplo.com", "marketing.eventos@exemplo.com"):
        assert c.email_permitido(email, "https://www.exemplo.com"), email


def test_nome_de_pessoa_depois_da_palavra_generica_e_nominal():
    # prospectador-14: antes, tudo o que vinha depois de "rh" ou "contato" passava como caixa da empresa.
    for email in ("rh.maria.silva@exemplo.com", "contato.joao@exemplo.com", "rh-maria@exemplo.com",
                  "marketing-ana@exemplo.com", "eventos.joao@exemplo.com", "joao.silva@exemplo.com",
                  "contato+joao@exemplo.com", "mariarh@exemplo.com", "rh.m.silva@exemplo.com"):
        assert not c.email_permitido(email, "exemplo.com"), email


def test_lead_com_email_nominal_fica_sem_o_email_e_a_previa_avisa():
    aceitos, _ = c.validar([{"empresa": "Empresa Teste", "site": "exemplo.com", "email": "rh.maria@exemplo.com",
                             "telefone": "(19) 3333-4444"}], set(), set())
    assert aceitos[0]["email"] == "" and "nominal" in aceitos[0]["aviso"]
    assert "Obs.: e-mail removido" in c._linha_lead(1, aceitos[0])


def test_empresa_pequena_sai_e_agencia_de_eventos_fica():
    # prospectador-28: na empresa muito pequena o "contato@" costuma ser do dono.
    aceitos, recusados = c.validar([
        {"empresa": "Micro Teste", "email": "contato@micro.exemplo.com", "site": "micro.exemplo.com", "funcionarios": 6},
        {"empresa": "Produtora Teste", "segmento": "Eventos", "email": "contato@prod.exemplo.com",
         "site": "prod.exemplo.com", "funcionarios": 8},
    ], set(), set())
    assert [a["empresa"] for a in aceitos] == ["Produtora Teste"]
    assert "pequena demais" in recusados[0]


def test_email_nominal_de_previa_antiga_nao_vai_ao_monday(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "PASTA_PREVIAS", tmp_path)
    monkeypatch.setattr(c, "_rotulos", lambda: {})
    monkeypatch.setattr(c, "ja_conhecidos", lambda: (set(), set()))
    monkeypatch.setattr(c, "_evento", lambda *_a: None)
    enviados = []
    monkeypatch.setattr(c, "criar_lead", lambda lead: enviados.append(c._valores(lead)) or 1)
    tarefa = tarefas.criar("usuario.teste@exemplo.com", "comercial", "prospectador", "Crie os leads", "simples")
    (tmp_path / "900.json").write_text(json.dumps({"usuario": "usuario.teste@exemplo.com", "pedido": "", "criados": [],
                                                   "leads": [{"empresa": "Empresa Teste", "site": "exemplo.com",
                                                              "email": "contato.joao@exemplo.com",
                                                              "telefone": "(19) 3333-4444"}]}), encoding="utf-8")
    assert "Criei 1 lead" in c.criar_da_previa(tarefa, "Crie os leads da prévia #900")
    assert c.COL["email"] not in enviados[0] and c.COL["telefone"] in enviados[0]


# --- Conserto 2: carteira fora da web e da persona de quem não é da Diretoria ---------------------------------

def test_nomes_de_clientes_viram_cliente(carteira_ficticia):
    texto = ("Clientes como Zephyra, o grupo Quorvex, a Talmira Foods e a X7 voltaram. Jundiaí e a Casa Veraneio "
             "seguem iguais; [cliente] não muda.")
    oculto = carteira.ocultar(texto)
    for nome in ("Zephyra", "Quorvex", "Talmira", "X7"):
        assert nome not in oculto, nome
    assert "Jundiaí" in oculto and "Casa Veraneio" in oculto and carteira.tem_nomes(texto)
    assert not carteira.tem_nomes(oculto)


def test_monday_fora_do_ar_nao_trava_o_pedido(monkeypatch):
    monkeypatch.setattr(carteira, "_nomes", None)
    monkeypatch.setattr(c, "clientes", lambda: (_ for _ in ()).throw(RuntimeError("sem rede")))
    assert carteira.ocultar("Texto qualquer") == "Texto qualquer"


def test_pedido_de_prospeccao_na_web_nao_leva_a_carteira(carteira_ficticia, monkeypatch):
    monkeypatch.setattr(c, "_rotulos", lambda: {"segmento": ["Indústria"]})
    monkeypatch.setattr(c, "_persona", lambda: "Persona: clientes como Zephyra e Talmira Foods, médio porte.")
    monkeypatch.setattr(c, "ja_conhecidos", lambda: pytest.fail("a lista de conhecidos não vai mais no pedido"))
    pedido = c.prompt_prospeccao("Prospecte 5 indústrias em Campinas", 5)
    for nome in ("ZEPHYRA", "Zephyra", "Quorvex", "TALMIRA", "Talmira", "X7NOVA", "zephyra.exemplo.com"):
        assert nome not in pedido, nome
    assert "Serviços financeiros (1)" in pedido and "101 a 300 (1)" in pedido and "Indústria" in pedido


def test_persona_e_feita_sem_pesquisa_na_web(carteira_ficticia, tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(c, "pedir_ao_max", lambda prompt, *a, **k: chamadas.append(k) or
                        "<<PERSONA>>\n# Persona\n<<FIM>>")
    monkeypatch.setattr(c, "PASTA_PERSONA", tmp_path / "14_persona.md")
    monkeypatch.setattr(c, "_evento", lambda *_a: None)
    monkeypatch.setitem(sys.modules, "cerebro", types.SimpleNamespace(indexar_oficiais=lambda: None))
    c.atualizar_persona(0)
    assert chamadas == [{"web": False}]
    assert "nomes das empresas clientes" in c.prompt_persona()


def test_trabalhador_sem_web_nao_libera_ferramentas(monkeypatch):
    if not Path("/repo/scripts/max/comum.py").exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    sys.path.insert(0, "/repo/scripts/max")
    try:
        import comum
        import trabalhos_max
    except Exception as erro:  # o trabalhador precisa das pastas do PC
        pytest.skip(f"trabalhador indisponível aqui: {erro}")
    comandos = []
    monkeypatch.setattr(trabalhos_max, "PASTA_PROSPECCAO", Path("/tmp/prospeccao-teste"))
    monkeypatch.setattr(comum, "claude_exe", lambda: "claude")
    monkeypatch.setattr(comum, "rodar_claude", lambda comando, *a, **k: comandos.append(comando) or "ok")
    trabalhos_max.executar_prospeccao({"prompt": "p", "web": False})
    trabalhos_max.executar_prospeccao({"prompt": "p"})
    assert comandos[0][comandos[0].index("--tools") + 1] == "" and "WebSearch" not in " ".join(comandos[0])
    assert "WebSearch,WebFetch" in comandos[1]


def test_prospectador_e_estrategista_so_diretoria_ou_liberados(monkeypatch):
    usuarios = {"func@exemplo.com": {"role": "funcionario", "agentes": "*"},
                "comercial@exemplo.com": {"role": "funcionario", "agentes": ["comercial/prospectador"]},
                "dir@exemplo.com": {"role": "diretoria", "agentes": "*"}}
    monkeypatch.setattr(acesso, "carregar_usuarios", lambda: usuarios)
    monkeypatch.setattr(acesso, "e_master", lambda login: False)
    monkeypatch.setattr(acesso, "ve_financeiro", lambda login: usuarios[login]["role"] == "diretoria")
    pode = lambda login, agente: acesso.pode_usar({"sub": login}, "comercial", agente)  # noqa: E731
    assert not pode("func@exemplo.com", "prospectador") and not pode("func@exemplo.com", "estrategista")
    assert acesso.pode_usar({"sub": "func@exemplo.com"}, "marketing", "copywriter")
    assert pode("comercial@exemplo.com", "prospectador") and not pode("comercial@exemplo.com", "estrategista")
    assert pode("dir@exemplo.com", "prospectador") and pode("dir@exemplo.com", "estrategista")


# --- Conserto 2c: rota sigilosa -----------------------------------------------------------------------------

def test_o_que_e_sigiloso(carteira_ficticia):
    assert roteamento.sigilosa("prospectador") and roteamento.sigilosa("estrategista")
    assert roteamento.sigilosa("copywriter", "Compare o faturamento de setembro")
    assert roteamento.sigilosa("analista_metricas", "Quanto deu o ROAS?")
    assert roteamento.sigilosa("copywriter", "Post com R$ 1.200 por noite")
    assert roteamento.sigilosa("analista_metricas", "Resumo", financeiro=True)
    assert roteamento.sigilosa("copywriter", "Resuma", contexto="Trecho: a Talmira Foods fez evento em junho.")
    assert not roteamento.sigilosa("copywriter", "Escreva a legenda do post de Natal", contexto="Lodge com piscina.")


def test_agente_da_carteira_nao_passa_por_gratuito_de_fora(monkeypatch):
    monkeypatch.setattr(config, "modelos_gratuitos", lambda: ["openrouter/teste:free", "groq/teste"])
    monkeypatch.setattr(config, "modelo_disponivel", lambda _m: True)
    monkeypatch.setattr(config, "MODELO_LOCAL", "ollama/teste")
    monkeypatch.setattr(saude, "disponivel", lambda _m: True)
    monkeypatch.setattr(tarefas, "chat_rapido_liberado", lambda *_a: False)
    for dificuldade in Dificuldade:
        etapas = roteamento.etapas_imediatas(dificuldade, "prospectador")
        assert [e.modelo for e in etapas] == ["ollama/teste"], dificuldade
    assert roteamento.etapas_imediatas(Dificuldade.simples, "copywriter")[0].modelo == "openrouter/teste:free"


def test_executor_recusa_gratuito_de_fora_em_tarefa_sigilosa():
    from agents import executor

    with pytest.raises(executor.RotaSigilosa):  # antes de chamar qualquer modelo
        executor._rodar("estrategista", "Monte a Matriz BCG", "Resposta.", "openrouter/teste:free", 60,
                        executor.Resultado(texto=""), 0)
    assert issubclass(executor.RotaSigilosa, executor.LocalOcupado)  # pula sem afastar o modelo
