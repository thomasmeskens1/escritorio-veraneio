"""Leitura do PPTX que volta da equipe (Onda 3 de novembro, 12/11/2026; editor_video-02 e moviemaker-35, fase 2).

A equipe abre o editável gerado por pptx_receita.py, muda um texto, troca uma foto ou aumenta o logo e devolve o
arquivo num pedido de ajuste. Este módulo lê o PPTX devolvido e compara com a receita da peça (o mesmo plano que
gerou o PPTX): textos, tamanho do texto, posição, fotos, logo e ordem dos slides. O resultado vira uma lista
curta ("slide 2: texto 1 “X” → “Y”") que entra no prompt do ajuste, para o Max aplicar só o que mudou.

As formas são reconhecidas pelo nome fixo que o gerador deu ("texto|c<cena>|<papel>", "foto|c<cena>",
"logo|c<cena>"); foto e logo levam no texto alternativo o hash da imagem original. Forma sem esse nome conta como
nova. Só lê: nunca altera o PPTX nem a receita.

Uso: python pptx_diferenca.py <pasta da peça> <pptx devolvido>
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pptx_receita  # noqa: E402

EMU_POR_PX = pptx_receita.EMU_POR_PX
TOLERANCIA_POSICAO = 0.02     # fração da largura/altura do slide: abaixo disso não conta como "mudou de lugar"
TOLERANCIA_TAMANHO_PX = 1.5   # diferença de tamanho de letra (px) que conta como mudança
TOLERANCIA_LOGO_PX = 3
MAXIMO_LINHAS = 30
NOME = re.compile(r"^(texto|foto|logo|imagem|filete)\|c(\d+)(?:\|(.+))?$")
HASH = re.compile(r"hash=([0-9a-f]{6,40})")


def _px(valor) -> float | None:
    return None if valor is None else round(int(valor) / EMU_POR_PX, 1)


def _plano(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _juntar(linhas: list[str]) -> str:
    return " / ".join(_plano(l) for l in linhas if _plano(l))


# ---------------------------------------------------------------- leitura (python-pptx)

def ler(arquivo: Path) -> dict:
    """PPTX -> {"largura", "altura", "slides": [{"n", "cena", "textos": {chave: {...}}, "fotos", "logos",
    "novos_textos", "novas_imagens"}]} (medidas em px da peça)."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    apresentacao = Presentation(str(arquivo))
    lido = {"largura": _px(apresentacao.slide_width), "altura": _px(apresentacao.slide_height), "slides": []}
    for n, folha in enumerate(apresentacao.slides, 1):
        slide = {"n": n, "cena": None, "textos": {}, "fotos": {}, "logos": {}, "novos_textos": [], "novas_imagens": 0}
        cenas = Counter()
        for forma in folha.shapes:
            achado = NOME.match(forma.name or "")
            caixa = {"x": _px(forma.left), "y": _px(forma.top), "largura": _px(forma.width), "altura": _px(forma.height)}
            if achado:
                cenas[int(achado[2])] += 1
            if forma.shape_type == MSO_SHAPE_TYPE.PICTURE:
                descr = forma._element.nvPicPr.cNvPr.get("descr") or ""
                original = HASH.search(descr)
                caixa.update(hash=pptx_receita.hash_de(forma.image.blob), hash_original=original[1] if original else None)
                if achado and achado[1] in ("foto", "logo"):
                    slide["fotos" if achado[1] == "foto" else "logos"][forma.name] = caixa
                elif not achado:
                    slide["novas_imagens"] += 1
            elif achado and achado[1] == "logo":  # marcador do logo que faltou na geração
                slide["logos"][forma.name] = {**caixa, "hash": None, "hash_original": None}
            elif forma.has_text_frame and forma.text_frame.text.strip():
                corridas = [c for p in forma.text_frame.paragraphs for c in p.runs]
                tamanho = next((c.font.size for c in corridas if c.font.size), None)
                caixa.update(linhas=[p.text for p in forma.text_frame.paragraphs],
                             tamanho=round(tamanho.pt / 0.75, 1) if tamanho else None)
                if achado and achado[1] == "texto":
                    slide["textos"][forma.name] = caixa
                else:
                    slide["novos_textos"].append(_juntar(caixa["linhas"]))
        slide["cena"] = cenas.most_common(1)[0][0] if cenas else None
        lido["slides"].append(slide)
    return lido


# ---------------------------------------------------------------- comparação (sem python-pptx)

def _mudou_de_lugar(antes: dict, depois: dict, largura: float, altura: float) -> bool:
    return (abs((depois.get("x") or 0) - (antes.get("x") or 0)) > largura * TOLERANCIA_POSICAO
            or abs((depois.get("y") or 0) - (antes.get("y") or 0)) > altura * TOLERANCIA_POSICAO)


def _textos(slide_plano: dict, slide_lido: dict, rotulo: str, largura: float, altura: float) -> list[str]:
    linhas = []
    for caixa in slide_plano["textos"]:
        antes = _juntar([l["texto"] for l in caixa["linhas"]])
        depois = slide_lido["textos"].get(caixa["chave"])
        if depois is None:
            linhas.append(f"{rotulo}: {caixa['papel']} apagado (“{antes}”)")
            continue
        novo = _juntar(depois["linhas"])
        if novo != antes:
            linhas.append(f"{rotulo}: {caixa['papel']} “{antes}” → “{novo}”")
        tamanho_antes = caixa["linhas"][0]["tamanho"]  # a primeira letra da caixa, como o leitor mede
        if depois.get("tamanho") and abs(depois["tamanho"] - tamanho_antes) > TOLERANCIA_TAMANHO_PX:
            linhas.append(f"{rotulo}: {caixa['papel']} com letra {tamanho_antes:g} → {depois['tamanho']:g} px")
        if _mudou_de_lugar(caixa, depois, largura, altura):
            linhas.append(f"{rotulo}: {caixa['papel']} mudou de lugar (y {caixa['y']:g} → {depois['y']:g} px)")
    for texto in slide_lido["novos_textos"]:
        linhas.append(f"{rotulo}: texto novo “{texto}”")
    return linhas


def _imagens(slide_plano: dict, slide_lido: dict, rotulo: str, largura: float, altura: float) -> list[str]:
    linhas = []
    chave_foto = f"foto|c{slide_plano['cena']}"
    foto = slide_lido["fotos"].get(chave_foto)
    if slide_plano.get("midia"):
        if foto is None:
            linhas.append(f"{rotulo}: foto removida (era {slide_plano['midia']})"
                          if not slide_lido["novas_imagens"] else f"{rotulo}: foto trocada (era {slide_plano['midia']})")
        elif foto.get("hash_original") and foto["hash"] != foto["hash_original"]:
            linhas.append(f"{rotulo}: foto trocada (era {slide_plano['midia']})")
        elif foto and _mudou_de_lugar({"x": 0, "y": 0}, foto, largura, altura):
            linhas.append(f"{rotulo}: foto mudou de lugar ou de recorte")
    elif slide_lido["novas_imagens"]:
        linhas.append(f"{rotulo}: {slide_lido['novas_imagens']} imagem(ns) nova(s) no slide")
    if slide_plano.get("midia") and foto is not None and slide_lido["novas_imagens"]:
        linhas.append(f"{rotulo}: {slide_lido['novas_imagens']} imagem(ns) nova(s) no slide")
    logo_plano = slide_plano.get("logo")
    logo = slide_lido["logos"].get(logo_plano["chave"]) if logo_plano else None
    if logo_plano and logo is None:
        linhas.append(f"{rotulo}: logo removido")
    elif logo is not None:
        if logo.get("hash_original") and logo["hash"] != logo["hash_original"]:
            linhas.append(f"{rotulo}: logo trocado por outro arquivo (confira se é da marca certa)")
        if abs((logo.get("altura") or 0) - logo_plano["altura"]) > TOLERANCIA_LOGO_PX:
            linhas.append(f"{rotulo}: logo com altura {logo_plano['altura']:g} → {logo['altura']:g} px")
        if abs((logo.get("y") or 0) - logo_plano["y"]) > altura * TOLERANCIA_POSICAO:
            linhas.append(f"{rotulo}: logo mudou de lugar (y {logo_plano['y']:g} → {logo['y']:g} px)")
    return linhas


def comparar(plano: dict, lido: dict) -> list[str]:
    """Lista do que mudou do plano (receita) para o PPTX lido. [] = nada mudou."""
    largura, altura = plano["largura"], plano["altura"]
    linhas = []
    if lido.get("largura") and (abs(lido["largura"] - largura) > 2 or abs(lido["altura"] - altura) > 2):
        linhas.append(f"tamanho do slide {largura}x{altura} → {lido['largura']:g}x{lido['altura']:g} px")
    por_cena = {}
    for slide in lido["slides"]:
        if slide["cena"] is not None and slide["cena"] not in por_cena:
            por_cena[slide["cena"]] = slide
    for slide_plano in plano["slides"]:
        cena = slide_plano["cena"]
        slide_lido = por_cena.get(cena)
        if slide_lido is None:
            linhas.append(f"cena {cena} apagada (o slide {slide_plano['n']} da receita não voltou)")
            continue
        rotulo = f"slide {slide_lido['n']}"
        if slide_lido["n"] != slide_plano["n"]:
            linhas.append(f"ordem: a cena {cena} (slide {slide_plano['n']} da receita) agora é o slide {slide_lido['n']}")
        linhas += _textos(slide_plano, slide_lido, rotulo, largura, altura)
        linhas += _imagens(slide_plano, slide_lido, rotulo, largura, altura)
    usados = {id(s) for s in por_cena.values()}
    for slide in lido["slides"]:
        if id(slide) not in usados:
            textos = "; ".join(f"“{t}”" for t in [*(_juntar(c["linhas"]) for c in slide["textos"].values()),
                                                    *slide["novos_textos"]][:3])
            linhas.append(f"slide {slide['n']}: novo (não está na receita){': ' + textos if textos else ''}")
    return linhas


def diferencas(rascunho: Path, arquivo: Path) -> list[str] | None:
    """Diferenças do PPTX devolvido contra a receita da pasta (None = sem receita ou PPTX ilegível)."""
    plano = pptx_receita.plano_da_pasta(rascunho)
    if plano is None:
        return None
    try:
        lido = ler(arquivo)
    except Exception:  # noqa: BLE001 - PPTX corrompido ou sem python-pptx: o ajuste segue sem a lista
        return None
    return comparar(plano, lido)


def instrucao(rascunho: Path, anexos: list[Path]) -> str:
    """Bloco do prompt do ajuste quando a equipe devolve o PPTX editável entre os anexos."""
    blocos = []
    for arquivo in [Path(a) for a in anexos or [] if str(a).lower().endswith(".pptx")]:
        mudancas = diferencas(rascunho, arquivo) if arquivo.is_file() else None
        if mudancas is None:
            continue
        if not mudancas:
            blocos.append(f"PPTX DEVOLVIDO PELA EQUIPE ({arquivo.name}): o sistema comparou com a receita da peça e "
                          "não achou mudança de texto, tamanho, posição, foto, logo ou ordem dos slides.")
            continue
        lista = "\n".join(f"- {m}" for m in mudancas[:MAXIMO_LINHAS])
        resto = f"\n- (e mais {len(mudancas) - MAXIMO_LINHAS})" if len(mudancas) > MAXIMO_LINHAS else ""
        blocos.append(f"PPTX DEVOLVIDO PELA EQUIPE ({arquivo.name}): o sistema comparou com a receita da peça e "
                      f"achou estas mudanças:\n{lista}{resto}\nAplique EXATAMENTE essas mudanças na arte/vídeo (e no "
                      "motion.json, molde.json e receita.json), sem mexer no resto. O PPTX novo o sistema gera sozinho.")
    return "\n\n".join(blocos)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    resultado = diferencas(Path(sys.argv[1]), Path(sys.argv[2]))
    print("sem receita ou PPTX ilegível" if resultado is None else "\n".join(resultado) or "nada mudou")
