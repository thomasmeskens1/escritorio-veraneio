"""O Gestor é o "cérebro" do andar de Marketing: pedido de peça completa feito a um especialista vai para ele.

"Faça um post sobre o Lodge 1" pedido ao Copywriter precisa de texto, arte e imagem: o Gestor monta o plano e
aciona Copywriter, Designer e Criador de Imagens. Pedido do escopo do especialista ("escreva a legenda do
post") continua com ele. Regras determinísticas, sem gastar modelo.
"""

import re

from estado import buscar_agente

ANDAR = "marketing"
GESTOR = "gestor"
PECAS = re.compile(r"\b(posts?|carross[eé]is|carrossel|reels?|stories|story|campanhas?|an[uú]ncios?|"
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


def para_o_gestor(andar: str, agente_id: str, texto: str) -> bool:
    if andar != ANDAR or agente_id == GESTOR or not buscar_agente(ANDAR, GESTOR):
        return False
    if not PECAS.search(texto):
        return False
    escopo = ESCOPO.get(agente_id)  # agentes criados pelo Construtor: toda peça vai ao Gestor
    return not (escopo and re.search(rf"\b({escopo})\b", texto, re.IGNORECASE))
