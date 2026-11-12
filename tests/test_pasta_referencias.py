"""Pasta de REFERÊNCIAS do Drive (12/11/2026, tarefas 290 a 294 do João): só quando citada, só da empresa da peça,
padrão "só estudo" (originais barrados), uso liberado pelo popup e estudo que vira observação para aprovação.
Pastas fictícias em tmp_path; nada toca o Drive de verdade."""

import sys
from pathlib import Path

import pytest

import correcoes
import referencias_pedido
import tarefas

LINK = "https://drive.google.com/drive/u/1/folders/1_rCQENXBusPiiLNeo13zW6MFEZgeZXD5"
CAMINHO = "Vá em Escritório veraneio -> referencias -> Casa veraneio -> 12.11.26 Gestor - Videos com serviços"
ESTUDO = "[Pasta de referências: só para estudo]"
USAR = "[Pasta de referências: pode usar os arquivos na peça]"


def test_pedido_cita_a_pasta_por_link_ou_caminho():
    assert referencias_pedido.cita(f"Use os takes daqui: {LINK}")
    assert referencias_pedido.cita(CAMINHO)
    assert referencias_pedido.cita("REFERENCIAS > CASA VERANEIO > pasta")
    assert not referencias_pedido.cita("Post do Lodge 3 com as referências da marca")


def test_uso_so_com_o_marcador_do_popup():
    assert referencias_pedido.uso(f"{LINK}\n\n{USAR}") == "usar"
    assert referencias_pedido.uso(f"{LINK}\n\n{ESTUDO}") == "estudo"
    assert referencias_pedido.uso(LINK) == "estudo"  # Monday, Telegram ou sem resposta: o padrão é estudo


def test_nota_do_agente_nao_manda_baixar_em_pasta_interna():
    nota = referencias_pedido.nota_para_agente(f"{LINK}\n\n{ESTUDO}")
    assert "SÓ PARA ESTUDO" in nota and "max_texto" in nota  # cita para proibir
    assert "LIBEROU" not in nota
    assert "USO" in referencias_pedido.nota_para_agente(f"{LINK}\n\n{USAR}")
    assert referencias_pedido.nota_para_agente("Post do Lodge 3") == ""


def test_link_de_mensagem_anterior_chega_a_producao():
    login = "teste_ref@exemplo.com"
    anterior = tarefas.criar(login, "marketing", "gestor", f"Use as referências: {LINK}\n\n{USAR}", "media",
                             "casa_veraneio")
    tarefas.atualizar(anterior, status="concluida", resposta="ok")
    atual = tarefas.criar(login, "marketing", "gestor", "Confirmado, pode produzir", "media", "casa_veraneio")
    linha = referencias_pedido.linha_para_producao(tarefas.obter(atual))
    assert LINK in linha and USAR in linha
    outro = tarefas.criar("outro_ref@exemplo.com", "marketing", "gestor", "Post do Lodge 3", "media",
                          "casa_veraneio")
    assert referencias_pedido.linha_para_producao(tarefas.obter(outro)) == ""


def test_estudo_vira_observacao_para_aprovar(monkeypatch):
    import atividade

    monkeypatch.setattr(atividade, "_no_loop", lambda corrotina: corrotina.close())
    tarefa = tarefas.criar("teste_ref@exemplo.com", "marketing", "editor_video", f"Vídeo\n\n{LINK}", "media",
                           "casa_veraneio")
    assert referencias_pedido.registrar_estudo(tarefa, "Abrir com o check-in presencial funciona bem." * 20, "Pasta X")
    obs = correcoes._db().execute("SELECT * FROM observacoes WHERE tarefa_anterior = ?", (tarefa,)).fetchone()
    assert obs["tipo"] == "estudo" and obs["status"] == "nova" and len(obs["correcao"]) <= 500
    assert "só estudo" in obs["resposta_anterior"]
    assert not referencias_pedido.registrar_estudo(tarefa, "   ", "Pasta X")


# --- Trabalhador do Max ------------------------------------------------------------------

@pytest.fixture
def modulo(monkeypatch, tmp_path):
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "pasta_referencias.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts/max não montado")
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))
    import pasta_referencias

    raiz = tmp_path / "drive" / "REFERENCIAS"
    monkeypatch.setattr(pasta_referencias, "RAIZ", raiz)
    monkeypatch.setattr(pasta_referencias, "cadeia_do_link", lambda id_nuvem: [
        "(NOVO) CASA VERANEIO", "ESCRITÓRIO VERANEIO", "REFERENCIAS", "CASA VERANEIO",
        "12.11.26 Gestor - Videos com Serviços"] if id_nuvem.startswith("1_rC") else ["MARKETING", "LODGES"])
    for empresa, nome in (("CASA VERANEIO", "12.11.26 Gestor - Videos com Serviços"), ("CASA VERO", "Tours Vero 2")):
        (raiz / empresa / nome).mkdir(parents=True)
    return pasta_referencias


def test_acha_pela_link_e_pelo_nome_so_da_empresa(modulo):
    pela_link = modulo.achar({"texto": f"Use: {LINK}\n\n{USAR}"}, "casa_veraneio")
    assert [p.name for p in pela_link.pastas] == ["12.11.26 Gestor - Videos com Serviços"]
    assert pela_link.modo == "usar" and pela_link.add_dirs == pela_link.pastas
    pelo_nome = modulo.achar({"texto": CAMINHO, "historico": []}, "casa_veraneio")
    assert len(pelo_nome.pastas) == 1 and pelo_nome.modo == "estudo" and pelo_nome.add_dirs == []
    outra = modulo.achar({"texto": f"{LINK} e a pasta Tours Vero 2"}, "casa_vero")
    assert [p.name for p in outra.pastas] == ["Tours Vero 2"]
    assert any("outra empresa" in a for a in outra.avisos)  # a da Casa Veraneio não entra na peça da Vero
    fora = modulo.achar({"texto": "https://drive.google.com/drive/folders/9xyzABCDEFGHIJ"}, "casa_veraneio")
    assert not fora.pastas and "não está dentro" in fora.avisos[0]


def test_so_estudo_barra_a_pasta_inteira_e_uso_libera_so_a_citada(modulo):
    estudo = modulo.achar({"texto": f"{LINK}\n\n{ESTUDO}"}, "casa_veraneio")
    assert estudo.bloquear == [modulo.RAIZ]
    assert modulo.Referencias().bloquear == [modulo.RAIZ]  # sem citação: REFERENCIAS nunca entra
    uso = modulo.achar({"texto": f"{LINK}\n\n{USAR}"}, "casa_veraneio")
    barradas = {p.name for p in uso.bloquear}
    assert "CASA VERO" in barradas and "Tours Vero 2" in barradas
    assert "CASA VERANEIO" not in barradas and "12.11.26 Gestor - Videos com Serviços" not in barradas


def test_estudo_de_imagem_tem_marca_e_folha_nao_vai_para_a_entrega(modulo, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    pasta = modulo.RAIZ / "CASA VERANEIO" / "12.11.26 Gestor - Videos com Serviços"
    Image.new("RGB", (2000, 1500), "white").save(pasta / "foto servico.jpg")
    (pasta / "roteiro.pdf").write_bytes(b"%PDF")
    rascunho = tmp_path / "rascunho"
    refs = modulo.preparar(modulo.achar({"texto": f"{LINK}\n\n{ESTUDO}"}, "casa_veraneio"), rascunho, None)
    assert len(refs.folhas) == 1
    with Image.open(refs.folhas[0]) as folha:
        assert max(folha.size) <= modulo.LADO_IMAGEM
    indice = (rascunho / modulo.ESTUDO / "indice.md").read_text(encoding="utf-8")
    assert "foto servico.jpg" in indice and "não aberto" in indice
    assert "SÓ PARA ESTUDO" in modulo.instrucao(refs) and modulo.APRENDIZADO in modulo.instrucao(refs)
    final = rascunho / "entrega"
    final.mkdir()
    (final / "arte.jpg").write_bytes(refs.folhas[0].read_bytes())
    (final / "outra.png").write_bytes(b"png")
    novos, linha = modulo.conferir_finais(refs, final, ["arte.jpg", "outra.png"])
    assert novos == ["outra.png"] and "arte.jpg" in linha and not (final / "arte.jpg").exists()
    (rascunho / modulo.ESTUDO / modulo.APRENDIZADO).write_text("  Abrir pelo check-in.  ", encoding="utf-8")
    assert modulo.aprendizado(rascunho) == "Abrir pelo check-in."
