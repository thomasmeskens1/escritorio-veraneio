"""Rede neural do Cérebro (Thomas, 29/10/2026): aprende, com o uso, quais trechos de conhecimento ajudam de verdade.

Cada consulta ao Cérebro guarda os sinais de cada trecho usado (cerebro_base.registrar_consulta): similaridade de
significado (a rede de embeddings), cobertura das palavras, peso da fonte, recência, pontuação e posição. O rótulo
vem depois, da própria tarefa: 👍 ou elogio = o trecho ajudou; 👎 ou correção = atrapalhou.

Com exemplos suficientes, treina uma rede neural pequena (perceptron multicamadas, scikit-learn, no PC, custo zero)
que prevê a utilidade de um trecho a partir desses sinais. Ela só entra na busca se separar o útil do inútil melhor
que a ordem atual (validação cruzada); senão fica aprendendo em silêncio. Treina no "Treinar agora" e na
consolidação semanal.
"""

import json
import logging
from datetime import datetime, timezone

import numpy as np

import config
import tarefas

log = logging.getLogger(__name__)

MINIMO_EXEMPLOS = 300
MINIMO_POR_CLASSE = 30
GANHO_MINIMO = 0.02  # a rede precisa superar a ordem atual por pelo menos 2 pontos de AUC
FONTES = ("ensinado", "oficial", "site", "drive", "dados", "rede", "tarefa")
PASTA = config.DADOS_DIR / "aprendizado"
ARQUIVO_MODELO = PASTA / "reranker.joblib"
ARQUIVO_META = PASTA / "reranker.json"

_modelo = None
_meta: dict | None = None


def vetor(s: dict) -> list[float]:
    return [s.get("cosseno", 0.0), s.get("cobertura", 0.0), s.get("peso", 1.0), s.get("recencia", 1.0),
            s.get("pontuacao", 0.0), min(s.get("posicao", 0), 40) / 40,
            *[1.0 if s.get("fonte") == f else 0.0 for f in FONTES]]


def _rotulos() -> dict[int, int]:
    """tarefa_id -> 1 (ajudou) ou 0 (atrapalhou). O 👍/👎 vale mais que o elogio/correção da mesma tarefa."""
    db = tarefas._db()
    rotulos: dict[int, int] = {}
    try:
        for l in db.execute("SELECT tarefa_anterior, tipo FROM observacoes WHERE tarefa_anterior IS NOT NULL"):
            if l["tipo"] in ("elogio", "correcao"):
                rotulos[l["tarefa_anterior"]] = 1 if l["tipo"] == "elogio" else 0
    except Exception:
        pass  # tabela ainda não criada
    try:
        for l in db.execute("SELECT tarefa_id, valor FROM avaliacoes"):
            rotulos[l["tarefa_id"]] = 1 if l["valor"] > 0 else 0
    except Exception:
        pass
    return rotulos


def exemplos() -> tuple[np.ndarray, np.ndarray]:
    rotulos = _rotulos()
    if not rotulos:
        return np.zeros((0, len(vetor({})))), np.zeros(0)
    try:
        linhas = tarefas._db().execute("SELECT tarefa_id, sinais FROM consulta_sinais").fetchall()
    except Exception:
        linhas = []
    pares = [(vetor(json.loads(l["sinais"])), rotulos[l["tarefa_id"]]) for l in linhas if l["tarefa_id"] in rotulos]
    if not pares:
        return np.zeros((0, len(vetor({})))), np.zeros(0)
    return np.array([p[0] for p in pares], dtype=np.float32), np.array([p[1] for p in pares])


def status() -> dict:
    """Para o relatório do treino: quantos exemplos rotulados já existem e se a rede está ativa."""
    _, y = exemplos()
    positivos, negativos = int(y.sum()), int(len(y) - y.sum())
    return {"exemplos": int(len(y)), "positivos": positivos, "negativos": negativos, "minimo": MINIMO_EXEMPLOS,
            "minimo_por_classe": MINIMO_POR_CLASSE, **({k: _meta.get(k) for k in
                                                         ("treinado_em", "auc", "auc_atual", "ativo")} if _meta else {})}


def treinar() -> dict:
    """Treina se houver exemplos suficientes; ativa só se superar a ordem atual. Devolve o status."""
    global _modelo, _meta
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y = exemplos()
    positivos, negativos = int(y.sum()), int(len(y) - y.sum())
    if len(y) < MINIMO_EXEMPLOS or min(positivos, negativos) < MINIMO_POR_CLASSE:
        return {**status(), "observacao": (f"Ainda aprendendo: {len(y)} de {MINIMO_EXEMPLOS} exemplos rotulados "
                                           f"({positivos} úteis, {negativos} que atrapalharam). Cada 👍/👎, elogio "
                                           "ou correção aumenta essa base.")}
    rede = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(16, 8), max_iter=2000, random_state=42))
    divisoes = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    try:
        previsto = cross_val_predict(rede, X, y, cv=divisoes, method="predict_proba")[:, 1]
        auc = float(roc_auc_score(y, previsto))
        auc_atual = float(roc_auc_score(y, -X[:, 5]))  # a ordem atual: quem vem primeiro é tido como mais útil
        rede.fit(X, y)
    except Exception:
        log.exception("Falha no treino da rede do Cérebro.")
        return {**status(), "observacao": "O treino da rede falhou; a busca segue com a ordem atual."}
    meta = {"treinado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "exemplos": int(len(y)),
            "auc": round(auc, 3), "auc_atual": round(auc_atual, 3), "ativo": auc > auc_atual + GANHO_MINIMO}
    import joblib

    PASTA.mkdir(parents=True, exist_ok=True)
    joblib.dump(rede, ARQUIVO_MODELO)
    ARQUIVO_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _meta, _modelo = meta, (rede if meta["ativo"] else None)
    log.info("Rede do Cérebro: %s exemplos, AUC %s (ordem atual %s), ativa=%s.", len(y), auc, auc_atual, meta["ativo"])
    return {**status(), "observacao": (
        f"A rede separou o útil do inútil com AUC {auc:.2f}, contra {auc_atual:.2f} da ordem atual: "
        + ("ela passa a reordenar as buscas do Cérebro." if meta["ativo"]
           else "ainda não supera a ordem atual o bastante, então segue aprendendo sem interferir."))}


def carregar() -> None:
    global _modelo, _meta
    if ARQUIVO_META.exists():
        _meta = json.loads(ARQUIVO_META.read_text(encoding="utf-8"))
        if _meta.get("ativo") and ARQUIVO_MODELO.exists():
            import joblib

            _modelo = joblib.load(ARQUIVO_MODELO)


def prever(sinais: list[dict]) -> np.ndarray | None:
    """Probabilidade de cada trecho ajudar (None se a rede ainda não está ativa)."""
    if _modelo is None or not sinais:
        return None
    try:
        return _modelo.predict_proba(np.array([vetor(s) for s in sinais], dtype=np.float32))[:, 1]
    except Exception:
        log.exception("Rede do Cérebro falhou ao prever; seguindo com a ordem atual.")
        return None
