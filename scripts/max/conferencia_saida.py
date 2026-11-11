"""Conferência da entrega no PC, só como AVISO (Onda 2 de novembro, 11/11/2026; moviemaker-21, sonoplasta-04,
designer-06, copywriter-03). Roda no trabalhador depois da conferência do texto aprovado e nunca derruba a entrega.

O motor das regras é o mesmo do backend (backend/conferente_motor.py, lido pelo caminho do repositório): formato da
legenda entregue (.docx), ritmo e cores do motion.json, fotos do Corp (evento e foto antiga) e o áudio da versão
_com_som medido pelo ffmpeg (volume, pico e buraco de silêncio). Sem IA e sem custo.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import comum

if str(comum.BACKEND_DIR) not in sys.path:
    sys.path.append(str(comum.BACKEND_DIR))  # no fim: os módulos do PC continuam na frente
import conferente_motor as motor  # noqa: E402

VIDEOS = {".mp4", ".mov"}
IGNORAR = {"_referencias", "anteriores", "_moldes"}
MAX_LINHAS = 8


# ---------------------------------------------------------------- áudio (ffmpeg)

def ler_medidas(saida: str) -> dict:
    """Lê o stderr do ffmpeg com ebur128 (peak=true) e silencedetect."""
    medidas: dict = {"lufs": None, "true_peak": None, "silencios": [], "duracao": None}
    if (achado := re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", saida)):
        h, m, s = achado.groups()
        medidas["duracao"] = int(h) * 3600 + int(m) * 60 + float(s)
    resumo = saida[saida.rfind("Summary:"):] if "Summary:" in saida else ""
    if (achado := re.search(r"\bI:\s*(-?[\d.]+)\s*LUFS", resumo)):
        medidas["lufs"] = float(achado.group(1))
    if (achado := re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", resumo, re.S)) and achado.group(1) != "-inf":
        medidas["true_peak"] = float(achado.group(1))
    inicio = None
    for tipo, valor in re.findall(r"silence_(start|end):\s*(-?[\d.]+)", saida):
        if tipo == "start":
            inicio = float(valor)
        elif inicio is not None:
            medidas["silencios"].append((inicio, float(valor)))
            inicio = None
    if inicio is not None:  # o silêncio vai até o fim do arquivo
        medidas["silencios"].append((inicio, medidas["duracao"] or inicio))
    return medidas


def medir_audio(arquivo: Path) -> dict:
    import sonoplasta

    som = motor.marcas()["som_comum"]
    saida = sonoplasta._rodar([sonoplasta._ffmpeg(), "-hide_banner", "-nostats", "-i", str(arquivo), "-map", "0:a:0?",
                               "-af", f"ebur128=peak=true,silencedetect=n={som['silencio_db']}dB:"
                               f"d={som['silencio_max_s']}", "-f", "null", "-"], timeout=300).stderr
    return ler_medidas(saida)


def _audio(entrega: Path, novos: list[str], rascunho: Path | None) -> list[str]:
    import sonoplasta

    linhas = []
    for nome in novos:
        caminho = Path(nome)
        if caminho.suffix.lower() not in VIDEOS or not caminho.stem.endswith(sonoplasta.SUFIXO):
            continue
        try:
            medidas = medir_audio(Path(entrega) / nome)
        except Exception:  # noqa: BLE001 - sem ffmpeg, sem medição
            continue
        sem_som = caminho.stem[:-len(sonoplasta.SUFIXO)] + caminho.suffix
        medidas["vinheta_em"] = sonoplasta.vinheta_em(rascunho, sem_som)
        if (avisos := motor.audio(medidas)):
            linhas.append(f"áudio de {caminho.name}: {'; '.join(avisos)}")
    return linhas


# ---------------------------------------------------------------- vídeo, fotos e legenda

def _json(arquivo: Path) -> dict:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def specs_de_video(rascunho: Path | None) -> list[tuple[str, dict]]:
    """Os motion*.json da raiz do rascunho (o do vídeo final e o de outras versões)."""
    if not rascunho or not Path(rascunho).is_dir():
        return []
    return [(a.name, spec) for a in sorted(Path(rascunho).glob("motion*.json")) if (spec := _json(a)).get("cenas")]


def fotos_usadas(rascunho: Path | None) -> list[str]:
    """Nomes das fotos e vídeos de origem: campos do motion.json e do molde.json e os arquivos de acervo/."""
    if not rascunho or not Path(rascunho).is_dir():
        return []
    nomes = []
    for _, spec in specs_de_video(rascunho):
        nomes += [str(c.get("video") or c.get("foto") or "") for c in spec["cenas"] if isinstance(c, dict)]
    for slide in _json(Path(rascunho) / "molde.json").get("slides") or []:
        if isinstance(slide, dict) and slide.get("foto"):
            nomes.append(str(slide["foto"]))
    acervo = Path(rascunho) / "acervo"
    if acervo.is_dir():
        nomes += [a.relative_to(rascunho).as_posix() for a in acervo.rglob("*") if a.is_file()]
    return [n for n in nomes if n and not any(p in IGNORAR for p in Path(n).parts)]


def _legendas(entrega: Path, novos: list[str], empresa: str) -> list[str]:
    import conferencia_texto

    linhas = []
    for nome in novos:
        if not conferencia_texto._e_legenda(nome):
            continue
        texto = conferencia_texto.texto_do_docx(Path(entrega) / nome)
        if texto.strip() and (avisos := motor.formato_legenda(texto, empresa) + motor.grafia(texto)):
            linhas.append(f"{Path(nome).name}: {'; '.join(avisos[:5])}")
    return linhas


def conferir(entrega: Path, novos: list[str], rascunho: Path | None, empresa: str, pedido: str = "",
             hoje: date | None = None) -> str:
    """Linha para o resumo da entrega ("" se nada a apontar). Só avisa: nada é barrado nem refeito aqui."""
    linhas = []
    etapas = [lambda: _legendas(entrega, novos, empresa)]
    if any(Path(n).suffix.lower() in VIDEOS for n in novos):
        etapas.append(lambda: [f"{nome}: {'; '.join(avisos[:6])}" for nome, spec in specs_de_video(rascunho)
                               if (avisos := motor.ritmo_do_video(spec, empresa, pedido))])
        etapas.append(lambda: _audio(entrega, novos, rascunho))
    etapas.append(lambda: motor.fotos(fotos_usadas(rascunho), empresa, (hoje or date.today()).year))
    for etapa in etapas:
        try:
            linhas += etapa()
        except Exception:  # noqa: BLE001 - a conferência nunca derruba a entrega
            continue
    if not linhas:
        return ""
    return ("⚠ Conferência da entrega (só aviso, confira antes de publicar): " + " | ".join(linhas[:MAX_LINHAS])
            + (f" (e mais {len(linhas) - MAX_LINHAS})" if len(linhas) > MAX_LINHAS else "") + ".")
