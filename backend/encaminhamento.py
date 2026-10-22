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


# Resposta aos botões "Só o planejamento" / "Peça final" (ou digitada assim pelo usuário).
ESCOLHA = re.compile(r"^\s*(planejamento|pe[cç]a\s+final)\s*:\s*", re.IGNORECASE)
# Pedido que já deixa claro que quer o arquivo pronto: não precisa perguntar.
PRODUCAO_EXPLICITA = re.compile(r"\b(produza|produzir|produção|pe[cç]a\s+final|arte\s+final|artes?|png|mp4|"
                                r"criativos?|renderiz\w*|v[ií]deo\s+final|edite|monte\s+o\s+v[ií]deo)\b",
                                re.IGNORECASE)


def escolha(texto: str) -> str | None:
    """"planejamento" | "peca" quando o texto começa com a resposta aos botões; None nos demais."""
    achou = ESCOLHA.match(texto)
    return None if not achou else ("planejamento" if achou.group(1).lower().startswith("plan") else "peca")


def para_o_gestor(andar: str, agente_id: str, texto: str) -> bool:
    if andar != ANDAR or agente_id == GESTOR or not buscar_agente(ANDAR, GESTOR):
        return False
    if (decidido := escolha(texto)):  # o usuário já escolheu: planejamento fica com o especialista
        return decidido == "peca"
    if not PECAS.search(texto) or e_pergunta(texto):
        return False
    escopo = ESCOPO.get(agente_id)  # agentes criados pelo Construtor: toda peça vai ao Gestor
    return not (escopo and re.search(rf"\b({escopo})\b", texto, re.IGNORECASE))


# Verbos de pedido de trabalho: "Pode montar um post do Lodge 1?" é pedido, mesmo terminando em "?".
PEDIDO_TRABALHO = re.compile(r"\b(mont\w*|fa[cç]\w*|faz|cri\w*|produz\w*|prepar\w*|elabor\w*|desenvolv\w*|"
                             r"planej\w*|escrev\w*|ger\w*|organiz\w*|ajust\w*)\b", re.IGNORECASE)


def pergunta_simples(texto: str) -> bool:
    """Dúvida que o Gestor responde direto, sem montar projeto com a equipe (plano + etapas + revisão).
    Stress test: cada pergunta simples virava um projeto de ~3 min e estourava a cota dos modelos gratuitos."""
    return (e_pergunta(texto) and not texto.lstrip().startswith("[") and not escolha(texto)
            and not PEDIDO_TRABALHO.search(texto))


def precisa_escolher(andar: str, agente_id: str, texto: str) -> bool:
    """Peça pedida a um especialista sem dizer se quer o planejamento ou o arquivo pronto ("Monta 4 stories para
    dezembro"): pergunta antes de acionar a produção. Teste real: o pedido virou produção no Max sem consulta."""
    from agents.projeto import e_ideacao  # import tardio: projeto carrega o andar inteiro

    if escolha(texto) or PRODUCAO_EXPLICITA.search(texto) or e_ideacao(texto) or e_pergunta(texto):
        return False
    if andar == ANDAR and agente_id == GESTOR:  # pedido feito direto ao Gestor também pergunta
        return bool(PECAS.search(texto))
    return para_o_gestor(andar, agente_id, texto)


# --- Resposta de volta a quem recebeu o pedido ------------------------------------------------
# A resposta final sempre volta ao chat onde o usuário pediu, mesmo passando pelo Gestor e pela produção.
# `pedido`: 1 = o texto da tarefa é o pedido do usuário (aparece como "Você" no chat de origem);
# 0 = tarefa interna (briefing de produção do Gestor), no chat de origem aparece só o resultado.

_ESQUEMA = "CREATE TABLE IF NOT EXISTS encaminhamentos (tarefa_id INTEGER PRIMARY KEY, andar TEXT, agente TEXT)"


_pronto = False  # tabela e migração verificadas uma vez por processo


def _db():
    global _pronto
    import tarefas
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        colunas = {c["name"] for c in db.execute("PRAGMA table_info(encaminhamentos)")}
        if "pedido" not in colunas:
            db.execute("ALTER TABLE encaminhamentos ADD COLUMN pedido INTEGER DEFAULT 1")
        db.execute("CREATE INDEX IF NOT EXISTS idx_encaminhamentos_chat ON encaminhamentos(andar, agente)")
        _pronto = True
    return db


def registrar(tarefa_id: int, andar: str, agente_origem: str, pedido: bool = True) -> None:
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO encaminhamentos (tarefa_id, andar, agente, pedido) VALUES (?, ?, ?, ?)",
                   (tarefa_id, andar, agente_origem, int(pedido)))


def origem(tarefa_id: int) -> tuple[str, str] | None:
    linha = _db().execute("SELECT andar, agente FROM encaminhamentos WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return (linha["andar"], linha["agente"]) if linha else None


def tarefas_do_chat(andar: str, agente: str) -> dict[int, bool]:
    """Tarefas que nasceram neste chat e rodaram em outro agente -> o texto delas é pedido do usuário?"""
    return {l["tarefa_id"]: bool(l["pedido"]) for l in _db().execute(
        "SELECT tarefa_id, pedido FROM encaminhamentos WHERE andar = ? AND agente = ?", (andar, agente))}


def pedido_original(texto: str) -> str:
    """'[Pedido feito ao Copywriter] Me dá 3 ideias...' -> 'Me dá 3 ideias...'."""
    return re.sub(r"^\[Pedido feito a[o]? [^\]]+\]\s*", "", texto)
