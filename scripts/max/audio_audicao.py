"""Folha de audição da biblioteca de músicas (Onda 1 de novembro, 11/11/2026; sonoplasta-01, mínimo do crítico).

Um MP3 por marca, com um trecho de cada faixa já gerada, numerado por bipes (1 bipe = faixa 1, 2 bipes = faixa
2...), e um .txt que diz o número, o arquivo, o estilo e o minuto de cada trecho. O Thomas ouve uma vez e responde
"aprovo 1, 3, 4"; o status vai para o catalogo.json do Drive (à mão ou pelo trabalhador). Só ffmpeg no host, sem
janela e sem gerar música nova (a geração está em standby desde 06/11/2026). As três marcas nunca se misturam.

Uso: python audio_audicao.py <pasta de saída> [--inicio 4] [--trecho 15]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comum  # noqa: E402
import sonoplasta  # noqa: E402

TAXA = 48000
BIPE_S, VAO_BIPE_S, ANTES_DO_TRECHO_S, DEPOIS_DO_TRECHO_S = 0.12, 0.18, 0.6, 1.4
LUFS_AUDICAO = -16  # todas no mesmo volume, para comparar só a música


def _ffmpeg(args: list, timeout: int = 300) -> None:
    feito = subprocess.run([sonoplasta._ffmpeg(), "-y", "-loglevel", "error", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=comum.SEM_JANELA, timeout=timeout)
    if feito.returncode != 0:
        raise RuntimeError(f"ffmpeg: {feito.stderr.strip()[-300:]}")


def _wav(saida: Path, filtro: str, segundos: float) -> Path:
    _ffmpeg(["-f", "lavfi", "-t", f"{segundos:.3f}", "-i", filtro, "-ar", str(TAXA), "-ac", "2", "-c:a", "pcm_s16le",
             str(saida)])
    return saida


def _trecho(faixa: Path, saida: Path, inicio: float, trecho: float) -> Path:
    _ffmpeg(["-ss", f"{inicio:.3f}", "-t", f"{trecho:.3f}", "-i", str(faixa), "-af",
             f"afade=t=in:d=0.5,afade=t=out:st={max(0.0, trecho - 1.2):.3f}:d=1.2,loudnorm=I={LUFS_AUDICAO}:TP=-1.5,"
             f"aresample={TAXA}", "-ac", "2", "-c:a", "pcm_s16le", str(saida)])
    return saida


def _minuto(segundos: float) -> str:
    return f"{int(segundos) // 60}:{int(segundos) % 60:02d}"


def folha_da_marca(empresa: str, itens: list[dict], destino: Path, inicio: float = 4.0, trecho: float = 15.0) -> dict:
    """Grava <destino>/AUDICAO - <MARCA>.mp3 com as faixas da marca; devolve {"mp3", "faixas": [...]}."""
    faixas = [f for f in itens if f.get("marca") == sonoplasta.MARCAS[empresa]]
    marca = sonoplasta.MARCAS[empresa]
    lista, registro, tempo = [], [], 0.0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bipe = _wav(tmp / "bipe.wav", f"sine=f=880:r={TAXA},afade=t=out:st={BIPE_S - 0.03}:d=0.03,apad", BIPE_S + VAO_BIPE_S)
        antes = _wav(tmp / "antes.wav", f"anullsrc=r={TAXA}:cl=stereo", ANTES_DO_TRECHO_S)
        depois = _wav(tmp / "depois.wav", f"anullsrc=r={TAXA}:cl=stereo", DEPOIS_DO_TRECHO_S)
        for numero, faixa in enumerate(faixas, 1):
            arquivo = sonoplasta.arquivo_da_faixa(faixa)
            if not arquivo:
                registro.append({"numero": numero, "arquivo": faixa.get("arquivo"), "erro": "arquivo não encontrado"})
                continue
            pedaco = _trecho(arquivo, tmp / f"faixa_{numero}.wav", inicio, trecho)
            lista += [bipe] * numero + [antes]
            tempo += numero * (BIPE_S + VAO_BIPE_S) + ANTES_DO_TRECHO_S
            registro.append({"numero": numero, "arquivo": faixa.get("arquivo"), "estilo": faixa.get("estilo"),
                             "bpm": faixa.get("bpm"), "clima": faixa.get("clima"), "status": faixa.get("status"),
                             "no_mp3": _minuto(tempo)})
            tempo += sonoplasta.duracao(pedaco) + DEPOIS_DO_TRECHO_S
            lista += [pedaco, depois]
        if not lista:
            return {"mp3": None, "faixas": registro}
        concat = tmp / "lista.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in lista), encoding="utf-8")
        destino.mkdir(parents=True, exist_ok=True)
        mp3 = destino / f"AUDICAO - {marca}.mp3"
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)],
                timeout=600)
    return {"mp3": mp3, "faixas": registro}


def texto_do_indice(resultados: dict[str, dict], inicio: float, trecho: float) -> str:
    linhas = ["FOLHA DE AUDIÇÃO DA BIBLIOTECA DE MÚSICAS (11/11/2026)", "",
              f"Cada MP3 tem um trecho de {trecho:.0f} s de cada faixa (a partir de {inicio:.0f} s), todas no mesmo "
              "volume. Antes de cada trecho tocam bipes: 1 bipe = faixa 1, 2 bipes = faixa 2, e assim por diante.",
              "Para aprovar, responda por marca, por exemplo: \"Casa Veraneio: aprovo 1, 3, 4; reprovo 2\". O que não "
              "for citado continua \"para aprovação\". As três marcas nunca se misturam.", ""]
    for empresa, resultado in resultados.items():
        marca = sonoplasta.MARCAS[empresa]
        linhas.append(f"== {marca}  ->  {resultado['mp3'].name if resultado['mp3'] else '(sem MP3)'}")
        for f in resultado["faixas"]:
            if f.get("erro"):
                linhas.append(f"  {f['numero']}. {f['arquivo']}: {f['erro']}")
                continue
            linhas.append(f"  {f['numero']}. {Path(f['arquivo']).name}  |  {f['estilo']}, {f['bpm']} BPM, "
                          f"{f['clima']}  |  no MP3 em {f['no_mp3']}  |  hoje: {f['status']}")
        linhas.append("")
    return "\n".join(linhas)


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("saida", type=Path)
    args.add_argument("--inicio", type=float, default=4.0, help="segundo da faixa em que o trecho começa")
    args.add_argument("--trecho", type=float, default=15.0, help="duração de cada trecho (s)")
    opcoes = args.parse_args()
    # O catálogo do Drive, só leitura (sem regravar o espelho nem mexer no status).
    itens = json.loads((sonoplasta.BIBLIOTECA / "catalogo.json").read_text(encoding="utf-8"))
    resultados = {e: folha_da_marca(e, itens, opcoes.saida, opcoes.inicio, opcoes.trecho) for e in sonoplasta.MARCAS}
    indice = opcoes.saida / "AUDICAO - qual numero e qual faixa.txt"
    indice.write_text(texto_do_indice(resultados, opcoes.inicio, opcoes.trecho), encoding="utf-8")
    print(indice)
    for resultado in resultados.values():
        print(resultado["mp3"])


if __name__ == "__main__":
    main()
