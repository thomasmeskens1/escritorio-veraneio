"""Trabalhador do plano Max: atende a fila do Escritório Veraneio no PC do dono.

Roda no PC do dono. A cada poucos segundos pede ao backend o próximo item:
  - produção (PNG/MP4/PDF): cria a pasta da requisição no Drive, roda o Claude Code (login Max) nela e
    devolve o resultado, que aparece no chat e no registro como "pedido concluído";
  - trabalho "anexo": o Claude Code lê a imagem/PDF enviado no chat e devolve a descrição;
  - trabalho "site": o Chrome renderiza www.casaveraneio.com e o texto vai ao Cérebro (site_casaveraneio.py).
Na subida e a cada 6 h, cataloga o acervo de fotos/vídeos dos lodges (catalogo_lodges.py) e lê a planilha
Info Lodges (planilha_lodges.py) para o Cérebro.

Uso: pythonw scripts/max/trabalhador_max.py  (sem janela; log em backend/dados/trabalhador_max.log)
"""

import os
import re
import shutil
import socket
import sys
import threading
import time
import traceback
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
PASTA_REFERENCIAS = "referencias"  # referências do item do Monday (baixadas a cada produção)
PASTA_FINAL = "entrega"       # só o que o Claude Code grava aqui vai para o Drive
RASCUNHOS = comum.DADOS / "producoes"  # rascunho local de cada peça (fora do Drive; base dos ajustes)
DIAS_RASCUNHO = 60
PASTA_DIRETRIZES = comum.DADOS / "conhecimento"   # manuais da Casa Veraneio (fora do git)
DIRETRIZES = {"criador_imagens": ("00", "01", "08", "09", "10", "04", "03"),
              "editor_video": ("00", "01", "08", "09", "10", "06", "05")}

INSTRUCOES = {
    "criador_imagens": (
        "Você é o Criador de Imagens. Entregue as artes em PNG. Monte cada arte como um arquivo .html "
        "(layout, tipografia, cores, imagens locais) e renderize com:\n"
        f'  python "{RENDERIZADOR}" arte.html arte.png 1080x1350\n'
        "Use 1080x1440 (3:4) para feed e 1080x1920 para stories/reels, salvo pedido diferente; respeite as zonas "
        "mortas do manual 08."
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
    """Título do projeto/pedido, ex.: "Post Réveillon Lodge 1"."""
    titulo = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", producao.get("titulo") or producao["texto"])
    return re.sub(r"\s+", " ", titulo).strip(" .")[:60] or f"Produção {producao['tarefa_id']}"


def pasta_de_entrega(producao: dict) -> Path:
    """Pasta no Drive. Ajuste: a mesma da peça ajustada. Nome repetido: "Título (2)"."""
    if producao.get("base"):
        return DRIVE / producao["base"]["pasta"]
    raiz, nome = DRIVE / producao["pasta_andar"], nome_pasta(producao)
    pasta, n = raiz / nome, 2
    while pasta.exists():
        pasta, n = raiz / f"{nome} ({n})", n + 1
    return pasta


def pasta_de_rascunho(producao: dict) -> Path:
    """Rascunho local da peça (HTML, cópias de fotos, cenas), fora do Drive; o ajuste reaproveita o da peça base."""
    base = (producao.get("base") or {}).get("tarefa_id") or producao["tarefa_id"]
    pasta = RASCUNHOS / str(base)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def entregaveis(pasta: Path) -> dict[str, float]:
    """Arquivos finais: só os da subpasta entrega/ do rascunho (raiz dela + EDITÁVEL/), com a data de modificação.
    Imagens intermediárias (fundos, recortes, logos) ficam fora dela e não vão para o Drive."""
    final = pasta / PASTA_FINAL
    if not final.is_dir():
        return {}
    achados = [a for a in final.iterdir() if a.is_file() and a.suffix.lower() in EXTENSOES_ENTREGA]
    if (final / "EDITÁVEL").is_dir():
        achados += [a for a in (final / "EDITÁVEL").rglob("*") if a.is_file()]
    return {a.relative_to(final).as_posix(): a.stat().st_mtime for a in achados}


def limpar_rascunhos() -> None:
    """Rascunhos parados há mais de DIAS_RASCUNHO dias saem do PC (a entrega continua no Drive)."""
    limite = time.time() - DIAS_RASCUNHO * 86400
    for pasta in RASCUNHOS.glob("*") if RASCUNHOS.is_dir() else []:
        if pasta.is_dir() and pasta.stat().st_mtime < limite:
            shutil.rmtree(pasta, ignore_errors=True)


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


def baixar_referencias(producao: dict, pasta: Path) -> list[str]:
    """Referências do item do Monday (arquivos enviados) para <pasta>/referencias; links externos só são citados."""
    baixadas = []
    for ref in producao.get("referencias") or []:
        if "monday" not in ref["url"] and "amazonaws" not in ref["url"]:
            baixadas.append(f"{ref['nome']} (link: {ref['url']})")
            continue
        destino = pasta / PASTA_REFERENCIAS
        destino.mkdir(exist_ok=True)
        nome = re.sub(r'[<>:"/\\|?*]', "_", ref["nome"])
        try:
            comum.baixar(ref["url"], destino / nome)
            baixadas.append(f"{PASTA_REFERENCIAS}/{nome}")
        except Exception as erro:
            log(f"   referência não baixada ({nome}): {erro}")
    return baixadas


def enviar_criativos(producao: dict, entrega: Path, arquivos: list[str]) -> None:
    """Item do Monday: cada arquivo final vai para a coluna Criativos (pelo backend, que tem o token)."""
    for nome in arquivos:
        try:
            comum.enviar_arquivo(f"/api/integracoes/monday/criativos/{producao['tarefa_id']}", entrega / nome)
        except Exception as erro:
            log(f"   criativo não enviado ao Monday ({nome}): {erro}")


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
            f"para a subpasta {PASTA_ACERVO}/ da pasta atual e trabalhe na cópia (se já houver cópia de uma versão "
            "anterior, reaproveite). Nunca grave, mova, renomeie ou "
            "apague nada no acervo. Arquivos grandes: copie um por vez, só os que vai usar.")


def instrucao_versao(producao: dict, versao: int) -> str:
    if not producao.get("base"):
        return ""
    return (f"Este pedido é um AJUSTE (versão {versao}) da peça #{producao['base']['tarefa_id']}. Nesta pasta estão "
            "os arquivos de trabalho da versão anterior (HTML, editável, fotos copiadas, cenas): reaproveite-os e "
            "aplique SOMENTE o ajuste pedido, sem refazer o resto. Gere de novo APENAS os arquivos finais que o ajuste "
            "muda: ajuste na arte = nova arte (e o editável dela); NÃO gere legenda nova se o pedido não for sobre a "
            f"legenda. Os novos finais vão para {PASTA_FINAL}/ com o sufixo _v{versao} (ex.: arte_v{versao}.png, "
            f"EDITÁVEL/<peça>_v{versao}_editavel.pptx); não apague as versões anteriores.")


def montar_prompt(producao: dict, pasta: Path, anexos: list[str] | None = None, versao: int = 1,
                  referencias: list[str] | None = None) -> str:
    historico = "\n".join(f"- Usuário: {h['texto'][:300]}\n  Resposta: {(h['resposta'] or '')[:400]}"
                          for h in producao.get("historico") or [])
    lista_anexos = "\n".join(f"  - {PASTA_ANEXOS}/{nome}" for nome in anexos or [])
    lista_referencias = "\n".join(f"  - {r}" for r in referencias or [])
    return "\n\n".join(filter(None, [
        INSTRUCOES.get(producao["agente"], "Entregue o resultado como arquivo."),
        "Contexto: Escritório Veraneio, equipe de marketing da Casa Veraneio. Responda em português do Brasil.",
        f"Conversa recente:\n{historico}" if historico else "",
        f"Pedido: {producao['texto']}",
        instrucao_versao(producao, versao),
        (f"Referências do item no Monday (ponto de partida, não regra absoluta):\n{lista_referencias}\n"
         "Abra com Read as que estão nesta pasta e use-as como inspiração de estilo, enquadramento ou texto.")
        if lista_referencias else "",
        (f"O usuário enviou estes arquivos junto com o pedido (copiados na subpasta {PASTA_ANEXOS}/):\n"
         f"{lista_anexos}\nAbra-os com Read e USE-OS na peça (fotos como imagens do layout, PDFs como fonte "
         "de textos e dados), conforme o pedido. Não altere os originais.") if lista_anexos else "",
        diretrizes(producao["agente"]),
        regras_acervo(),
        f"Grave SOMENTE dentro da pasta atual ({pasta}), que é o rascunho desta peça. Arquivos de trabalho (HTML, "
        "fundos, recortes, logos, cópias de fotos, cenas brutas) ficam FORA da subpasta "
        f"{PASTA_FINAL}/. Só o que estiver em {PASTA_FINAL}/ vai para o Drive (não use \"MARKETING > THOMAS\" citado "
        f"nas diretrizes). Em {PASTA_FINAL}/ entregue: (1) a arte final (PNG, MP4 ou PDF); (2) o editável em "
        f"{PASTA_FINAL}/EDITÁVEL/, gerado com python-pptx conforme as diretrizes (em vídeo, também "
        f"{PASTA_FINAL}/EDITÁVEL/CENAS/ e manifest.json); (3) a legenda, quando a peça tiver (stories não têm), em "
        "\"Legenda - <peça>.docx\", gerada com python-docx, no lugar do Google Doc. Não use Higgsfield nem outra IA "
        "de imagem.",
        "Ao terminar, responda com um resumo curto (até 5 linhas) do que foi entregue.",
    ]))


def comando_producao() -> list[str]:
    return [comum.claude_exe(), "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
            "--max-turns", "40", "--allowedTools", "Read,Write,Edit,Glob,Bash(ffmpeg:*),Bash(ffprobe:*),Bash(python:*)"]


def produzir(producao: dict) -> None:
    entrega = pasta_de_entrega(producao)
    relativa = entrega.relative_to(DRIVE).as_posix()
    rascunho = pasta_de_rascunho(producao)
    versao_arquivo = rascunho / ".versao"
    versao = int(versao_arquivo.read_text()) + 1 if producao.get("base") and versao_arquivo.exists() else 1
    log(f"Produção #{producao['tarefa_id']} ({producao['agente']}) v{versao} -> {relativa}")

    ambiente = dict(os.environ)
    if (dir_ffmpeg := ffmpeg_dir()):
        ambiente["PATH"] = dir_ffmpeg + os.pathsep + ambiente.get("PATH", "")
    try:
        anexos = copiar_anexos(producao, rascunho)
        referencias = baixar_referencias(producao, rascunho)
        antes = entregaveis(rascunho)
        # O pedido vai pela entrada padrão (texto longo, com quebras de linha).
        resumo = comum.rodar_claude(comando_producao(), montar_prompt(producao, rascunho, anexos, versao, referencias),
                                    rascunho, TEMPO_LIMITE, ambiente)
        # Só os finais novos ou alterados vão para o Drive (sem pasta de trabalho na entrega).
        novos = sorted(nome for nome, mtime in entregaveis(rascunho).items() if antes.get(nome) != mtime)
        if not any(Path(n).suffix.lower() in EXTENSOES_ARTE for n in novos):
            raise RuntimeError("Nenhum arquivo PNG/MP4/PDF foi gerado.")
        for nome in novos:
            (entrega / nome).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rascunho / PASTA_FINAL / nome, entrega / nome)
        versao_arquivo.write_text(str(versao))
        arquivos = [n for n in novos if "/" not in n or n.lower().endswith(".pptx")]  # sem listar cada cena
        if producao.get("monday"):  # antes de concluir: o item já recebe os criativos quando vira "Revisão"
            enviar_criativos(producao, entrega, arquivos)
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


PORTA_TRAVA = 47831  # só um trabalhador por PC: o segundo a abrir esta porta local encerra


def instancia_unica() -> socket.socket | None:
    trava = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        trava.bind(("127.0.0.1", PORTA_TRAVA))
        return trava
    except OSError:
        trava.close()
        return None


def main() -> None:
    trava = instancia_unica()  # mantida aberta enquanto o trabalhador roda
    if not trava:
        log("Já existe um Trabalhador Max rodando neste PC; esta cópia foi encerrada.")
        return
    if not DRIVE.exists():
        log(f"Pasta do Drive não encontrada: {DRIVE}")
        sys.exit(1)
    log(f"Trabalhador Max ativo. Fila: {comum.BACKEND} | Drive: {DRIVE} | log: {comum.ARQUIVO_LOG}")
    limpar_rascunhos()
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
    try:
        main()
    except Exception:  # sem janela (pythonw), o erro só fica no log
        log("Trabalhador Max parou por um erro inesperado:\n" + traceback.format_exc())
        raise
