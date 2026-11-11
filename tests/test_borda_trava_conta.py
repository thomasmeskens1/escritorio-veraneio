"""Portas fechadas para a internet (brainstorm de novembro, Onda 1, conserto 6).

despachante-05: a chave de operador e as rotas do trabalhador do Max só valem dentro do PC (backend/borda.py). O
pedido de fora é reconhecido pelos cabeçalhos que o Worker põe (deploy/worker/src/index.js), porque o IP é sempre
local. construtor-07: a trava por senha errada vale por conta, e não só por (login, IP).
"""

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import borda
import config
import producao

LOGIN = "usuario.teste@exemplo.com"
TOKEN = "chave-de-operador-ficticia-para-teste-0123456789"  # segredos: ignorar (valor fictício de teste)
# Exatamente o que o Worker manda (versão nova, com a marca; a antiga não tinha X-Escritorio-Borda).
CABECALHOS_WORKER = {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https",
                     "X-Forwarded-Host": "escritorio-veraneio.exemplo.workers.dev", "X-Escritorio-Borda": "worker",
                     "CF-Connecting-IP": "203.0.113.7", "CF-Ray": "0000000000000000-GRU"}
WORKER_ANTIGO = {k: v for k, v in CABECALHOS_WORKER.items() if k != "X-Escritorio-Borda"}


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    import main

    (tmp_path / "operador.token").write_text(TOKEN, encoding="utf-8")
    monkeypatch.setattr(config, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(producao, "ARQUIVO_TOKEN", tmp_path / "operador.token")
    monkeypatch.setattr(config, "DONO_MAX", LOGIN)
    usuarios = {LOGIN: {"nome": "Teste", "role": "diretoria", "senha": "x", "sessao": 0}}
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: usuarios)
    return TestClient(main.app)  # sem "with": a subida (vigias, fila do Max) não roda


def _operador():
    return {"Authorization": f"Bearer {TOKEN}"}


def _dono():
    return {"Authorization": "Bearer " + auth.criar_token({"login": LOGIN, "nome": "Teste", "role": "diretoria"})}


# --- reconhecer de onde veio ---------------------------------------------------------------------------------------

def test_sem_cabecalho_da_borda_e_local():
    assert not borda.veio_de_fora({"Authorization": "Bearer x", "Content-Type": "application/json"})
    for nome in ("X-Escritorio-Borda", "x-forwarded-host", "X-Forwarded-For", "CF-Connecting-IP", "cf-ray"):
        assert borda.veio_de_fora({nome: ""}), nome  # basta um deles, mesmo vazio


def test_rotas_internas_e_rotas_da_equipe():
    for caminho in ("/api/producao/proxima", "/api/producao/7/concluir", "/api/producao/7/folha",
                    "/api/producao/trabalhos/3/status", "/api/cerebro/ingerir", "/api/integracoes/monday/criativos/9"):
        assert borda.caminho_interno(caminho), caminho
    for caminho in ("/", "/api/login", "/api/producao/uso-max", "/api/producao/7/desdobrar", "/api/producao/trabalhos",
                    "/api/integracoes/monday/webhook/abc", "/api/cerebro/estatisticas", "/api/saude"):
        assert not borda.caminho_interno(caminho), caminho


# --- o trabalhador do Max (localhost) segue funcionando --------------------------------------------------------------

def _pasta_max() -> Path | None:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "comum.py").exists():
            return pasta
    return None


def test_toda_rota_que_o_trabalhador_chama_e_interna():
    """Se o trabalhador ganhar uma rota nova, ela precisa entrar em CAMINHOS_INTERNOS (e no Worker)."""
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não encontrado (monte em /repo/scripts)")
    caminhos = set()
    for arquivo in pasta.glob("*.py"):
        texto = re.sub(r"\{[^{}\n]*\}", "1", arquivo.read_text(encoding="utf-8"))  # f"/x/{producao['id']}" -> /x/1
        caminhos.update(re.findall(r"[\"'](/api/[^\"'?\s]+)", texto))
    assert caminhos, "nenhuma rota encontrada nos scripts do Max"
    assert {c for c in caminhos if not borda.caminho_interno(c)} == set()


def test_trabalhador_local_continua_entrando(cliente, monkeypatch):
    """O pedido montado por scripts/max/comum.py (cabeçalhos de verdade) chega ao backend e passa pela chave."""
    pasta = _pasta_max()
    if not pasta:
        pytest.skip("scripts/max não encontrado (monte em /repo/scripts)")
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    import comum

    capturado = {}

    def urlopen_falso(req, timeout=None):
        capturado.update(req.header_items())
        raise RuntimeError("sem rede no teste")

    monkeypatch.setattr(comum, "ARQUIVO_TOKEN", config.DADOS_DIR / "operador.token")
    monkeypatch.setattr(comum.urllib.request, "urlopen", urlopen_falso)
    with pytest.raises(RuntimeError):
        comum.chamar("GET", "/api/producao/trabalhos/999999/status")
    assert not borda.veio_de_fora(capturado)
    resposta = cliente.get("/api/producao/trabalhos/999999/status", headers=capturado)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"status": "cancelado"}  # trabalho inexistente: o trabalhador encerra o Claude Code


def test_chave_de_operador_vale_em_localhost(cliente):
    resposta = cliente.post("/api/producao/trabalhos", json={"tipo": "inexistente"}, headers=_operador())
    assert resposta.status_code == 422  # passou da chave; parou só no tipo inválido (nada é criado)


# --- quem chega pela internet ------------------------------------------------------------------------------------

@pytest.mark.parametrize("worker", [CABECALHOS_WORKER, WORKER_ANTIGO], ids=["worker-novo", "worker-antigo"])
def test_rota_do_trabalhador_some_para_quem_vem_de_fora(cliente, worker):
    resposta = cliente.get("/api/producao/trabalhos/999999/status", headers={**worker, **_operador()})
    assert resposta.status_code == 404
    assert cliente.post("/api/cerebro/ingerir", json={}, headers={**worker, **_operador()}).status_code == 404
    # Nem o dono usa essas rotas de fora: são só do trabalhador.
    assert cliente.get("/api/producao/proxima", headers={**worker, **_dono()}).status_code == 404


@pytest.mark.parametrize("worker", [CABECALHOS_WORKER, WORKER_ANTIGO], ids=["worker-novo", "worker-antigo"])
def test_chave_de_operador_recusada_pela_internet(cliente, worker):
    resposta = cliente.post("/api/producao/trabalhos", json={"tipo": "inexistente"}, headers={**worker, **_operador()})
    assert resposta.status_code == 401
    assert "dentro do PC" in resposta.json()["detail"]


def test_visitante_nao_se_passa_por_local_mandando_cabecalho_vazio(cliente):
    """O Worker grava os cabeçalhos com set: o visitante pode mandar outros, mas não apagar os da borda."""
    resposta = cliente.post("/api/producao/trabalhos", json={"tipo": "inexistente"},
                            headers={"X-Escritorio-Borda": "", **_operador()})
    assert resposta.status_code == 401


def test_equipe_pelo_worker_continua_funcionando(cliente):
    # Login (página pública), saúde e uma rota da equipe com o JWT: a borda não atrapalha.
    assert cliente.get("/api/saude", headers=CABECALHOS_WORKER).status_code in (200, 503)
    login = cliente.post("/api/login", json={"usuario": "ninguem@exemplo.com", "senha": "errada"},
                         headers=CABECALHOS_WORKER)
    assert login.status_code == 401  # chegou ao login (não foi barrado na borda)
    resposta = cliente.post("/api/producao/trabalhos", json={"tipo": "inexistente"}, headers={**CABECALHOS_WORKER,
                                                                                               **_dono()})
    assert resposta.status_code == 422  # o dono, com o login dele, segue usando de fora
    uso = cliente.get("/api/producao/uso-max", headers={**CABECALHOS_WORKER, **_dono()})
    assert uso.status_code == 200, uso.text  # painel da equipe pelo Worker


# --- trava por conta (construtor-07) -------------------------------------------------------------------------------

@pytest.fixture
def contas_limpas(monkeypatch):
    monkeypatch.setattr(auth, "_falhas_conta", {})
    monkeypatch.setattr(auth, "_conta_travada_ate", {})
    avisos = []
    monkeypatch.setattr(auth, "_disparar_aviso", avisos.append)
    return avisos


def test_conta_trava_depois_de_15_erros_na_hora(contas_limpas, monkeypatch):
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: {LOGIN: {}})
    for i in range(auth.MAX_FALHAS_CONTA - 1):
        assert not auth.registrar_falha_conta(LOGIN, agora=100.0 + i)
    assert not auth.conta_travada(LOGIN, agora=200.0)
    assert auth.registrar_falha_conta(" USUARIO.TESTE@exemplo.com ", agora=200.0)  # mesmo login, outra grafia
    assert auth.conta_travada(LOGIN, agora=201.0)
    assert auth.conta_travada(LOGIN, agora=200.0 + auth.BLOQUEIO_CONTA_S - 1)
    assert not auth.conta_travada(LOGIN, agora=200.0 + auth.BLOQUEIO_CONTA_S + 1)  # 30 min depois, solta
    assert contas_limpas == [LOGIN]  # o Telegram avisa uma vez


def test_erros_antigos_saem_da_conta_e_login_certo_zera(contas_limpas):
    for i in range(auth.MAX_FALHAS_CONTA - 1):
        auth.registrar_falha_conta(LOGIN, agora=float(i))
    assert not auth.registrar_falha_conta(LOGIN, agora=auth.JANELA_FALHAS_CONTA_S + 20.0)  # os antigos venceram
    for i in range(auth.MAX_FALHAS_CONTA - 2):
        auth.registrar_falha_conta(LOGIN, agora=5000.0 + i)
    auth.limpar_falhas_conta(LOGIN)
    assert not auth.registrar_falha_conta(LOGIN, agora=5100.0)


def test_login_inexistente_trava_igual_mas_sem_aviso(contas_limpas, monkeypatch):
    monkeypatch.setattr(auth, "carregar_usuarios", lambda: {})
    for i in range(auth.MAX_FALHAS_CONTA):
        auth.registrar_falha_conta("ninguem@exemplo.com", agora=float(i))
    assert auth.conta_travada("ninguem@exemplo.com", agora=20.0)  # resposta igual: não revela quem existe
    assert contas_limpas == []


def test_trocar_de_rede_nao_escapa_da_trava(cliente, contas_limpas, monkeypatch):
    """Pela rota de login: a cada tentativa o (login, IP) é novo, e mesmo assim a conta trava e nem a senha certa entra."""
    import main

    monkeypatch.setattr(main, "_falhas_login", {})
    monkeypatch.setattr(main, "_falhas_ip", {})
    senha_certa = {"login": LOGIN, "nome": "Teste", "role": "diretoria"}
    monkeypatch.setattr(main, "autenticar", lambda usuario, senha: senha_certa if senha == "certa" else None)
    for _ in range(auth.MAX_FALHAS_CONTA):
        main._falhas_login.clear()  # outra rede: a trava antiga por (login, IP) recomeça do zero
        main._falhas_ip.clear()
        assert cliente.post("/api/login", json={"usuario": LOGIN, "senha": "errada"}).status_code == 401
    main._falhas_login.clear()
    assert cliente.post("/api/login", json={"usuario": LOGIN, "senha": "certa"}).status_code == 429
    assert contas_limpas == [LOGIN]
