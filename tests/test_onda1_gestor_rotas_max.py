"""Onda 1 do brainstorming, grupo G (31/10/2026): ficha de sucesso do Gestor (gestor-07), planejamento fora do Groq
(social_media-19), Brevo sem leads da prospecção (prospectador-16), medição do Max (despachante-07) e modelo por tipo
de trabalho (despachante-06). Banco temporário (tests/conftest.py); nada sai para a internet.
"""

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

import corrida
import producao
import roteamento
import tarefas
import uso_max
from agents import ferramentas_brevo as fb
from agents import projeto
from roteamento import Etapa

tarefas.iniciar()

# --- social_media-19: planejamento nunca no Groq ----------------------------------------------------------------

ETAPAS = [Etapa("groq/openai/gpt-oss-120b", 240), Etapa("openrouter/nvidia/forte:free", 240),
          Etapa("groq/qwen/qwen3.8-27b", 240), Etapa("claude-code/max", 900)]


def test_planejamento_do_social_media_e_do_gestor_sai_do_groq():
    for agente, texto in (("social_media", "Planejamento mensal de dezembro da Casa Vero"),
                          ("gestor", "Monte o calendário de publicações"),
                          ("social_media", "Planejamento: grade da semana"),
                          ("social_media", "Quero os posts do mês de janeiro")):
        modelos = [e.modelo for e in roteamento.sem_groq_no_planejamento(ETAPAS, agente, texto)]
        assert not any(m.startswith("groq/") for m in modelos), (agente, texto)
        assert modelos == ["openrouter/nvidia/forte:free", "claude-code/max"]  # o forte primeiro, o Max depois


def test_pedido_curto_e_outros_agentes_continuam_no_groq():
    assert roteamento.sem_groq_no_planejamento(ETAPAS, "social_media", "Legenda do Lodge 1") == ETAPAS
    assert roteamento.sem_groq_no_planejamento(ETAPAS, "copywriter", "Planejamento mensal") == ETAPAS


def test_corrida_aplica_a_regra_quando_recebe_o_pedido():
    ajustadas = corrida.ajustar(ETAPAS, "social_media", "planejamento de dezembro")
    assert not any(e.modelo.startswith("groq/") for e in ajustadas)
    assert len(corrida.ajustar(ETAPAS)) == len(ETAPAS)  # chamada antiga (sem agente): nada muda


# --- gestor-07: ficha de sucesso -------------------------------------------------------------------------------

def _gestor(plano: str, ficha: str = "", chamadas: list | None = None):
    def executar(agente, descricao, esperado, papel):
        if chamadas is not None:
            chamadas.append((agente, esperado, descricao))
        if "JSON com o entendimento" in esperado:
            return plano
        if "Ficha de sucesso" in esperado:
            return ficha
        return "Entrega final do carrossel." if agente == "gestor" else f"entrega de {agente}"
    return executar


ETAPA = '"etapas": [{"agente": "copywriter", "instrucao": "Textos", "fase": 1}]'


def test_ficha_de_sucesso_vai_para_a_pasta_as_etapas_e_o_fim_da_entrega(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = ('{"entendimento": "Carrossel do Lodge 1", "duvida": "", "titulo": "Carrossel Lodge 1", '
             '"papel": "conversao", "cta": "Chame no Direct", "metrica": "mensagens no Direct", '
             '"hipotese": "capa sem casa gera mais deslizes", ' + ETAPA + '}')
    chamadas = []
    final = projeto.executar_projeto(11, "Carrossel do Lodge 1", "CTX", _gestor(plano, chamadas=chamadas),
                                     threading.Event())
    ficha = (tmp_path / "11" / "sucesso.md").read_text(encoding="utf-8")
    assert "PAPEL: Conversão" in ficha and "CHAMADA PRINCIPAL: Chame no Direct" in ficha
    assert not any("Ficha de sucesso" in e for _, e, _ in chamadas)  # veio completa no plano: sem chamada extra
    etapa = next(d for a, _, d in chamadas if a == "copywriter")
    assert "FICHA DE SUCESSO" in etapa and "mensagens no Direct" in etapa
    assert "Recuse (reescreva)" in chamadas[-1][2]  # a revisão confere a chamada contra o papel
    assert final.startswith("Entrega final do carrossel.")
    assert final.rstrip().endswith("- Hipótese: capa sem casa gera mais deslizes")
    assert "Como vamos medir\n- Papel: Conversão" in final
    assert projeto.sucesso_do_projeto(11) == ficha


def test_campo_faltando_ou_papel_invalido_pede_a_ficha_de_novo(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = '{"entendimento": "E", "duvida": "", "titulo": "T", "papel": "Vendas", "cta": "Reserve", ' + ETAPA + '}'
    ficha = ("PAPEL: Confiança\nCHAMADA PRINCIPAL: Veja os depoimentos\nMÉTRICA PRINCIPAL: salvamentos\n"
             "HIPÓTESE: depoimento em vídeo gera mais salvamentos")
    chamadas = []
    final = projeto.executar_projeto(12, "Post de depoimentos", "CTX", _gestor(plano, ficha, chamadas),
                                     threading.Event())
    assert sum("Ficha de sucesso" in e for _, e, _ in chamadas) == 1
    gravada = (tmp_path / "12" / "sucesso.md").read_text(encoding="utf-8")
    assert "PAPEL: Confiança" in gravada and "CHAMADA PRINCIPAL: Reserve" in gravada  # o do plano vale
    assert "- Métrica principal: salvamentos" in final


def test_sem_ficha_a_entrega_segue_sem_o_bloco(tmp_path, monkeypatch):
    monkeypatch.setattr(projeto, "PASTA_PROJETOS", tmp_path)
    plano = '{"entendimento": "E", "duvida": "", "titulo": "T", ' + ETAPA + '}'
    final = projeto.executar_projeto(13, "Post", "CTX", _gestor(plano, "não sei"), threading.Event())
    assert final == "Entrega final do carrossel."
    assert projeto.NAO_DEFINIDO in (tmp_path / "13" / "sucesso.md").read_text(encoding="utf-8")


# --- prospectador-16: lead de prospecção nunca no Brevo -------------------------------------------------------

def test_brevo_nunca_toca_contatos_listas_nem_destinatarios():
    for metodo, caminho, corpo in (("POST", "/contacts", {"email": "usuario.teste@exemplo.com"}),
                                   ("POST", "/contacts/import", {"listIds": [1]}),
                                   ("GET", "/contacts?limit=50", None),
                                   ("POST", "/contacts/lists/3/contacts/add", {}),
                                   ("POST", "/emailCampaigns", {"name": "x", "recipients": {"listIds": [3]}}),
                                   ("PUT", "/emailCampaigns/9", {"listIds": [3]})):
        with pytest.raises(fb.BrevoBloqueado):
            fb._api(metodo, caminho, "chave-falsa", corpo)  # barrado antes de qualquer rede


def test_pedido_com_leads_da_prospeccao_nao_vira_rascunho(monkeypatch):
    tarefa_id = tarefas.criar("usuario.teste", "marketing", "email_marketing",
                              "Monte um e-mail para os leads da Prospecção Ativa do Corporativo", "media",
                              "cv_corporativo")
    monkeypatch.setattr(fb, "_chave", lambda: "chave-falsa")
    monkeypatch.setattr(fb, "_api", lambda *_a, **_k: pytest.fail("não podia chamar o Brevo"))
    resposta = fb.CriarRascunhoBrevo(empresa="cv_corporativo", tarefa_id=tarefa_id)._run()
    assert resposta == fb.RECUSA_PROSPECCAO
    outra = tarefas.criar("usuario.teste", "marketing", "email_marketing", "E-mail de férias de janeiro", "media",
                          "casa_veraneio")
    assert not fb.pedido_de_prospeccao(outra)


@pytest.fixture
def scripts_max():
    if not Path("/repo/scripts/max/comum.py").exists():
        pytest.skip("scripts/max não montado em /repo/scripts/max")
    sys.path.insert(0, "/repo/scripts/max")
    import comum
    return comum


def test_leitura_de_emails_do_brevo_nunca_pede_contatos(scripts_max):
    import emails_brevo

    with pytest.raises(PermissionError):
        emails_brevo._get("/contacts?limit=500", "chave-falsa")


# --- despachante-07: medição do Max ----------------------------------------------------------------------------

def _trabalho_texto(tarefa_id: int, agente: str) -> int:
    payload = json.dumps({"prompt": "x" * 1200, "limite_s": 900, "tarefa_id": tarefa_id, "agente": agente})
    with producao._db() as db:
        return db.execute("INSERT INTO trabalhos_max (tipo, payload, status, criado_em) VALUES ('texto', ?, "
                          "'executando', ?)", (payload, tarefas._agora())).lastrowid


def test_conclusao_grava_o_uso_e_o_resumo_soma_por_tipo_agente_e_empresa(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    with uso_max._db() as db:
        db.execute("DELETE FROM uso_max")
    tarefa_id = tarefas.criar("usuario.teste", "marketing", "gestor", "Carrossel", "media", "casa_vero")
    novo = _trabalho_texto(tarefa_id, "copywriter")
    uso = uso_max.Uso(chars_entrada=1200, chars_saida=300, tokens_entrada=900, tokens_cache=5000, tokens_saida=400,
                      rodadas=2, duracao_s=42.5, modelo="claude-sonnet")
    asyncio.run(producao.concluir_trabalho(novo, producao.Resultado(resultado="ok" * 150, uso=uso), ""))
    antigo = _trabalho_texto(tarefa_id, "")  # trabalhador antigo: sem os números
    asyncio.run(producao.concluir_trabalho(antigo, producao.Resultado(resultado="resposta"), ""))
    resumo = uso_max.resumo(7, lambda a: f"Nome {a}")
    assert resumo["total"]["trabalhos"] == 2 and resumo["total"]["tokens"] == 6300
    assert resumo["por_tipo"][0]["chave"] == "texto" and resumo["por_tipo"][0]["trabalhos"] == 2
    agentes = {g["chave"]: g for g in resumo["por_agente"]}
    assert agentes["copywriter"]["nome"] == "Nome copywriter" and agentes["copywriter"]["rodadas"] == 2
    assert agentes["gestor"]["chars"] == 1200 + len("resposta")  # o backend mede o que sabe
    assert [g["chave"] for g in resumo["por_empresa"]] == ["casa_vero"]


def test_uso_absurdo_e_recusado_na_fronteira():
    with pytest.raises(ValueError):
        uso_max.Uso(tokens_entrada=-1)
    assert producao.Resultado(resultado="ok").uso is None  # campos opcionais: compatível com o trabalhador antigo


# --- despachante-06 e despachante-07 no trabalhador ------------------------------------------------------------

def test_modelo_por_tipo_e_numeros_de_uso_do_claude_code(scripts_max, monkeypatch, tmp_path):
    comum = scripts_max
    arquivo = tmp_path / "modelos_max.json"
    monkeypatch.setattr(comum, "ARQUIVO_MODELOS", arquivo)
    assert comum.modelo_para("texto") == ""  # sem o arquivo: nenhuma troca
    arquivo.write_text(json.dumps({"texto": "sonnet", "anexo": "padrao", "producao": "x; rm -rf"}), encoding="utf-8")
    assert comum.modelo_para("texto") == "sonnet"
    assert comum.modelo_para("anexo") == "" and comum.modelo_para("producao") == ""  # padrão e nome inválido

    comandos = []

    class Processo:
        returncode = 0

        def __init__(self, comando, *_a, stdout=None, **_k):
            comandos.append(comando)
            stdout.write(json.dumps({"result": "resposta", "num_turns": 3, "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 100, "output_tokens": 20},
                "modelUsage": {"claude-sonnet-x": {}}}))
            self.stdin = type("E", (), {"write": lambda *_: None, "close": lambda *_: None})()

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(comum.subprocess, "Popen", Processo)
    comum.zerar_uso()
    assert comum.rodar_claude(["claude", "-p"], "oi", tmp_path, 60, tipo="texto") == "resposta"
    comum.rodar_claude(["claude", "-p"], "de novo", tmp_path, 60)  # sem tipo: sem --model
    assert comandos[0][:4] == ["claude", *comum.ISOLAMENTO, "--model"] and comandos[0][4] == "sonnet"
    assert "--model" not in comandos[1]
    uso = comum.uso_acumulado()
    assert uso["tokens_entrada"] == 20 and uso["tokens_cache"] == 200 and uso["tokens_saida"] == 40
    assert uso["rodadas"] == 6 and uso["chars_entrada"] == len("oi") + len("de novo")
    assert uso["modelo"] == "claude-sonnet-x"
    uso_max.Uso(**uso)  # o backend aceita o que o trabalhador manda
