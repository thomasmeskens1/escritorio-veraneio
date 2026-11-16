"""Drive pela API (16/11/2026): Docs e Planilhas nativos do Google, que no G: são só atalhos, vão ao Cérebro das pastas
LODGES, MARKETING e CORPORATIVO; nada sensível vai nem é lido. Banco do Drive fictício em tmp_path; nada toca o Drive
nem a API de verdade."""

import io
import sqlite3
import sys
from pathlib import Path

import pytest

DOC = "application/vnd.google-apps.document"
PLANILHA = "application/vnd.google-apps.spreadsheet"


def _modulo(monkeypatch, tmp_path):
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "drive_api.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts/max não montado")
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))
    import drive_api

    return drive_api


def _banco(tmp_path, arquivos: list[tuple]) -> str:
    """arquivos: (id, caminho 'A/B/Titulo.gdoc', mime, modificado)."""
    caminho = str(tmp_path / "metadata_sqlite_db")
    db = sqlite3.connect(caminho)
    db.execute("CREATE TABLE items (stable_id INTEGER, id TEXT, trashed INT, is_folder INT, mime_type TEXT, "
               "modified_date INT, local_title TEXT)")
    db.execute("CREATE TABLE stable_parents (item_stable_id INTEGER, parent_stable_id INTEGER)")
    pastas, proximo = {}, [1]

    def pasta(partes: tuple) -> int:
        if partes not in pastas:
            proximo[0] += 1
            pastas[partes] = proximo[0]
            db.execute("INSERT INTO items VALUES (?, ?, 0, 1, 'application/vnd.google-apps.folder', 0, ?)",
                       (proximo[0], f"pasta{proximo[0]}", partes[-1]))
            if len(partes) > 1:
                db.execute("INSERT INTO stable_parents VALUES (?, ?)", (proximo[0], pasta(partes[:-1])))
        return pastas[partes]

    for nuvem, rota, mime, modificado in arquivos:
        *topo, titulo = rota.split("/")
        proximo[0] += 1
        sid = proximo[0]
        db.execute("INSERT INTO items VALUES (?, ?, 0, 0, ?, ?, ?)", (sid, nuvem, mime, modificado, titulo))
        db.execute("INSERT INTO stable_parents VALUES (?, ?)", (sid, pasta(tuple(topo))))
    db.commit()
    db.close()
    return caminho


ARQUIVOS = [
    ("idlegenda", "(NOVO) CASA VERANEIO/MARKETING/THOMAS/Legenda - Post 1.gdoc", DOC, 1),
    ("idinfos", "(NOVO) CASA VERANEIO/LODGES/INFOS LODGES/Infos Lodge Brasil.gsheet", PLANILHA, 1),
    ("idseguro", "(NOVO) CASA VERANEIO/CORPORATIVO/EVENTOS/Info seguro eventos.gsheet", PLANILHA, 1),
    ("idsenha", "(NOVO) CASA VERANEIO/MARKETING/Senhas e Dados bancários.gdoc", DOC, 1),
    ("idclientes", "(NOVO) CASA VERANEIO/MARKETING/CLIENTES FECHADOS/Controle.gsheet", PLANILHA, 1),
    ("idproducao", "(NOVO) CASA VERANEIO/PRODUÇÃO/Pesquisa de satisfação.gsheet", PLANILHA, 1),
    ("local-123", "(NOVO) CASA VERANEIO/MARKETING/Novo.gdoc", DOC, 1),  # ainda não sincronizado
]


def test_so_as_pastas_liberadas_e_nada_sensivel(monkeypatch, tmp_path):
    d = _modulo(monkeypatch, tmp_path)
    itens = {i["id"]: i for i in d.nativos(_banco(tmp_path, ARQUIVOS))}
    assert "local-123" not in itens
    assert itens["idlegenda"]["titulo"] == "Legenda - Post 1"
    assert itens["idlegenda"]["pastas"] == ["(NOVO) CASA VERANEIO", "MARKETING", "THOMAS"]
    destino = {i: d.empresa_no_cerebro(item) for i, item in itens.items()}
    assert destino == {"idlegenda": "casa_veraneio", "idinfos": "casa_veraneio", "idseguro": "cv_corporativo",
                       "idsenha": None, "idclientes": None, "idproducao": None}


def test_envia_so_o_que_mudou_e_tira_o_que_sumiu(monkeypatch, tmp_path):
    d = _modulo(monkeypatch, tmp_path)
    enviados, removidos, exportados = [], [], []
    hashes = tmp_path / "hashes.json"

    def rodar(arquivos, rodada):
        (tmp_path / rodada).mkdir()
        return d.sincronizar(banco=_banco(tmp_path / rodada, arquivos),
                             enviar=lambda docs: enviados.extend(docs) or True,
                             remover=lambda tipo, refs: removidos.extend(refs) or True,
                             exportar_fn=lambda i, m, t: exportados.append(i) or f"texto de {i}",
                             token_fn=lambda: "falso", arquivo_hashes=hashes)

    r = rodar(ARQUIVOS, "1")
    assert (r["liberados"], r["enviados"]) == (3, 3)
    assert sorted(exportados) == ["idinfos", "idlegenda", "idseguro"]  # o sensível nem é exportado
    doc = next(x for x in enviados if x["fonte_ref"] == "drive/nativo/idlegenda")
    assert doc["fonte_tipo"] == "drive" and doc["empresa"] == "casa_veraneio"
    assert "texto de idlegenda" in doc["conteudo"] and "MARKETING > THOMAS" in doc["conteudo"]

    exportados.clear()
    alterado = [("idlegenda", ARQUIVOS[0][1], DOC, 2), ARQUIVOS[1]]  # legenda editada; seguro apagado
    rodar(alterado, "2")
    assert exportados == ["idlegenda"]
    assert removidos == ["drive/nativo/idseguro"]


def test_planilha_vira_texto_com_todas_as_abas(monkeypatch, tmp_path):
    d = _modulo(monkeypatch, tmp_path)
    openpyxl = pytest.importorskip("openpyxl")
    livro = openpyxl.Workbook()
    livro.active.title = "Lodges"
    livro.active.append(["Lodge", "Cidade"])
    livro.active.append([5, "Ubatuba"])
    livro.create_sheet("Vazia")
    buffer = io.BytesIO()
    livro.save(buffer)
    texto = d._planilha_em_texto(buffer.getvalue())
    assert texto == "## Aba: Lodges\nLodge | Cidade\n5 | Ubatuba"


def test_ler_acha_pelo_caminho_do_g_e_recusa_sensivel(monkeypatch, tmp_path):
    d = _modulo(monkeypatch, tmp_path)
    banco = _banco(tmp_path, ARQUIVOS)
    caminho = r"G:\Drives compartilhados\(NOVO) CASA VERANEIO\MARKETING\THOMAS\Legenda - Post 1.gdoc"
    assert d._resolver(caminho, banco)["id"] == "idlegenda"
    assert d._resolver("https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit", banco)["id"] \
        == "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    originais = d.nativos
    monkeypatch.setattr(d, "nativos", lambda banco_=None: originais(banco))
    monkeypatch.setattr(d, "_token", lambda: "falso")
    monkeypatch.setattr(d, "exportar", lambda *a: pytest.fail("não pode exportar arquivo sensível"))
    assert "sensível" in d.ler(r"G:\x\(NOVO) CASA VERANEIO\MARKETING\Senhas e Dados bancários.gdoc")
