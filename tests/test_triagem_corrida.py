"""Triagem (porta de entrada), corrida de modelos com aprendizado e produção só com pedido de arquivo
(Thomas, 30/10/2026). Banco temporário (tests/conftest.py).

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_triagem_corrida.py
"""

import asyncio

import config
import corrida
import orquestrador
import tarefas
import triagem
from roteamento import Etapa

tarefas.iniciar()
USUARIO = {"sub": config.DONO_MAX, "master": True}


def test_triagem_indica_o_especialista_e_o_gestor_nas_pecas(monkeypatch):
    # Só as regras: o classificador aprenderia com as tarefas que os outros testes deixam no banco temporário.
    monkeypatch.setattr(triagem, "_modelo", None)
    monkeypatch.setattr(triagem, "_treinar_se_preciso", lambda: None)
    casos = {"Escreve uma legenda para o Lodge 28": "copywriter",
             "Faça um post para o Lodge 12 em Juquehy": "gestor",
             "Quero uma matriz SWOT da Casa Vero": "estrategista",
             "Quais feriados prolongados teremos em 2027?": "analista_tendencias",
             "Me ajuda a escrever um briefing melhor": "professor",
             "asdf qualquer coisa": "professor"}
    for texto, esperado in casos.items():
        r = triagem.sugerir(USUARIO, texto)
        assert r["sugestao"]["agente"] == esperado, (texto, r["sugestao"])
        assert r["sugestao"]["motivo"]


def test_escolha_na_triagem_vira_exemplo_de_treino():
    r = triagem.sugerir(USUARIO, "Preciso do texto do convite do evento")
    with triagem._db() as db:
        db.execute("UPDATE triagens SET escolhido = 'email_marketing' WHERE id = ?", (r["id"],))
    textos, rotulos, pesos = triagem._exemplos()
    assert ("Preciso do texto do convite do evento", "email_marketing", 3.0) in zip(textos, rotulos, pesos)


def test_ordem_e_limite_aprendidos(monkeypatch):
    monkeypatch.setattr(corrida, "perfis", lambda: {
        "openrouter/lento:free": {"tentativas": 20, "sucessos": 4, "taxa": 0.2, "p50": 100.0, "p90": 200.0},
        "openrouter/bom:free": {"tentativas": 20, "sucessos": 18, "taxa": 0.9, "p50": 20.0, "p90": 30.0},
        "openrouter/nunca:free": {"tentativas": 10, "sucessos": 0, "taxa": 0.0, "p50": None, "p90": None}})
    etapas = [Etapa("openrouter/nunca:free", 240), Etapa("openrouter/lento:free", 240),
              Etapa("openrouter/bom:free", 240), Etapa("ollama/local", 360)]
    ajustadas = corrida.ajustar(etapas)
    assert [e.modelo for e in ajustadas] == ["openrouter/bom:free", "openrouter/lento:free", "openrouter/nunca:free",
                                             "ollama/local"]  # o local (fixo) não sai do lugar
    assert ajustadas[0].limite_s == 60          # responde em ~30 s: não precisa esperar 4 min
    assert ajustadas[3].limite_s == 360


def test_corrida_larga_o_segundo_quando_o_primeiro_demora(monkeypatch):
    monkeypatch.setattr(corrida, "atraso_da_corrida", lambda modelo: 0.05)
    lento, rapido = Etapa("openrouter/lento:free", 240), Etapa("openrouter/rapido:free", 240)

    async def tentar(etapa):
        await asyncio.sleep(1.0 if etapa is lento else 0.05)
        return f"resposta de {etapa.modelo}", ""

    etapa, resultado, segunda = asyncio.run(corrida.correr(tentar, lento, rapido))
    assert etapa is rapido and segunda and "rapido" in resultado


def test_corrida_nao_larga_o_segundo_quando_o_primeiro_responde(monkeypatch):
    monkeypatch.setattr(corrida, "atraso_da_corrida", lambda modelo: 0.5)
    chamadas = []

    async def tentar(etapa):
        chamadas.append(etapa.modelo)
        return "ok", ""

    etapa, _, segunda = asyncio.run(corrida.correr(tentar, Etapa("openrouter/a:free", 240), Etapa("openrouter/b:free", 240)))
    assert chamadas == ["openrouter/a:free"] and not segunda


def test_agentes_com_efeito_externo_nao_correm():
    a, b = Etapa("openrouter/a:free", 240), Etapa("openrouter/b:free", 240)
    assert corrida.pode_correr("copywriter", a, b)
    for agente in ("gestor", "social_media", "email_marketing", "prospectador", "construtor"):
        assert not corrida.pode_correr(agente, a, b)
    assert not corrida.pode_correr("copywriter", a, Etapa("claude-code/max", 900))


def test_producao_so_com_pedido_de_arquivo():
    persona = ("PERSONA | CASA VERANEIO\nPerfil principal: pessoas de alto poder aquisitivo...\n"
               + "Fotografias e vídeos que transmitam a realidade do imóvel.\n" * 20
               + "Preciso que salve essa informação para as criações")
    assert not orquestrador._pede_arquivo(persona)
    assert orquestrador._pede_arquivo("[Pedido feito ao Copywriter] Faça um post para o Lodge 1")
    assert orquestrador._pede_arquivo("Preciso de uma nova foto de capa para o Youtube da Casa Vero")
    assert orquestrador._pede_arquivo("Produza a peça do item abaixo\n\nFORMATO DA PEÇA: CARROSSEL")


def test_fila_de_adiadas_roda_ate_tres_juntas(monkeypatch):
    import atividade
    from estado import buscar_agente

    rodando, liberar = [], asyncio.Event()

    async def executar(linha, agente, etapas):
        rodando.append(linha["id"])
        await liberar.wait()
        return True

    async def nada(*_a):
        return None

    monkeypatch.setattr(orquestrador, "_executar_etapas", executar)
    monkeypatch.setattr(orquestrador, "_etapas_fila", lambda *_a: [Etapa("openrouter/x:free", 60)])
    monkeypatch.setattr(atividade, "ocupar", nada)
    monkeypatch.setattr(atividade, "liberar", nada)
    with tarefas._db() as db:
        db.execute("UPDATE tarefas SET status = 'falhou' WHERE status = 'adiada'")
    agentes = ["copywriter", "social_media", "designer", "gestor"]
    ids = []
    for agente in agentes:
        tarefa = tarefas.criar("ana-fila", "marketing", agente, "Pedido", "simples")
        tarefas.atualizar(tarefa, status="adiada")
        ids.append(tarefa)
    for agente in agentes:
        buscar_agente("marketing", agente).status = orquestrador.Status.disponivel

    async def cenario():
        await orquestrador._processar_proxima()
        await asyncio.sleep(0.05)
        assert len(rodando) == 3  # três juntas, a quarta espera a vez
        liberar.set()
        await asyncio.sleep(0.05)

    asyncio.run(cenario())
