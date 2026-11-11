"""Onda 1, agente D (brainstorm de 11/11/2026): Drive do PC incompleto (despachante-10), coletas do painel paradas e
rodapé de procedência (analista_metricas-07, -27, -34) e caixa de saída do trabalhador (despachante-07). Banco
temporário (tests/conftest.py) e um analytics.db de teste, com dados fictícios: o painel real nunca é lido."""

import asyncio
import sqlite3
import sys
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import alarme_telegram
import drive_pc
import painel_coletas
import producao
import saude
import tarefas

tarefas.iniciar()


def _producao(texto: str, agente: str = "criador_imagens") -> int:
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", agente, texto, "media")
    tarefas.atualizar(tarefa_id, status="producao")
    return tarefa_id


def _so_estas(*ids: int) -> None:
    with tarefas._db() as db:
        db.execute(f"UPDATE tarefas SET status = 'falhou' WHERE status = 'producao' "
                   f"AND id NOT IN ({','.join('?' * len(ids))})", ids)


# --- Drive do PC (despachante-10) ---------------------------------------------------------------------------------

def test_peca_sem_acervo_e_reconhecida():
    assert not drive_pc.precisa_do_acervo("criador_imagens", "Capa do carrossel Janeiro no Nordeste, sem nenhuma casa, "
                                                             "com o logo da Casa Veraneio")
    assert drive_pc.precisa_do_acervo("criador_imagens", "Post com fotos do Lodge 12")
    assert drive_pc.precisa_do_acervo("editor_video", "Vídeo tipográfico")  # vídeo usa as filmagens: espera


def test_aviso_do_drive_so_depois_de_20_min():
    agora = 1_000_000.0
    drive_pc.registrar("acervo dos Lodges", True, agora)
    assert drive_pc.aviso(agora + 60) is None
    drive_pc.registrar("acervo dos Lodges", True, agora + 20 * 60)  # o trabalhador continua avisando
    texto = drive_pc.aviso(agora + 21 * 60)
    assert texto and "acervo dos Lodges" in texto and "21 min" in texto
    assert drive_pc.aviso(agora + 21 * 60 + drive_pc.SEM_NOTICIA_S + 60) is None  # trabalhador calado
    drive_pc.registrar("", False, agora + 30 * 60)
    assert drive_pc.aviso(agora + 31 * 60) is None


def test_sem_acervo_sai_a_peca_que_nao_usa_o_acervo(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(producao, "_retomar_orfaos", lambda: [])
    usa = _producao("Post com fotos do Lodge 3")
    nao_usa = _producao("Capa tipográfica Janeiro no Nordeste, sem nenhuma casa")
    _so_estas(usa, nao_usa)
    montadas = []

    async def montar(linha):
        montadas.append(linha["id"])
        return {"tarefa_id": linha["id"]}

    async def nada(*_a):
        return None

    import atividade
    import monday

    monkeypatch.setattr(producao, "_montar_producao", montar)
    monkeypatch.setattr(atividade, "ocupar", nada)
    monkeypatch.setattr(monday, "andamento", lambda *_a, **_k: None)
    item = asyncio.run(producao.proxima(sem_producao=True, faltando="acervo dos Lodges", authorization=""))
    assert item["producao"] == {"tarefa_id": nao_usa} and montadas == [nao_usa]
    assert tarefas.obter(usa)["status"] == "producao"  # a que usa o acervo espera
    # Quem pediu a peça que espera recebe o aviso uma vez (evento espera_drive), não a cada consulta.
    asyncio.run(producao.proxima(sem_producao=True, faltando="acervo dos Lodges", authorization=""))
    eventos = [e for e in tarefas.eventos_de([usa])[usa] if e["tipo"] == "espera_drive"]
    assert len(eventos) == 1
    # Drive inteiro fora: nenhuma peça sai.
    assert asyncio.run(producao.proxima(sem_producao=True, faltando="marcas, fontes", authorization=""))[
        "producao"] is None
    drive_pc.registrar("", False)
    tarefas.atualizar(usa, status="falhou")


# --- Painel analítico: coletas e rodapé (analista_metricas-07, -27, -34) ------------------------------------------

@pytest.fixture
def painel(tmp_path, monkeypatch):
    banco = tmp_path / "analytics.db"
    agora = datetime.now()
    with sqlite3.connect(banco) as db:
        db.execute("CREATE TABLE execucoes (id INTEGER PRIMARY KEY AUTOINCREMENT, iniciado_em TEXT, finalizado_em TEXT, "
                   "contas_atualizadas INTEGER, erros TEXT, escopo TEXT)")
        db.execute("CREATE TABLE instagram_diario (data TEXT)")
        rodadas = [  # da mais antiga para a mais nova (dados fictícios)
            "Google Ads: autorização expirada; refaça o login",
            "YouTube (canal) (400): API key not valid\nGoogle Ads: autorização expirada; refaça o login\n"
            "Instagram insights (@contateste): limite de uso",
            "YouTube (canal) (400): API key not valid\nYouTube Analytics: autorização expirada; refaça o login\n"
            "Google Ads: autorização expirada; refaça o login",
            "YouTube (canal) (400): API key not valid\nYouTube Analytics: autorização expirada; refaça o login\n"
            "Google Ads: autorização expirada; refaça o login\nBrevo: falha de conexão (ConnectError)",
        ]
        for n, erros in enumerate(rodadas):
            fim = (agora - timedelta(hours=len(rodadas) - n)).isoformat(timespec="seconds")
            db.execute("INSERT INTO execucoes (iniciado_em, finalizado_em, contas_atualizadas, erros) VALUES (?, ?, 3, ?)",
                       (fim, fim, erros))
        db.execute("INSERT INTO execucoes (iniciado_em, finalizado_em, contas_atualizadas, erros, escopo) "
                   "VALUES (?, ?, 1, 'CRM (Monday): erro', 'crm')", (agora.isoformat(), agora.isoformat()))
    monkeypatch.setattr(painel_coletas, "BANCO", banco)
    return banco


def test_coleta_parada_vira_aviso_por_fonte(painel):
    falhas = {f["fonte"]: f for f in painel_coletas.fontes_com_falha()}
    assert set(falhas) == {"YouTube (canal)", "YouTube Analytics", "Google Ads"}  # Brevo falhou só uma vez
    assert falhas["Google Ads"]["rodadas"] == 4 and falhas["YouTube Analytics"]["rodadas"] == 2
    avisos = painel_coletas.avisos()
    assert len(avisos) == 3 and all(a.startswith("Coleta do painel parada:") for a in avisos)
    assert not any("CRM" in a for a in avisos)  # atualização de aba (escopo) não conta como rodada completa


def test_coleta_inteira_parada(painel):
    assert any("sem coleta completa" in a for a in painel_coletas.avisos(datetime.now() + timedelta(hours=20)))
    assert not any("sem coleta completa" in a for a in painel_coletas.avisos())


def test_aviso_da_coleta_vai_ao_telegram(painel, monkeypatch):
    monkeypatch.setattr(saude, "ollama_ok", lambda: True)
    avisos = saude.avisos_da_operacao()
    assert any("YouTube Analytics" in a for a in avisos)
    enviadas = []
    alarme = alarme_telegram.Alarme(enviadas.append)
    alarme.conferir(avisos, agora=0)
    alarme.conferir(avisos, agora=600)  # o mesmo problema não é repetido a cada 5 min
    assert len(enviadas) == 1 and "Google Ads" in enviadas[0]


def test_sem_banco_do_painel_nada_quebra(tmp_path, monkeypatch):
    monkeypatch.setattr(painel_coletas, "BANCO", tmp_path / "nao_existe.db")
    assert painel_coletas.avisos() == [] and painel_coletas.fontes_com_falha() == []


def test_rodape_de_procedencia_escrito_pelo_sistema(painel):
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "marketing", "analista_metricas", "Como foi o mês?", "media")
    assert painel_coletas.com_rodape(tarefa_id, "Sem números.") == "Sem números."  # não consultou o painel
    for detalhe in ("comparar_redes(dias=30)", "analisar_brevo(dias=30)", "comparar_redes(dias=30)",
                    "comparar_redes(dias=7)"):
        tarefas.registrar_evento(tarefa_id, "consulta_painel", "analista_metricas", detalhe=detalhe)
    texto = painel_coletas.com_rodape(tarefa_id, "Os seguidores cresceram.")
    ultima = painel_coletas.ultima_coleta()
    assert texto.startswith("Os seguidores cresceram.\n\n---\nOrigem dos números (escrita pelo sistema)")
    assert "- comparar_redes (dias=30; dias=7)" in texto and "- analisar_brevo (dias=30)" in texto
    assert f"Última coleta do painel: {ultima:%d/%m/%Y às %H:%M}." in texto
    assert "Coleta com falha agora: YouTube (canal)" in texto


# --- Caixa de saída do trabalhador (despachante-07) ---------------------------------------------------------------

@pytest.fixture
def caixa(tmp_path, monkeypatch):
    if not Path("/repo/scripts/max/caixa_saida.py").exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    sys.path.insert(0, "/repo/scripts/max")
    import caixa_saida

    monkeypatch.setattr(caixa_saida, "PASTA", tmp_path / "caixa_saida")
    return caixa_saida


def test_conclusao_fica_guardada_ate_o_backend_confirmar(caixa):
    caixa.guardar(41, {"resumo": "Peça pronta", "pasta": "MARKETING/Teste"})

    def fora_do_ar(*_a):
        raise ConnectionError("backend reiniciando")

    assert caixa.reenviar(fora_do_ar) is False  # a fila espera: pedir /proxima faria a peça de novo
    assert [p["tarefa_id"] for p in caixa.pendentes()] == [41]
    chamadas = []
    assert caixa.reenviar(lambda *a: chamadas.append(a) or {"ok": True}) is True
    assert chamadas == [("POST", "/api/producao/41/concluir", {"resumo": "Peça pronta", "pasta": "MARKETING/Teste"})]
    assert caixa.pendentes() == []


def test_conclusao_recusada_ou_velha_sai_da_caixa(caixa):
    caixa.guardar(42, {"resumo": "x"})

    def nao_existe(*_a):
        raise urllib.error.HTTPError("http://teste", 404, "Produção não encontrada", None, None)

    assert caixa.reenviar(nao_existe) is True and caixa.pendentes() == []
    caixa.guardar(43, {"resumo": "y"})
    assert caixa.reenviar(lambda *_a: pytest.fail("não devia reenviar"), agora=caixa.pendentes()[0]["em"]
                          + caixa.VALIDADE_S + 1) is True
    caixa.guardar(44, {"resumo": "z"})

    def erro_500(*_a):
        raise urllib.error.HTTPError("http://teste", 500, "erro", None, None)

    for _ in range(caixa.MAX_RECUSAS_DO_SERVIDOR - 1):
        assert caixa.reenviar(erro_500) is False
    assert caixa.reenviar(erro_500) is True and caixa.pendentes() == []
