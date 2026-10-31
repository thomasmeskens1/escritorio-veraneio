"""Pasta FINAL e folha de aprovação de cada peça (Onda 2, designer-09 e designer-10, 31/10/2026).

FINAL/: dentro da pasta da peça no Drive, sempre o conjunto completo e ATUAL, um arquivo por peça, sem sufixo de
versão. Ajuste que refaz só os slides 2 e 6 (slide_02_v2.png, slide_06_v2.png) deixa em FINAL/ os slides 1, 3, 4, 5
da versão anterior e os 2 e 6 novos, todos com o nome base (slide_02.png). Os arquivos de cada versão continuam na
raiz da pasta como antes (nada é renomeado nem movido: os links já enviados não quebram); FINAL/ é só cópia.

Folha de aprovação: um JPG com as miniaturas numeradas das artes da FINAL/ (vídeo = primeiro quadro), com nome e
formato de cada uma. Vai ao chat junto com a entrega (backend/folha_aprovacao.py), para aprovar ou pedir
"slide 3: trocar foto" olhando uma imagem só. Feita em código (Pillow + ffmpeg), sem gastar Max.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PASTA = "FINAL"
NOME_FOLHA = "FOLHA DE APROVAÇÃO.jpg"
ARTES = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"}
VIDEOS = {".mp4", ".mov"}
DOCUMENTOS = {".docx", ".pptx"}
IGNORADAS = {PASTA.lower(), "anteriores", "cenas"}  # subpastas que não entram (cenas brutas do vídeo ficam fora)
# "_v3" no fim do nome (arte_v3.png) ou antes de "_editavel" (peca_v3_editavel.pptx); "_2" de sem_sobrescrever também
_VERSAO = re.compile(r"_v(\d{1,3})(?=(?:_\d{1,2})?(?:_editavel)?$)", re.IGNORECASE)
_REPETIDO = re.compile(r"(?<=_v\d)_\d{1,2}$|(?<=_v\d\d)_\d{1,2}$")


def chave_e_versao(relativo: str) -> tuple[str, int]:
    """("EDITÁVEL/peca_editavel.pptx", 3) para "EDITÁVEL/peca_v3_editavel.pptx"; sem sufixo = versão 1."""
    caminho = Path(relativo)
    tronco = _REPETIDO.sub("", caminho.stem)
    achado = _VERSAO.search(tronco)
    versao = int(achado.group(1)) if achado else 1
    base = _VERSAO.sub("", tronco) if achado else tronco
    return caminho.with_name(f"{base}{caminho.suffix}").as_posix(), versao


def _candidatos(entrega: Path) -> list[Path]:
    achados = []
    for arquivo in entrega.rglob("*"):
        partes = [p.lower() for p in arquivo.relative_to(entrega).parts[:-1]]
        if not arquivo.is_file() or any(p in IGNORADAS for p in partes) or arquivo.name == NOME_FOLHA:
            continue
        if arquivo.suffix.lower() in ARTES | DOCUMENTOS:
            achados.append(arquivo)
    return achados


def vigentes(entrega: Path) -> dict[str, Path]:
    """Nome base -> arquivo da versão mais alta (empate: o mais recente)."""
    escolhidos: dict[str, tuple[int, float, Path]] = {}
    for arquivo in _candidatos(entrega):
        chave, versao = chave_e_versao(arquivo.relative_to(entrega).as_posix())
        atual = (versao, arquivo.stat().st_mtime, arquivo)
        if chave not in escolhidos or atual[:2] > escolhidos[chave][:2]:
            escolhidos[chave] = atual
    return {chave: v[2] for chave, v in escolhidos.items()}


def atualizar(entrega: Path) -> list[str]:
    """Refaz FINAL/ com a versão vigente de cada peça; devolve os nomes (relativos a FINAL/), em ordem."""
    escolhidos = vigentes(entrega)
    final = entrega / PASTA
    final.mkdir(parents=True, exist_ok=True)
    for antigo in [a for a in final.rglob("*") if a.is_file()]:  # tira o que deixou de ser vigente
        relativo = antigo.relative_to(final).as_posix()
        if relativo != NOME_FOLHA and relativo not in escolhidos:
            antigo.unlink()
    for chave, origem in escolhidos.items():
        destino = final / chave
        if destino.exists() and destino.stat().st_size == origem.stat().st_size \
                and destino.stat().st_mtime >= origem.stat().st_mtime:
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
    return sorted(escolhidos, key=ordem_natural)


def ordem_natural(nome: str) -> list:
    """slide_2 antes de slide_10 (ordem do feed)."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", nome)]


# --- Folha de aprovação -----------------------------------------------------------------------------------------

LARGURA_MINIATURA = 300
COLUNAS_MAX = 4
MARGEM = 24
LEGENDA_ALTURA = 64
TITULO_ALTURA = 70
FUNDO, TINTA, CINZA, DESTAQUE = (246, 243, 238), (43, 43, 43), (122, 112, 101), (47, 74, 58)


def _fonte(tamanho: int):
    from PIL import ImageFont

    for nome in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _primeiro_quadro(video: Path, ambiente: dict | None) -> Path | None:
    destino = Path(tempfile.mkdtemp(prefix="folha-")) / "quadro.png"
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", str(destino)],
                       capture_output=True, timeout=60, env=ambiente,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001 - sem ffmpeg: a miniatura vira um quadro cinza com "vídeo"
        return None
    return destino if destino.is_file() else None


def _formato(arquivo: Path, imagem, ambiente: dict | None) -> str:
    medida = f"{imagem.width}×{imagem.height}" if imagem is not None else ""
    if arquivo.suffix.lower() in VIDEOS:
        try:
            saida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(arquivo)], capture_output=True, text=True, timeout=60, env=ambiente,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
            medida = f"{medida} · {round(float(saida))} s".strip(" ·")
        except Exception:  # noqa: BLE001
            pass
        return f"{medida} · vídeo".strip(" ·")
    return medida or arquivo.suffix.lstrip(".").upper()


def _miniatura(arquivo: Path, ambiente: dict | None):
    """(imagem reduzida ou None, texto do formato)."""
    from PIL import Image

    origem = _primeiro_quadro(arquivo, ambiente) if arquivo.suffix.lower() in VIDEOS else arquivo
    if origem is None or arquivo.suffix.lower() == ".pdf":
        return None, _formato(arquivo, None, ambiente)
    try:
        with Image.open(origem) as aberta:
            imagem = aberta.convert("RGB")
    except Exception:  # noqa: BLE001
        return None, _formato(arquivo, None, ambiente)
    formato = _formato(arquivo, imagem, ambiente)
    altura = round(imagem.height * LARGURA_MINIATURA / imagem.width)
    return imagem.resize((LARGURA_MINIATURA, max(altura, 1))), formato


def folha(final: Path, nomes: list[str], titulo: str, ambiente: dict | None = None) -> Path | None:
    """Grava FINAL/FOLHA DE APROVAÇÃO.jpg com as artes de `nomes` (relativos a FINAL/); None se houver menos de 2."""
    from PIL import Image, ImageDraw

    artes = [n for n in nomes if "/" not in n and Path(n).suffix.lower() in ARTES]
    if len(artes) < 2:
        return None
    itens = [(n, *_miniatura(final / n, ambiente)) for n in artes]
    altura_quadro = max((img.height for _, img, _ in itens if img is not None), default=LARGURA_MINIATURA)
    colunas = min(COLUNAS_MAX, len(itens))
    linhas = -(-len(itens) // colunas)
    largura = MARGEM + colunas * (LARGURA_MINIATURA + MARGEM)
    altura = TITULO_ALTURA + linhas * (altura_quadro + LEGENDA_ALTURA + MARGEM) + MARGEM
    tela = Image.new("RGB", (largura, altura), FUNDO)
    desenho = ImageDraw.Draw(tela)
    desenho.text((MARGEM, 22), titulo[:80], fill=TINTA, font=_fonte(24))
    desenho.text((MARGEM, 50), f"{len(itens)} arquivo(s) na ordem do feed · versão vigente da pasta FINAL",
                 fill=CINZA, font=_fonte(14))
    fonte_nome, fonte_formato, fonte_numero = _fonte(15), _fonte(13), _fonte(20)
    for i, (nome, imagem, formato) in enumerate(itens):
        x = MARGEM + (i % colunas) * (LARGURA_MINIATURA + MARGEM)
        y = TITULO_ALTURA + (i // colunas) * (altura_quadro + LEGENDA_ALTURA + MARGEM)
        if imagem is not None:
            tela.paste(imagem, (x, y))
        else:
            desenho.rectangle((x, y, x + LARGURA_MINIATURA, y + altura_quadro), fill=(220, 214, 205))
            desenho.text((x + 12, y + 12), Path(nome).suffix.lstrip(".").upper(), fill=CINZA, font=fonte_nome)
        desenho.rectangle((x, y, x + 34, y + 30), fill=DESTAQUE)
        desenho.text((x + 8, y + 3), str(i + 1), fill=(255, 255, 255), font=fonte_numero)
        desenho.text((x, y + altura_quadro + 8), nome[:38], fill=TINTA, font=fonte_nome)
        desenho.text((x, y + altura_quadro + 30), formato, fill=CINZA, font=fonte_formato)
    destino = final / NOME_FOLHA
    tela.save(destino, "JPEG", quality=85, optimize=True)
    return destino
