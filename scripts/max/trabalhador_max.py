"""Trabalhador do plano Max: atende a fila do Escritório Veraneio no PC do dono.

Roda no PC do dono. A cada poucos segundos pede ao backend o próximo item:
  - produção (PNG/MP4/PDF): cria a pasta da requisição no Drive, roda o Claude Code (login Max) nela e
    devolve o resultado, que aparece no chat e no registro como "pedido concluído";
  - trabalho "anexo": o Claude Code lê a imagem/PDF enviado no chat e devolve a descrição;
  - trabalho "site": o Chrome renderiza www.casaveraneio.com e o texto vai ao Cérebro (site_casaveraneio.py).
Na subida e a cada 6 h, cataloga o acervo de fotos/vídeos dos lodges (catalogo_lodges.py) e lê a planilha
Info Lodges (planilha_lodges.py) para o Cérebro.

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
import planilha_lodges
import trabalhos_max
from comum import DRIVE, log

RENDERIZADOR = Path(__file__).with_name("renderizar_png.py").as_posix()
INTERVALO = 10                # segundos entre consultas à fila
TEMPO_LIMITE = 30 * 60        # por produção
INTERVALO_CATALOGO = 6 * 3600
EXTENSOES_ARTE = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"}
EXTENSOES_ENTREGA = EXTENSOES_ARTE | {".docx"}  # + legenda; o editável fica em EDITÁVEL/
PASTA_ANEXOS = "anexos"       # subpasta da requisição com os arquivos enviados no chat
PASTA_ACERVO = "acervo"       # cópias das fotos/vídeos do acervo usadas na peça
PASTA_DIRETRIZES = comum.DADOS / "conhecimento"   # manuais da Casa Veraneio (fora do git)
DIRETRIZES = {"criador_imagens": ("00", "01", "04", "03"), "editor_video": ("00", "01", "06", "05")}

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


def diretrizes(agente: str) -> str:
    """Manuais da Casa Veraneio para o agente de produção (regras, marca e função)."""
    partes = []
    for prefixo in DIRETRIZES.get(agente, ()):
        achados = sorted(PASTA_DIRETRIZES.glob(f"{prefixo}_*.md"))
        if achados:
            partes.append(achados[0].read_text(encoding="utf-8").strip())
    return ("DIRETRIZES DA CASA VERANEIO (siga à risca):\n\n" + "\n\n".join(partes)) if partes else ""


def regras_acervo() -> str:
    return (f"Fotos e vídeos reais dos Lodges ficam no acervo, SOMENTE LEITURA: {comum.ACERVO} "
            "(só as pastas numeradas \"Lodges N - M\" > pasta do Lodge; o índice, para ler com python, está em "
            f"{comum.CEREBRO / 'catalogo_lodges.md'}). Para usar um arquivo, COPIE-o com python (shutil.copy2) "
            f"para a subpasta {PASTA_ACERVO}/ desta requisição e trabalhe na cópia. Nunca grave, mova, renomeie ou "
            "apague nada no acervo. Arquivos grandes: copie um por vez, só os que vai usar.")


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
        diretrizes(producao["agente"]),
        regras_acervo(),
        f"Grave SOMENTE dentro da pasta atual ({pasta}). A pasta de entrega é ESTA (não use \"MARKETING > "
        "THOMAS\" citado nas diretrizes). Entregue: (1) a arte final na raiz (PNG, MP4 ou PDF); (2) o editável "
        "em EDITÁVEL/, gerado com python-pptx conforme as diretrizes (em vídeo, também EDITÁVEL/CENAS/ e "
        "manifest.json); (3) a legenda, quando a peça tiver (stories não têm), em \"Legenda - <peça>.docx\" na "
        "raiz, gerada com python-docx, no lugar do Google Doc. Não use Higgsfield nem outra IA de imagem.",
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
        if not any(Path(a).suffix.lower() in EXTENSOES_ARTE for a in arquivos):
            raise RuntimeError("Nenhum arquivo PNG/MP4/PDF foi gerado.")
        if (pasta / "EDITÁVEL").is_dir():
            arquivos += [f"EDITÁVEL/{a.name}" for a in sorted((pasta / "EDITÁVEL").glob("*.pptx"))]
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
    """O acervo é grande: cataloga (e lê a planilha) numa thread para não segurar a fila."""
    if not _catalogo_rodando.acquire(blocking=False):
        return

    def rodar():
        try:
            catalogo_lodges.rodar()
            planilha_lodges.rodar()
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
