"""Peças comuns do trabalhador Max: pastas, chamadas ao backend, Claude Code e envio ao Cérebro."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND_DIR = RAIZ / "backend"
DADOS = BACKEND_DIR / "dados"
BACKEND = os.getenv("ESCRITORIO_URL", "http://localhost:8000")
ARQUIVO_TOKEN = DADOS / "operador.token"
DRIVE = Path(os.getenv("ESCRITORIO_DRIVE", r"G:\Drives compartilhados\(NOVO) CASA VERANEIO\ESCRITÓRIO VERANEIO"))
CEREBRO = DRIVE / "CÉREBRO"   # toda gravação de conhecimento vai para cá
# Acervo de fotos/vídeos dos lodges: SOMENTE LEITURA.
ACERVO = Path(os.getenv("ESCRITORIO_ACERVO",
                        r"G:\Drives compartilhados\(NOVO) CASA VERANEIO\LODGES\FOTOS E VIDEOS LODGES"))
# Pasta de trabalho do Claude Code FORA do repositório: lá ele não herda o .claude/ nem o CLAUDE.md do projeto
# (que liberam MCP) e as ferramentas de arquivo ficam presas a ela (--restricted).
TRABALHO = Path(os.getenv("ESCRITORIO_TRABALHO", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EscritorioVeraneio"))
# Isolamento de toda chamada ao Claude Code: sem configurações do usuário/projeto, sem nenhum servidor MCP.
ISOLAMENTO = ["--restricted", "--strict-mcp-config"]
# Variáveis de ambiente com cara de segredo não passam para o Claude Code (nem para o Python que ele roda).
_SEGREDO_NO_NOME = re.compile(r"KEY|TOKEN|SECRET|SENHA|PASSWORD|CREDENTIAL|MONDAY|OPENROUTER|JWT", re.IGNORECASE)
LOTE_CEREBRO = 10           # documentos por chamada de ingestão
TEMPO_INGESTAO = 300        # o Cérebro calcula os embeddings na hora
ARQUIVO_LOG = DADOS / "trabalhador_max.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # acima disso, o log atual vira .1 e começa outro
# Programas chamados pelo trabalhador (Claude Code, Chrome) abrem sem janela: ele roda invisível (pythonw).
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_trava_log = threading.Lock()


def log(texto: str) -> None:
    """No arquivo de log (o trabalhador roda sem janela) e, se houver terminal, na tela também."""
    linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {texto}"
    if sys.stdout:
        print(linha, flush=True)
    with _trava_log:
        try:
            if ARQUIVO_LOG.exists() and ARQUIVO_LOG.stat().st_size > LOG_MAX_BYTES:
                ARQUIVO_LOG.replace(ARQUIVO_LOG.with_suffix(".log.1"))
            with ARQUIVO_LOG.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha + "\n")
        except OSError:
            pass  # log nunca derruba o trabalhador


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


def chamar(metodo: str, caminho: str, corpo: dict | None = None, timeout: int = 60) -> dict:
    token = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"{BACKEND}{caminho}", data=dados, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resposta:
        return json.load(resposta)


def enviar_arquivo(caminho_api: str, arquivo: Path, timeout: int = 300) -> dict:
    """POST multipart (campo "arquivo") para o backend, com o token de operador."""
    token = ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    fronteira = os.urandom(16).hex()
    cabecalho = (f'--{fronteira}\r\nContent-Disposition: form-data; name="arquivo"; '
                 f'filename="{arquivo.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    corpo = cabecalho + arquivo.read_bytes() + f"\r\n--{fronteira}--\r\n".encode()
    req = urllib.request.Request(f"{BACKEND}{caminho_api}", data=corpo, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={fronteira}"})
    with urllib.request.urlopen(req, timeout=timeout) as resposta:
        return json.load(resposta)


def baixar(url: str, destino: Path, timeout: int = 300, max_bytes: int | None = None) -> None:
    """Baixa para `destino`; acima de `max_bytes` interrompe e apaga o parcial."""
    requisicao = urllib.request.Request(url, headers={"User-Agent": "EscritorioVeraneio/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta, destino.open("wb") as arquivo:
            lido = 0
            while bloco := resposta.read(1024 * 1024):
                lido += len(bloco)
                if max_bytes and lido > max_bytes:
                    raise ValueError(f"arquivo maior que {max_bytes // (1024 * 1024)} MB")
                arquivo.write(bloco)
    except Exception:
        destino.unlink(missing_ok=True)
        raise


def ambiente_seguro(base: dict | None = None) -> dict:
    """Cópia do ambiente sem chaves, tokens e senhas (o Claude Code usa o login Max salvo, não variáveis)."""
    return {k: v for k, v in (base or os.environ).items() if not _SEGREDO_NO_NOME.search(k)}


# Plano Max sem cota (janela de 5 h) ou deslogado: não é falha da peça nem do pedido. O trabalhador devolve a peça
# à fila e espera (revisão de 30/10/2026: antes, 5 peças da fila falhavam em 1 minuto quando a cota acabava).
SEM_COTA = re.compile(r"usage limit|limit reached|5-hour limit|out of (?:extra )?usage|limit will reset|"
                      r"not logged in|/login\b", re.IGNORECASE)


class MaxSemCota(RuntimeError):
    """O Claude Code recusou por cota ou login do plano Max."""


CAIXA_DE_AREIA = Path(__file__).with_name("caixa_de_areia")  # sitecustomize.py: entra em todo python da produção
PROGRAMAS_DA_PRODUCAO = ("ffmpeg", "ffprobe", "chrome", "msedge", "python", "pythonw", "python3",
                         Path(sys.executable).stem.lower())


ARQUIVO_BLOQUEIOS = ".bloqueios_caixa.txt"  # na pasta da peça: uma linha por tentativa barrada (vai ao painel)


def ler_bloqueios(pasta_da_peca: Path) -> list[str]:
    """Linhas que a caixa de areia registrou nesta pasta (e apaga o arquivo, para a próxima rodada começar limpa)."""
    arquivo = pasta_da_peca / ARQUIVO_BLOQUEIOS
    try:
        linhas = [l.strip() for l in arquivo.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        arquivo.unlink(missing_ok=True)
    except OSError:
        return []
    return linhas[-50:]


def caixa_de_areia(pasta_da_peca: Path, outras_bloqueadas: list[Path] = ()) -> dict:
    """Variáveis que prendem o python da produção (revisão de 30/10/2026, item 1.1): sem ler o repositório, a pasta dev
    e credenciais do usuário, gravando só na pasta da peça e no TEMP, sem rede externa e sem outros programas.
    O CÉREBRO fica de fora da gravação como o resto do Drive (o python só grava na pasta da peça e no TEMP)."""
    casa = Path.home()
    local, roaming = Path(os.environ.get("LOCALAPPDATA", casa)), Path(os.environ.get("APPDATA", casa))
    bloqueadas = [RAIZ.parent, casa / ".claude", casa / ".ssh", casa / ".aws", casa / ".config", casa / ".docker",
                  local / "Google" / "Chrome" / "User Data", local / "Microsoft" / "Edge" / "User Data",
                  roaming / "Mozilla", roaming / "Microsoft" / "Credentials", local / "Microsoft" / "Credentials",
                  *outras_bloqueadas]  # fotos das outras empresas
    return {
        "PYTHONPATH": str(CAIXA_DE_AREIA),
        "VERANEIO_AREIA_BLOQUEADAS": os.pathsep.join(map(str, bloqueadas)),
        "VERANEIO_AREIA_LIBERADAS": str(Path(__file__).parent),  # o renderizador e a própria caixa (código público)
        "VERANEIO_AREIA_ESCRITA": os.pathsep.join([str(pasta_da_peca), tempfile.gettempdir()]),
        "VERANEIO_AREIA_PROGRAMAS": ",".join(PROGRAMAS_DA_PRODUCAO),
        "VERANEIO_AREIA_REGISTRO": str(pasta_da_peca / ARQUIVO_BLOQUEIOS),
    }


class Cancelado(RuntimeError):
    """O backend cancelou o trabalho (ninguém espera mais o resultado): o Claude Code foi encerrado."""


INTERVALO_CANCELAMENTO = 30


ARQUIVO_PROGRESSO = "progresso.txt"  # o Claude Code anota cada peça que começa ("1/4 | Criando Story 1")
INTERVALO_PROGRESSO = 10


def encerrar_arvore(processo: subprocess.Popen) -> None:
    """Encerra o Claude Code E os filhos (ffmpeg, Chrome, python): antes só o claude.exe morria e o ffmpeg seguia
    gravando um MP4 que saía como pronto (revisão de 30/10/2026, 2.4)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(processo.pid)], capture_output=True, creationflags=SEM_JANELA)
    else:
        processo.kill()
    try:
        processo.wait(timeout=30)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait()


# Modelo por tipo de trabalho (despachante-06): dados/modelos_max.json, fora do git, lido a cada chamada (muda sem
# reiniciar). Ex.: {"texto": "sonnet", "anexo": "sonnet"}. Sem o arquivo, tipo ausente, "" ou "padrao": nenhuma troca
# (o modelo padrão do Claude Code, como sempre foi).
ARQUIVO_MODELOS = DADOS / "modelos_max.json"
TIPOS_DE_TRABALHO = ("texto", "anexo", "prospeccao", "producao")
_NOME_DE_MODELO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-\[\]]{0,63}")


def modelo_para(tipo: str) -> str:
    """Alias/nome do modelo para este tipo de trabalho ("" = padrão do Claude Code)."""
    try:
        escolhas = json.loads(ARQUIVO_MODELOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    valor = str(escolhas.get(tipo) or "").strip() if isinstance(escolhas, dict) and tipo in TIPOS_DE_TRABALHO else ""
    if valor.lower() in ("", "padrao", "padrão") or not _NOME_DE_MODELO.fullmatch(valor):
        return ""
    return valor


# Medição do Max (despachante-07): o que o Claude Code devolve na saída JSON (tokens, rodadas) e a duração medida,
# somados por trabalho (a produção pode rodar duas vezes). Vai ao backend junto com a conclusão ou a falha.
_uso = threading.local()


def zerar_uso() -> None:
    _uso.dados = {"chars_entrada": 0, "chars_saida": 0, "tokens_entrada": 0, "tokens_cache": 0, "tokens_saida": 0,
                  "rodadas": 0, "duracao_s": 0.0, "modelo": ""}


def uso_acumulado() -> dict:
    if not hasattr(_uso, "dados"):
        zerar_uso()
    return {**_uso.dados, "duracao_s": round(_uso.dados["duracao_s"], 1)}


def _somar_uso(saida: dict, prompt: str, duracao_s: float, modelo: str) -> None:
    if not hasattr(_uso, "dados"):
        zerar_uso()
    d, usage = _uso.dados, saida.get("usage") if isinstance(saida.get("usage"), dict) else {}
    numero = lambda v: int(v) if isinstance(v, (int, float)) and v >= 0 else 0
    d["chars_entrada"] += len(prompt)
    d["chars_saida"] += len(str(saida.get("result") or ""))
    d["tokens_entrada"] += numero(usage.get("input_tokens"))
    d["tokens_cache"] += numero(usage.get("cache_creation_input_tokens")) + numero(usage.get("cache_read_input_tokens"))
    d["tokens_saida"] += numero(usage.get("output_tokens"))
    d["rodadas"] += numero(saida.get("num_turns"))
    d["duracao_s"] += max(duracao_s, 0.0)
    usados = list(saida.get("modelUsage") or {}) if isinstance(saida.get("modelUsage"), dict) else []
    d["modelo"] = (",".join(usados) or modelo or d["modelo"])[:80]


def rodar_claude(comando: list[str], prompt: str, cwd: Path, timeout: int, env: dict | None = None,
                 ao_progresso=None, cancelado=None, tipo: str = "") -> str:
    """Roda o Claude Code com o prompt pela entrada padrão; devolve o texto final ou levanta RuntimeError.
    Sempre isolado (ISOLAMENTO) e com o ambiente sem segredos. `ao_progresso(linhas)`: chamado quando o
    progresso.txt da pasta muda (a cada INTERVALO_PROGRESSO s). `tipo`: escolhe o modelo (modelos_max.json) e
    soma o consumo em uso_acumulado()."""
    modelo = modelo_para(tipo) if tipo else ""
    comando = [comando[0], *ISOLAMENTO, *(["--model", modelo] if modelo else []), *comando[1:]]
    inicio = time.monotonic()
    try:
        return _rodar_claude(comando, prompt, cwd, timeout, env, ao_progresso, cancelado, modelo)
    except (subprocess.TimeoutExpired, Cancelado):  # encerrado no meio: sem saída JSON, só a duração
        _somar_uso({}, prompt, time.monotonic() - inicio, modelo)
        raise


def _rodar_claude(comando: list[str], prompt: str, cwd: Path, timeout: int, env: dict | None, ao_progresso,
                  cancelado, modelo: str) -> str:
    progresso = cwd / ARQUIVO_PROGRESSO
    progresso.unlink(missing_ok=True)
    visto: list[str] = []
    inicio = time.monotonic()
    proxima_conferencia = inicio + INTERVALO_CANCELAMENTO
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as saida_padrao, \
            tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as saida_erro:
        processo = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=saida_padrao, stderr=saida_erro, cwd=cwd,
                                    env=ambiente_seguro(env), text=True, encoding="utf-8", errors="replace",
                                    creationflags=SEM_JANELA)
        processo.stdin.write(prompt)
        processo.stdin.close()
        while True:
            try:
                processo.wait(timeout=INTERVALO_PROGRESSO)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - inicio > timeout:
                    encerrar_arvore(processo)
                    raise subprocess.TimeoutExpired(comando, timeout)
                if cancelado and time.monotonic() >= proxima_conferencia:
                    proxima_conferencia = time.monotonic() + INTERVALO_CANCELAMENTO
                    if cancelado():
                        encerrar_arvore(processo)
                        raise Cancelado("cancelado pelo escritório (ninguém espera mais o resultado)")
            if ao_progresso and progresso.exists():
                linhas = [l.strip() for l in progresso.read_text(encoding="utf-8", errors="replace").splitlines()
                          if l.strip()][-30:]
                if linhas != visto:
                    visto = linhas
                    try:
                        ao_progresso(linhas)
                    except Exception as erro:  # progresso nunca derruba a produção
                        log(f"   progresso não enviado ({erro})")
        saida_padrao.seek(0)
        saida_erro.seek(0)
        texto_saida, texto_erro = saida_padrao.read(), saida_erro.read()
    try:
        saida = json.loads(texto_saida or "{}")
    except ValueError:
        saida = {"is_error": True, "result": (texto_saida or "")[-500:]}
    if not isinstance(saida, dict):
        saida = {"is_error": True, "result": str(saida)[-500:]}
    _somar_uso(saida, prompt, time.monotonic() - inicio, modelo)
    if processo.returncode != 0 or saida.get("is_error"):
        motivo = {"error_max_turns": "atingiu o limite de rodadas",
                  "error_during_execution": "erro durante a execução"}.get(saida.get("subtype"), saida.get("subtype"))
        mensagem = (saida.get("result") or texto_erro[-500:]
                    or f"Claude Code terminou com erro{f' ({motivo})' if motivo else ''}.")
        raise (MaxSemCota if SEM_COTA.search(mensagem) else RuntimeError)(mensagem)
    return saida.get("result", "")


def remover_do_cerebro(fonte_tipo: str, refs: list[str]) -> bool:
    """Desativa no Cérebro os documentos que sumiram da fonte (ex.: página que deixou de existir)."""
    try:
        for inicio in range(0, len(refs), 100):
            chamar("POST", "/api/cerebro/ingerir", {"remover": [{"fonte_tipo": fonte_tipo, "fonte_ref": r}
                                                                for r in refs[inicio:inicio + 100]]})
        return True
    except Exception as erro:
        log(f"   AVISO: não foi possível remover do Cérebro ({erro}); nova tentativa no próximo ciclo.")
        return False


def enviar_ao_cerebro(documentos: list[dict], chamar_api=None) -> bool:
    """POST /api/cerebro/ingerir em lotes. False (com aviso) se o endpoint não existe ou o backend falhou."""
    chamar_api = chamar_api or (lambda *args: chamar(*args, timeout=TEMPO_INGESTAO))
    for inicio in range(0, len(documentos), LOTE_CEREBRO):
        lote = documentos[inicio:inicio + LOTE_CEREBRO]
        try:
            chamar_api("POST", "/api/cerebro/ingerir", {"documentos": lote})
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                log("   AVISO: o Cérebro ainda não tem a rota /api/cerebro/ingerir (404); envio adiado.")
            else:
                log(f"   AVISO: o Cérebro recusou o envio (HTTP {erro.code}); nova tentativa no próximo ciclo.")
            return False
        except Exception as erro:
            log(f"   AVISO: não foi possível enviar ao Cérebro ({erro}); nova tentativa no próximo ciclo.")
            return False
    return True
