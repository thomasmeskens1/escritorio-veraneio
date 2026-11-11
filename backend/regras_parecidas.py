"""Regra parecida (Onda 2, N2-cerebro-21): ao aprovar uma regra nova, o sistema avisa "parecida com a regra #N" para a
Diretoria escolher entre substituir, unir (editar o texto e substituir) ou manter as duas.

Caso que motivou: o Copywriter tinha três regras quase iguais ocupando 3 das 15 vagas do contexto. A comparação é por
embedding (Ollama local, custo zero) quando ele responde, senão por texto (palavras em comum e sequência). Também mostra
as propostas parecidas descartadas nos últimos 60 dias, para o que foi recusado não voltar sem ninguém notar.
Só avisa: nada é desativado sem a escolha de quem aprova, e a regra substituída continua guardada (ativa = 0).
"""

import logging
import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher

import tarefas

log = logging.getLogger(__name__)

LIMIAR_EMBEDDING = 0.85   # cosseno entre os vetores do Ollama
LIMIAR_TEXTO = 0.55       # maior entre palavras em comum (Jaccard) e sequência (difflib)
MAX_AVISOS = 3
DIAS_DESCARTADAS = 60
MIN_PALAVRA = 3
VAZIAS = {"para", "com", "sem", "que", "nao", "uma", "um", "dos", "das", "nos", "nas", "por", "pelo", "pela", "sempre",
          "nunca", "deve", "ser", "mais", "menos", "como", "quando", "isso", "esse", "essa", "este", "esta", "the"}


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    # "[Casa Vero] ..." da consolidação e "Seguir este padrão aprovado por ...:" do elogio não contam na comparação
    sem_acento = re.sub(r"^\s*\[[^\]]{1,40}\]\s*", "", sem_acento)
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def _palavras(texto: str) -> set[str]:
    return {p for p in _normal(texto).split() if len(p) >= MIN_PALAVRA and p not in VAZIAS}


def semelhanca_texto(a: str, b: str) -> float:
    pa, pb = _palavras(a), _palavras(b)
    jaccard = len(pa & pb) / len(pa | pb) if pa and pb else 0.0
    sequencia = SequenceMatcher(None, _normal(a), _normal(b)).ratio()
    return round(max(jaccard, sequencia), 3)


def _semelhancas_embedding(nova: str, textos: list[str]) -> list[float] | None:
    """Cosseno da regra nova com cada texto, ou None se o Ollama não respondeu (a comparação fica por texto)."""
    if not textos:
        return []
    try:
        import cerebro_embed

        matriz = cerebro_embed.gerar([nova, *textos])
    except Exception as erro:  # o aviso nunca atrapalha a aprovação
        log.info("Regra parecida: embedding indisponível (%s).", str(erro)[:120])
        return None
    if matriz is None or len(matriz) != len(textos) + 1:
        return None
    return [round(float(v), 3) for v in matriz[1:] @ matriz[0]]


def _candidatas(agente: str, empresa: str) -> list[dict]:
    """Regras ativas do mesmo agente (ou de todos) e propostas descartadas há até DIAS_DESCARTADAS dias."""
    import correcoes

    db = correcoes._db()
    filtro_agente = "" if agente == "*" else "AND agente IN (?, '*') "
    params = () if agente == "*" else (agente,)
    filtro_empresa = "" if empresa == "*" else "AND empresa IN (?, '*') "
    params_empresa = () if empresa == "*" else (empresa,)
    regras = [{"tipo": "regra", "id": r["id"], "agente": r["agente"], "empresa": r["empresa"], "texto": r["regra"],
               "em": r["criada_em"]} for r in db.execute(
        f"SELECT id, agente, empresa, regra, criada_em FROM regras_aprendidas WHERE ativa = 1 {filtro_agente}"
        f"{filtro_empresa}ORDER BY id DESC", (*params, *params_empresa))]
    desde = tarefas._agora(-timedelta(days=DIAS_DESCARTADAS))
    descartadas = [{"tipo": "descartada", "id": o["id"], "agente": o["agente"], "empresa": "*",
                    "texto": o["regra"] or o["correcao"], "em": o["decidido_em"]} for o in db.execute(
        f"SELECT id, agente, regra, correcao, decidido_em FROM observacoes WHERE status = 'descartada' "
        f"AND decidido_em >= ? {filtro_agente}ORDER BY id DESC LIMIT 200", (desde, *params))]
    return regras + descartadas


def parecidas(regra: str, agente: str, empresa: str = "*", ignorar_observacao: int | None = None) -> list[dict]:
    """Até MAX_AVISOS regras ativas (ou propostas descartadas) parecidas com `regra`, da mais parecida para a menos.
    Cada item: tipo ('regra' | 'descartada'), id, texto, semelhanca, metodo ('embedding' | 'texto')."""
    regra = (regra or "").strip()
    if len(regra) < 5:
        return []
    candidatas = [c for c in _candidatas(agente, empresa)
                  if c["texto"] and not (c["tipo"] == "descartada" and c["id"] == ignorar_observacao)]
    if not candidatas:
        return []
    vetores = _semelhancas_embedding(regra, [c["texto"] for c in candidatas])
    achadas = []
    for n, c in enumerate(candidatas):
        texto = semelhanca_texto(regra, c["texto"])
        if vetores is not None and vetores[n] >= LIMIAR_EMBEDDING:
            achadas.append({**c, "semelhanca": vetores[n], "metodo": "embedding"})
        elif texto >= LIMIAR_TEXTO:
            achadas.append({**c, "semelhanca": texto, "metodo": "texto"})
    achadas.sort(key=lambda c: (c["tipo"] != "regra", -c["semelhanca"]))
    return achadas[:MAX_AVISOS]


def aviso(achadas: list[dict]) -> str:
    """Frase curta para a tela ("" se não há nada parecido)."""
    if not achadas:
        return ""
    partes = [f"parecida com a regra #{c['id']}" if c["tipo"] == "regra" else
              f"parecida com uma proposta descartada em {str(c['em'] or '')[:10]}" for c in achadas]
    return ("Esta regra está " + "; ".join(partes) +
            ". Escolha: substituir a antiga, unir as duas (edite o texto e substitua) ou manter as duas.")
