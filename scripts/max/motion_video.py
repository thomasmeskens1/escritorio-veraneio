"""ffmpeg do motion graphics (motion.py; Thomas, 04/11/2026): achar o ffmpeg, rodar sem janela com os quadros pelo
stdin, juntar cenas e tirar quadros de prévia. Na produção o ffmpeg roda pela caixa de areia (só "-" para o stdin:
"pipe:" seria barrado como protocolo)."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

FPS = 30
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def achar_ffmpeg(programa: str = "ffmpeg") -> str | None:
    """No PATH (produção) ou no pacote do WinGet (mesma busca do trabalhador_max.ffmpeg_dir)."""
    if (encontrado := shutil.which(programa)):
        return encontrado
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    achados = sorted(pacotes.glob(f"Gyan.FFmpeg*/*/bin/{programa}.exe")) if pacotes.is_dir() else []
    return str(achados[-1]) if achados else None


def duracao_do_video(video: Path) -> float:
    ffprobe = achar_ffmpeg("ffprobe") or "ffprobe"
    saida = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True, check=True, creationflags=SEM_JANELA).stdout
    return float(saida.strip())


def _rodar(comando: list[str], quadros=None) -> None:
    with tempfile.TemporaryFile() as erros:
        # Sem DEVNULL: abrir o "nul" do Windows para gravar é barrado pela caixa de areia (só grava na peça e no TEMP).
        processo = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=erros, stderr=erros,
                                    creationflags=SEM_JANELA)
        try:
            for dados in quadros or ():
                processo.stdin.write(dados)
        except (BrokenPipeError, OSError):
            pass  # o ffmpeg fechou antes (erro abaixo)
        finally:
            if processo.stdin:
                try:
                    processo.stdin.close()
                except OSError:
                    pass
        codigo = processo.wait()
        if codigo:
            erros.seek(0)
            raise RuntimeError(f"ffmpeg falhou ({codigo}): {erros.read().decode('utf-8', 'replace')[-800:]}")


CODIFICACAO = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "10M", "-bufsize", "20M",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]


def juntar_cenas(cenas: list[Path], saida: Path) -> Path:
    """Concatena as cenas já normalizadas (corte seco; fades e xfade ficam com o Max quando o roteiro pedir)."""
    entradas = [a for c in cenas for a in ("-i", str(c))]
    filtro = "".join(f"[{n}:v][{n}:a]" for n in range(len(cenas))) + f"concat=n={len(cenas)}:v=1:a=1[v][a]"
    saida.parent.mkdir(parents=True, exist_ok=True)
    _rodar([achar_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro,
            "-map", "[v]", "-map", "[a]", *CODIFICACAO, str(saida)])
    return saida


def previa(video: Path, tempos: list[float], pasta: Path, prefixo: str) -> list[Path]:
    """Quadros PNG do MP4 pronto, para conferir com Read (texto cortado, fonte, cor)."""
    pasta.mkdir(parents=True, exist_ok=True)
    gerados = []
    for t in tempos:
        png = pasta / f"{prefixo}_{t:05.2f}s.png"
        _rodar([achar_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
                "-frames:v", "1", str(png)])
        gerados.append(png)
    return gerados
