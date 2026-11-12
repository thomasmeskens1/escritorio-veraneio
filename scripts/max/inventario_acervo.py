"""Inventário do material de UM imóvel do acervo, sem IA (brainstorm de 11/11/2026, Onda 2: moviemaker-01,
editor_video-01, despachante-11 e gestor-04).

Caso real (Lodge 32, tarefas 246, 247 e 256): o Gestor planejou o Reels sem saber os nomes, a duração nem se havia
drone nos 2 vídeos da pasta, e no fim os dois eram o mesmo arquivo de 88 s em 4K. Aqui o trabalhador, sem o Claude,
lê SÓ a pasta do imóvel pedido no acervo (nunca o acervo inteiro): ffprobe em cada vídeo (duração, resolução,
orientação, fps, áudio, indício de drone pelo nome ou metadado), cópias repetidas (tamanho, duração e o começo do
arquivo) e as fotos contadas por subpasta. Devolve um JSON; o backend (backend/inventario.py) guarda por 7 dias e
monta o bloco do Gestor, do Moviemaker e do Editor de Vídeo.

Somente leitura: nada é gravado, movido ou apagado no acervo. O cache local (backend/dados/inventario_videos.json) é
por arquivo (caminho, tamanho e data): arquivo que muda é lido de novo; nada é apagado dele.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import catalogo_lodges
import comum

ARQUIVO_CACHE = comum.DADOS / "inventario_videos.json"
MAX_VIDEOS = 40                 # pasta com mais vídeos que isso: os demais só contados
LIMITE_TOTAL_S = 150            # a leitura toda; o que passar fica "não lido" (o backend espera bem menos)
BYTES_DO_COMECO = 256 * 1024    # para achar cópias: o começo do arquivo, sem baixar o vídeo inteiro do Drive
DRONE = re.compile(r"\b(?:dji|drone|mavic|a[eé]re[oa]s?|aerial)|^dji_", re.IGNORECASE)
PEDIDO = re.compile(r"\blodges?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)


def ffprobe_exe() -> str:
    """ffprobe do PATH ou do pacote do WinGet (o mesmo que o trabalhador usa para o ffmpeg)."""
    if (encontrado := shutil.which("ffprobe")):
        return encontrado
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    achados = sorted(pacotes.glob("Gyan.FFmpeg*/*/bin/ffprobe.exe"))
    return str(achados[-1]) if achados else "ffprobe"


def sondar(arquivo: Path) -> dict:
    """Saída JSON do ffprobe (streams e formato). Sem janela (pythonw)."""
    saida = subprocess.run([ffprobe_exe(), "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                            str(arquivo)], capture_output=True, text=True, timeout=60, creationflags=comum.SEM_JANELA)
    if saida.returncode != 0:
        raise RuntimeError((saida.stderr or "ffprobe falhou").strip()[:120])
    return json.loads(saida.stdout or "{}")


def _fps(texto: str) -> float | None:
    try:
        num, _, den = (texto or "").partition("/")
        valor = float(num) / float(den or 1)
        return round(valor, 2) if valor > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _rotacao(stream: dict) -> int:
    """Celular grava 1920×1080 com rotação 90: na tela é vertical."""
    try:
        if (girar := (stream.get("tags") or {}).get("rotate")):
            return abs(int(float(girar))) % 180
        for dado in stream.get("side_data_list") or []:
            if "rotation" in dado:
                return abs(int(float(dado["rotation"]))) % 180
    except (TypeError, ValueError):
        pass
    return 0


def resumir(nome: str, dados: dict) -> dict:
    """Do JSON do ffprobe ao que interessa no plano."""
    streams = dados.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), {})
    formato = dados.get("format") or {}
    largura, altura = int(video.get("width") or 0), int(video.get("height") or 0)
    if _rotacao(video) == 90:
        largura, altura = altura, largura
    try:
        duracao = round(float(formato.get("duration") or video.get("duration") or 0), 1) or None
    except ValueError:
        duracao = None
    tags = " ".join(str(v) for v in {**(formato.get("tags") or {}), **(video.get("tags") or {})}.values())
    return {
        "nome": nome, "duracao_s": duracao, "largura": largura or None, "altura": altura or None,
        "orientacao": ("vertical" if altura > largura else "horizontal" if largura > altura else "quadrado")
        if largura and altura else "desconhecida",
        "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or ""),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "drone": bool(DRONE.search(nome) or re.search(r"\bdji\b|mavic|phantom|fc\d{4}", tags, re.IGNORECASE)),
    }


def _comeco(arquivo: Path) -> str:
    with open(arquivo, "rb") as aberto:
        return hashlib.sha1(aberto.read(BYTES_DO_COMECO)).hexdigest()[:16]


def _ler_cache(arquivo: Path) -> dict:
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pastas_do_imovel(acervo: Path, numero: int) -> list[Path]:
    """Pastas do Lodge `numero`: só a faixa "Lodges N-M" que o contém é listada (o acervo não é percorrido)."""
    achadas = []
    for faixa, inicio, fim in catalogo_lodges.pastas_de_faixa(acervo):
        if not inicio <= numero <= fim:
            continue
        for pasta in sorted(faixa.iterdir(), key=lambda p: p.name.lower()):
            casamento = catalogo_lodges.PADRAO_NUMERO.search(pasta.name)
            if pasta.is_dir() and casamento and int(casamento.group(1)) == numero:
                achadas.append(pasta)
    return achadas


def ler_pasta(pasta: Path, sonda=sondar, cache: dict | None = None, limite_s: float = LIMITE_TOTAL_S) -> dict:
    """Vídeos (ffprobe), cópias repetidas e fotos por subpasta de UMA pasta de imóvel. `cache` é atualizado."""
    cache = {} if cache is None else cache
    fim = time.monotonic() + limite_s
    videos, fotos, outros = [], {}, 0
    for raiz, dirs, arquivos in os.walk(pasta, onerror=lambda _: None):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for nome in sorted(arquivos):
            if nome.lower() in catalogo_lodges.IGNORAR or nome.startswith(("~$", ".")):
                continue
            arquivo = Path(raiz, nome)
            relativo = arquivo.relative_to(pasta).as_posix()
            extensao = arquivo.suffix.lower()
            if extensao in catalogo_lodges.FOTOS:
                subpasta = relativo.split("/")[0] if "/" in relativo else "(raiz)"
                fotos[subpasta] = fotos.get(subpasta, 0) + 1
            elif extensao in catalogo_lodges.VIDEOS:
                videos.append((relativo, arquivo))
            else:
                outros += 1
    lidos, nao_lidos = [], []
    for relativo, arquivo in videos:
        if len(lidos) >= MAX_VIDEOS or time.monotonic() > fim:
            nao_lidos.append(relativo)
            continue
        try:
            info = arquivo.stat()
            chave = f"{arquivo}|{info.st_size}|{int(info.st_mtime)}"
            if chave not in cache:
                cache[chave] = {**resumir(relativo, sonda(arquivo)), "bytes": info.st_size, "comeco": _comeco(arquivo)}
            lidos.append({**cache[chave], "nome": relativo})
        except Exception as erro:  # noqa: BLE001 - um arquivo ruim não derruba o inventário
            lidos.append({"nome": relativo, "erro": str(erro)[:120]})
    _marcar_copias(lidos)
    return {"videos": lidos, "videos_nao_lidos": nao_lidos, "fotos": sum(fotos.values()),
            "fotos_por_pasta": dict(sorted(fotos.items())), "outros": outros}


def _marcar_copias(videos: list[dict]) -> None:
    """Mesmo tamanho, mesma duração e mesmo começo: o segundo é cópia do primeiro (caso do Lodge 32)."""
    vistos: dict[tuple, str] = {}
    for video in videos:
        if "erro" in video:
            continue
        chave = (video.get("bytes"), video.get("duracao_s"), video.get("comeco"))
        if chave in vistos:
            video["copia_de"] = vistos[chave]
        else:
            vistos[chave] = video["nome"]


def inventariar(imovel: str, acervo: Path | None = None, sonda=sondar, arquivo_cache: Path | None = None) -> dict:
    """Ficha do imóvel ("Lodge 32"). Pasta não achada: {"encontrado": False}."""
    acervo = acervo or comum.ACERVO
    arquivo_cache = arquivo_cache or ARQUIVO_CACHE
    if not acervo.is_dir():
        raise RuntimeError(f"Acervo dos Lodges não acessível neste PC: {acervo}")
    if not (numero := PEDIDO.search(imovel or "")):
        raise RuntimeError(f"Imóvel sem número de Lodge: {imovel!r}")
    pastas = pastas_do_imovel(acervo, int(numero.group(1)))
    ficha = {"imovel": f"Lodge {int(numero.group(1))}", "lido_em": datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "encontrado": bool(pastas)}
    if not pastas:
        return ficha
    cache = _ler_cache(arquivo_cache)
    marketing = []
    if acervo == comum.ACERVO:  # material do Marketing (LODGES por categoria) do mesmo Lodge: citado, não lido
        import acervo_marketing

        marketing = [str(p) for p in acervo_marketing.pastas_do_lodge(int(numero.group(1)))]
    ficha.update(pasta=pastas[0].relative_to(acervo).as_posix(), outras_pastas=[
        p.relative_to(acervo).as_posix() for p in pastas[1:]] + marketing, **ler_pasta(pastas[0], sonda, cache))
    try:
        arquivo_cache.parent.mkdir(parents=True, exist_ok=True)
        arquivo_cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # sem cache local: a próxima leitura só demora mais
    return ficha


def executar(payload: dict) -> str:
    """Trabalho "inventario" da fila (trabalhos_max.EXECUTORES): sem o Claude Code, só leitura."""
    comum.log(f"   inventário do material: {payload.get('imovel')}")
    return json.dumps(inventariar(payload.get("imovel") or ""), ensure_ascii=False)
