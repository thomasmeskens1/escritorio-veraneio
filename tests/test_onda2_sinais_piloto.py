"""Onda 2 de novembro, agente M: regra parecida (N2-cerebro-21), sinais de aprendizado só registrados (N2-cerebro-20)
e o mecanismo do piloto da prospecção (N2-prospectador-09). Banco temporário (tests/conftest.py), prévias numa pasta
temporária e dados fictícios; nada chama o Max, o Monday nem o Ollama.
"""

import asyncio
import json

import pytest

import avaliacoes
import comercial as c
import correcoes
import insatisfacoes
import prospeccao_piloto as piloto
import regras_parecidas
import sinais
import tarefas

tarefas.iniciar()
USUARIO = "usuario.teste@exemplo.com"
OUTRO = "vendedor.teste@exemplo.com"


@pytest.fixture(autouse=True)
def _sem_ollama(monkeypatch):
    import cerebro_embed

    monkeypatch.setattr(cerebro_embed, "gerar", lambda *_a, **_k: None)  # a comparação cai no texto


def _concluida(agente: str, texto: str, resposta: str = "Resposta pronta.", usuario: str = USUARIO,
               empresa: str = "casa_veraneio") -> int:
    tarefa_id = tarefas.criar(usuario, "marketing", agente, texto, "simples", empresa)
    tarefas.atualizar(tarefa_id, status="concluida", resposta=resposta, tempo_segundos=1.0)
    return tarefa_id


def _regra(agente: str, texto: str, empresa: str = "casa_veraneio") -> int:
    with correcoes._db() as db:
        return db.execute("INSERT INTO regras_aprendidas (agente, regra, criada_em, empresa) VALUES (?, ?, ?, ?)",
                          (agente, texto, tarefas._agora(), empresa)).lastrowid


def _observacao(agente: str, texto: str, tarefa_id: int | None = None, usuario: str = USUARIO) -> int:
    with correcoes._db() as db:
        return db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, tipo) "
                          "VALUES (?, ?, 'marketing', ?, ?, ?, 'correcao')",
                          (tarefas._agora(), usuario, agente, tarefa_id, texto)).lastrowid


# --- N2-cerebro-21: regra parecida ------------------------------------------------------------------------------

def test_regra_parecida_por_texto_e_so_do_mesmo_agente():
    antiga = _regra("copywriter", "Nunca use emojis no início da legenda zzparecida")
    _regra("designer", "Nunca use emojis no início da legenda zzparecida")
    achadas = regras_parecidas.parecidas("Não use emojis no início das legendas zzparecida", "copywriter",
                                         "casa_veraneio")
    assert [a["id"] for a in achadas if a["tipo"] == "regra"] == [antiga]
    assert achadas[0]["metodo"] == "texto"
    assert f"parecida com a regra #{antiga}" in regras_parecidas.aviso(achadas)
    assert not regras_parecidas.parecidas("Logo sempre no canto inferior direito zzoutra", "copywriter")


def test_regra_parecida_por_embedding_quando_o_ollama_responde(monkeypatch):
    import numpy as np

    import cerebro_embed

    antiga = _regra("moviemaker", "Cortes rápidos nos primeiros segundos zzembed")
    monkeypatch.setattr(cerebro_embed, "gerar", lambda textos, **_k: np.ones((len(textos), 4), dtype=np.float32) / 2)
    achadas = regras_parecidas.parecidas("Abertura dinâmica zzembed", "moviemaker")
    assert any(a["id"] == antiga and a["metodo"] == "embedding" for a in achadas)


def test_aprovar_com_substituir_desativa_a_antiga_sem_apagar(monkeypatch):
    import cerebro

    async def ensinar(*_a, **_k):
        return None

    monkeypatch.setattr(cerebro, "ensinar", ensinar)
    monkeypatch.setattr(correcoes, "_dono", lambda _a: {"sub": "dono", "nome": "Dono", "role": "diretoria"})
    antiga = _regra("copywriter", "CTA sempre com link da bio zzsubst")
    obs = _observacao("copywriter", "CTA sempre com o link da bio zzsubst")
    rascunho = correcoes.Rascunho(regra="CTA sempre com o link da bio zzsubst")
    assert correcoes.ver_parecidas(obs, rascunho)["parecidas"][0]["id"] == antiga
    resposta = asyncio.run(correcoes.aprovar(obs, correcoes.Decisao(regra="CTA sempre com o link da bio zzsubst",
                                                                    substituir=antiga)))
    linha = correcoes._db().execute("SELECT ativa, substituida_por, regra FROM regras_aprendidas WHERE id = ?",
                                    (antiga,)).fetchone()
    assert resposta["substituida"] == antiga and linha["ativa"] == 0 and linha["substituida_por"] == resposta["regra_id"]
    assert linha["regra"] == "CTA sempre com link da bio zzsubst"  # guardada


# --- N2-cerebro-20: sinais só registrados -----------------------------------------------------------------------

def test_voto_e_troca_de_voto_viram_sinais_sem_apagar():
    tarefa = _concluida("copywriter", "Legenda zzvoto")
    linha = tarefas.obter(tarefa)
    avaliacoes.avaliar(linha, USUARIO, 1)
    avaliacoes.avaliar(linha, USUARIO, -1)
    avaliacoes.avaliar(linha, USUARIO, 0)
    tipos = [(s["tipo"], s["valor"]) for s in sinais._db().execute(
        "SELECT tipo, valor FROM sinais_aprendizado WHERE tarefa_id = ? ORDER BY id", (tarefa,))]
    assert tipos == [("voto", 1), ("voto", -1), ("voto_retirado", 0)]
    sinal = sinais._db().execute("SELECT agente, empresa, em FROM sinais_aprendizado WHERE tarefa_id = ?",
                                 (tarefa,)).fetchone()
    assert sinal["agente"] == "copywriter" and sinal["empresa"] == "casa_veraneio" and sinal["em"]


def test_ajuste_logo_depois_autocorrecao_correcao_e_reacao_negativa():
    entrega = _concluida("designer", "Post do Lodge 900 zzsinal")
    ajuste = _concluida("designer", "Aumente a logo zzsinal")
    corrigida = _concluida("gestor", "Plano zzauto")
    _concluida("gestor", "E o Lodge? zzauto", resposta="Corrigindo a resposta anterior: o Lodge 900 tem 5 suítes.")
    obs = _observacao("copywriter", "Na verdade é com acento zzobs", entrega)
    insatisfacoes.registrar(tarefas.obter(entrega), USUARIO, "mensagem", "dados", "não era isso")
    sinais.varrer()
    sinais.varrer()  # idempotente
    por_chave = {s["chave"]: s for s in sinais._db().execute("SELECT * FROM sinais_aprendizado")}
    assert por_chave[f"ajuste:{ajuste}"]["tarefa_id"] == entrega and por_chave[f"ajuste:{ajuste}"]["peso"] == 0.5
    autocorrecao = [s for s in por_chave.values() if s["tipo"] == "autocorrecao" and s["tarefa_id"] == corrigida]
    assert len(autocorrecao) == 1 and autocorrecao[0]["valor"] == -1
    assert por_chave[f"obs:{obs}"]["tipo"] == "correcao"
    assert any(s["tipo"] == "reacao_negativa" and s["tarefa_id"] == entrega for s in por_chave.values())
    resumo = sinais.resumo()
    assert resumo["total"] >= 4 and {"ajuste_logo_depois", "autocorrecao"} <= {t["tipo"] for t in resumo["por_tipo"]}


def test_comentario_do_voto_nao_conta_duas_vezes():
    tarefa = _concluida("copywriter", "Legenda zzcomentario")
    avaliacoes.avaliar(tarefas.obter(tarefa), USUARIO, -1, "faltou o CTA zzcomentario")
    sinais.varrer()
    tipos = [s["tipo"] for s in sinais._db().execute("SELECT tipo FROM sinais_aprendizado WHERE tarefa_id = ?",
                                                     (tarefa,))]
    assert tipos == ["voto"]


def test_nada_le_os_sinais_para_o_prompt():
    assert "sinais" not in correcoes.regras_para("copywriter", "casa_veraneio")
    import ajustes

    assert not hasattr(ajustes, "sinais")


# --- N2-prospectador-09: piloto ---------------------------------------------------------------------------------

def _lead(n: int) -> dict:
    return {"empresa": f"Empresa Piloto {n}", "cidade": "Joinville", "uf": "SC", "segmento": "Indústria",
            "email": f"contato@e{n}.exemplo.com", "telefone": "4730000000", "site": f"https://e{n}.exemplo.com",
            "motivo": "Indústria com 200 funcionários"}


@pytest.fixture
def previas(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "PASTA_PREVIAS", tmp_path)
    monkeypatch.setattr(piloto, "carregar_usuarios", lambda: {})
    for previa_id in (701, 702, 703):
        (tmp_path / f"{previa_id}.json").write_text(json.dumps({
            "usuario": USUARIO, "pedido": "Prospecte 5 indústrias", "leads": [_lead(n) for n in range(1, 6)],
            "criados": []}), encoding="utf-8")
    return tmp_path


def test_nota_fica_na_previa_sem_contato_e_troca_vai_ao_historico(previas):
    piloto.dar_nota(701, 2, OUTRO, 4, "Bom porte, ligar para contato@e2.exemplo.com")
    piloto.dar_nota(701, 2, OUTRO, 5, "Melhor ainda")
    previa = json.loads((previas / "701.json").read_text(encoding="utf-8"))
    assert previa["notas"]["2"][OUTRO]["nota"] == 5
    assert previa["notas_historico"][0]["nota"] == 4 and "contato@" not in json.dumps(previa["notas_historico"])
    with pytest.raises(ValueError):
        piloto.dar_nota(701, 1, OUTRO, 6)
    with pytest.raises(LookupError):
        piloto.dar_nota(701, 9, OUTRO, 3)


def test_piloto_mostra_leads_sem_contato_e_fecha_o_resumo_com_as_3_previas(previas):
    estado = piloto.marcar([701, 702, 703], "master")
    texto = json.dumps(estado)
    assert "exemplo.com" not in texto and "4730000000" not in texto and not estado["completo"]
    for previa_id in (701, 702, 703):
        for n in range(1, 6):
            piloto.dar_nota(previa_id, n, OUTRO, 5 if n <= 2 else 2, "fit bom" if n == 1 else "")
    estado = piloto.estado(OUTRO)
    resumo = estado["resumo"]
    assert estado["completo"] and resumo["leads"] == 15 and resumo["ligaria"] == 6 and resumo["ligaria_pct"] == 40
    assert resumo["distribuicao"]["5"] == 6 and resumo["distribuicao"]["2"] == 9
    assert estado["previas"][0]["leads"][0]["notas"][0]["minha"]
    assert json.loads((previas / "piloto.json").read_text(encoding="utf-8"))["resumo_fechado_em"]


def test_nota_pelo_chat_nunca_cria_lead(previas, monkeypatch):
    criados = []
    monkeypatch.setattr(c, "criar_lead", lambda lead: criados.append(lead) or 1)
    tarefa = tarefas.criar(USUARIO, "comercial", "prospectador", "nota", "simples", "cv_corporativo")
    texto = "Prévia #701: lead 1 = 5, ótimo fit; lead 3: nota 2, fora do perfil"
    assert c.e_pedido_de_trabalho(texto) and piloto.e_nota(texto)
    resposta = c.executar(tarefa, texto)
    assert "lead 1 = 5" in resposta and "lead 3 = 2" in resposta and not criados
    assert not piloto.e_nota("Crie os leads 1 e 3 da prévia #701")
    assert piloto.ler_notas("Nota 4 para o lead 2 da prévia #701: porte bom") == [(2, 4, "porte bom")]
    previa = json.loads((previas / "701.json").read_text(encoding="utf-8"))
    assert previa["notas"]["3"][USUARIO]["comentario"] == "fora do perfil"


def test_previa_fora_do_piloto_so_o_dono_da_nota(previas, monkeypatch):
    monkeypatch.setattr("auth.e_master", lambda _login: False)
    tarefa = tarefas.criar(OUTRO, "comercial", "prospectador", "nota", "simples", "cv_corporativo")
    assert "não é sua" in piloto.nota_pelo_chat(tarefa, "Nota 3 para o lead 1 da prévia #702")
