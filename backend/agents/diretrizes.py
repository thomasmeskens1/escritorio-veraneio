"""Diretrizes da Casa Veraneio para os agentes (backend/dados/conhecimento, fora do git), por FUNÇÃO.

Cada agente recebe só as seções dos manuais que usa no trabalho (mapa SECOES): as regras de ouro e as regras
gerais sempre, inteiras; identidade visual para quem cria arte e vídeo, tom de voz para quem escreve, playbook de
mídia paga para o Tráfego e o Analista, e assim por diante. O catálogo de Lodges fica de fora (a ficha oficial do
Lodge citado entra direto no contexto, fichas.py). Antes, cada agente levava os manuais inteiros (~9 mil tokens),
o que estourava o limite gratuito do Groq; com o mapa, ~3 a 5 mil tokens sem perder regra da função.
Versão essencial (Groq gratuito e modelo local): regras de ouro, 10 regras, histórico de erros, regras de dados,
tabela de formatos e o documento da função.
"""

import re
from functools import lru_cache
from pathlib import Path

import config

TODOS = "*"
MARKETING = ("gestor", "designer", "criador_imagens", "copywriter", "social_media", "moviemaker", "editor_video",
             "gestor_trafego", "analista_metricas")
VISUAL = ("gestor", "designer", "criador_imagens", "moviemaker", "editor_video")
TEXTO = ("gestor", "copywriter", "social_media", "moviemaker", "gestor_trafego")
PRODUZEM = ("gestor", "designer", "criador_imagens", "copywriter", "moviemaker", "editor_video")
ESTRATEGIA = ("gestor", "social_media", "gestor_trafego", "analista_metricas")

# Manual -> {número da seção (ou "ouro") -> quem recebe}. Seção fora do mapa não vai para ninguém;
# manual com TODOS no lugar do dicionário vai inteiro para quem está em DA_FUNCAO.
SECOES = {
    "00": {"ouro": TODOS, "2": TODOS, "3": ("gestor",), "4": ("gestor", "social_media"),
           "5": ("gestor", "designer", "criador_imagens", "editor_video"), "6": PRODUZEM,
           "7": ("gestor", "designer", "copywriter", "editor_video"), "8": TODOS},
    "01": {"1": TODOS, "2": TODOS, "3": VISUAL, "4": TEXTO, "5": TODOS, "7": TODOS, "8": ESTRATEGIA,
           "9": ("gestor", "designer", "criador_imagens", "copywriter", "social_media", "moviemaker")},
    "02": {"1": ESTRATEGIA, "2": ("gestor", "social_media"), "3": ("gestor", "social_media"),
           "4": ("gestor", "social_media"), "5": ("social_media",), "6": ("gestor_trafego", "analista_metricas"),
           "7": ("social_media", "designer"), "8": ("social_media",), "9": ESTRATEGIA},
    "05": {"1": ("moviemaker",), "2": ("moviemaker", "editor_video"), "3": ("moviemaker",),
           "4": ("moviemaker", "editor_video"), "5": ("moviemaker", "editor_video"), "6": ("moviemaker",),
           "7": ("moviemaker", "editor_video"), "8": ("moviemaker", "editor_video")},
    "08": {"1": TODOS, "2": TODOS, "3": TODOS, "4": ("designer", "social_media")},
    "09": {"1": TODOS, "2": ("gestor", "social_media"), "3": ("gestor", "social_media"),
           "4": ("gestor", "social_media")},
    "10": {"1": TODOS, "2": TODOS, "3": TODOS, "4": ("gestor", "social_media")},
}
ORDEM = ("00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10")
# Agente -> documentos da função, que vão inteiros (exceto o 05, recortado pelo mapa para o Editor).
DA_FUNCAO = {
    "social_media": ("02",), "gestor_trafego": ("02",), "analista_metricas": ("02",), "gestor": ("02",),
    "designer": ("03",), "criador_imagens": ("04",), "moviemaker": ("05",), "editor_video": ("06", "05"),
    "copywriter": ("07",),
}
# Versão essencial (Groq gratuito e modelo local, contexto curto): estas seções + o documento da função.
ESSENCIAL = {"00": ("ouro", "2", "8"), "01": ("5",), "08": ("2",)}
CABECALHO = ("DIRETRIZES DA CASA VERANEIO (siga à risca). Dados de Lodges (local, capacidade, preços, estadia "
             "mínima, atributos): use a ficha oficial do Lodge citado e o Cérebro; o que não estiver lá é PENDENTE.\n"
             "Ajustes deste sistema (valem sobre os manuais): as entregas ficam na pasta do Escritório Veraneio no "
             "Drive, não em \"MARKETING > THOMAS\"; a legenda vai em .docx no lugar do Google Doc; Higgsfield não "
             "é usado; os arquivos (PNG, MP4, PPTX editável) são produzidos pelo Criador de Imagens e pelo Editor "
             "de Vídeo no Claude Code, a partir do plano do Gestor.")
# O que precisa estar no prompt de TODO agente do Marketing (conferido por verificar()).
OBRIGATORIOS = ("REGRAS DE OURO", "WhatsApp", "1080")


def _arquivo(prefixo: str) -> Path | None:
    achados = sorted(config.PASTA_CONHECIMENTO.glob(f"{prefixo}_*.md"))
    return achados[0] if achados else None


def _secoes(texto: str) -> list[str]:
    return re.split(r"\n(?=## )", texto)


def _chave(secao: str) -> str | None:
    """"## 3. Identidade visual" -> "3"; "## REGRAS DE OURO..." -> "ouro"; cabeçalho do arquivo -> None."""
    if secao.startswith("## REGRAS DE OURO"):
        return "ouro"
    achou = re.match(r"## (\d+)\.", secao)
    return achou.group(1) if achou else None


def _recebe(quem, agente_id: str) -> bool:
    return quem == TODOS or agente_id in quem


@lru_cache(maxsize=128)
def _ler(caminho: Path, _mtime: float, agente_id: str, compacto: bool) -> str:
    secoes = _secoes(caminho.read_text(encoding="utf-8").strip())
    prefixo = caminho.name[:2]
    if compacto and prefixo in ESSENCIAL:
        return "\n".join(s for s in secoes if _chave(s) in ESSENCIAL[prefixo])
    mapa = SECOES.get(prefixo)
    if mapa is None:  # documento da função (03, 04, 06, 07): inteiro
        return "\n".join(secoes)
    return "\n".join(s for s in secoes if (c := _chave(s)) and c in mapa and _recebe(mapa[c], agente_id))


def para(agente_id: str, compacto: bool = False) -> str:
    """Texto das diretrizes do agente ("" se ele não tem documentos ou a pasta não existe)."""
    funcao = DA_FUNCAO.get(agente_id)
    if not funcao:
        return ""
    prefixos = tuple(p for p in ORDEM if p in funcao or p in (ESSENCIAL if compacto else SECOES))
    partes = []
    for prefixo in prefixos:
        caminho = _arquivo(prefixo)
        if caminho and (texto := _ler(caminho, caminho.stat().st_mtime, agente_id, compacto)):
            partes.append(texto)
    return f"{CABECALHO}\n\n" + "\n\n".join(partes) if partes else ""


def verificar() -> dict[str, dict]:
    """Por agente: tamanho aproximado (tokens) e o que faltou dos OBRIGATORIOS. Usado no teste de prompts."""
    resultado = {}
    for agente in MARKETING:
        texto = para(agente)
        resultado[agente] = {"tokens": len(texto) // 4, "faltando": [o for o in OBRIGATORIOS if o not in texto]}
    return resultado
