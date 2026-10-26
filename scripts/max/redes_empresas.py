"""YouTube da Casa Vero para o Cérebro (leitura liberada pelo Thomas em 26/10/2026).

- YouTube da Casa Vero (@CasaVeroImóveis): cada vídeo (tours de imóveis e shorts) vira um documento com título, data,
  descrição e a fala do vídeo (legenda automática do YouTube, em português). A fala é transcrição automática: pode
  ter erros e não substitui a ficha do site (fonte "rede", peso abaixo de "site").
  Cada vídeo é baixado UMA vez (cache em backend/dados/redes/youtube/); com pausa entre vídeos e, se o YouTube
  limitar (HTTP 429), para e continua no próximo ciclo.
- Instagram: as publicações das 3 contas vêm do painel analítico, pela API oficial da Meta (painel_analitico.py);
  a leitura pública sem login é bloqueada pelo Instagram.
Telefones e WhatsApp saem do texto (regra de ouro). Somente leitura; nada é publicado.

Uso: python scripts/max/redes_empresas.py (também roda no ciclo de 6 h do trabalhador).
"""

import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import comum
from comum import log
from sites_empresas import TELEFONE

CANAL_VERO = "https://www.youtube.com/channel/UClSXjsr4I17PslswQpLqzYQ"
CACHE = comum.DADOS / "redes" / "youtube"
PAUSA_S = 8
MAX_NOVOS_POR_CICLO = 15        # vídeos novos baixados por ciclo (o resto fica para o próximo)
MAX_FALA = 15000                # caracteres da fala por vídeo no Cérebro (tours passam de 60 mil)
LOTE = 3                        # vídeos por envio ao Cérebro


def _yt_dlp(*argumentos: str, timeout: int = 300) -> subprocess.CompletedProcess:
    python = Path(sys.executable).with_name("python.exe")  # o trabalhador roda em pythonw.exe
    return subprocess.run([str(python if python.exists() else sys.executable), "-m", "yt_dlp", "--no-warnings",
                           *argumentos], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=comum.SEM_JANELA)


def _ids_do_canal() -> list[str]:
    ids = []
    for aba in ("videos", "shorts"):
        saida = _yt_dlp("--flat-playlist", "--print", "id", f"{CANAL_VERO}/{aba}")
        ids += [i.strip() for i in saida.stdout.splitlines() if i.strip()]
    return list(dict.fromkeys(ids))


def _fala(vtt: str) -> str:
    """Legenda automática (VTT) -> texto corrido: a legenda automática repete cada linha na seguinte."""
    linhas = []
    for linha in vtt.splitlines():
        linha = html.unescape(re.sub(r"<[^>]+>", "", linha)).replace(">>", "").strip()
        if not linha or "-->" in linha or linha.startswith(("WEBVTT", "Kind:", "Language:")) or linha.isdigit():
            continue
        if not linhas or linha != linhas[-1]:
            linhas.append(linha)
    return TELEFONE.sub("", re.sub(r"\s+", " ", " ".join(linhas))).strip()


def _baixar_video(video_id: str, pasta: Path) -> dict | None:
    """Metadados + fala de um vídeo. None se o YouTube limitou (tentar no próximo ciclo)."""
    saida = _yt_dlp("--skip-download", "--write-info-json", "--write-auto-subs", "--write-subs",
                    "--sub-langs", "pt-orig,pt", "--sub-format", "vtt", "-o", str(pasta / "%(id)s.%(ext)s"),
                    f"https://www.youtube.com/watch?v={video_id}")
    info = pasta / f"{video_id}.info.json"
    if not info.exists():
        if "429" in saida.stderr:
            return None
        return {"id": video_id, "erro": saida.stderr[-300:]}
    dados = json.loads(info.read_text(encoding="utf-8"))
    legendas = sorted(pasta.glob(f"{video_id}*.vtt"))
    fala = _fala(legendas[0].read_text(encoding="utf-8")) if legendas else ""
    for arquivo in [info, *legendas]:
        arquivo.unlink(missing_ok=True)
    return {"id": video_id, "titulo": dados.get("title", ""), "data": dados.get("upload_date", ""),
            "duracao_s": dados.get("duration"), "descricao": TELEFONE.sub("", dados.get("description") or ""),
            "fala": fala}


def youtube_vero() -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    novos = 0
    for video_id in _ids_do_canal():
        destino = CACHE / f"{video_id}.json"
        if destino.exists() or novos >= MAX_NOVOS_POR_CICLO:
            continue
        video = _baixar_video(video_id, CACHE)
        if video is None:
            log("   YouTube limitou as requisições; os vídeos restantes ficam para o próximo ciclo.")
            break
        destino.write_text(json.dumps(video, ensure_ascii=False), encoding="utf-8")
        novos += 1
        time.sleep(PAUSA_S)
    if novos:
        log(f"   YouTube da Casa Vero: {novos} vídeo(s) novo(s) lido(s).")
    documentos = []
    for arquivo in sorted(CACHE.glob("*.json")):
        video = json.loads(arquivo.read_text(encoding="utf-8"))
        if video.get("erro") or not video.get("titulo"):
            continue
        data = video["data"]
        imoveis = sorted({f"Vero {n}" for n in re.findall(r"\bvero\s*(\d+)", f"{video['titulo']} {video['descricao']}", re.I)})
        partes = [f"Fonte: https://www.youtube.com/watch?v={video['id']} (YouTube da Casa Vero Imóveis"
                  + (f", publicado em {data[6:8]}/{data[4:6]}/{data[:4]}" if len(data) == 8 else "") + ")",
                  f"Vídeo do canal da Casa Vero Imóveis: {video['titulo']}"]
        if imoveis:
            partes.append(f"Imóvel(is) do vídeo: {', '.join(imoveis)} (a ficha do site vale mais que a fala do vídeo)")
        if video["descricao"].strip():
            partes.append(f"Descrição: {video['descricao'].strip()[:3000]}")
        if video["fala"]:
            partes.append("Fala do vídeo (transcrição automática, pode ter erros; não use preço nem número dito no "
                          f"vídeo sem conferir na ficha): {video['fala'][:MAX_FALA]}")
        documentos.append({"fonte_tipo": "rede", "empresa": "casa_vero", "fonte_ref": f"vero/youtube/{video['id']}",
                           "titulo": f"YouTube: {video['titulo'][:150]} — Casa Vero", "conteudo": "\n".join(partes)})
    return documentos


def rodar() -> None:
    documentos = []
    try:
        documentos += youtube_vero()
    except Exception as erro:  # rede fora do ar não derruba o trabalhador
        log(f"YouTube da Casa Vero: não foi possível ler ({erro}).")
    if documentos:
        # Lotes pequenos: a fala de um tour gera muitos trechos e o Cérebro calcula os embeddings na hora (lote de
        # 10 vídeos passou dos 5 min de espera). Documento sem mudança é ignorado pelo Cérebro, sem custo.
        enviados = all([comum.enviar_ao_cerebro(documentos[i:i + LOTE]) for i in range(0, len(documentos), LOTE)])
        log(f"Redes sociais: {len(documentos)} documento(s) para o Cérebro{'' if enviados else ' (envio adiado)'}.")


if __name__ == "__main__":
    rodar()
