"""Vinheta animada do logo de cada empresa (Thomas, 04/11/2026): quadro de ~3 s logo antes do fechamento/CTA.

Fundo Verde #00361B, logo centralizado (leitura boa no celular), movimento elegante e lento: o símbolo entra
primeiro (escala suave ou máscara), o nome se revela da esquerda para a direita, um filete Caramelo se desenha
embaixo e tudo assenta com ease-out. Cada empresa tem uma coreografia própria na mesma linguagem; nunca o logo
de outra empresa (cada uma lê só a pasta dela em CÉREBRO/MARCAS, copiada para _referencias/ na produção).

Uso: python motion.py vinheta --empresa casa_veraneio --formato 1080x1920 --saida vinheta_9x16.mp4
"""

from pathlib import Path

from PIL import Image

import motion

# empresa: (pasta em MARCAS, logo sobre Verde, onde o símbolo acaba (fração da largura), altura em 9:16,
#           entrada do símbolo, entrada do nome). Alturas: um pouco acima dos ~135 px do manual 06 (a vinheta é só o logo); o da
#           Corp tem a linha "CORP." e o da Vero "IMÓVEIS ESPECIAIS", que precisam de mais altura para ler no celular.
VINHETAS = {
    "casa_veraneio": ("CASA_VERANEIO", "logo_caramelo_texto_creme.png", 0.305, 170,
                      {"efeito": "escala", "duracao": 0.9}, {"efeito": "revela", "direcao": "direita", "duracao": 0.9}),
    "cv_corporativo": ("CORPORATIVO", "logo_corp_caramelo_texto_branco.png", 0.315, 185,
                       {"efeito": "revela", "direcao": "cima", "duracao": 0.8},
                       {"efeito": "revela", "direcao": "direita", "duracao": 0.9}),
    "casa_vero": ("CASA_VERO", "logo_vero_caramelo_creme.png", 0.42, 240,
                  {"efeito": "revela", "direcao": "cima", "duracao": 0.9}, {"efeito": "sobe", "duracao": 0.8}),
}
DURACAO = 3.2
FORMATOS = ("1080x1920", "1080x1350", "1920x1080")


def arquivo_logo(empresa: str, base: Path) -> Path:
    """Logo da própria empresa: primeiro a cópia em _referencias/<PASTA> da peça, depois o CÉREBRO."""
    if empresa not in VINHETAS:
        raise ValueError(f"Empresa sem vinheta: {empresa!r} (use {', '.join(VINHETAS)})")
    pasta, nome = VINHETAS[empresa][:2]
    for candidato in (base / "_referencias" / pasta / nome, motion.pasta_marcas() / pasta / nome):
        if candidato.is_file():
            return candidato
    raise ValueError(f"Logo {pasta}/{nome} não encontrado (nem em _referencias/ nem no CÉREBRO).")


def elementos(empresa: str, formato: str, logo: Path) -> list[dict]:
    """Símbolo, nome e filete posicionados como no logo inteiro, centralizado na tela (um pouco acima do meio)."""
    _, _, corte, altura, entrada_simbolo, entrada_nome = VINHETAS[empresa]
    largura_tela, altura_tela = (int(v) for v in formato.split("x"))
    # O lado menor é sempre 1080; no 16:9 (tela deitada) o logo cresce 25% para não ficar perdido na largura.
    fator = min(largura_tela, altura_tela) / 1080 * (1.25 if largura_tela > altura_tela else 1.0)
    altura = round(altura * fator)
    with Image.open(logo) as aberto:
        caixa = aberto.getchannel("A").getbbox() or (0, 0, *aberto.size)
        largura_original, proporcao = aberto.width, aberto.width / aberto.height
    largura = round(altura * proporcao)
    esquerda = (largura_tela - largura * (caixa[0] + caixa[2]) / largura_original) / 2  # centra a parte com tinta
    topo = round(altura_tela * 0.47 - altura / 2)
    rel = logo.name
    return [
        {"tipo": "imagem", "arquivo": rel, "altura": altura, "recorte": [0, corte], "x": esquerda, "y": topo,
         "entrada": {**entrada_simbolo, "inicio": 0.35}},
        {"tipo": "imagem", "arquivo": rel, "altura": altura, "recorte": [corte, 1], "x": esquerda + largura * corte,
         "y": topo, "entrada": {**entrada_nome, "inicio": 0.85}},
        {"tipo": "filete", "largura": round(min(largura * 0.42, 220 * fator)), "espessura": max(2, round(2 * fator)),
         "cor": "caramelo", "y": topo + altura + round(56 * fator),
         "entrada": {"efeito": "desenha", "inicio": 1.55, "duracao": 0.9}},
    ]


def vinheta(empresa: str, formato: str, saida: Path, base: Path | None = None) -> dict:
    """Renderiza a vinheta (MP4 H.264 30 fps, fundo Verde opaco, trilha AAC silenciosa)."""
    if formato not in FORMATOS:
        raise ValueError(f"Formato da vinheta: {', '.join(FORMATOS)}")
    saida = Path(saida).resolve()
    base = Path(base or saida.parent).resolve()
    logo = arquivo_logo(empresa, base)
    # A imagem é procurada pelo nome: a pasta da empresa entra antes de todas as outras.
    return motion.aplicar(None, saida, elementos(empresa, formato, logo), formato, DURACAO, fundo="verde",
                          base=base, sai=False, pastas=[logo.parent])
