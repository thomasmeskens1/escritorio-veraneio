"""Onda 1 (11/11/2026), pacote de sigilo do Comercial e prospecção que chega ao fim: persona só como rascunho
(N2-prospectador-01), fonte do contato conferida (-35), item do Monday e rodapé na prévia (-33, -37), análise de
negócio sem web (N2-estrategista-18), CONFIDENCIAL na pasta restrita (-06), Construtor fora do Comercial
(N2-construtor-02), uma linha por empresa em lotes de 5 (N2-prospectador-02) e "possível cliente: confira" (-06).
Só dados fictícios (exemplo.com, empresas inventadas); sem Monday, Max nem Drive.
"""

import json
import sys
import types

import pytest

import agentes_dinamicos as ad
import auth
import carteira
import comercial as c
import config
import documentos
import documentos_entrega as entrega
import estudos
import persona_corporativo as persona
import producao
import prospeccao_conferencia as conf
import prospeccao_leitura as leitura
import tarefas

tarefas.iniciar()

DONO = "usuario.teste@exemplo.com"
CLIENTES = {
    "contas": [{"nome": "ZEPHYRA INVESTIMENTOS LTDA", "industry": "Serviços financeiros", "text_mkxj2284": "São Paulo",
                "dropdown_mkxj16y9": "", "data_mknc1nvw": "", "company_domain": "zephyra.exemplo.com"}],
    "ganhos": [{"nome": "1124 - TALMIRA FOODS copy", "dropdown_mm3b42sb": "PJ", "color_mm4pd1wc": "Evento",
                "n_meros_mkmgpvds": "120", "local_mkmgy5nb": "Jundiaí", "date_mkp5eds": "2026-11-20"}],
}


@pytest.fixture
def carteira_ficticia(monkeypatch):
    monkeypatch.setattr(c, "clientes", lambda: CLIENTES)
    monkeypatch.setattr(carteira, "_nomes", None)
    yield
    carteira._nomes = None


def _lead(nome="Empresa Nova", dominio="nova.exemplo.com", **extra):
    return {"empresa": nome, "site": f"https://{dominio}", "email": f"eventos@{dominio}", "telefone": "(19) 3333-4444",
            "fontes": [f"https://{dominio}/contato"], "motivo": "teste", **extra}


# --- N2-prospectador-01: persona só com pedido explícito e como rascunho ------------------------------------------

def test_so_pedido_explicito_refaz_a_persona():
    for texto in ("Refaça a persona", "Atualize a persona do cliente corporativo", "Monte a persona",
                  "Crie a persona do cliente corporativo"):
        assert c.REFAZ_PERSONA.search(texto) and c.e_pedido_de_trabalho(texto), texto
    for texto in ("Me explique a persona", "Prospecte 5 empresas da persona", "Faça uma prospecção com a persona",
                  "Qual é a nossa persona?"):
        assert not c.REFAZ_PERSONA.search(texto), texto
    assert not c.e_pedido_de_trabalho("Me explique a persona")
    assert c.APROVA_PERSONA.search("Aprovo a persona nova") and c.PEDE_PERSONA.search("Aprovo a persona nova")


def test_prospeccao_que_cita_a_persona_nao_refaz_o_manual(monkeypatch):
    monkeypatch.setattr(c, "atualizar_persona", lambda _t: pytest.fail("não refaz a persona"))
    monkeypatch.setattr(c, "prospectar", lambda _t, texto: f"prospecção: {texto}")
    assert c.executar(0, "Monte a persona e prospecte 5 empresas").startswith("prospecção")


def test_persona_nova_vira_rascunho_e_so_o_thomas_aprova(carteira_ficticia, tmp_path, monkeypatch):
    manual = tmp_path / "14_persona_corporativo.md"
    manual.write_text("# Persona antiga\nRegras do Thomas.\n", encoding="utf-8")
    monkeypatch.setattr(c, "PASTA_PERSONA", manual)
    monkeypatch.setattr(persona, "PASTA", tmp_path / "persona")
    monkeypatch.setattr(config, "DONO_MAX", DONO)
    monkeypatch.setattr(c, "_evento", lambda *_a: None)
    indexados = []
    monkeypatch.setitem(sys.modules, "cerebro", types.SimpleNamespace(indexar_oficiais=lambda: indexados.append(1)))
    chamadas = []
    monkeypatch.setattr(c, "pedir_ao_max", lambda prompt, *a, **k: chamadas.append(k) or
                        "<<PERSONA>>\n# Persona nova\n<<FIM>>")
    tarefa = tarefas.criar(DONO, "comercial", "prospectador", "Refaça a persona", "complexa", "cv_corporativo")
    resposta = c.executar(tarefa, "Refaça a persona")
    assert chamadas[0]["web"] is False and "RASCUNHO" in resposta and "Uso interno" in resposta
    assert manual.read_text(encoding="utf-8").startswith("# Persona antiga") and not indexados
    assert "Só o Thomas" in persona.aprovar("Aprovo a persona nova", "outra.pessoa@exemplo.com")
    assert manual.read_text(encoding="utf-8").startswith("# Persona antiga")
    feito = c.executar(tarefa, "Aprovo a persona nova")
    assert "aprovada" in feito and manual.read_text(encoding="utf-8").startswith("# Persona nova") and indexados
    guardadas = [a.name for a in (tmp_path / "persona").iterdir()]
    assert any(n.startswith("14_persona_corporativo_ate_") for n in guardadas)  # a anterior fica guardada
    assert any(n.startswith(f"14_persona_aprovada_{tarefa}_") for n in guardadas)  # nada apagado
    assert "Não achei nenhum rascunho" in persona.aprovar("Aprovo a persona nova", DONO)


# --- N2-prospectador-02: uma linha por empresa, leitura tolerante e lotes de 5 -----------------------------------

def test_leitura_tolerante_pula_so_a_linha_com_defeito():
    resposta = ("Conferi as empresas.\n```json\n"
                '<<LEAD>>{"empresa": "Alfa Teste", "site": "https://alfa.exemplo.com", "fontes": ["x"],}\n'
                '<<LEAD>>{"empresa": "Beta Teste", "site": \n'
                '<<LEAD>>{"empresa": "Gama Teste", "motivo": "tem {chaves} e \\"aspas\\" no texto"}\n'
                "```\n<<FIM>>\nResumo.")
    leads, defeitos = leitura.ler(resposta)
    assert [l["empresa"] for l in leads] == ["Alfa Teste", "Gama Teste"] and defeitos == 1
    antigo = '<<LEADS>>\n[{"empresa": "Delta Teste"}, {"empresa": "Epsilon Teste", "site": "https://e'  # cortado
    leads, _ = leitura.ler(antigo)
    assert [l["empresa"] for l in leads] == ["Delta Teste"]
    assert not leitura.tem_leads("Preciso saber a cidade antes de pesquisar.")


def test_dez_empresas_viram_dois_lotes_de_cinco_e_o_que_falha_vira_previa_parcial(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "PASTA_PREVIAS", tmp_path)
    monkeypatch.setattr(c, "_evento", lambda *a: eventos.append(a))
    monkeypatch.setattr(c, "ja_conhecidos", lambda: (set(), set()))
    monkeypatch.setattr(c, "_rotulos", lambda: {"segmento": []})
    monkeypatch.setattr(c, "_persona", lambda: "")
    monkeypatch.setattr(c, "clientes", lambda: CLIENTES)
    monkeypatch.setattr(conf, "ARQUIVO_APELIDOS", tmp_path / "apelidos.json")
    monkeypatch.setattr(c, "na_frente", lambda _id: 2)
    eventos, prompts = [], []

    def pedir(prompt, limite_s, web=True, origem="", ao_enfileirar=None):
        prompts.append(prompt)
        ao_enfileirar(100 + len(prompts))
        if len(prompts) == 2:
            raise TimeoutError("A pesquisa no Claude Code (Max) não terminou a tempo.")
        return "".join(f"<<LEAD>>{json.dumps(_lead(f'Empresa {n}', f'e{n}.exemplo.com'))}\n" for n in range(1, 6))

    monkeypatch.setattr(c, "pedir_ao_max", pedir)
    tarefa = tarefas.criar(DONO, "comercial", "prospectador", "Prospecte 10 empresas", "complexa", "cv_corporativo")
    texto = c.prospectar(tarefa, "Prospecte 10 empresas de tecnologia em Campinas")
    assert c.lotes(10) == [5, 5] and c.lotes(7) == [5, 2] and len(prompts) == 2
    assert "até 5 empresas" in prompts[0] and "NÃO REPITA" in prompts[1] and "Empresa 3" in prompts[1]
    assert "<<LEAD>>" in prompts[0]
    assert texto.startswith(f"Prévia #{tarefa}: 5 empresa") and "Prévia parcial: lote 2 de 2" in texto
    assert any("lote 1 de 2 na fila do Max, 2 trabalho(s) na frente" in str(e) for e in eventos)
    previa = json.loads((tmp_path / f"{tarefa}.json").read_text(encoding="utf-8"))
    assert previa["parcial"] and previa["trabalhos_max"] == [101, 102]


def test_item_do_monday_fica_gravado_na_previa(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "PASTA_PREVIAS", tmp_path)
    monkeypatch.setattr(c, "_evento", lambda *_a: None)
    monkeypatch.setattr(c, "ja_conhecidos", lambda: (set(), set()))
    monkeypatch.setattr(conf, "ARQUIVO_APELIDOS", tmp_path / "apelidos.json")
    monkeypatch.setattr(c, "criar_lead", lambda _lead: 987654)
    tarefa = tarefas.criar(DONO, "comercial", "prospectador", "Crie os leads", "simples", "cv_corporativo")
    (tmp_path / "901.json").write_text(json.dumps({"usuario": DONO, "pedido": "", "criados": [], "leads": [_lead()]}),
                                       encoding="utf-8")
    assert "Criei 1 lead" in c.criar_da_previa(tarefa, "Crie os leads da prévia #901")
    item = json.loads((tmp_path / "901.json").read_text(encoding="utf-8"))["itens_monday"]["1"]
    assert item["item_id"] == 987654 and item["criado_por"] == DONO and item["criado_em"]


# --- N2-prospectador-35: fonte do contato conferida pelo código ---------------------------------------------------

def test_fonte_de_perfil_pessoal_ou_sem_fonte_da_empresa_derruba_o_canal(tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "ARQUIVO_APELIDOS", tmp_path / "apelidos.json")
    pessoal = _lead("Pessoal Teste", "pessoal.exemplo.com", fontes=["https://www.linkedin.com/in/fulano-teste"])
    busca = _lead("Busca Teste", "busca.exemplo.com", fontes=["https://www.google.com/search?q=busca"])
    sem = _lead("Sem Fonte Teste", "sem.exemplo.com", fontes=[])
    cadastro = _lead("Cadastro Teste", "cadastro.exemplo.com", fontes=["https://cnpj.biz/00000000000100"])
    rastreio = _lead("Rastreio Teste", "rastreio.exemplo.com",
                     fontes=["https://rastreio.exemplo.com/contato?utm_source=x&gclid=1&pagina=2", "texto sem link"])
    aceitos, recusados = c.validar([pessoal, busca, sem, cadastro, rastreio], set(), set())
    assert [a["empresa"] for a in aceitos] == ["Cadastro Teste", "Rastreio Teste"]
    assert sum("canal sem fonte da empresa" in r for r in recusados) == 3
    assert aceitos[1]["fontes"] == ["https://rastreio.exemplo.com/contato?pagina=2"]


# --- N2-prospectador-06: possível cliente com outro nome, outro domínio ou do mesmo grupo -------------------------

def test_parecido_com_cliente_ganha_aviso_e_igual_continua_recusado(tmp_path, monkeypatch):
    arquivo = tmp_path / "apelidos.json"
    arquivo.write_text(json.dumps({"grupo ficticio": ["Talmira Foods", "Marca Orvalis", "orvalis.exemplo.com.br"]}),
                       encoding="utf-8")
    monkeypatch.setattr(conf, "ARQUIVO_APELIDOS", arquivo)
    nomes = {c._chave("ZEPHYRA INVESTIMENTOS LTDA"), c._chave("1124 - TALMIRA FOODS")}
    dominios = {"quarzeno.com.br"}
    aceitos, recusados = c.validar([
        _lead("Zephyra Capital Partners", "zcp.exemplo.com"),         # mesma raiz de nome
        _lead("Quarzeno Global", "quarzeno.com"),                     # mesmo nome-base do domínio
        _lead("Marca Orvalis", "orvalis.exemplo.com.br"),             # mesmo grupo (apelidos)
        _lead("Empresa Distinta", "distinta.exemplo.com"),
        _lead("Zephyra Investimentos", "outra.exemplo.com"),          # igual: recusa como antes
    ], nomes, dominios)
    avisos = {a["empresa"]: a.get("aviso", "") for a in aceitos}
    assert avisos["Zephyra Capital Partners"].startswith("possível cliente: confira")
    assert avisos["Quarzeno Global"].startswith("possível cliente: confira")
    assert "mesmo grupo" in avisos["Marca Orvalis"] and avisos["Empresa Distinta"] == ""
    assert recusados == ["Zephyra Investimentos: já está no CRM"]
    assert "Obs.: possível cliente: confira" in c._linha_lead(1, aceitos[0])


# --- N2-estrategista-18: análise de negócio sem web e com o cliente escondido -------------------------------------

def _estudo_falso(monkeypatch, pedidos):
    monkeypatch.setattr(estudos, "_painel", lambda financeiro=True: "Painel: a Talmira Foods voltou.")
    monkeypatch.setattr(estudos, "_cerebro", lambda *_a, **_k: "Cérebro: proposta da Zephyra em outubro.")
    monkeypatch.setattr(c, "_persona", lambda: "Persona: gestoras como a Zephyra.")
    monkeypatch.setattr(auth, "ve_financeiro", lambda _l: False)
    monkeypatch.setattr(c, "pedir_ao_max", lambda prompt, limite_s, web=True: pedidos.append((prompt, limite_s, web))
                        or "Análise fictícia.")


def test_analise_de_orcamento_roda_sem_web_e_sem_nome_de_cliente(carteira_ficticia, monkeypatch):
    pedidos = []
    _estudo_falso(monkeypatch, pedidos)
    tarefa = tarefas.criar(DONO, "comercial", "estrategista", "x", "complexa", "*")
    historico = [{"texto": "Como está a Talmira Foods?", "resposta": "A Talmira Foods pediu orçamento."}]
    estudos.executar(tarefa, "estrategista", "Analise este orçamento da Zephyra para 120 pessoas", "*", historico)
    prompt, limite, web = pedidos[0]
    assert web is False and limite == estudos.LIMITE_ANALISE_S
    for nome in ("Zephyra", "ZEPHYRA", "Talmira", "TALMIRA"):
        assert nome not in prompt, nome
    assert "não há pesquisa na web" in prompt and "PERSONA DO CLIENTE CORPORATIVO" in prompt
    eventos = tarefas.eventos_de([tarefa])[tarefa]
    assert any(e["tipo"] == "analise_sem_web" for e in eventos)


def test_estudo_de_mercado_segue_com_web_mas_cliente_citado_tira_a_web(carteira_ficticia, monkeypatch):
    pedidos = []
    _estudo_falso(monkeypatch, pedidos)
    tarefa = tarefas.criar(DONO, "comercial", "estrategista", "x", "complexa", "*")
    estudos.executar(tarefa, "estrategista", "Faça a Matriz BCG das três empresas", "*", [])
    estudos.executar(tarefa, "estrategista", "Qual a estratégia de mercado para recuperar a Zephyra?", "*", [])
    assert [p[2] for p in pedidos] == [True, False]
    assert all("Zephyra" not in p[0] and "Talmira" not in p[0] for p in pedidos)
    assert "sem pesquisa na web" in estudos.aviso_inicio("estrategista", "Avalie esta proposta")
    assert "pesquisar na web" in estudos.aviso_inicio("estrategista", "Faça a Matriz BCG")
    # Com anexo, a análise vai pelo caminho normal (lê o anexo e já é sigiloso para o Estrategista).
    assert not estudos.e_estudo("estrategista", "Analise esta proposta", com_anexo=True)
    assert estudos.e_estudo("estrategista", "Analise esta proposta")


# --- N2-estrategista-06: CONFIDENCIAL vai para a subpasta restrita do Drive ---------------------------------------

def _payload_documento() -> dict:
    linha = producao._db().execute("SELECT payload FROM trabalhos_max WHERE tipo = 'documento' ORDER BY id DESC "
                                   "LIMIT 1").fetchone()
    return json.loads(linha["payload"])


def test_estudo_confidencial_nao_vai_para_a_pasta_compartilhada(monkeypatch):
    tarefa = tarefas.criar(DONO, "comercial", "estrategista", "Matriz BCG com receita", "complexa", "cv_corporativo")
    entrega.anexar(tarefa, b"docx", "Estudo.docx", documentos.MIME_DOCX, "teste")
    assert _payload_documento()["pasta_andar"] == "COMERCIAL" and not _payload_documento()["restrita"]
    entrega.anexar(tarefa, b"docx", "Estudo.docx", documentos.MIME_DOCX, "teste", restrito=True)
    assert _payload_documento()["pasta_andar"] == "COMERCIAL/RESTRITO" and _payload_documento()["restrita"]
    # O selo decide: resposta de quem vê o financeiro, com valores, sai restrita.
    capturado = {}
    monkeypatch.setattr(entrega, "anexar", lambda *a, **k: capturado.update(k) or "id")
    monkeypatch.setattr(auth, "ve_financeiro", lambda _l: True)
    linha = {"id": tarefa, "status": "concluida", "texto": "Matriz BCG", "agente": "estrategista",
             "modelo": estudos.MODELO, "empresa": "cv_corporativo", "usuario": DONO, "andar": "comercial",
             "resposta": "Receita de R$ 10.000 no trimestre. " + "Análise. " * 200}
    monkeypatch.setattr(entrega, "de", lambda _id: [])
    assert entrega.documento_da_resposta(linha) == "id" and capturado == {"restrito": True}


# --- N2-construtor-02: Construtor bloqueado no Comercial ----------------------------------------------------------

def test_construtor_nao_cria_agente_no_comercial():
    with pytest.raises(ad.ErroValidacao, match="não recebe agentes novos"):
        ad.validar({"nome": "Vendedor Teste", "andar": "comercial", "setor": "corporativo", "funcao": "Vendas",
                    "goal": "Vender eventos corporativos", "backstory": "x" * 450, "aparencia": {}})
    assert "comercial" not in ad.setores_com_vagas() and "marketing" in ad.setores_com_vagas()
