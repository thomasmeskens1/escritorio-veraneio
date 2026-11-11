"""Pedido de vídeo que contraria o manual vira pergunta de um clique (moviemaker-02, Onda 1 de novembro).

Caso real (Lodge 32, tarefas 246, 247 e 257): o pedido trazia "2 takes de 2 s" por espaço, contra o mínimo de 3,5 s
por take do manual 05 §5, e o plano repetiu o pedido em silêncio (10 cenas em 1x). Aqui, conta em código, sem IA: os
números do pedido (segundos por take, número de takes, velocidade) contra as regras numéricas do manual 05 §5. Com
conflito, sai o formulário que já existe (<<FORMULARIO>>) com duas opções, e a escolha volta no chat como resposta.
Só a Casa Veraneio: o manual 05 é dela, e o 0,75x no Corporativo e na Casa Vero depende da decisão 1 (em aberto).
"""

import json
import re

EMPRESAS = {"casa_veraneio"}
AGENTES = {"moviemaker", "editor_video", "gestor"}
MINIMO_TAKE_S, MAXIMO_TAKES = 3.5, 7
TITULO = "Pedido fora do padrão de vídeo"
SEGUIR_PEDIDO = "Seguir meu pedido só nesta peça"
SEGUIR_PADRAO = "Seguir o padrão (5 a 7 takes de 3,5 a 6 s, em 0,75x)"

VIDEO = re.compile(r"\b(reels?|v[ií]deos?|takes?|cenas?|shorts?|tiktok|stories)\b", re.I)
_NUM = r"(\d{1,2}(?:[.,]\d)?)"
SEGUNDOS = [  # "2 takes de 2 s", "cenas de 1,5 segundo", "2 s cada take", "cortes de 2s"
    re.compile(rf"\b(?:takes?|cenas?|cortes?|planos?|frames?)\s+(?:curt[oa]s\s+)?de\s+{_NUM}\s*(?:s|seg|segundos?)\b",
               re.I),
    re.compile(rf"\b{_NUM}\s*(?:s|seg|segundos?)\s+(?:cada|por|em\s+cada)\s+(?:take|cena|corte|plano|frame)\b", re.I),
]
QUANTIDADE = re.compile(r"\b(\d{1,2})\s+(?:takes|cenas|cortes|planos)\b", re.I)
# "em 1x" / "velocidade 1x" (e não "1x por semana"), velocidade normal, sem câmera lenta, acelerado.
VELOCIDADE = re.compile(r"\b(?:em|na|velocidade(?:\s+de)?|reprodu[cç][aã]o(?:\s+em)?)\s+(?:1|1[.,]5|2)\s?x\b|"
                        r"velocidade\s+normal|sem\s+c[aâ]mera\s+lenta|\bacelerad[oa]s?\b|\bacelerar\b", re.I)
RESPOSTA = re.compile(rf"{re.escape(TITULO)}|seguir\s+(?:meu\s+pedido|o\s+padr[aã]o)", re.I)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def conflitos(pedido: str, empresa: str | None) -> list[str]:
    """O que o pedido pede contra o manual 05 §5 (lista vazia se nada, se não é vídeo ou se já é a resposta)."""
    texto = pedido or ""
    if empresa not in EMPRESAS or not VIDEO.search(texto) or RESPOSTA.search(texto):
        return []
    achados = []
    curtos = sorted({_numero(m.group(1)) for p in SEGUNDOS for m in p.finditer(texto)
                     if _numero(m.group(1)) < MINIMO_TAKE_S})
    if curtos:
        achados.append(f"take de {', '.join(f'{s:g}'.replace('.', ',') for s in curtos)} s "
                       "(o manual pede no mínimo 3,5 s por take)")
    if (muitos := [int(m.group(1)) for m in QUANTIDADE.finditer(texto) if int(m.group(1)) > MAXIMO_TAKES]):
        achados.append(f"{max(muitos)} takes (o manual pede de 5 a {MAXIMO_TAKES} num reels)")
    if (velocidade := VELOCIDADE.search(texto)):
        achados.append(f"\"{velocidade.group(0)}\" (o padrão é 0,75x em todos os takes e nunca acelerar)")
    return achados


def formulario(achados: list[str]) -> str:
    """Bloco <<FORMULARIO>> de uma pergunta, no formato que o chat já transforma em pop-up."""
    dados = {"titulo": TITULO, "botao": "Enviar escolha", "campos": [{
        "nome": "escolha_video", "rotulo": "O pedido contraria o manual de vídeo: " + "; ".join(achados)
        + ". Como seguimos nesta peça?", "tipo": "opcoes", "opcoes": [SEGUIR_PEDIDO, SEGUIR_PADRAO],
        "obrigatorio": True}]}
    return f"<<FORMULARIO>>{json.dumps(dados, ensure_ascii=False)}<<FIM DO FORMULARIO>>"


def pergunta(achados: list[str]) -> str:
    """Texto curto + formulário, para o chat (sem escolher sozinho qual regra vale)."""
    return ("Antes de roteirizar: o pedido pede " + "; ".join(achados) + ". Não escolho sozinho qual regra vale. "
            "Você quer seguir o seu pedido só nesta peça ou o padrão do manual?\n\n" + formulario(achados))


def escolha(texto: str) -> str:
    """"pedido", "padrao" ou "" na resposta ao formulário."""
    if SEGUIR_PEDIDO.lower() in (texto or "").lower():
        return "pedido"
    return "padrao" if re.search(r"seguir\s+o\s+padr[aã]o", texto or "", re.I) else ""


def bloco(agente_id: str, empresa: str | None, pedido: str) -> str:
    """Instrução para o contexto do agente: perguntar (conflito novo) ou registrar a escolha (resposta)."""
    if agente_id not in AGENTES:
        return ""
    if (decidido := escolha(pedido)):
        exc = ("seguir o PEDIDO do usuário só nesta peça (exceção ao manual 05 §5 aprovada por ele)"
               if decidido == "pedido" else "seguir o PADRÃO do manual 05 §5 (5 a 7 takes de 3,5 a 6 s, em 0,75x), "
               "no lugar dos números do pedido que o contrariavam")
        return (f"DECISÃO DO USUÁRIO SOBRE O PADRÃO DE VÍDEO: {exc}. Escreva essa decisão numa linha do roteiro "
                "(\"Ritmo: ...\") e no manifest, para o Editor e o Max não decidirem sozinhos. Não pergunte de novo.")
    if agente_id == "gestor" or not (achados := conflitos(pedido, empresa)):
        return ""  # o Gestor pergunta antes do plano, em código (agents/projeto_regras.py)
    return ("PEDIDO FORA DO PADRÃO DE VÍDEO: o pedido pede " + "; ".join(achados) + ". NÃO escreva o roteiro ainda "
            "nem escolha a regra: explique o conflito em 1 ou 2 frases e termine a resposta exatamente com este "
            f"formulário:\n{formulario(achados)}")
