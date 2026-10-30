"""Max sem cota, Max que falha e trabalhador sem Drive (revisão de 30/10/2026, itens 1.2-1.4). Banco temporário
(tests/conftest.py). Os testes do trabalhador (scripts/max) rodam quando a pasta está montada em /repo/scripts/max:

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -v "$(pwd -W)/scripts/max:/repo/scripts/max:ro" \
      -w /app -e PYTHONPATH=/app api python -m pytest -p no:cacheprovider /testes/test_max_resiliencia.py
"""

import asyncio
import sys
from pathlib import Path

import pytest

import orquestrador
import producao
import saude
import tarefas
from estado import buscar_agente
from roteamento import Etapa

tarefas.iniciar()
MAX = "claude-code/max"


def test_max_sem_cota_pausa_30_min_e_nunca_e_afastado():
    tipo, ate, _ = saude._classificar("Claude Code (Max): You've hit your usage limit · resets 7:30pm")
    assert tipo == "cota" and ate > 0
    for _ in range(5):  # falhas repetidas do Max: pausa curta, nunca 7 dias fora da rota
        saude.registrar_falha(MAX, "Claude Code (Max): erro durante a execução")
    linha = saude._db().execute("SELECT tipo, afastamentos FROM saude_modelos WHERE modelo = ?", (MAX,)).fetchone()
    assert linha["tipo"] != "afastado" and linha["afastamentos"] == 0


def test_falha_do_modelo_segue_para_o_proximo_e_nao_vira_erro_interno(monkeypatch):
    from agents import executor

    async def falha(*_args, **_kwargs):
        raise saude.FalhaDoModelo("Claude Code (Max): usage limit")

    monkeypatch.setattr(executor, "executar", falha)
    tarefa_id = tarefas.criar("ana-max", "marketing", "copywriter", "Legenda do Lodge 3", "simples")
    agente = buscar_agente("marketing", "copywriter")
    resultado, erro = asyncio.run(orquestrador._tentar(tarefas.obter(tarefa_id), agente, Etapa(MAX, 900)))
    assert resultado is None and "usage limit" in erro  # devolve a falha (o próximo modelo tenta), sem ErroInterno


def test_plano_sem_json_e_falha_do_modelo():
    from agents import projeto

    for resposta in ("Não consegui planejar.", '{"etapas": [{"agente": "copywriter", "instrucao": "x",]}'):
        with pytest.raises(saude.FalhaDoModelo):
            projeto._extrair_plano(resposta)


def _producao(status: str) -> int:
    tarefa_id = tarefas.criar("ana-max", "marketing", "criador_imagens", "Produza a peça final do projeto #1", "media")
    tarefas.atualizar(tarefa_id, status=status)
    return tarefa_id


def test_peca_sem_cota_volta_para_a_fila(monkeypatch):
    import atividade
    import monday

    async def nada(*_args):
        return None

    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(atividade, "liberar", nada)
    monkeypatch.setattr(monday, "andamento", lambda *_a, **_k: None)
    tarefa_id = _producao("produzindo")
    asyncio.run(producao.devolver(tarefa_id, producao.Falha(erro="You've hit your usage limit"), ""))
    assert tarefas.obter(tarefa_id)["status"] == "producao"
    assert not saude.disponivel(MAX)  # o Max sai da rota até a cota voltar


def test_sem_drive_o_trabalhador_so_recebe_trabalhos(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(producao, "_retomar_orfaos", lambda: [])
    tarefa_id = _producao("producao")
    item = asyncio.run(producao.proxima(sem_producao=True, authorization=""))
    assert item == {"producao": None, "trabalho": None}
    assert tarefas.obter(tarefa_id)["status"] == "producao"  # a peça continua esperando na fila


@pytest.fixture
def comum():
    if not Path("/repo/scripts/max/comum.py").exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    sys.path.insert(0, "/repo/scripts/max")
    import comum as modulo
    return modulo


def test_trabalhador_reconhece_falta_de_cota(comum, monkeypatch, tmp_path):
    class Processo:
        returncode = 1

        def __init__(self, *_a, stdout=None, **_k):
            stdout.write('{"is_error": true, "result": "Claude AI usage limit reached|1793394000"}')
            self.stdin = type("E", (), {"write": lambda *_: None, "close": lambda *_: None})()

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(comum.subprocess, "Popen", Processo)
    with pytest.raises(comum.MaxSemCota):
        comum.rodar_claude(["claude"], "oi", tmp_path, 60)
    assert not comum.SEM_COTA.search("Claude Code terminou com erro (erro durante a execução).")


@pytest.fixture
def areia(tmp_path, monkeypatch):
    """A caixa de areia da produção (scripts/max/caixa_de_areia), sem instalar o gancho no processo do pytest."""
    arquivo = Path("/repo/scripts/max/caixa_de_areia/sitecustomize.py")
    if not arquivo.exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    import importlib.util

    spec = importlib.util.spec_from_file_location("areia_teste", arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # sem as variáveis de ambiente: nenhum gancho instalado
    peca = tmp_path / "peca"
    peca.mkdir()
    monkeypatch.setattr(modulo, "_BLOQUEADAS", [str(tmp_path / "repo")])
    monkeypatch.setattr(modulo, "_LIBERADAS", [])
    monkeypatch.setattr(modulo, "_ESCRITA", [str(peca)])
    monkeypatch.setattr(modulo, "_PROGRAMAS", {"ffmpeg", "python"})
    return modulo, tmp_path, peca


def test_caixa_de_areia_bloqueia_segredo_repositorio_rede_e_programas(areia):
    modulo, raiz, peca = areia
    bloqueados = [("open", (str(raiz / "repo" / "README.md"), "r", 0)),
                  ("open", (str(peca / ".env"), "r", 0)),
                  ("open", (str(raiz / "fora.txt"), "w", 0)),
                  ("socket.connect", (None, ("8.8.8.8", 53))),
                  ("socket.getaddrinfo", ("example.com", 443)),
                  ("subprocess.Popen", (None, ["curl", "http://x"], None, None)),
                  ("subprocess.Popen", (None, "ffmpeg -version & curl http://x", None, None)),
                  ("subprocess.Popen", (None, ["ffmpeg", "-i", "http://example.com/a.mp4", "x.mp4"], None, None)),
                  ("subprocess.Popen", (None, ["python", "-I", "-c", "1"], None, None)),
                  ("ctypes.call_function", (0, ()))]
    for evento, args in bloqueados:
        with pytest.raises(PermissionError):
            modulo._gancho(evento, args)
    for evento, args in [("open", (str(peca / "arte.html"), "w", 0)),
                         ("socket.connect", (None, ("127.0.0.1", 8080))),
                         ("subprocess.Popen", (None, ["ffmpeg", "-i", str(peca / "a.mp4"), str(peca / "b.mp4")], None, None))]:
        modulo._gancho(evento, args)  # a produção normal continua


# --- Item 1.10: "Parar" de verdade --------------------------------------------------------------------------------

def _parar(tarefa_id: int) -> None:
    tarefas.atualizar(tarefa_id, status="falhou", motivo=f"{tarefas.MOTIVO_PARADA} por Ana.")


def test_parar_cancela_execucao_e_trabalho_do_max_na_fila():
    import max_texto

    tarefa_id = tarefas.criar("ana-parar", "marketing", "copywriter", "Legenda", "simples")
    with max_texto._db() as db:
        trabalho = db.execute("INSERT INTO trabalhos_max (tipo, payload, status, criado_em) "
                              "VALUES ('texto', '{}', 'pendente', ?)", (tarefas._agora(),)).lastrowid
    max_texto.registrar_trabalho(tarefa_id, trabalho)

    async def cenario():
        execucao = asyncio.create_task(asyncio.sleep(60))
        orquestrador._execucoes[tarefa_id] = execucao
        orquestrador.interromper(tarefa_id)
        with pytest.raises(asyncio.CancelledError):
            await execucao

    asyncio.run(cenario())
    status = max_texto._db().execute("SELECT status FROM trabalhos_max WHERE id = ?", (trabalho,)).fetchone()[0]
    assert status == "falhou"  # o Max não roda um pedido que ninguém espera mais


def test_tarefa_parada_nao_tenta_outro_modelo(monkeypatch):
    tentativas = []

    async def tentar(*_a):
        tentativas.append(1)
        return None, "falhou"

    monkeypatch.setattr(orquestrador, "_tentar", tentar)
    tarefa_id = tarefas.criar("ana-parar", "marketing", "copywriter", "Legenda", "simples")
    _parar(tarefa_id)
    agente = buscar_agente("marketing", "copywriter")
    assert asyncio.run(orquestrador._executar_etapas(tarefas.obter(tarefa_id), agente,
                                                     [Etapa("openrouter/a:free", 60), Etapa("ollama/b", 60)]))
    assert tentativas == []


def test_peca_parada_concluida_pelo_max_e_descartada_sem_travar_a_fila(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    tarefa_id = _producao("produzindo")
    _parar(tarefa_id)
    conclusao = producao.Conclusao(resumo="ok", pasta="MARKETING/x", arquivos=["a.png"], link="")
    resposta = asyncio.run(producao.concluir(tarefa_id, conclusao, ""))
    assert resposta == {"ok": True, "descartada": True}


# --- Item 1.11: pergunta antiga não sequestra o próximo pedido -----------------------------------------------------

def _espera(texto: str, resposta: str, pergunta: str, criada_em: str | None = None) -> int:
    import espera

    tarefa_id = tarefas.criar("ana-espera", "marketing", "gestor", texto, "media")
    tarefas.atualizar(tarefa_id, status="concluida", resposta=resposta)
    espera.guardar(tarefa_id, "ana-espera", "marketing", "gestor", pergunta)
    if criada_em:
        with espera._db() as db:
            db.execute("UPDATE producao_em_espera SET criada_em = ? WHERE tarefa_id = ?", (criada_em, tarefa_id))
    return tarefa_id


def test_pergunta_vence_em_6_horas():
    import espera

    _espera("Post do Lodge 1", "Plano...", "Qual data?", "2026-10-01T10:00:00Z")
    assert espera.no_chat("ana-espera", "marketing", "gestor") is None


def test_pedido_novo_nao_vira_resposta_da_pergunta_antiga():
    import espera

    tarefa_id = _espera("Post do Lodge 1 no Réveillon", "Plano do Lodge 1", "Qual data você prefere?")
    pendente = espera.no_chat("ana-espera", "marketing", "gestor")
    assert pendente["tarefa_id"] == tarefa_id
    assert espera.e_pedido_novo("Faça um post do Lodge 10", pendente)
    assert espera.e_pedido_novo("E o Lodge 10, como fica?", pendente)  # imóvel que não era do trabalho
    for resposta in ("dia 20/11", "Pode seguir", "Sim, o Lodge 1 mesmo", "o primeiro"):
        assert not espera.e_pedido_novo(resposta, pendente), resposta
    assert asyncio.run(orquestrador.retomar_producao(pendente, "Faça um post do Lodge 10")) is None
    assert espera.no_chat("ana-espera", "marketing", "gestor") is not None  # a espera segue para a resposta


# --- Seção 2: Max e produção (2.1, 2.4, 2.5, 2.6, 2.10) --------------------------------------------------------------

def test_sobrecarga_e_resposta_vazia_nao_afastam_e_413_nao_pausa():
    assert saude._classificar("Invalid response from LLM call - None or empty.")[0] == "limite"
    assert saude._classificar("Error code: 503 - overloaded")[0] == "limite"
    tipo, ate, _ = saude._classificar("Error code: 413 - Request too large for model")
    assert tipo == "grande" and ate <= __import__("time").time() + 1


def test_devolver_modelo_a_rota():
    saude.registrar_falha("openrouter/teste:free", "404 not found")
    assert not saude.disponivel("openrouter/teste:free")
    assert saude.devolver_a_rota("openrouter/teste:free")
    assert saude.disponivel("openrouter/teste:free")


def test_erro_ao_montar_a_peca_nao_muda_o_estado_e_falha_na_terceira(monkeypatch):
    import atividade
    import monday

    async def nada(*_a):
        return None

    async def quebra(_linha):
        raise RuntimeError("Monday fora do ar")

    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(producao, "_retomar_orfaos", lambda: [])
    monkeypatch.setattr(producao, "_montar_producao", quebra)
    monkeypatch.setattr(atividade, "ocupar", nada)
    monkeypatch.setattr(atividade, "liberar", nada)
    monkeypatch.setattr(monday, "andamento", lambda *_a, **_k: None)
    import orquestrador as orq

    async def entregar(*_a):
        return None

    monkeypatch.setattr(orq, "_entregar", entregar)
    monkeypatch.setattr(orq, "entregar_na_origem", entregar)
    with tarefas._db() as db:  # só esta peça na fila
        db.execute("UPDATE tarefas SET status = 'falhou' WHERE status = 'producao'")
    tarefa_id = _producao("producao")
    for _ in range(2):
        assert asyncio.run(producao.proxima(authorization=""))["producao"] is None
        assert tarefas.obter(tarefa_id)["status"] == "producao"  # nada mudou: sem eventos duplicados
    asyncio.run(producao.proxima(authorization=""))
    assert tarefas.obter(tarefa_id)["status"] == "falhou"


@pytest.fixture
def trabalhador(monkeypatch):
    if not Path("/repo/scripts/max/trabalhador_max.py").exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    sys.path.insert(0, "/repo/scripts/max")
    try:
        import trabalhador_max
    except Exception as erro:  # dependências do PC (ex.: catálogo do Drive) podem faltar no contêiner
        pytest.skip(f"trabalhador indisponível no contêiner: {erro}")
    return trabalhador_max


def test_entrega_nunca_sobrescreve_arte_no_drive(trabalhador, tmp_path):
    original = tmp_path / "arte.png"
    original.write_bytes(b"original")
    assert trabalhador.sem_sobrescrever(original, 2).name == "arte_v2.png"
    (tmp_path / "arte_v2.png").write_bytes(b"x")
    assert trabalhador.sem_sobrescrever(original, 2).name == "arte_2.png"
    assert trabalhador.sem_sobrescrever(tmp_path / "nova.png", 1).name == "nova.png"


# --- 2.2 e 2.8: trabalho que ninguém espera é cancelado; tentativa que estourou não grava ----------------------------

def _trabalho(tipo: str, status: str) -> int:
    with producao._db() as db:
        return db.execute("INSERT INTO trabalhos_max (tipo, payload, status, criado_em) VALUES (?, '{}', ?, ?)",
                          (tipo, status, tarefas._agora())).lastrowid


def test_reinicio_cancela_pesquisa_e_conclusao_tardia_e_aceita(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    pesquisa = _trabalho("prospeccao", "executando")
    producao.iniciar()
    assert producao.obter_trabalho(pesquisa)["status"] == "cancelado"
    assert asyncio.run(producao.status_do_trabalho(pesquisa, ""))["status"] == "cancelado"
    asyncio.run(producao.concluir_trabalho(pesquisa, producao.Resultado(resultado="tarde demais"), ""))  # sem 404
    assert producao.obter_trabalho(pesquisa)["status"] == "cancelado"


def test_tentativa_que_estourou_o_tempo_nao_grava_a_etapa(tmp_path, monkeypatch):
    import threading

    from agents import projeto

    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    cancelar = threading.Event()
    plano = ('{"entendimento": "E", "duvida": "", "titulo": "T", "etapas": '
             '[{"agente": "copywriter", "instrucao": "Textos", "fase": 1}]}')

    def executar(agente, descricao, esperado, papel):
        if "JSON com o entendimento" in esperado:
            return plano
        cancelar.set()  # o tempo estourou enquanto o modelo escrevia
        return "texto atrasado"

    with pytest.raises(projeto.Cancelado):
        projeto.executar_projeto(9, "pedido", "CTX", executar, cancelar)
    assert not list((tmp_path / "9" / "etapas").glob("*.md"))


def test_peca_le_so_as_fotos_da_propria_empresa(trabalhador):
    liberadas, bloqueadas = trabalhador.pastas_de_fotos("casa_vero")
    assert trabalhador.catalogo_fotos_empresas.FOTOS_EVENTOS in bloqueadas
    assert trabalhador.catalogo_fotos_empresas.FOTOS_EVENTOS not in liberadas
    liberadas, bloqueadas = trabalhador.pastas_de_fotos("cv_corporativo")
    assert all(p in bloqueadas for p in trabalhador.catalogo_fotos_empresas.PASTAS_VERO)


def test_conclusao_repetida_da_peca_nao_trava_o_trabalhador(monkeypatch):
    import atividade
    import monday

    async def nada(*_a):
        return None

    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(atividade, "liberar", nada)
    monkeypatch.setattr(monday, "andamento", lambda *_a, **_k: None)
    import orquestrador as orq

    monkeypatch.setattr(orq, "_entregar", nada)
    monkeypatch.setattr(orq, "entregar_na_origem", nada)
    tarefa_id = _producao("produzindo")
    conclusao = producao.Conclusao(resumo="ok", pasta="MARKETING/x", arquivos=["a.png"], link="")
    asyncio.run(producao.concluir(tarefa_id, conclusao, ""))
    assert asyncio.run(producao.concluir(tarefa_id, conclusao, "")) == {"ok": True, "descartada": True}
