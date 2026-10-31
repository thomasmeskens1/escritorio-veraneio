"""Onda 3, grupo O (31/10/2026): modelos de estilo aprovados no Cérebro (cerebro-12, gestor-22) e "Repetir para…" até
5 Lodges (copywriter-04). Banco temporário (tests/conftest.py); dados fictícios; o modelo de IA é simulado.
"""

import asyncio
import re

import pytest

import avaliacoes
import cerebro
import cerebro_base as base
import cerebro_imoveis as imoveis
import cerebro_modelos as modelos
import correcoes
import orquestrador
import repetir_lodges as repetir
import saude
import tarefas
from cerebro_texto import dividir

tarefas.iniciar()

DIRETORIA = {"sub": "usuario.teste", "nome": "Pessoa Teste", "role": "diretoria"}
LEGENDA = ("Lodge 801 em Cidade Modelo / SP: 5 suítes para até 14 pessoas, piscina e churrasqueira para o grupo todo.\n"
           "Diária a partir de R$ 4.000\n"
           "Garanta o seu. Link na bio.\n#casaveraneio\n\n"
           "Conferência automática (só aviso, confira):\n- algo")


@pytest.fixture(autouse=True)
def _sem_modelos_depois():
    """Os modelos de teste saem da busca no fim (o banco é o mesmo dos outros arquivos de teste)."""
    yield
    for m in modelos.ativos():
        modelos.remover(m["id"])
    base._indice = None  # o índice em cache (até 15 s) não pode esconder os trechos dos próximos testes


def _apagar_lodges_de_teste() -> None:
    with base._trava, base.db() as conexao:
        conexao.execute("DELETE FROM conhecimento WHERE fonte_ref IN ('site/lodges/lodge-801', 'site/lodges/lodge-802', 'site/lodges/lodge-803')")
    base._indice = None
    imoveis.atualizar("casa_veraneio", forcar=True)


@pytest.fixture(autouse=True, scope="module")
def _lodges_de_teste_saem_no_fim():
    """O banco de teste é um só: os Lodges fictícios deste arquivo não podem vazar para o catálogo dos outros."""
    _apagar_lodges_de_teste()
    yield
    _apagar_lodges_de_teste()


def _documento(ref: str, conteudo: str) -> None:
    titulo = conteudo.splitlines()[0].lstrip("# ")
    for t, c in dividir(titulo, conteudo):
        base._inserir("site", ref, t, c, "casa_veraneio")


def _lodges() -> None:
    # Outros arquivos de teste gravam Lodges 801/802 com outros dados no mesmo banco: estes testes regravam os seus.
    with base._trava, base.db() as conexao:
        conexao.execute("DELETE FROM conhecimento WHERE fonte_ref IN ('site/lodges/lodge-801', 'site/lodges/lodge-802', "
                        "'site/lodges/lodge-803')")
    _documento("site/lodges/lodge-801", "# Lodge 801 — Cidade Modelo - SP\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-801\nResumo: 6 quartos | até 14 pessoas | categoria: Campo\n\n## Acomodações\n5 suítes.\n\n"
               "## Comodidades\nPiscina, Churrasqueira")
    _documento("site/lodges/lodge-802", "# Lodge 802 — Vila Exemplo - RJ\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-802\nResumo: 4 quartos | até 10 pessoas | categoria: Praia\n\n## Acomodações\n3 suítes.\n\n"
               "## Valores por época\n- Alta temporada: diária R$ 9.000\n\n## Comodidades\nSauna, Vista para o mar")
    _documento("site/lodges/lodge-803", "# Lodge 803 — Serra Exemplo - MG\nFonte: https://www.casaveraneio.com/lodges/"
               "lodge-803\nResumo: 3 quartos | até 8 pessoas | categoria: Serra\n\n## Acomodações\n2 suítes.")
    imoveis.atualizar("casa_veraneio", forcar=True)


def _tarefa(agente="copywriter", resposta=LEGENDA, texto="Legenda para o Lodge 801", empresa="casa_veraneio",
            status="concluida") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", agente, texto, "simples", empresa)
    tarefas.atualizar(tarefa_id, status=status, resposta=resposta, tempo_segundos=1.0)
    return tarefa_id


# --- Modelos de estilo (cerebro-12) ---------------------------------------------------------------------------

def test_formato_provavel():
    assert modelos.formato_provavel("email_marketing", "texto") == "email"
    assert modelos.formato_provavel("copywriter", "Assunto: Janeiro\nCorpo") == "email"
    assert modelos.formato_provavel("social_media", "texto") == "legenda"
    assert modelos.formato_provavel("copywriter", "Nova descrição para o site do Lodge") == "descricao_casa"
    assert modelos.formato_provavel("moviemaker", "Cena 1") == "roteiro"
    assert modelos.formato_provavel("copywriter", "Texto qualquer") == "outro"


def test_limpar_tira_rodape_e_contato():
    texto = modelos.limpar(LEGENDA + "\nFale com usuario.teste@exemplo.com")
    assert "Conferência automática" not in texto and "@exemplo.com" not in texto and "Link na bio" in texto


def test_modelo_entra_na_busca_com_etiqueta_so_da_empresa():
    novo = modelos.guardar("casa_veraneio", "copywriter", "legenda", "Legenda modelo do Lodge 801: gramado amplo, "
                           "piscina aquecida e fogo de chão xyzmodelo para o grupo.", "Pessoa Teste")
    base.indice_atual(fresco=True)  # o índice da busca pode ter até 15 s
    trechos = base.buscar("xyzmodelo fogo de chão", k=5, empresa="casa_veraneio")
    achado = next(t for t in trechos if t["fonte_ref"] == f"modelo:{novo}")
    assert achado["fonte_tipo"] == "modelo" and achado["titulo"].startswith("Modelo de estilo · Legenda de post")
    assert "MODELO DE ESTILO: siga o tom" in cerebro._formatar([achado], 2000)
    assert not any(t["fonte_ref"] == f"modelo:{novo}" for t in base.buscar("xyzmodelo fogo de chão", k=5,
                                                                             empresa="casa_vero"))
    with pytest.raises(ValueError):
        modelos.guardar("*", "copywriter", "legenda", "Texto que valeria para as três empresas.", "Pessoa Teste")


def test_maximo_por_grupo_tira_o_mais_antigo(monkeypatch):
    monkeypatch.setattr(modelos, "MAX_POR_GRUPO", 2)
    ids = [modelos.guardar("casa_veraneio", "gestor_trafego", "anuncio", f"Anúncio modelo número {n} com chamada "
                           "clara e curta.", "Pessoa Teste") for n in range(3)]
    ativos = {m["id"] for m in modelos.ativos("casa_veraneio") if m["formato"] == "anuncio"}
    assert ativos == set(ids[1:])
    assert not base.db().execute("SELECT 1 FROM conhecimento WHERE fonte_ref = ? AND ativo = 1",
                                 (f"modelo:{ids[0]}",)).fetchone()
    assert modelos.remover(ids[1]) and not modelos.remover(ids[1])


def test_elogio_vira_modelo_pela_lista_de_aprovacao(monkeypatch):
    monkeypatch.setattr(correcoes, "_dono", lambda authorization: DIRETORIA)
    tarefa_id = _tarefa(resposta="Texto inteiro elogiado do Lodge 801, " + "com muitos detalhes " * 40)
    with correcoes._db() as db:
        obs = db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, "
                         "resposta_anterior, tipo) VALUES (?, 'usuario.teste', 'marketing', 'copywriter', ?, "
                         "'Adorei', 'trecho', 'elogio')", (tarefas._agora(), tarefa_id)).lastrowid
    previa = modelos.ver_previa(observacao_id=obs)
    assert previa["texto"].endswith("detalhes") and len(previa["texto"]) > 400  # o texto inteiro, não os 400
    resposta = modelos.criar(modelos.NovoModelo(observacao_id=obs, formato="descricao_casa"))
    assert resposta["ok"] and resposta["empresa_nome"] == "Casa Veraneio"
    assert correcoes._db().execute("SELECT status FROM observacoes WHERE id = ?", (obs,)).fetchone()[0] == "modelo"
    m = next(m for m in modelos.ativos() if m["id"] == resposta["id"])
    assert (m["agente"], m["formato"], m["observacao_id"], m["aprovado_por"]) == (
        "copywriter", "descricao_casa", obs, "Pessoa Teste")


def test_joinha_e_candidato_ate_virar_modelo(monkeypatch):
    monkeypatch.setattr(correcoes, "_dono", lambda authorization: DIRETORIA)
    tarefa_id = _tarefa(resposta="Legenda com 👍 do Lodge 801, pronta e aprovada pela equipe.")
    with avaliacoes._db() as db:
        db.execute("INSERT INTO avaliacoes VALUES (?, 'usuario.teste', 1, NULL, ?)", (tarefa_id, tarefas._agora()))
    assert tarefa_id in {c["id"] for c in modelos.candidatos()}
    modelos.criar(modelos.NovoModelo(tarefa_id=tarefa_id, formato="legenda", texto="Versão editada da legenda modelo."))
    assert tarefa_id not in {c["id"] for c in modelos.candidatos()}
    outra = _tarefa(empresa="*", resposta="Texto das três empresas, sem empresa definida.")
    with pytest.raises(Exception) as erro:
        modelos.criar(modelos.NovoModelo(tarefa_id=outra, formato="outro"))
    assert getattr(erro.value, "status_code", 0) == 422


# --- Repetir para… (copywriter-04) ----------------------------------------------------------------------------

def test_validar_lodges():
    _lodges()
    assert repetir.validar(tarefas.obter(_tarefa()), [802, 801, 802, 803]) == [802, 803]  # sem a origem e repetidos
    casos = [(_tarefa(status="executando"), [802], "já pronto"), (_tarefa(agente="designer"), [802], "agentes de texto"),
             (_tarefa(empresa="cv_corporativo"), [802], "Casa Veraneio"), (_tarefa(), [801], "diferente"),
             (_tarefa(), [802, 803, 804, 805, 806, 807], "No máximo"), (_tarefa(), [802, 899], "Lodge 899")]
    for tarefa_id, lodges, trecho in casos:
        with pytest.raises(ValueError, match=trecho):
            repetir.validar(tarefas.obter(tarefa_id), lodges)


def test_prompt_leva_a_ficha_sem_valores_e_o_texto_sem_rodape():
    _lodges()
    original = repetir.texto_base(LEGENDA)
    assert "Conferência automática" not in original and "R$" not in original and "Link na bio" in original
    prompt = repetir.montar_prompt("copywriter", "casa_veraneio", original, 801, 802, "Legenda para o Lodge 801")
    assert "FICHA DO LODGE 802" in prompt and "Vila Exemplo" in prompt and "Sauna" in prompt
    assert "R$" not in prompt and "9.000" not in prompt and "escrito para o Lodge 801" in prompt
    assert repetir.texto_base("Lodge 802:\n\nTexto repetido") == "Texto repetido"


def test_conferencia_do_texto_gerado():
    _lodges()
    final = repetir.conferir("Lodge 802 em Vila Exemplo / RJ com 7 suítes, igual ao Lodge 801.\nDiária R$ 9.000\n"
                             "Fale no WhatsApp.", 802, "casa_veraneio", "Legenda")
    assert final.startswith("Lodge 802:") and "R$" not in final
    assert "WhatsApp citado" in final and "7 suítes" in final and "cita o Lodge 801" in final


def test_gerar_pula_o_modelo_que_falha(monkeypatch):
    tarefa_id = _tarefa(status="executando")
    chamados = []

    def falso(modelo, prompt, limite):
        chamados.append(modelo)
        if modelo == "openrouter/a:free":
            raise RuntimeError("fora do ar")
        return "<think>pensando</think>Texto novo do Lodge 802 pronto para postar."

    monkeypatch.setattr(repetir, "_chamar", falso)
    monkeypatch.setattr(saude, "registrar_falha", lambda *a: None)
    monkeypatch.setattr(saude, "registrar_sucesso", lambda *a: None)
    modelo, texto = repetir.gerar(tarefa_id, "prompt", [("openrouter/a:free", 10), ("groq/b", 10)])
    assert (modelo, chamados) == ("groq/b", ["openrouter/a:free", "groq/b"]) and not texto.startswith("<think>")
    monkeypatch.setattr(repetir, "_chamar", lambda *a: "")
    assert repetir.gerar(tarefa_id, "prompt", [("groq/b", 10)]) is None


def test_rota_sem_max_nem_api_paga(monkeypatch):
    monkeypatch.setattr(repetir.roteamento, "_gratuitos", lambda maximo=None: [
        repetir.roteamento.Etapa("openrouter/a:free", 240)])
    rota = [m for m, _ in repetir.modelos_gratuitos("copywriter", "Legenda do Lodge 802")]
    assert rota[0] == "openrouter/a:free" and not any(m.startswith(("anthropic/", "claude-code/")) for m in rota)
    sigilosa = [m for m, _ in repetir.modelos_gratuitos("copywriter", "faturamento do CRM do mês")]
    assert "openrouter/a:free" not in sigilosa  # decisão 12: sigiloso nunca vai a gratuito de fora


def test_repetir_cria_uma_tarefa_por_lodge_e_entrega_cada_uma(monkeypatch):
    _lodges()
    origem = tarefas.obter(_tarefa())
    avisos, concluidas, fundo = [], {}, []

    async def enviar(login, mensagem):
        avisos.append(mensagem)
        return True

    async def concluir(tarefa_id, modelo, resultado):
        concluidas[tarefa_id] = (modelo, resultado.texto)

    monkeypatch.setattr(repetir.gerenciador, "enviar_para_usuario", enviar)
    monkeypatch.setattr(orquestrador, "_concluir", concluir)
    monkeypatch.setattr(orquestrador, "_em_segundo_plano", lambda corrotina: fundo.append(corrotina))
    monkeypatch.setattr(repetir, "modelos_gratuitos", lambda agente, texto: [("openrouter/a:free", 10)])
    monkeypatch.setattr(saude, "registrar_sucesso", lambda *a: None)
    vistos = []

    def falso(modelo, prompt, limite):
        numero = re.search(r"para o Lodge (\d+)\.\n", prompt).group(1)
        vistos.append(numero)
        return f"Lodge {numero}: texto novo no mesmo tom. Garanta o seu. Link na bio. #casaveraneio"

    monkeypatch.setattr(repetir, "_chamar", falso)

    async def rodar():
        ids = await repetir.repetir(origem, [802, 803], "usuario.teste")
        await fundo[0]
        return ids

    ids = asyncio.run(rodar())
    assert len(ids) == 2 and vistos == ["802", "803"]
    assert [tarefas.obter(i)["texto"][:28] for i in ids] == ["Repetir para o Lodge 802: me", "Repetir para o Lodge 803: me"]
    assert all(tarefas.obter(i)["empresa"] == "casa_veraneio" and tarefas.obter(i)["agente"] == "copywriter" for i in ids)
    assert concluidas[ids[0]][0] == "openrouter/a:free" and concluidas[ids[0]][1].startswith("Lodge 802:")
    assert avisos[0]["tipo"] == "aviso" and "Lodge 802, Lodge 803" in avisos[0]["texto"]
