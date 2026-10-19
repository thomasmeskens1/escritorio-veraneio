"""Trabalhador do plano Max: produz os arquivos (PNG/MP4/PDF) pedidos pelo dono no Escritório Veraneio.

Roda no PC do dono. A cada poucos segundos pede ao backend a próxima produção, cria a pasta da
requisição no Drive sincronizado, executa o Claude Code (login Max) nessa pasta e devolve o resultado,
que aparece no chat e no registro como "pedido concluído".

Uso: python scripts/max/trabalhador_max.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = os.getenv("ESCRITORIO_URL", "http://localhost:8000")
ARQUIVO_TOKEN = RAIZ / "backend" / "dados" / "operador.token"
DRIVE = Path(os.getenv("ESCRITORIO_DRIVE", r"G:\Drives compartilhados\(NOVO) CASA VERANEIO\ESCRITÓRIO VERANEIO"))
RENDERIZADOR = Path(__file__).with_name("renderizar_png.py").as_posix()
INTERVALO = 10                # segundos entre consultas à fila
TEMPO_LIMITE = 30 * 60        # por produção
EXTENSOES_ENTREGA = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"}

INSTRUCOES = {
    "criador_imagens": (
        "Você é o Criador de Imagens. Entregue as artes em PNG. Monte cada arte como um arquivo .html "
        "(layout, tipografia, cores, imagens locais) e renderize com:\n"
        f'  python "{RENDERIZADOR}" arte.html arte.png 1080x1350\n'
        "Use 1080x1350 para feed e 1080x1920 para stories/reels, salvo pedido diferente."
    ),
    "editor_video": (
        "Você é o Editor de Vídeo. Entregue o vídeo final em MP4 (H.264 + AAC), vertical 1080x1920 "
        "salvo pedido diferente, usando ffmpeg/ffprobe (já disponíveis no PATH). Para telas de texto, "
        f'monte PNGs com: python "{RENDERIZADOR}" tela.html tela.png 1080x1920 e use-os no ffmpeg.'
    ),
}


def claude_exe() -> str:
    """O executável nativo, e não o claude.cmd: o cmd.exe quebra argumentos com quebras de linha e parênteses."""
    pastas_npm = [Path(os.environ.get("APPDATA", "")) / "npm"]
    if (encontrado := shutil.which("claude")):
        pastas_npm.insert(0, Path(encontrado).parent)
    for pasta in pastas_npm:
        nativo = pasta / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if nativo.exists():
            return str(nativo)
    return encontrado or "claude"


def ffmpeg_dir() -> str | None:
    encontrado = shutil.which("ffmpeg")
    if encontrado:
        return str(Path(encontrado).parent)
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    achados = sorted(pacotes.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
    return str(achados[-1].parent) if achados else None


def chamar(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    token = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"{BACKEND}{caminho}", data=dados, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resposta:
        return json.load(resposta)


def nome_pasta(producao: dict) -> str:
    """Ex.: 2026-10-19 - 42 - Reels piscina verão"""
    resumo = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", producao["texto"]).strip()
    resumo = re.sub(r"\s+", " ", resumo)[:50].rstrip(" .")
    return f"{producao['criada_em'][:10]} - {producao['tarefa_id']} - {resumo}"


def montar_prompt(producao: dict, pasta: Path) -> str:
    historico = "\n".join(f"- Usuário: {h['texto'][:300]}\n  Resposta: {(h['resposta'] or '')[:400]}"
                          for h in producao.get("historico") or [])
    return "\n\n".join(filter(None, [
        INSTRUCOES.get(producao["agente"], "Entregue o resultado como arquivo."),
        "Contexto: Escritório Veraneio, equipe de marketing da Casa Veraneio. Responda em português do Brasil.",
        f"Conversa recente:\n{historico}" if historico else "",
        f"Pedido: {producao['texto']}",
        f"Trabalhe SOMENTE dentro da pasta atual ({pasta}) e salve nela os arquivos finais. "
        "O acervo de fotos e vídeos dos produtos ainda não está disponível: use apenas arquivos citados "
        "no pedido ou construa a peça com tipografia, cores e formas.",
        "Ao terminar, responda com um resumo curto (até 5 linhas) do que foi entregue.",
    ]))


def guardar_rascunhos(pasta: Path) -> None:
    """Deixa só as entregas na pasta da requisição; HTML e outros arquivos de trabalho vão para _trabalho."""
    rascunhos = [a for a in pasta.iterdir() if a.is_file() and a.suffix.lower() not in EXTENSOES_ENTREGA]
    if rascunhos:
        destino = pasta / "_trabalho"
        destino.mkdir(exist_ok=True)
        for arquivo in rascunhos:
            arquivo.replace(destino / arquivo.name)


def produzir(producao: dict) -> None:
    pasta = DRIVE / producao["pasta_andar"] / nome_pasta(producao)
    pasta.mkdir(parents=True, exist_ok=True)
    relativa = f"{producao['pasta_andar']}/{pasta.name}"
    print(f"[{datetime.now():%H:%M:%S}] Produção #{producao['tarefa_id']} ({producao['agente']}) -> {relativa}")

    ambiente = dict(os.environ)
    if (dir_ffmpeg := ffmpeg_dir()):
        ambiente["PATH"] = dir_ffmpeg + os.pathsep + ambiente.get("PATH", "")
    comando = [claude_exe(), "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--max-turns", "40",
               "--allowedTools", "Read,Write,Edit,Glob,Bash(ffmpeg:*),Bash(ffprobe:*),Bash(python:*)"]
    try:
        # O pedido vai pela entrada padrão (texto longo, com quebras de linha).
        processo = subprocess.run(comando, input=montar_prompt(producao, pasta), cwd=pasta, env=ambiente,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=TEMPO_LIMITE)
        saida = json.loads(processo.stdout or "{}")
        if processo.returncode != 0 or saida.get("is_error"):
            raise RuntimeError(saida.get("result") or processo.stderr[-500:] or "Claude Code terminou com erro.")
        arquivos = sorted(a.name for a in pasta.iterdir() if a.suffix.lower() in EXTENSOES_ENTREGA)
        if not arquivos:
            raise RuntimeError("Nenhum arquivo PNG/MP4/PDF foi gerado.")
        guardar_rascunhos(pasta)
        chamar("POST", f"/api/producao/{producao['tarefa_id']}/concluir",
               {"resumo": saida.get("result", ""), "pasta": relativa, "arquivos": arquivos})
        print(f"   concluída: {', '.join(arquivos)}")
    except Exception as erro:
        print(f"   falhou: {erro}")
        chamar("POST", f"/api/producao/{producao['tarefa_id']}/falhar", {"erro": str(erro)})


def main() -> None:
    if not DRIVE.exists():
        sys.exit(f"Pasta do Drive não encontrada: {DRIVE}")
    print(f"Trabalhador Max ativo. Fila: {BACKEND} | Drive: {DRIVE}")
    while True:
        try:
            producao = chamar("GET", "/api/producao/proxima")["producao"]
        except Exception as erro:  # backend fora do ar: tenta de novo
            print(f"[{datetime.now():%H:%M:%S}] Backend indisponível ({erro}); nova tentativa em {INTERVALO * 3} s.")
            time.sleep(INTERVALO * 3)
            continue
        if producao:
            produzir(producao)
        else:
            time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
