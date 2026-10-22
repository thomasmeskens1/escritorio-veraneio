"""Aprendizado do Despachante: ajusta a dificuldade das tarefas com base no histórico.

Fase 1 (estatística, ativa desde as primeiras tarefas): por agente e dificuldade, mede quantas tarefas
precisaram da fila e quanto tempo levaram, e sobe ou desce o nível quando o padrão é claro.
Fase 2 (ML progressivo): treina um classificador local nos marcos de 10/50/100/200 tarefas e, depois,
a cada 50 novas tarefas com a janela das últimas 200. Só é usado se acertar mais que as regras fixas.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from statistics import median

import config
import tarefas

log = logging.getLogger(__name__)

NIVEIS = ["simples", "media", "complexa"]
_PLURAL = {"simples": "simples", "media": "médias", "complexa": "complexas"}
MARCOS = [10, 50, 100, 200]
JANELA = 200
RETREINO_A_CADA = 50

MIN_AMOSTRAS_AJUSTE = 5
LIMITE_FILA_SUBIR = 0.5                               # metade ou mais precisou da fila: sobe um nível
TEMPO_ALTO = {"simples": 120, "media": 600}           # mediana acima disso: sobe um nível
TEMPO_BAIXO_MEDIA = 30                                # média sempre rápida e sem fila: desce para simples

PASTA = config.DADOS_DIR / "aprendizado"
ARQUIVO_MODELO = PASTA / "modelo.joblib"
ARQUIVO_META = PASTA / "modelo.json"

_ajustes: dict[tuple[str, str], dict] = {}
_modelo = None        # pipeline do scikit-learn, quando ativo
_meta: dict | None = None
_treinando = False


# --- Dados ---------------------------------------------------------------------------------

def _finalizadas(limite: int = JANELA) -> list:
    return tarefas._db().execute(
        "SELECT agente, texto, dificuldade, status, tempo_segundos, motivo FROM tarefas "
        "WHERE status IN ('concluida', 'falhou') ORDER BY id DESC LIMIT ?", (limite,),
    ).fetchall()


def _total_finalizadas() -> int:
    return tarefas._db().execute("SELECT COUNT(*) FROM tarefas WHERE status IN ('concluida', 'falhou')").fetchone()[0]


def rotulo_observado(linha) -> str:
    """Dificuldade que a tarefa 'mostrou ter' pelo resultado (alvo do aprendizado)."""
    if linha["status"] == "falhou" or linha["motivo"] is not None or linha["tempo_segundos"] > TEMPO_ALTO["media"]:
        return "complexa"
    return "simples" if linha["tempo_segundos"] <= 60 else "media"


# --- Fase 1: estatística -------------------------------------------------------------------

def atualizar_ajustes() -> None:
    grupos: dict[tuple[str, str], list] = {}
    for linha in _finalizadas():
        grupos.setdefault((linha["agente"], linha["dificuldade"]), []).append(linha)

    novos = {}
    for (agente, nivel), linhas in grupos.items():
        if len(linhas) < MIN_AMOSTRAS_AJUSTE:
            continue
        taxa_fila = sum(l["motivo"] is not None for l in linhas) / len(linhas)
        tempo = median(l["tempo_segundos"] for l in linhas)
        indice = NIVEIS.index(nivel)
        if indice < 2 and (taxa_fila >= LIMITE_FILA_SUBIR or tempo > TEMPO_ALTO[nivel]):
            motivo = (f"{taxa_fila:.0%} das tarefas {_PLURAL[nivel]} precisaram da fila" if taxa_fila >= LIMITE_FILA_SUBIR
                      else f"tempo mediano de {tempo:.0f} s")
            novos[(agente, nivel)] = {"para": NIVEIS[indice + 1], "motivo": motivo}
        elif nivel == "media" and taxa_fila == 0 and tempo < TEMPO_BAIXO_MEDIA:
            novos[(agente, nivel)] = {"para": "simples", "motivo": f"médias concluídas em {tempo:.0f} s, sem fila"}
    _ajustes.clear()
    _ajustes.update(novos)


def ajustar(agente: str, nivel: str, texto: str) -> str:
    """Nível final: modelo treinado (se ativo e melhor que as regras), senão regras + ajustes estatísticos."""
    if _modelo is not None:
        try:
            return str(_modelo.predict([_entrada(agente, texto)])[0])
        except Exception:
            log.exception("Falha ao prever com o modelo treinado; usando as regras.")
    ajuste = _ajustes.get((agente, nivel))
    return ajuste["para"] if ajuste else nivel


# --- Fase 2: ML progressivo ----------------------------------------------------------------

def _entrada(agente: str, texto: str) -> str:
    # O agente vira um token no texto: um único TF-IDF cobre os dois sinais.
    return f"__agente_{agente}__ {texto}"


def _proximo_marco(total: int) -> int:
    ultimo = (_meta or {}).get("amostras_totais", 0)
    for marco in MARCOS:
        if ultimo < marco:
            return marco
    return ultimo + RETREINO_A_CADA


def _treinar(linhas: list[dict]) -> tuple[object, dict]:
    """Roda em thread. Validação cruzada contra a acurácia das regras fixas nos mesmos dados."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline

    entradas = [_entrada(l["agente"], l["texto"]) for l in linhas]
    rotulos = [rotulo_observado(l) for l in linhas]
    acuracia_regras = sum(l["dificuldade"] == r for l, r in zip(linhas, rotulos)) / len(linhas)
    meta = {"treinado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "amostras": len(linhas),
            "acuracia": None, "acuracia_regras": round(acuracia_regras, 3), "ativo": False}

    menor_classe = min(rotulos.count(r) for r in set(rotulos))
    if len(set(rotulos)) < 2 or menor_classe < 2:
        meta["observacao"] = "Dados ainda sem variedade suficiente para treinar."
        return None, meta

    pipeline = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True),
                             LogisticRegression(max_iter=1000, class_weight="balanced"))
    divisoes = StratifiedKFold(n_splits=min(5, menor_classe), shuffle=True, random_state=42)
    acuracia = cross_val_score(pipeline, entradas, rotulos, cv=divisoes).mean()
    pipeline.fit(entradas, rotulos)
    meta["acuracia"] = round(float(acuracia), 3)
    meta["ativo"] = bool(acuracia > acuracia_regras)  # bool do Python (o do NumPy não vai para JSON)
    return pipeline, meta


async def talvez_treinar(forcar: bool = False) -> dict | None:
    """Chamado ao fim de cada tarefa: atualiza a estatística e treina ao atingir o próximo marco.
    `forcar=True` (botão "Treinar agora" da diretoria) treina já. Devolve o resultado do treino, se houve."""
    global _modelo, _meta, _treinando
    atualizar_ajustes()
    total = _total_finalizadas()
    if _treinando or not total or (not forcar and total < _proximo_marco(total)):
        return None
    _treinando = True
    try:
        linhas = [dict(l) for l in _finalizadas(JANELA)]  # lê no loop principal; treina em thread
        modelo, meta = await asyncio.to_thread(_treinar, linhas)
        meta["amostras_totais"] = total
        _salvar(modelo, meta)
        _meta, _modelo = meta, (modelo if meta["ativo"] else None)
        log.info("Aprendizado: treino com %s tarefas, acurácia %s (regras %s), ativo=%s.",
                 meta["amostras"], meta["acuracia"], meta["acuracia_regras"], meta["ativo"])
        return meta
    except Exception:
        log.exception("Falha no treino do aprendizado.")
        return None
    finally:
        _treinando = False


def ajustes_do_agente(agente: str) -> list[dict]:
    return [{"de": de, **ajuste} for (a, de), ajuste in _ajustes.items() if a == agente]


def _salvar(modelo, meta: dict) -> None:
    import joblib

    PASTA.mkdir(parents=True, exist_ok=True)
    ARQUIVO_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if modelo is not None:
        joblib.dump(modelo, ARQUIVO_MODELO)


def carregar() -> None:
    """Na subida do servidor: recupera o último treino e recalcula a estatística."""
    global _modelo, _meta
    atualizar_ajustes()
    if ARQUIVO_META.exists():
        _meta = json.loads(ARQUIVO_META.read_text(encoding="utf-8"))
        if _meta.get("ativo") and ARQUIVO_MODELO.exists():
            import joblib

            _modelo = joblib.load(ARQUIVO_MODELO)


def resumo(nome_do_agente) -> dict:
    """Para o painel do Despachante."""
    total = _total_finalizadas()
    modelo = None
    if _meta:
        modelo = {k: _meta.get(k) for k in ("treinado_em", "amostras", "acuracia", "acuracia_regras", "ativo")}
    return {
        "tarefas_registradas": total,
        "marcos": MARCOS,
        "janela": JANELA,
        "retreino_a_cada": RETREINO_A_CADA,
        "proximo_treino_em": max(0, _proximo_marco(total) - total),
        "modelo": modelo,
        "ajustes": [{"agente": agente, "agente_nome": nome_do_agente(agente), "de": de, **ajuste}
                    for (agente, de), ajuste in _ajustes.items()],
    }
