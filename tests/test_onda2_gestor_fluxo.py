"""Onda 2 de novembro, agente K: pergunta com opções e "Escolha por mim", pedido repetido e planejamento em tabela
gravado no Monday pelo código. Banco temporário (tests/conftest.py); o Monday é sempre falso (nada é escrito)."""

import json
import threading

import pytest

import pedido_repetido

pedido_repetido.ATIVO = True  # o aviso está desligado em produção; os testes conferem o mecanismo
import plano_tabela
import tarefas
from agents import consulta_repetida, pergunta_gestor, projeto

tarefas.iniciar()

PERGUNTA = "Quais Lodges do Nordeste entram no carrossel?"
COM_DUVIDA = ('{"entendimento": "Carrossel com Lodges do Nordeste.", "duvida": "' + PERGUNTA + '", '
              '"opcoes": ["Lodges 12 e 40", "Lodges 12, 40 e 77"], "pode_decidir": true, "titulo": "", "etapas": []}')
COM_PLANO = ('{"entendimento": "Escolhi os Lodges 12 e 40 porque têm fotos.", "duvida": "", "titulo": "Carrossel NE", '
             '"etapas": [{"agente": "copywriter", "instrucao": "Textos", "fase": 1}]}')


def _gestor(respostas, descricoes):
    """Devolve, em ordem, as respostas do plano; as outras chamadas recebem uma entrega fixa."""
    fila = list(respostas)

    def executar(agente, descricao, esperado, papel):
        descricoes.append((agente, esperado, descricao))
        if "JSON com o entendimento" in esperado:
            return fila.pop(0) if len(fila) > 1 else fila[0]
        return "Entrega final." if agente == "gestor" else f"entrega de {agente}"
    return executar


# --- 1. Pergunta com opções e "Escolha por mim" ---------------------------------------------------------------

def test_delegacao_reconhecida():
    for texto in ("Escolha por mim", "acho que você pode escolher", "você escolhe", "tanto faz", "decide você",
                  "Pode preencher por favor", "fica a seu critério"):
        assert pergunta_gestor.e_delegacao(texto), texto
    for texto in ("Os Lodges 12 e 40", "não pode escolher, eu mando a lista", "Quero o Lodge 3"):
        assert not pergunta_gestor.e_delegacao(texto), texto


def test_duvida_sai_como_formulario_com_opcoes(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    descricoes = []
    final = projeto.executar_projeto(990001, "Carrossel do Nordeste", "CTX", _gestor([COM_DUVIDA], descricoes),
                                     threading.Event())
    assert final.endswith(f"PERGUNTA: {PERGUNTA}")  # a espera da produção continua lendo esta linha
    bloco = json.loads(final.split("<<FORMULARIO>>")[1].split("<<FIM DO FORMULARIO>>")[0])
    assert bloco["campos"][0]["opcoes"] == ["Lodges 12 e 40", "Lodges 12, 40 e 77", "Escolha por mim"]
    assert '"opcoes"' in descricoes[0][2] and "pode_decidir" in descricoes[0][2]


def test_fato_da_equipe_nao_oferece_escolha_por_mim(tmp_path):
    (tmp_path / "1").mkdir()
    dados = pergunta_gestor.guardar(tmp_path / "1", '{"pode_decidir": true}', "Qual a condição especial do pacote?")
    assert not dados["pode_decidir"]  # a regra do manual 10 §5 vale mesmo que o modelo diga true
    texto = pergunta_gestor.texto_da_pergunta(tmp_path / "1", "", dados["pergunta"])
    assert "Escolha por mim" not in texto and "PENDENTE" in texto


def test_escolha_por_mim_decide_e_a_pergunta_nao_volta(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    login = "usuario.teste@exemplo.com"
    a = tarefas.criar(login, "marketing", "gestor", "Carrossel do Nordeste", "media", "casa_veraneio")
    projeto.executar_projeto(a, "Carrossel do Nordeste", "CTX", _gestor([COM_DUVIDA], []), threading.Event())
    resposta = f"Respostas — Pergunta do Gestor:\n- {PERGUNTA}: Escolha por mim"
    b = tarefas.criar(login, "marketing", "gestor", resposta, "media", "casa_veraneio")
    descricoes = []
    # O modelo insiste duas vezes na mesma pergunta: o sistema decide pela 1ª opção que o próprio Gestor ofereceu.
    final = projeto.executar_projeto(b, resposta, "CTX", _gestor([COM_DUVIDA, COM_DUVIDA, COM_PLANO], descricoes),
                                     threading.Event())
    planos = [d for _, e, d in descricoes if "JSON com o entendimento" in e]
    assert "DECISÕES JÁ TOMADAS" in planos[0] and "DELEGOU" in planos[0]
    assert "DECISÃO FINAL" in planos[-1] and "Lodges 12 e 40" in planos[-1]
    assert "PERGUNTA:" not in final and final.startswith("Entrega final.")
    decisoes = json.loads((tmp_path / str(b) / "decisoes.json").read_text(encoding="utf-8"))
    assert decisoes[0]["delegada"] and decisoes[0]["escolha"] == "Lodges 12 e 40"
    assert "Decisão:" in (tmp_path / str(b) / "plano.md").read_text(encoding="utf-8")
    assert not (tmp_path / str(b) / "duvida.txt").exists()


def test_resposta_dada_e_lembrada_sem_trava_forcada(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    login = "usuario.teste2@exemplo.com"
    a = tarefas.criar(login, "marketing", "gestor", "Carrossel do Nordeste", "media", "casa_veraneio")
    projeto.executar_projeto(a, "Carrossel do Nordeste", "CTX", _gestor([COM_DUVIDA], []), threading.Event())
    b = tarefas.criar(login, "marketing", "gestor", "Os Lodges 12 e 40", "media", "casa_veraneio")
    descricoes = []
    final = projeto.executar_projeto(b, "Os Lodges 12 e 40", "CTX", _gestor([COM_DUVIDA, COM_PLANO], descricoes),
                                     threading.Event())
    planos = [d for _, e, d in descricoes if "JSON com o entendimento" in e]
    assert len(planos) == 2 and "resposta do usuário: Os Lodges 12 e 40" in planos[1]
    assert "PERGUNTA:" not in final


def test_pedido_novo_nao_vira_resposta(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    login = "usuario.teste3@exemplo.com"
    a = tarefas.criar(login, "marketing", "gestor", "Carrossel do Nordeste", "media", "casa_veraneio")
    projeto.executar_projeto(a, "Carrossel do Nordeste", "CTX", _gestor([COM_DUVIDA], []), threading.Event())
    b = tarefas.criar(login, "marketing", "gestor", "Faça um post do Lodge 10 para o feriado", "media", "casa_veraneio")
    (tmp_path / str(b)).mkdir()
    assert pergunta_gestor.decisoes(tmp_path / str(b), "Faça um post do Lodge 10 para o feriado") == []


# --- 2. Pedido repetido: continuar em vez de refazer -------------------------------------------------------------

def _producao(login, texto, empresa="casa_veraneio"):
    import producao

    tarefa_id = tarefas.criar(login, "marketing", "editor_video", texto, "complexa", empresa)
    tarefas.atualizar(tarefa_id, status="concluida", resposta="ok")
    with producao._db() as db:
        db.execute("INSERT INTO producao_info (tarefa_id, titulo, pasta) VALUES (?, ?, ?)", (tarefa_id, "Reels", "/x"))
    return tarefa_id


def test_peca_parecida_oferece_os_tres_botoes():
    login = "usuario.repetido@exemplo.com"
    feita = _producao(login, "Produza a peça final do projeto #1.\n\nPedido original: Reels do Lodge 32 beira-mar"
                             "\n\nResultado consolidado do Gestor:\nLodge 77 e Lodge 80")
    aviso = pedido_repetido.aviso(login, "marketing", "gestor", "Peça final: Reels do Lodge 032 no Juquehy",
                                  "casa_veraneio")
    assert aviso["titulo"] == "Peça parecida" and f"#{feita}" in aviso["texto"]
    rotulos = [o["rotulo"] for o in aviso["opcoes"]]
    assert rotulos == ["Ajuste da v1", "Variante B", "Peça nova"]
    assert aviso["opcoes"][0]["texto"] == f"Ajuste na peça #{feita}: Reels do Lodge 032 no Juquehy"
    for opcao in aviso["opcoes"][1:]:  # o pedido reenviado pelo botão segue sem novo aviso
        assert pedido_repetido.aviso(login, "marketing", "gestor", opcao["texto"], "casa_veraneio") is None
    # Outro formato, outro Lodge, outra empresa ou só planejamento: segue normal.
    for texto, empresa in (("Peça final: Carrossel do Lodge 32", "casa_veraneio"),
                           ("Peça final: Reels do Lodge 77", "casa_veraneio"),
                           ("Peça final: Reels do Lodge 32", "casa_vero"),
                           ("Planejamento: Reels do Lodge 32", "casa_veraneio")):
        assert pedido_repetido.aviso(login, "marketing", "gestor", texto, empresa) is None, texto


def test_pedido_identico_em_2_horas_avisa_sem_bloquear():
    login = "usuario.identico@exemplo.com"
    antes = tarefas.criar(login, "marketing", "gestor", "[Pedido feito ao Copywriter] Texto de boas-vindas da Casa\n\n"
                                                      "FORMATO DA PEÇA (obrigatório): POST", "media", "cv_corporativo")
    aviso = pedido_repetido.aviso(login, "marketing", "copywriter", "Texto de boas-vindas da casa!", "cv_corporativo",
                                  para_o_gestor=True)
    assert aviso["titulo"] == "Pedido repetido" and f"#{antes}" in aviso["texto"]
    assert pedido_repetido.aviso(login, "marketing", "copywriter", aviso["opcoes"][0]["texto"], "cv_corporativo",
                                 para_o_gestor=True) is None
    assert pedido_repetido.aviso(login, "marketing", "copywriter", "Texto de boas-vindas da casa!",
                                 "cv_corporativo") is None  # fica com o especialista: não é o caminho do Gestor


def test_consulta_repetida_ao_cerebro():
    pergunta, resposta = "Monte o planejamento de dezembro da Casa Veraneio", "[1] Lodge 12... " * 50
    assert consulta_repetida.aviso(77001, "social_media", pergunta, resposta) is None
    assert "já recebeu isso" in consulta_repetida.aviso(77001, "social_media", pergunta + "!", resposta)
    assert consulta_repetida.aviso(77001, "social_media", pergunta, resposta) is None  # 3ª: vai inteira
    assert consulta_repetida.aviso(77001, "social_media", pergunta, resposta + " novo") is None  # a base mudou
    assert consulta_repetida.aviso(77001, "copywriter", pergunta, resposta) is None  # outro agente


# --- 3. Planejamento do mês em tabela, gravado no Monday pelo código ---------------------------------------------

LINHAS = [{"data": "2026-12-05", "tipo": "reels", "tema": "Réveillon no Lodge 32", "lodge": "32", "papel": "Descoberta",
           "roteiro": "Abertura no Lodge 32", "legenda": "Virada no Lodge 32"},
          {"data": "", "tipo": "STORIES", "tema": "Contagem regressiva", "lodge": "", "legenda": "não vai"},
          {"data": "2026-12-20", "tipo": "POST", "tema": "Ceia de Natal", "lodge": "040"},
          {"tipo": "FOLDER", "tema": "inválida"}]


def _entrega(linhas=LINHAS):
    return f"Plano de dezembro com 3 peças.\n\n<<PLANO_TABELA>>{json.dumps(linhas)}<<FIM DO PLANO_TABELA>>"


@pytest.fixture
def monday_falso(monkeypatch, tmp_path):
    import monday
    import monday_datas

    criados = []
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    monkeypatch.setattr(monday, "ativo", lambda: True)
    monkeypatch.setattr(monday, "grupo_por_nome", lambda nome, criar=False: {"id": "g1", "title": nome})
    monkeypatch.setattr(monday, "_api", lambda *a, **k: {})
    monkeypatch.setattr(monday_datas, "reposicionar_seguro", lambda item_id: None)

    def criar_item(grupo_id, nome, valores):
        criados.append((nome, valores))
        return {"id": str(len(criados)), "name": nome, "url": f"https://exemplo.monday/{len(criados)}"}
    monkeypatch.setattr(monday, "criar_item", criar_item)
    return criados


def test_tabela_sai_do_texto_e_fica_no_projeto(monday_falso, tmp_path):
    tarefa = tarefas.criar("usuario.plano@exemplo.com", "marketing", "gestor", "Planejamento de dezembro", "media",
                           "casa_veraneio")
    (tmp_path / str(tarefa)).mkdir()
    texto = plano_tabela.com_tabela(tmp_path / str(tarefa), _entrega(), "Planejamento de dezembro")
    assert "<<PLANO_TABELA>>" not in texto and f"[Tabela do planejamento #{tarefa}: 3 peças" in texto
    linhas = plano_tabela.carregar(tarefa)["linhas"]
    assert [l["tipo"] for l in linhas] == ["REELS", "STORIES", "POST"]
    assert linhas[1]["legenda"] == "" and linhas[2]["lodge"] == "40"
    assert plano_tabela.com_tabela(tmp_path / "x", "Texto <<PLANO_TABELA>>[{cortado", "") == "Texto"
    assert plano_tabela.e_planejamento("Monte o planejamento de dezembro da Casa Veraneio")
    assert not plano_tabela.e_planejamento("Post do Lodge 10")


def test_gravar_no_monday_exatamente_o_aprovado(monday_falso, tmp_path):
    tarefa = tarefas.criar("usuario.plano2@exemplo.com", "marketing", "gestor", "Planejamento de dezembro", "media",
                           "casa_veraneio")
    (tmp_path / str(tarefa)).mkdir()
    plano_tabela.com_tabela(tmp_path / str(tarefa), _entrega(), "Planejamento de dezembro")
    E = plano_tabela.Escolha
    # A pessoa desmarcou o STORIES, mudou a data do Reels e trocou o Lodge 32 pelo 35.
    resultado = plano_tabela.gravar(tarefa, [E(indice=0, data="2026-12-06", lodge="35"), E(indice=2, data="2026-12-20",
                                                                                         lodge="40")])
    assert resultado["criados"] == 2 and len(monday_falso) == 2
    nome, valores = monday_falso[0]
    assert nome == "REELS | Réveillon no Lodge 35"
    assert any(v == {"date": "2026-12-06"} for v in valores.values())
    assert "Lodge 35" in json.dumps(valores, ensure_ascii=False) and "Lodge 32" not in json.dumps(valores)
    assert monday_falso[1][0] == "POST | Ceia de Natal (Lodge 40)"
    # Clique duplo / "Gravar tudo" depois: o que já foi não grava de novo; o STORIES entra sozinho.
    tudo = plano_tabela.gravar(tarefa, [E(indice=0), E(indice=1), E(indice=2)])
    assert tudo["criados"] == 1 and len(monday_falso) == 3 and monday_falso[2][0].startswith("STORIES |")
    assert all(l["gravado"] for l in plano_tabela.carregar(tarefa)["linhas"])
    with pytest.raises(ValueError):
        plano_tabela.gravar(tarefa, [E(indice=9)])
    with pytest.raises(ValueError):
        plano_tabela.gravar(tarefa, [E(indice=0, data="06/12/2026")])


def test_lance_no_monday_abre_a_tabela(monday_falso, tmp_path):
    tarefa = tarefas.criar("usuario.plano3@exemplo.com", "marketing", "gestor", "Planejamento de dezembro", "media",
                           "casa_veraneio")
    assert plano_tabela.aviso_lancar(tarefa) is None  # sem tabela: segue o caminho antigo (Social Media)
    (tmp_path / str(tarefa)).mkdir()
    plano_tabela.com_tabela(tmp_path / str(tarefa), _entrega(), "")
    aviso = plano_tabela.aviso_lancar(tarefa)
    assert aviso["titulo"] == "Gravar no Monday" and f"#{tarefa}: 3 peças" in aviso["texto"]


def test_projeto_de_planejamento_pede_e_guarda_a_tabela(monday_falso, tmp_path):
    tarefa = tarefas.criar("usuario.plano4@exemplo.com", "marketing", "gestor", "Planejamento de dezembro", "media",
                           "casa_veraneio")
    descricoes = []

    def executar(agente, descricao, esperado, papel):
        descricoes.append(descricao)
        if "JSON com o entendimento" in esperado:
            return COM_PLANO
        return _entrega() if agente == "gestor" else "entrega"
    final = projeto.executar_projeto(tarefa, "Planejamento: monte o planejamento de dezembro", "CTX", executar,
                                     threading.Event())
    assert "<<PLANO_TABELA>>" in descricoes[-1]  # a consolidação recebe a instrução da tabela
    assert f"[Tabela do planejamento #{tarefa}: 3 peças" in final and "<<PLANO_TABELA>>" not in final
