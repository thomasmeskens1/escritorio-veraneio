"""Prova semanal do Cérebro (cerebro-06), num banco temporário (conftest) com um gabarito FICTÍCIO.

  docker compose run --rm --no-deps -T -v "$(pwd -W)/tests:/testes:ro" -w /app -e PYTHONPATH=/app api \
      python -m pytest -p no:cacheprovider /testes/test_cerebro_prova.py
"""

import json
import tempfile
from pathlib import Path

import pytest

import cerebro_base as base
import cerebro_prova
import cerebro_prova_gabarito
import reranker
import saude
import tarefas

_PASTA = Path(tempfile.mkdtemp())
EXEMPLO = Path(__file__).parent / "cerebro_prova_exemplo.json"

reranker.PASTA = _PASTA / "aprendizado"
reranker.ARQUIVO_MODELO = reranker.PASTA / "reranker.joblib"
reranker.ARQUIVO_META = reranker.PASTA / "reranker.json"
cerebro_prova.ARQUIVO = EXEMPLO
tarefas.iniciar()


@pytest.fixture(autouse=True)
def _indice_novo_depois():
    """A busca aceita índice de até 15 s: sem isto, o teste seguinte (outro arquivo) veria a base fictícia velha."""
    yield
    base._indice = None


class _Rede:
    """Rede de mentira: acha todo trecho igualmente útil (não muda a ordem da busca)."""

    def __init__(self, nome: str):
        self.nome = nome

    def __eq__(self, outro):
        return getattr(outro, "nome", outro) == self.nome

    def predict_proba(self, X):
        import numpy as np

        return np.full((len(X), 2), 0.5)


def _trecho(empresa: str, ref: str, titulo: str, conteudo: str) -> None:
    with base.db() as db:
        db.execute("INSERT INTO conhecimento (fonte_tipo, fonte_ref, titulo, conteudo, peso_fonte, criado_em, "
                   "atualizado_em, empresa) VALUES ('site', ?, ?, ?, 1.1, ?, ?, ?)",
                   (ref, titulo, conteudo, base.agora(), base.agora(), empresa))
    base._mudou()


def _base_ficticia() -> None:
    if base.db().execute("SELECT 1 FROM conhecimento WHERE fonte_ref = 'site/lodges/lodge-901'").fetchone():
        return
    _trecho("casa_veraneio", "site/lodges/lodge-901", "Lodge 901 — Cidade Exemplo - SP › Lodge 901 — Cidade Exemplo - SP",
            "Fonte: https://exemplo.invalid/lodges/lodge-901\nResumo: 6 quartos | 6 banheiros | até 12 pessoas | "
            "categoria: Campo")
    _trecho("casa_veraneio", "site/lodges-orlando", "Lodges Orlando", "Casas com piscina em Orlando, na Flórida.")
    _trecho("cv_corporativo", "corporativo/espacos/lodge-901", "Lodge 901 — Vila Fictícia - SP (Corporativo)",
            "Espaço para eventos (Lodge 901).\nLocal: Vila Fictícia - SP\nConvidados: até 80 pessoas")
    _trecho("casa_vero", "vero/imoveis/vero-901", "Vero 901 — Casa Serra Exemplo (Casa Vero)",
            "Negócio e localização: Venda — Casa Serra Exemplo\nResumo: 5 dormitórios | 3 suítes")


def _limpar_provas() -> None:
    with cerebro_prova._db() as db:
        db.execute("DELETE FROM provas_cerebro")


def test_conferir_ref_texto_e_proibidos():
    item = {"ref": "site/lodges/lodge-1", "contem": ["Vila Fictícia"], "nao_contem": ["Orlando"],
            "proibido_ref": ["vero/"]}
    certo = {"fonte_ref": "site/lodges/lodge-1", "titulo": "Lodge 1 — VILA FICTICIA - SP", "conteudo": ""}
    assert cerebro_prova.conferir(item, [certo]) is None  # sem acento e sem caixa
    assert "não veio" in cerebro_prova.conferir(item, [{**certo, "fonte_ref": "site/lodges/lodge-2"}])
    assert "sem" in cerebro_prova.conferir(item, [{**certo, "titulo": "Lodge 1 — Cidade Exemplo"}])
    assert "proibida" in cerebro_prova.conferir(item, [certo, {"fonte_ref": "vero/imoveis/vero-1"}])
    assert "Orlando" in cerebro_prova.conferir(item, [certo, {"fonte_ref": "site/x", "conteudo": "orlando"}])


def test_prova_na_busca_separa_empresas_e_marca_gabarito_desatualizado():
    _base_ficticia()
    prova = cerebro_prova.rodar(cerebro_prova.carregar_gabarito(EXEMPLO))
    assert prova["falhas"] == [] and (prova["acertos"], prova["total"]) == (5, 5)
    assert prova["por_empresa"]["cv_corporativo"] == {"acertos": 1, "total": 1}
    assert prova["desatualizadas"] == ["cv-999-cidade"]  # a ficha do Lodge 999 não existe: não conta na nota


def test_retreino_que_piora_a_nota_e_descartado_e_avisa(monkeypatch):
    _base_ficticia()
    _limpar_provas()
    reranker.PASTA.mkdir(parents=True, exist_ok=True)
    reranker.ARQUIVO_META.write_text(json.dumps({"treinado_em": "antigo", "ativo": True}), encoding="utf-8")
    reranker.ARQUIVO_MODELO.write_bytes(b"rede antiga")
    reranker._meta, reranker._modelo = {"treinado_em": "antigo", "ativo": True}, _Rede("rede antiga")

    def treino_que_atrapalha():
        reranker.ARQUIVO_MODELO.write_bytes(b"rede nova")
        reranker._meta, reranker._modelo = {"treinado_em": "novo", "ativo": True}, _Rede("rede nova")
        return {"observacao": "treinou"}

    notas = iter([5, 3])
    original = cerebro_prova.rodar

    def rodar_com_nota(gabarito=None, k=cerebro_prova.K):
        prova = original(gabarito)
        return {**prova, "acertos": next(notas)}

    monkeypatch.setattr(reranker, "treinar", treino_que_atrapalha)
    monkeypatch.setattr(cerebro_prova, "rodar", rodar_com_nota)
    status = cerebro_prova.treinar_com_prova("teste")
    assert status["prova"]["descartado"] and reranker._modelo == "rede antiga"
    assert reranker.ARQUIVO_MODELO.read_bytes() == b"rede antiga"
    assert json.loads(reranker.ARQUIVO_META.read_text(encoding="utf-8"))["treinado_em"] == "antigo"
    assert cerebro_prova.resumo()["acertos"] == 5  # a nota em uso é a da rede que voltou
    avisos = cerebro_prova.avisos()
    assert any("descartado" in a and "3/5" in a for a in avisos)
    assert any("gabarito" in a for a in avisos)  # o Lodge 999 do exemplo saiu da base
    monkeypatch.setattr(saude, "avisos_da_caixa_de_areia", lambda: [])
    monkeypatch.setattr(saude, "ollama_ok", lambda: True)
    assert any("Prova do Cérebro" in a for a in saude.avisos_da_operacao())


def test_retreino_que_mantem_a_nota_fica_e_queda_sem_retreino_avisa(monkeypatch):
    _base_ficticia()
    _limpar_provas()
    reranker._meta, reranker._modelo = {"treinado_em": "antigo", "ativo": True}, _Rede("rede antiga")

    def treino_bom():
        reranker._meta, reranker._modelo = {"treinado_em": "bom", "ativo": True}, _Rede("rede boa")
        return {"observacao": "treinou"}

    monkeypatch.setattr(reranker, "treinar", treino_bom)
    status = cerebro_prova.treinar_com_prova("teste")
    assert not status["prova"].get("descartado") and reranker._modelo == "rede boa"
    assert "5/5" in status["prova"]["observacao"]
    # Semana seguinte: a ficha do Corporativo sumiu da busca (fonte mudou), sem retreino que mexa na rede.
    with base.db() as db:
        db.execute("UPDATE conhecimento SET conteudo = 'Espaço para eventos.' WHERE fonte_ref = "
                   "'corporativo/espacos/lodge-901'")
        db.execute("UPDATE conhecimento SET titulo = 'Espaço 901' WHERE fonte_ref = 'corporativo/espacos/lodge-901'")
    base._mudou()
    monkeypatch.setattr(reranker, "treinar", lambda: {"observacao": "Ainda aprendendo"})
    cerebro_prova.treinar_com_prova("teste")
    assert cerebro_prova.resumo()["acertos"] == 4
    assert any("caiu de 5/5" in a for a in cerebro_prova.avisos())
    with base.db() as db:  # devolve a base fictícia para os outros testes
        db.execute("DELETE FROM conhecimento WHERE fonte_ref LIKE '%-901' OR fonte_ref = 'site/lodges-orlando'")
    base._mudou()
    reranker._meta, reranker._modelo = None, None


def test_gabarito_sai_das_fichas_do_banco_em_blocos_separados():
    _base_ficticia()
    gabarito = cerebro_prova_gabarito.gerar(base.db())
    cv = {i["id"]: i for i in gabarito["empresas"]["casa_veraneio"]}
    assert cv["cv-901-cidade"]["contem"] == ["Cidade Exemplo"] and cv["cv-901-pessoas"]["contem"] == ["até 12 pessoas"]
    assert "vero/" in cv["cv-901-cidade"]["proibido_ref"]
    corp = {i["id"]: i for i in gabarito["empresas"]["cv_corporativo"]}
    assert corp["corp-901-local"]["contem"] == ["Vila Fictícia"] and "site/" in corp["corp-901-local"]["proibido_ref"]
    vero = {i["id"]: i for i in gabarito["empresas"]["casa_vero"]}
    assert vero["vero-901-dormitorios"]["contem"] == ["5 dormitórios"]
