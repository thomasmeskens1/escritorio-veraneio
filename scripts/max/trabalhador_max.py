"""Trabalhador do plano Max: atende a fila do Escritório Veraneio no PC do dono.

Roda no PC do dono. A cada poucos segundos pede ao backend o próximo item:
  - produção (PNG/MP4/PDF): cria a pasta da requisição no Drive, roda o Claude Code (login Max) nela e
    devolve o resultado, que aparece no chat e no registro como "pedido concluído";
  - trabalho "anexo": o Claude Code lê a imagem/PDF enviado no chat e devolve a descrição;
  - trabalho "site": o Claude Code lê www.casaveraneio.com e ensina o Cérebro (trabalhos_max.py).
Na subida e a cada 6 h, cataloga o acervo de fotos/vídeos dos lodges para o Cérebro (catalogo_lodges.py).

Uso: python scripts/max/trabalhador_max.py
"""

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import catalogo_lodges
import comum
import trabalhos_max
from comum import DRIVE, log

RENDERIZADOR = Path(__file__).with_name("renderizar_png.py").as_posix()
INTERVALO = 10                # segundos entre consultas à fila
TEMPO_LIMITE = 30 * 60        # por produção
INTERVALO_CATALOGO = 6 * 3600
EXTENSOES_ENTREGA = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"}
PASTA_ANEXOS = "anexos"       # subpasta da requisição com os arquivos enviados no chat

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


def ffmpeg_dir() -> str | None:
    encontrado = shutil.which("ffmpeg")
    if encontrado:
        return str(Path(encontrado).parent)
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    achados = sorted(pacotes.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
    return str(achados[-1].parent) if achados else None


def nome_pasta(producao: dict) -> str:
    """Ex.: 2026-10-19 - 42 - Reels piscina verão"""
    resumo = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", producao["texto"]).strip()
    resumo = re.sub(r"\s+", " ", resumo)[:50].rstrip(" .")
    return f"{producao['criada_em'][:10]} - {producao['tarefa_id']} - {resumo}"


def copiar_anexos(producao: dict, pasta: Path) -> list[str]:
    """Copia os anexos do chat (backend/dados/anexos) para <pasta>/anexos; devolve os nomes copiados."""
    copiados = []
    for relativo in producao.get("anexos") or []:
        try:
            origem = trabalhos_max.arquivo_do_anexo({"arquivo": relativo})
        except RuntimeError as erro:
            log(f"   anexo ignorado: {erro}")
            continue
        destino = pasta / PASTA_ANEXOS
        destino.mkdir(exist_ok=True)
        shutil.copy2(origem, destino / origem.name)
        copiados.append(origem.name)
    return copiados


def montar_prompt(producao: dict, pasta: Path, anexos: list[str] | None = None) -> str:
    historico = "\n".join(f"- Usuário: {h['texto'][:300]}\n  Resposta: {(h['resposta'] or '')[:400]}"
                          for h in producao.get("historico") or [])
    lista_anexos = "\n".join(f"  - {PASTA_ANEXOS}/{nome}" for nome in anexos or [])
    return "\n\n".join(filter(None, [
        INSTRUCOES.get(producao["agente"], "Entregue o resultado como arquivo."),
        "Contexto: Escritório Veraneio, equipe de marketing da Casa Veraneio. Responda em português do Brasil.",
        f"Conversa recente:\n{historico}" if historico else "",
        f"Pedido: {producao['texto']}",
        (f"O usuário enviou estes arquivos junto com o pedido (copiados na subpasta {PASTA_ANEXOS}/):\n"
         f"{lista_anexos}\nAbra-os com Read e USE-OS na peça (fotos como imagens do layout, PDFs como fonte "
         "de textos e dados), conforme o pedido. Não altere os originais.") if lista_anexos else "",
        f"Trabalhe SOMENTE dentro da pasta atual ({pasta}) e salve nela os arquivos finais. "
        "O acervo de fotos e vídeos dos produtos ainda não está disponível: use apenas arquivos citados "
        "no pedido ou enviados como anexo, ou construa a peça com tipografia, cores e formas.",
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


def comando_producao() -> list[str]:
    return [comum.claude_exe(), "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
            "--max-turns", "40", "--allowedTools", "Read,Write,Edit,Glob,Bash(ffmpeg:*),Bash(ffprobe:*),Bash(python:*)"]


def produzir(producao: dict) -> None:
    pasta = DRIVE / producao["pasta_andar"] / nome_pasta(producao)
    pasta.mkdir(parents=True, exist_ok=True)
    relativa = f"{producao['pasta_andar']}/{pasta.name}"
    log(f"Produção #{producao['tarefa_id']} ({producao['agente']}) -> {relativa}")

    ambiente = dict(os.environ)
    if (dir_ffmpeg := ffmpeg_dir()):
        ambiente["PATH"] = dir_ffmpeg + os.pathsep + ambiente.get("PATH", "")
    try:
        anexos = copiar_anexos(producao, pasta)
        # O pedido vai pela entrada padrão (texto longo, com quebras de linha).
        resumo = comum.rodar_claude(comando_producao(), montar_prompt(producao, pasta, anexos), pasta,
                                    TEMPO_LIMITE, ambiente)
        arquivos = sorted(a.name for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in EXTENSOES_ENTREGA)
        if not arquivos:
            raise RuntimeError("Nenhum arquivo PNG/MP4/PDF foi gerado.")
        guardar_rascunhos(pasta)
        comum.chamar("POST", f"/api/producao/{producao['tarefa_id']}/concluir",
                     {"resumo": resumo, "pasta": relativa, "arquivos": arquivos})
        log(f"   concluída: {', '.join(arquivos)}")
    except Exception as erro:
        log(f"   falhou: {erro}")
        try:
            comum.chamar("POST", f"/api/producao/{producao['tarefa_id']}/falhar", {"erro": str(erro)})
        except Exception as erro_api:
            log(f"   não foi possível avisar a falha ao backend: {erro_api}")


_catalogo_rodando = threading.Lock()


def catalogo_em_segundo_plano() -> None:
    """O acervo é grande: cataloga numa thread para não segurar a fila."""
    if not _catalogo_rodando.acquire(blocking=False):
        return

    def rodar():
        try:
            catalogo_lodges.rodar()
        finally:
            _catalogo_rodando.release()

    threading.Thread(target=rodar, name="catalogo-lodges", daemon=True).start()


def main() -> None:
    if not DRIVE.exists():
        sys.exit(f"Pasta do Drive não encontrada: {DRIVE}")
    log(f"Trabalhador Max ativo. Fila: {comum.BACKEND} | Drive: {DRIVE}")
    proximo_catalogo = 0.0
    while True:
        if time.monotonic() >= proximo_catalogo:
            catalogo_em_segundo_plano()
            proximo_catalogo = time.monotonic() + INTERVALO_CATALOGO
        try:
            item = comum.chamar("GET", "/api/producao/proxima")
        except Exception as erro:  # backend fora do ar: tenta de novo
            log(f"Backend indisponível ({erro}); nova tentativa em {INTERVALO * 3} s.")
            time.sleep(INTERVALO * 3)
            continue
        if item.get("producao"):
            produzir(item["producao"])
        elif item.get("trabalho"):
            trabalhos_max.executar(item["trabalho"])
        else:
            time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
