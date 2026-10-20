"""Peças comuns do trabalhador Max: pastas, chamadas ao backend, Claude Code e envio ao Cérebro."""

import json
import os
import shutil
import subprocess
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
LOTE_CEREBRO = 10           # documentos por chamada de ingestão
TEMPO_INGESTAO = 300        # o Cérebro calcula os embeddings na hora


def log(texto: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {texto}", flush=True)


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


def rodar_claude(comando: list[str], prompt: str, cwd: Path, timeout: int, env: dict | None = None) -> str:
    """Roda o Claude Code com o prompt pela entrada padrão; devolve o texto final ou levanta RuntimeError."""
    processo = subprocess.run(comando, input=prompt, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    try:
        saida = json.loads(processo.stdout or "{}")
    except ValueError:
        saida = {"is_error": True, "result": (processo.stdout or "")[-500:]}
    if processo.returncode != 0 or saida.get("is_error"):
        raise RuntimeError(saida.get("result") or processo.stderr[-500:] or "Claude Code terminou com erro.")
    return saida.get("result", "")


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
