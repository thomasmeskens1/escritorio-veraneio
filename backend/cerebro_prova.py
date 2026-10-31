"""Prova semanal do Cérebro (brainstorm de 31/10/2026, cerebro-06): um número para a qualidade da busca e um alarme.

O gabarito (backend/dados/cerebro_prova.json, fora do git; gerado por cerebro_prova_gabarito.py a partir das fichas
oficiais) tem 20 a 30 perguntas por empresa. A prova mede a BUSCA, não uma resposta gerada: para cada pergunta,
base.buscar devolve os 5 primeiros trechos da empresa e o código confere, sem IA, que
- um deles é do documento esperado (`ref`) e traz todos os textos esperados (`contem`), e
- nenhum traz texto proibido (`nao_contem`, ex.: Orlando) nem vem de fonte proibida (`proibido_ref`: outra empresa).
Nota = perguntas certas / perguntas válidas. Pergunta cujo documento sumiu da base não conta: vira "gabarito
desatualizado" (o Lodge mudou ou saiu do site; gere o gabarito de novo).

Roda no retreino da rede neural do Cérebro (consolidação semanal e "Treinar agora"): prova antes, treina, prova
depois. Se a nota com a rede nova cair em relação à versão em uso, o retreino é descartado (a rede anterior volta) e
fica um aviso no painel da Diretoria. Custo zero: só busca local (embedding no Ollama), nada de Max nem gratuitos.
"""

import json
import logging
import unicodedata
from datetime import datetime, timedelta, timezone

import cerebro_base as base
import config
import tarefas

log = logging.getLogger(__name__)

ARQUIVO = config.DADOS_DIR / "cerebro_prova.json"
K = 5  # o trecho certo precisa vir entre os 5 primeiros (o que o agente recebe)
EMPRESAS = {"casa_veraneio": "Casa Veraneio", "cv_corporativo": "Corporativo", "casa_vero": "Casa Vero"}
DIAS_AVISO = 8  # descarte ou queda fica no painel até a prova da semana seguinte

_ESQUEMA = """CREATE TABLE IF NOT EXISTS provas_cerebro (
    id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, origem TEXT NOT NULL, acertos INTEGER NOT NULL,
    total INTEGER NOT NULL, detalhes TEXT NOT NULL, aprovada INTEGER NOT NULL, descartado INTEGER NOT NULL DEFAULT 0,
    referencia INTEGER)"""


def _db():
    db = tarefas._db()
    db.execute(_ESQUEMA)
    return db


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def carregar_gabarito(caminho=None) -> dict | None:
    try:
        dados = json.loads((caminho or ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados.get("empresas"), dict) else None


def _refs_ativas(refs: set[str]) -> set[str]:
    if not refs:
        return set()
    marcadores = ",".join("?" * len(refs))
    with base._trava:
        return {l[0] for l in base.db().execute(f"SELECT DISTINCT fonte_ref FROM conhecimento WHERE ativo = 1 AND "
                                                f"fonte_ref IN ({marcadores})", list(refs))}


def conferir(item: dict, trechos: list[dict]) -> str | None:
    """None se a busca acertou; senão, o motivo em poucas palavras."""
    for t in trechos:
        if any((t.get("fonte_ref") or "").startswith(p) for p in item.get("proibido_ref") or []):
            return f"trouxe trecho de fonte proibida ({t.get('fonte_ref')})"
        texto = _normal(f"{t.get('titulo', '')} {t.get('conteudo', '')}")
        if (ruim := next((p for p in item.get("nao_contem") or [] if _normal(p) in texto), None)):
            return f"trouxe \"{ruim}\" ({t.get('fonte_ref')})"
    ref, contem = item.get("ref"), [_normal(c) for c in item.get("contem") or []]
    if not ref and not contem:
        return None
    candidatos = [t for t in trechos if not ref or t.get("fonte_ref") == ref]
    if not candidatos:
        return f"a ficha {ref} não veio entre os {K} primeiros"
    if not any(all(c in _normal(f"{t.get('titulo', '')} {t.get('conteudo', '')}") for c in contem)
               for t in candidatos):
        return f"veio a ficha, mas sem \"{', '.join(item.get('contem') or [])}\""
    return None


def rodar(gabarito: dict | None = None, k: int = K) -> dict | None:
    """Roda todas as perguntas na busca atual. None se não há gabarito."""
    gabarito = gabarito or carregar_gabarito()
    if not gabarito:
        return None
    blocos = {e: [i for i in itens if isinstance(i, dict) and i.get("pergunta")]
              for e, itens in gabarito["empresas"].items() if e in EMPRESAS}
    ativas = _refs_ativas({i["ref"] for itens in blocos.values() for i in itens if i.get("ref")})
    base.indice_atual(fresco=True)  # a prova vê a base de agora (a busca dos agentes aceita índice de até 15 s)
    por_empresa, falhas, desatualizadas = {}, [], []
    for empresa, itens in blocos.items():
        acertos = total = 0
        for item in itens:
            if item.get("ref") and item["ref"] not in ativas:
                desatualizadas.append(item.get("id") or item["pergunta"])
                continue
            total += 1
            try:
                motivo = conferir(item, base.buscar(item["pergunta"], k=k, empresa=empresa, financeiro=False))
            except Exception as erro:  # uma pergunta com problema não derruba a prova
                motivo = f"a busca falhou: {erro}"
            if motivo:
                falhas.append({"empresa": empresa, "id": item.get("id"), "pergunta": item["pergunta"],
                               "motivo": motivo})
            else:
                acertos += 1
        por_empresa[empresa] = {"acertos": acertos, "total": total}
    return {"em": base.agora(), "acertos": sum(p["acertos"] for p in por_empresa.values()),
            "total": sum(p["total"] for p in por_empresa.values()), "por_empresa": por_empresa, "falhas": falhas,
            "desatualizadas": desatualizadas}


def _registrar(prova: dict, origem: str, aprovada: bool, descartado: bool = False,
               referencia: int | None = None) -> None:
    detalhes = {k: prova[k] for k in ("por_empresa", "falhas", "desatualizadas")}
    with _db() as db:
        db.execute("INSERT INTO provas_cerebro (em, origem, acertos, total, detalhes, aprovada, descartado, referencia) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (prova["em"], origem, prova["acertos"], prova["total"],
                                                        json.dumps(detalhes, ensure_ascii=False), int(aprovada),
                                                        int(descartado), referencia))


def _linha(l) -> dict:
    return {"em": l["em"], "origem": l["origem"], "acertos": l["acertos"], "total": l["total"],
            "aprovada": bool(l["aprovada"]), "descartado": bool(l["descartado"]), "referencia": l["referencia"],
            **json.loads(l["detalhes"])}


def ultimas(n: int = 2, aprovadas: bool = True) -> list[dict]:
    filtro = "WHERE aprovada = 1" if aprovadas else ""
    return [_linha(l) for l in _db().execute(f"SELECT * FROM provas_cerebro {filtro} ORDER BY id DESC LIMIT ?", (n,))]


# --- Retreino com prova -----------------------------------------------------------------------------------------

def _guardar_rede() -> dict:
    import reranker

    def ler(caminho):
        return caminho.read_bytes() if caminho.exists() else None

    return {"modelo": ler(reranker.ARQUIVO_MODELO), "meta": ler(reranker.ARQUIVO_META),
            "_modelo": reranker._modelo, "_meta": reranker._meta}


def _restaurar_rede(copia: dict) -> None:
    import reranker

    for caminho, conteudo in ((reranker.ARQUIVO_MODELO, copia["modelo"]), (reranker.ARQUIVO_META, copia["meta"])):
        if conteudo is None:
            caminho.unlink(missing_ok=True)
        else:
            caminho.write_bytes(conteudo)
    reranker._modelo, reranker._meta = copia["_modelo"], copia["_meta"]


def _nota(prova: dict) -> str:
    return f"{prova['acertos']}/{prova['total']}"


def treinar_com_prova(origem: str) -> dict:
    """reranker.treinar com a prova antes e depois. Devolve o status do treino com a chave "prova"."""
    import reranker

    gabarito = carregar_gabarito()
    if not gabarito:
        return {**reranker.treinar(), "prova": {"observacao": "Prova do Cérebro sem gabarito (gere com "
                                                              "cerebro_prova_gabarito.py)."}}
    antes = rodar(gabarito)
    copia = _guardar_rede()
    status = reranker.treinar()
    novo = (reranker._meta or {}).get("treinado_em") != (copia["_meta"] or {}).get("treinado_em")
    # A rede só mexe na busca se estiver ativa: treino que não ativou nem desativou nada não muda a nota.
    mexeu = novo and (reranker._modelo is not None or copia["_modelo"] is not None)
    if not mexeu:
        _registrar(antes, origem, aprovada=True)
        return {**status, "prova": {**_resumo(antes), "observacao": f"Prova do Cérebro: {_nota(antes)}."}}
    depois = rodar(gabarito)
    if depois["acertos"] < antes["acertos"]:
        _restaurar_rede(copia)
        _registrar(depois, origem, aprovada=False, descartado=True, referencia=antes["acertos"])
        _registrar(antes, origem, aprovada=True)
        log.warning("Prova do Cérebro: rede nova tirou %s contra %s; retreino descartado.", _nota(depois), _nota(antes))
        return {**reranker.status(), "prova": {**_resumo(depois), "descartado": True, "observacao": (
            f"Prova do Cérebro: a rede nova tirou {_nota(depois)}, contra {_nota(antes)} da versão em uso. O retreino "
            "foi descartado e a rede anterior voltou.")}}
    _registrar(depois, origem, aprovada=True, referencia=antes["acertos"])
    return {**status, "prova": {**_resumo(depois), "observacao": (
        f"Prova do Cérebro: {_nota(depois)} com a rede nova ({_nota(antes)} antes do retreino).")}}


# --- Painel -----------------------------------------------------------------------------------------------------

def _resumo(prova: dict) -> dict:
    return {"em": prova["em"], "acertos": prova["acertos"], "total": prova["total"],
            "por_empresa": {EMPRESAS.get(e, e): p for e, p in prova["por_empresa"].items()},
            "falhas": prova["falhas"][:8], "desatualizadas": len(prova.get("desatualizadas") or [])}


def resumo() -> dict | None:
    """Última prova aprovada (a nota em uso), para o painel da Diretoria."""
    try:
        ultima = ultimas(1)
    except Exception:
        log.exception("Não foi possível ler a prova do Cérebro.")
        return None
    return _resumo(ultima[0]) if ultima else None


def _recente(em: str) -> bool:
    try:
        quando = datetime.strptime(em, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - quando < timedelta(days=DIAS_AVISO)


def _pct(prova: dict) -> float:
    return prova["acertos"] / prova["total"] if prova["total"] else 1.0


def _data(em: str) -> str:
    return f"{em[8:10]}/{em[5:7]}"


def avisos() -> list[str]:
    """Descarte de retreino, queda da nota e gabarito desatualizado (para saude.avisos_da_operacao)."""
    try:
        recentes, aprovadas = ultimas(2, aprovadas=False), ultimas(2)
    except Exception:
        log.exception("Não foi possível ler a prova do Cérebro.")
        return []
    saida = []
    descarte = next((p for p in recentes if p["descartado"] and _recente(p["em"])), None)
    if descarte:
        saida.append(f"Prova do Cérebro ({_data(descarte['em'])}): o retreino da rede neural tirou {_nota(descarte)}, "
                     f"contra {descarte['referencia']}/{descarte['total']} da versão em uso. O retreino foi descartado "
                     "e a rede anterior voltou.")
    if len(aprovadas) == 2 and _recente(aprovadas[0]["em"]) and _pct(aprovadas[0]) < _pct(aprovadas[1]):
        atual, anterior = aprovadas
        falhou = "; ".join(f"{EMPRESAS.get(f['empresa'], f['empresa'])}: {f['pergunta']} ({f['motivo']})"
                           for f in atual["falhas"][:3])
        saida.append(f"Prova do Cérebro caiu de {_nota(anterior)} ({_data(anterior['em'])}) para {_nota(atual)} "
                     f"({_data(atual['em'])}). A queda não veio da rede neural (essa é conferida no retreino): confira "
                     f"as fontes que mudaram. Ex.: {falhou}")
    if aprovadas and (n := len(aprovadas[0].get("desatualizadas") or [])):
        saida.append(f"Prova do Cérebro: {n} pergunta(s) do gabarito apontam para fichas que saíram da base. Gere o "
                     "gabarito de novo (cerebro_prova_gabarito.py).")
    return saida
