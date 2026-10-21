"""O Gestor é o "cérebro" do andar de Marketing: pedido de peça completa feito a um especialista vai para ele.

"Faça um post sobre o Lodge 1" pedido ao Copywriter precisa de texto, arte e imagem: o Gestor monta o plano e
aciona Copywriter, Designer e Criador de Imagens. Pedido do escopo do especialista ("escreva a legenda do
post") continua com ele. Regras determinísticas, sem gastar modelo.
"""

import re

from estado import buscar_agente

ANDAR = "marketing"
GESTOR = "gestor"
PECAS = re.compile(r"\b(posts?|carross[eé]is|carrossel|reels?|shorts|stories|story|campanhas?|an[uú]ncios?|"
                   r"calend[aá]rio|pe[cç]as?|publica[cç][aã]o|publica[cç][oõ]es)\b", re.IGNORECASE)
# Palavras que mostram que o pedido é do escopo do próprio especialista.
ESCOPO = {
    "copywriter": r"legendas?|textos?|copy|t[ií]tulos?|ganchos?|hashtags?|chamadas?|cta",
    "designer": r"artes?|layouts?|design|capas?|templates?|selos?",
    "criador_imagens": r"imagens?|fotos?|artes?|png",
    "moviemaker": r"roteiros?|storyboard|ritmo|cenas?",
    "editor_video": r"edi[cç][aã]o|editar|mp4|render|cortes?",
    "social_media": r"calend[aá]rio|planejamento|pautas?|cronograma|hashtags?",
    "gestor_trafego": r"campanhas?|an[uú]ncios?|tr[aá]fego|segmenta[cç][aã]o|p[uú]blicos?",
    "analista_metricas": r"m[eé]tricas?|relat[oó]rios?|indicadores?|kpis?|resultados?",
}


PERGUNTA = re.compile(r"^\s*(qual|quais|como|quando|onde|por ?que|o que|quanto|quantos|quantas|existe|explique|"
                      r"me explique|me diga|pode me dizer|voc[eê] sabe|[eé] poss[ií]vel)\b", re.IGNORECASE)


def e_pergunta(texto: str) -> bool:
    """Dúvida para o especialista responder (não é pedido de produção)."""
    return texto.strip().endswith("?") or bool(PERGUNTA.search(texto))


def para_o_gestor(andar: str, agente_id: str, texto: str) -> bool:
    if andar != ANDAR or agente_id == GESTOR or not buscar_agente(ANDAR, GESTOR):
        return False
    if not PECAS.search(texto) or e_pergunta(texto):
        return False
    escopo = ESCOPO.get(agente_id)  # agentes criados pelo Construtor: toda peça vai ao Gestor
    return not (escopo and re.search(rf"\b({escopo})\b", texto, re.IGNORECASE))


# --- Resposta de volta a quem recebeu o pedido ------------------------------------------------

_ESQUEMA = "CREATE TABLE IF NOT EXISTS encaminhamentos (tarefa_id INTEGER PRIMARY KEY, andar TEXT, agente TEXT)"


def _db():
    import tarefas
    db = tarefas._db()
    db.execute(_ESQUEMA)
    return db


def registrar(tarefa_id: int, andar: str, agente_origem: str) -> None:
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO encaminhamentos VALUES (?, ?, ?)", (tarefa_id, andar, agente_origem))


def origem(tarefa_id: int) -> tuple[str, str] | None:
    linha = _db().execute("SELECT andar, agente FROM encaminhamentos WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return (linha["andar"], linha["agente"]) if linha else None
