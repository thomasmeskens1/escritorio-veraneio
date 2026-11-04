"""Decisões do Thomas de 04/11/2026: "Réveillon 2027" (nunca 2026/27), nomes da agenda para todos e documentos da
resposta também no Drive, numa pasta da solicitação. Banco temporário (tests/conftest.py)."""

import base64
import json

import agenda_clientes as a
import conferente
import documentos
import documentos_entrega as entrega
import producao
import tarefas

tarefas.iniciar()


def test_reveillon_2026_27_vira_aviso_e_2027_nao():
    avisos = " ".join(conferente.conferir("Garanta o seu Réveillon 2026/27 no Lodge 34.", "casa_veraneio"))
    assert "nome do período fora do padrão" in avisos
    assert "nome do período" not in " ".join(conferente.conferir("Garanta o seu Réveillon 2027.", "casa_veraneio"))


def test_nomes_da_agenda_para_todos():
    # Era o "*" em dados/agenda_clientes.json; desde a decisão 11 (04/11/2026) vale sem arquivo.
    assert a.ve_nomes("qualquer.pessoa@exemplo.com")


def test_documento_vai_para_a_fila_do_drive_na_pasta_da_solicitacao():
    tarefa = tarefas.criar("usuario.teste", "comercial", "estrategista", "[Pedido feito ao Estrategista] Matriz BCG "
                           "dos Lodges / praia", "media", "cv_corporativo")
    anexo = entrega.anexar(tarefa, b"conteudo do docx", "Estudo.docx", documentos.MIME_DOCX, "teste")
    assert anexo
    linha = producao._db().execute("SELECT payload FROM trabalhos_max WHERE tipo = 'documento' ORDER BY id DESC "
                                   "LIMIT 1").fetchone()
    payload = json.loads(linha["payload"])
    assert payload["pasta_andar"] == "COMERCIAL" and payload["tarefa_id"] == tarefa
    assert payload["pasta"] == f"CORP ｜ ESTUDO - MATRIZ BCG DOS LODGES PRAIA #{tarefa}"
    assert base64.b64decode(payload["conteudo_b64"]) == b"conteudo do docx"
