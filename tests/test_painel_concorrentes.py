"""Concorrentes do painel no Cérebro (18/11/2026): cada concorrente cadastrado no Laboratório vira uma ficha na empresa
de quem ele é concorrente, mais um índice por empresa; quem sai do painel é desativado no Cérebro. Banco fictício."""

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


def _modulo():
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "painel_analitico.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            break
    else:
        pytest.skip("scripts/max não montado")
    import painel_analitico
    return painel_analitico


def _banco():
    b = sqlite3.connect(":memory:")
    b.row_factory = sqlite3.Row
    b.executescript("""
        CREATE TABLE concorrentes (usuario TEXT, nome TEXT, foto TEXT, biografia TEXT, site TEXT, adicionado_em TEXT,
            atualizado_em TEXT, meta_page_id TEXT, google_dominio TEXT, meta_busca_em TEXT, anuncios_em TEXT, empresa TEXT);
        CREATE TABLE concorrentes_diario (usuario TEXT, data TEXT, seguidores INTEGER, posts INTEGER);
        CREATE TABLE concorrentes_posts (post_id TEXT, usuario TEXT, publicado_em TEXT, tipo TEXT, legenda TEXT, link TEXT,
            miniatura TEXT, curtidas INTEGER, comentarios INTEGER, visualizacoes INTEGER, atualizado_em TEXT);
        CREATE TABLE concorrentes_anuncios (anuncio_id TEXT, usuario TEXT, plataforma TEXT, ativo INTEGER, inicio TEXT,
            fim TEXT, formato TEXT, texto TEXT, titulo TEXT, chamada TEXT, destino TEXT, dias_exibido INTEGER);
    """)
    hoje = date.today()
    b.executemany("INSERT INTO concorrentes (usuario, nome, site, adicionado_em, empresa, meta_page_id) VALUES (?,?,?,?,?,?)", [
        ("casasdepraia", "Casas de Praia", "https://casasdepraia.com", "2026-11-17", "veraneio", "123"),
        ("eventosx", "Eventos X", None, "2026-11-18", "corp", None),
    ])
    b.executemany("INSERT INTO concorrentes_diario VALUES (?,?,?,?)", [
        ("casasdepraia", (hoje - timedelta(days=5)).isoformat(), 1000, 300),
        ("casasdepraia", hoje.isoformat(), 1050, 302),
    ])
    b.executemany("INSERT INTO concorrentes_posts (post_id, usuario, publicado_em, tipo, legenda, link, curtidas, comentarios) "
                  "VALUES (?,?,?,?,?,?,?,?)", [
        ("1", "casasdepraia", (hoje - timedelta(days=2)).isoformat(), "REELS", "Casa pé na areia", "https://ig/1", 500, 20),
        ("2", "casasdepraia", (hoje - timedelta(days=60)).isoformat(), "FOTO", "Vista do mar", "https://ig/2", 10, 1),
    ])
    b.executemany("INSERT INTO concorrentes_anuncios (anuncio_id, usuario, plataforma, ativo, inicio, formato, texto, titulo) "
                  "VALUES (?,?,?,?,?,?,?,?)", [
        ("meta:1", "casasdepraia", "meta", 1, "2026-11-01", "IMAGE", "Black Friday 6ª diária grátis", "Reserve"),
        ("meta:2", "casasdepraia", "meta", 1, "2026-11-02", "IMAGE", "Black Friday 6ª diária grátis", "Reserve"),
        ("meta:3", "casasdepraia", "meta", 0, "2026-10-01", "IMAGE", "Anúncio antigo", "Fora do ar"),
    ])
    return b


def test_ficha_e_indice_por_empresa():
    p = _modulo()
    docs = p.concorrentes(_banco())
    refs = {d["fonte_ref"]: d for d in docs}
    ficha = refs["analytics/casa_veraneio/concorrentes/casasdepraia"]
    assert ficha["empresa"] == "casa_veraneio" and ficha["fonte_tipo"] == "dados"
    assert "NÃO é uma empresa do grupo" in ficha["conteudo"]
    assert "1.050" in ficha["conteudo"] and "+50" in ficha["conteudo"]
    assert "Casa pé na areia" in ficha["conteudo"]
    assert ficha["conteudo"].count("Black Friday") == 1  # variações do mesmo anúncio contam uma vez
    assert "Anúncio antigo" not in ficha["conteudo"]  # só o que está no ar
    assert refs["analytics/cv_corporativo/concorrentes/eventosx"]["empresa"] == "cv_corporativo"
    indice = refs["analytics/casa_veraneio/concorrentes"]["conteudo"]
    assert "Casas de Praia (@casasdepraia)" in indice and "Eventos X" not in indice


def test_concorrente_removido_sai_do_cerebro(tmp_path):
    p = _modulo()
    arquivo = tmp_path / "concorrentes.json"
    removidos = []
    remover = lambda tipo, refs: removidos.append((tipo, refs)) or True
    p.remover_concorrentes_antigos({"a", "b"}, arquivo, remover)
    assert removidos == []
    p.remover_concorrentes_antigos({"a"}, arquivo, remover)
    assert removidos == [("dados", ["b"])]
    assert json.loads(arquivo.read_text(encoding="utf-8")) == ["a"]


def test_falha_ao_remover_tenta_de_novo(tmp_path):
    p = _modulo()
    arquivo = tmp_path / "concorrentes.json"
    arquivo.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    p.remover_concorrentes_antigos({"a"}, arquivo, lambda tipo, refs: False)
    assert json.loads(arquivo.read_text(encoding="utf-8")) == ["a", "b"]


def test_painel_sem_tabela_de_concorrentes():
    p = _modulo()
    b = sqlite3.connect(":memory:")
    b.row_factory = sqlite3.Row
    assert p.concorrentes(b) == []
