"""Onda 3, item 8: documentos como entrega. Planilha do catálogo em .xlsx pelo chat do Cérebro e pela rota (cerebro-21)
e .docx do estudo do Estrategista e do plano do Gestor de Tráfego como anexo da resposta (estrategista-16,
gestor_trafego-07). Banco temporário (tests/conftest.py), arquivos em tmp_path, dados fictícios.
"""

import asyncio
import io
import struct
import zipfile
import zlib
from xml.etree import ElementTree

import openpyxl
import pytest

import anexos
import auth
import cerebro_base as base
import cerebro_imoveis as imoveis
import documentos
import documentos_entrega as entrega
import historico
import orquestrador
import tarefas
from cerebro_texto import dividir

tarefas.iniciar()


def _documento(ref: str, conteudo: str, empresa: str = "casa_veraneio", fonte: str = "site") -> None:
    for t, c in dividir(conteudo.splitlines()[0].lstrip("# "), conteudo):
        base._inserir(fonte, ref, t, c, empresa)


def _apagar_lodges_de_teste() -> None:
    with base._trava, base.db() as conexao:
        conexao.execute("DELETE FROM conhecimento WHERE fonte_ref IN ('site/lodges/lodge-801', 'site/lodges/lodge-802')")
    base._indice = None
    imoveis.atualizar("casa_veraneio", forcar=True)


@pytest.fixture(autouse=True, scope="module")
def _lodges_de_teste_saem_no_fim():
    """O banco de teste é um só: os Lodges fictícios deste arquivo não podem vazar para o catálogo dos outros."""
    _apagar_lodges_de_teste()
    yield
    _apagar_lodges_de_teste()


def _lodges() -> None:
    if base.db().execute("SELECT 1 FROM conhecimento WHERE fonte_ref = 'site/lodges/lodge-801'").fetchone():
        return
    _documento("site/lodges/lodge-801", "# Lodge 801 — Cidade Ficticia Oito - SP\nFonte: https://www.exemplo.com/lodges/"
               "lodge-801 (dados oficiais do site)\nResumo: 6 quartos | até 14 pessoas | categoria: Campo\n\n"
               "## Valores por época\n- Alta temporada: diária R$ 9.876\n\n## Comodidades\nSauna, Piscina")
    _documento("site/lodges/lodge-802", "# Lodge 802 — Cidade Ficticia Oito - SP\nFonte: https://www.exemplo.com/lodges/"
               "lodge-802\nResumo: 3 quartos | até 6 pessoas | categoria: Praia\n\n## Comodidades\nChurrasqueira")


@pytest.fixture
def pasta_anexos(tmp_path, monkeypatch):
    monkeypatch.setattr(anexos, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(anexos, "PASTA", tmp_path / "dados" / "anexos")
    return tmp_path


def _tarefa(agente: str, texto: str, resposta: str = "", modelo: str = "groq/teste", andar: str = "comercial",
            empresa: str = "casa_veraneio") -> int:
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", andar, agente, texto, "simples", empresa)
    tarefas.atualizar(tarefa_id, status="concluida", resposta=resposta, modelo=modelo, tempo_segundos=1.0)
    return tarefa_id


def _arquivo(anexo: dict) -> bytes:
    linha = anexos._db().execute("SELECT caminho FROM anexos WHERE id = ?", (anexo["id"],)).fetchone()
    return anexos._absoluto(linha["caminho"]).read_bytes()


# --- Planilha do catálogo (cerebro-21) ----------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("Me manda a planilha do catálogo", True), ("Quero uma lista em Excel dos Lodges", True),
    ("xlsx dos imóveis com piscina", True), ("Planilha do Lodge 801", False),
    ("Escreva uma legenda para o Lodge de praia", False), ("Atualize a planilha de custos", False)])
def test_pede_planilha(texto, esperado):
    assert entrega.pede_planilha(texto) is esperado


def test_planilha_no_chat_anexa_xlsx_sem_preco(pasta_anexos):
    _lodges()
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "cerebro", "cerebro", "planilha do catálogo", "simples")
    resposta = entrega.planilha_no_chat(tarefa_id, "Me manda a planilha do catálogo", "casa_veraneio")
    assert "Planilha do catálogo da Casa Veraneio" in resposta and "Sem preços" in resposta
    assert len(resposta.splitlines()) == 3
    [anexo] = entrega.de(tarefa_id)
    assert anexo["mime"] == documentos.MIME_XLSX and anexo["nome"].endswith(".xlsx")
    livro = openpyxl.load_workbook(io.BytesIO(_arquivo(anexo)))
    assert livro.sheetnames == ["Imóveis", "Fonte e data"]
    aba = livro["Imóveis"]
    assert [c.value for c in aba[1]][:4] == ["Lodge", "Nome", "Cidade", "UF"]
    assert aba.auto_filter.ref and aba.freeze_panes == "A2"
    linhas = {r[0].value: r for r in aba.iter_rows(min_row=2)}
    assert 801 in linhas and linhas[801][3].value == "SP" and linhas[801][11].hyperlink is not None
    tudo = " ".join(str(c.value) for folha in livro for r in folha.iter_rows() for c in r if c.value is not None)
    assert "9.876" not in tudo and "R$" not in tudo  # sem preço
    fonte = {r[0].value: r[1].value for r in livro["Fonte e data"].iter_rows()}
    assert fonte["Empresa"] == "Casa Veraneio" and "Sem preços" in fonte["Atenção"]
    # Dono do pedido é o dono do anexo, e a descrição já nasce gravada: reenviar o arquivo não chama modelo nenhum.
    assert asyncio.run(anexos.descrever([anexo["id"]], "usuario.teste@exemplo.com")).count("gerada em código") == 1


def test_planilha_com_filtro_do_pedido(pasta_anexos):
    _lodges()
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "cerebro", "cerebro", "x", "simples")
    resposta = entrega.planilha_no_chat(tarefa_id, "Planilha em Excel dos Lodges com sauna", "casa_veraneio")
    assert "filtro: com sauna" in resposta
    aba = openpyxl.load_workbook(io.BytesIO(_arquivo(entrega.de(tarefa_id)[0])))["Imóveis"]
    numeros = [r[0].value for r in aba.iter_rows(min_row=2)]
    assert 801 in numeros and 802 not in numeros


def test_planilha_de_corp_e_vero_fica_para_depois(pasta_anexos):
    tarefa_id = tarefas.criar("usuario.teste@exemplo.com", "cerebro", "cerebro", "x", "simples", "cv_corporativo")
    assert "ainda não está pronta" in entrega.planilha_no_chat(tarefa_id, "planilha do catálogo", "cv_corporativo")
    assert entrega.de(tarefa_id) == [] and entrega.planilha_no_chat(tarefa_id, "Oi, tudo bem?", "casa_veraneio") is None


def test_rota_de_download_exige_login(monkeypatch):
    _lodges()
    monkeypatch.setattr(auth, "validar_token", lambda token: None)
    with pytest.raises(Exception) as erro:
        entrega.baixar_catalogo(authorization="Bearer falso")
    assert getattr(erro.value, "status_code", None) == 401
    monkeypatch.setattr(auth, "validar_token", lambda token: {"sub": "usuario.teste@exemplo.com"})
    resposta = entrega.baixar_catalogo(authorization="Bearer valido")
    assert resposta.media_type == documentos.MIME_XLSX and "attachment" in resposta.headers["content-disposition"]
    assert openpyxl.load_workbook(io.BytesIO(resposta.body)).sheetnames[0] == "Imóveis"


# --- .docx da resposta (estrategista-16, gestor_trafego-07) ----------------------------------------------------

ESTUDO = ("# Onde estamos\nA **Casa Veraneio** está em crescimento.\n\n## Matriz BCG\n| Empresa | Quadrante |\n|---|---|\n"
          "| Casa Veraneio | Estrela |\n| Casa Vero | Interrogação |\n\n- Primeiro passo: revisar o funil\n"
          "  - detalhe do passo\n- Fonte: [Relatório fictício](https://exemplo.com/estudo)\n\n" + "Texto do estudo. " * 90)


def _xml(conteudo: bytes, parte: str = "word/document.xml") -> str:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        texto = pacote.read(parte).decode()
    ElementTree.fromstring(texto)  # XML bem formado
    return texto


def test_estudo_do_estrategista_vira_docx_com_selo(pasta_anexos, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "ve_financeiro", lambda login: False)
    monkeypatch.setenv("DOCUMENTOS_MARCAS_DIR", str(tmp_path / "sem_marcas"))  # a cópia real do logo não conta aqui
    tarefa_id = _tarefa("estrategista", "Faça a matriz BCG das empresas", ESTUDO, modelo="claude-code/max")
    assert entrega.documento_da_resposta(tarefas.obter(tarefa_id))
    assert entrega.documento_da_resposta(tarefas.obter(tarefa_id)) is None  # uma vez só por resposta
    [anexo] = entrega.de(tarefa_id)
    assert anexo["mime"] == documentos.MIME_DOCX and " - Estudo - " in anexo["nome"]
    conteudo = _arquivo(anexo)
    xml = _xml(conteudo)
    for parte in ("word/styles.xml", "[Content_Types].xml", "docProps/core.xml"):
        _xml(conteudo, parte)
    assert f"ESTUDO de {documentos.hoje()}" in xml and "Estudo estratégico" in xml
    assert "<w:tbl>" in xml and "Interrogação" in xml and 'w:val="Titulo2"' in xml
    assert "Relatório fictício (https://exemplo.com/estudo)" in xml and "CONFIDENCIAL" not in xml
    assert "word/media/logo.png" not in zipfile.ZipFile(io.BytesIO(conteudo)).namelist()  # sem logo: só o nome
    mensagens = historico._mensagens_da_tarefa(tarefas.obter(tarefa_id))
    assert mensagens[-1]["anexos"][0]["id"] == anexo["id"]
    assert orquestrador._mensagem(tarefas.obter(tarefa_id))["anexos"][0]["id"] == anexo["id"]


def _png(largura: int, altura: int) -> bytes:
    bloco = lambda tipo, dados: struct.pack(">I", len(dados)) + tipo + dados + struct.pack(
        ">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    linhas = b"".join(b"\x00" + b"\xff\xff\xff" * largura for _ in range(altura))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(linhas)) + bloco(b"IEND", b""))


def test_capa_com_logo_lido_na_hora_e_confidencial(pasta_anexos, tmp_path, monkeypatch):
    marcas = tmp_path / "marcas" / "CASA_VERANEIO"
    marcas.mkdir(parents=True)
    (marcas / "logo_branca.png").write_bytes(_png(4, 2))
    monkeypatch.setenv("DOCUMENTOS_MARCAS_DIR", str(tmp_path / "marcas"))
    monkeypatch.setattr(auth, "ve_financeiro", lambda login: True)
    resposta = "## Plano\nInvestimento sugerido de R$ 1.000 por mês na campanha fictícia.\n" + "Conjunto A. " * 150
    tarefa_id = _tarefa("gestor_trafego", "Monte o plano de campanha do Lodge 801", resposta, andar="marketing")
    entrega.documento_da_resposta(tarefas.obter(tarefa_id))
    conteudo = _arquivo(entrega.de(tarefa_id)[0])
    pacote = zipfile.ZipFile(io.BytesIO(conteudo))
    assert pacote.read("word/media/logo.png") == _png(4, 2)
    assert 'Target="media/logo.png"' in _xml(conteudo, "word/_rels/document.xml.rels")
    xml = _xml(conteudo)
    assert "Plano de campanha" in xml and "CONFIDENCIAL" in xml and "ESTUDO de" not in xml
    assert 'cx="1800000" cy="900000"' in xml  # 5 cm de largura, proporção do PNG


@pytest.mark.parametrize("agente, texto, resposta, modelo", [
    ("estrategista", "O que é a matriz BCG?", "Explicação curta.", "groq/teste"),        # curta
    ("estrategista", "Me explique a BCG", "Texto. " * 300, "groq/teste"),                # conversa, sem pedir arquivo
    ("gestor_trafego", "Oi, tudo bem?", "Texto. " * 300, "groq/teste"),                  # não é plano
    ("cerebro", "Plano de campanha em documento", "Texto. " * 300, "groq/teste"),        # agente sem documento
    ("gestor_trafego", "Plano de campanha", "<<FORMULARIO>>{}<<FIM DO FORMULARIO>>" + "x" * 1300, "groq/teste")])
def test_respostas_que_ficam_so_no_chat(pasta_anexos, agente, texto, resposta, modelo):
    tarefa_id = _tarefa(agente, texto, resposta, modelo)
    assert entrega.documento_da_resposta(tarefas.obter(tarefa_id)) is None and entrega.de(tarefa_id) == []


def test_estrategista_com_pedido_de_documento(pasta_anexos, monkeypatch):
    monkeypatch.setattr(auth, "ve_financeiro", lambda login: False)
    tarefa_id = _tarefa("estrategista", "Me entregue a SWOT em documento Word", ESTUDO)
    assert entrega.documento_da_resposta(tarefas.obter(tarefa_id))
    assert "ESTUDO de" in _xml(_arquivo(entrega.de(tarefa_id)[0]))
