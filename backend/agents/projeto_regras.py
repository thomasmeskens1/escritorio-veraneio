"""Regras em código sobre o plano do Gestor (Onda 1 de novembro). Ficam fora de projeto.py para ele não passar de
500 linhas.

- Analista de Tendências ANTES de quem escreve (analista_tendencias-30): no projeto 237 o Analista e o Copywriter
  caíram na mesma fase, o texto saiu sem os ângulos e o trabalho do Analista se perdeu.
- Pedido de vídeo fora do manual vira pergunta antes do plano (moviemaker-02, pedido_video.py).
- Plano com o Gestor de Tráfego fecha com o checklist da Meta (gestor_trafego-03).
"""

import pedido_video
from conferente_regras import CHECKLIST_META, CHECKLIST_META_TITULO

ANALISTA = "analista_tendencias"
ESCREVEM = {"copywriter", "social_media", "moviemaker", "email_marketing"}


def analista_antes(plano: list[dict]) -> tuple[list[dict], str]:
    """(plano, nota). Se o Analista está na mesma fase de quem escreve, ou depois, ele vai para a fase antes da
    primeira escrita, e quem vinha dali em diante desce uma fase (a ordem entre os demais não muda)."""
    escritas = [p["fase"] for p in plano if p["agente"] in ESCREVEM]
    analistas = [p for p in plano if p["agente"] == ANALISTA]
    if not escritas or not analistas or max(p["fase"] for p in analistas) < min(escritas):
        return plano, ""
    primeira = min(escritas)
    novo = []
    for passo in plano:
        if passo["agente"] == ANALISTA:
            novo.append({**passo, "fase": primeira})
        else:
            novo.append({**passo, "fase": passo["fase"] + 1 if passo["fase"] >= primeira else passo["fase"]})
    return novo, (f"Regra do sistema: o Analista de Tendências foi para a fase {primeira}, antes de quem escreve, para "
                  "os ângulos dele chegarem ao texto.")


def lembrete_angulos(plano: list[dict], numero: int, passo: dict) -> str:
    """Linha extra na etapa de quem escreve, quando o Analista roda numa fase anterior."""
    if passo["agente"] not in ESCREVEM:
        return ""
    anteriores = [n for n, p in enumerate(plano, 1) if p["agente"] == ANALISTA and p["fase"] < passo["fase"]]
    if not anteriores:
        return ""
    return (f"\n\nUse os ângulos do Analista de Tendências (etapa {anteriores[0]}, acima): o gancho e o dado real que "
            "ele trouxe entram no seu texto; não invente outro ângulo sem dizer por quê.")


def pergunta_de_video(pedido: str, empresa: str | None) -> str:
    """Texto com o formulário de um clique, se o pedido de vídeo contraria o manual 05 §5; "" se não."""
    achados = pedido_video.conflitos(pedido, empresa)
    return pedido_video.pergunta(achados) if achados else ""


def com_checklist_meta(texto: str, plano: list[dict]) -> str:
    """Entrega final do projeto com o Gestor de Tráfego: o checklist fixo da Meta no fim (uma vez)."""
    if not any(p["agente"] == "gestor_trafego" for p in plano) or CHECKLIST_META_TITULO in texto:
        return texto
    return f"{texto.rstrip()}\n\n{CHECKLIST_META}"
