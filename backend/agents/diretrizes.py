"""Diretrizes da Casa Veraneio para os agentes (backend/dados/conhecimento, fora do git).

Cada agente recebe, junto da persona: as regras globais (00), a base de marca e negócio (01, sem o catálogo
de Lodges, que o agente consulta atualizado no Cérebro) e o documento da sua função. Com o modelo local
(contexto curto), só as 10 regras globais e o documento da função.
"""

import re
from functools import lru_cache
from pathlib import Path

import config

GERAIS = ("00", "01")
# Agente -> documentos da função (prefixo do arquivo).
DA_FUNCAO = {
    "social_media": ("02",), "gestor_trafego": ("02",), "analista_metricas": ("02",), "gestor": ("02",),
    "designer": ("03",), "criador_imagens": ("04",), "moviemaker": ("05",), "editor_video": ("06", "05"),
    "copywriter": ("07",),
}
SECOES_FORA = ("6. Catálogo de Lodges",)  # dados de Lodge: o Cérebro tem o site atualizado
SECAO_REGRAS = "2. As 10 regras"
CABECALHO = ("DIRETRIZES DA CASA VERANEIO (siga à risca). Dados de Lodges (local, capacidade, preços, estadia "
             "mínima, atributos): consulte o Cérebro, que tem o site atualizado; o que não estiver lá é PENDENTE.\n"
             "Ajustes deste sistema (valem sobre os manuais): as entregas ficam na pasta do Escritório Veraneio no "
             "Drive, não em \"MARKETING > THOMAS\"; a legenda vai em .docx no lugar do Google Doc; Higgsfield não "
             "é usado; os arquivos (PNG, MP4, PPTX editável) são produzidos pelo Criador de Imagens e pelo Editor "
             "de Vídeo no Claude Code, a partir do plano do Gestor.")


def _arquivo(prefixo: str) -> Path | None:
    achados = sorted(config.PASTA_CONHECIMENTO.glob(f"{prefixo}_*.md"))
    return achados[0] if achados else None


def _secoes(texto: str) -> list[str]:
    return re.split(r"\n(?=## )", texto)


@lru_cache(maxsize=64)
def _ler(caminho: Path, _mtime: float, compacto: bool) -> str:
    texto = caminho.read_text(encoding="utf-8").strip()
    secoes = _secoes(texto)
    if caminho.name.startswith("00") and compacto:
        return "\n".join(s for s in secoes if s.startswith(f"## {SECAO_REGRAS}"))
    return "\n".join(s for s in secoes if not s.startswith(tuple(f"## {t}" for t in SECOES_FORA)))


def para(agente_id: str, compacto: bool = False) -> str:
    """Texto das diretrizes do agente ("" se ele não tem documentos ou a pasta não existe)."""
    funcao = DA_FUNCAO.get(agente_id)
    if not funcao:
        return ""
    gerais = ("00",) if compacto else GERAIS
    partes = []
    for prefixo in (*gerais, *funcao):
        caminho = _arquivo(prefixo)
        if caminho:
            partes.append(_ler(caminho, caminho.stat().st_mtime, compacto))
    return f"{CABECALHO}\n\n" + "\n\n".join(partes) if partes else ""
