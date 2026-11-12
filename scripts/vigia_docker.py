"""Vigia do escritório: religa sozinho o Docker, a API e o trabalhador do Max depois de queda de luz ou de internet.

Pedido do Thomas, 12/11/2026. Roda escondido (pythonw, sem janela) pela tarefa agendada
"Escritorio Veraneio - Vigia", no login e a cada 5 minutos. A cada rodada:
1. Docker parado: liga o Docker Desktop sem janela (docker desktop start).
2. API sem responder em /api/saude: espera a volta sozinha (o contêiner tem restart: unless-stopped). Se seguir
   fora, roda `docker compose up -d --no-recreate`, que só sobe o que está parado.
3. Trabalhador do Max parado: dispara a tarefa agendada dele.
Nunca mexe durante o reinício planejado (backend/dados/manutencao, do reiniciar_api.py). Para pausar o vigia (ex.:
desligar o Docker de propósito), crie o arquivo backend/dados/vigia_pausado; para voltar, apague-o.
Registro: %LOCALAPPDATA%/EscritorioVeraneio/vigia.log (só as últimas linhas).

Instalar a tarefa (uma vez):  python scripts/vigia_docker.py --instalar
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "backend" / "dados"
MANUTENCAO, PAUSADO = DADOS / "manutencao", DADOS / "vigia_pausado"
SAUDE = "http://127.0.0.1:8000/api/saude"
TAREFA_VIGIA = "Escritorio Veraneio - Vigia"
TAREFA_MAX = "Escritorio Veraneio - Trabalhador Max"
LOG = Path(os.environ.get("LOCALAPPDATA", str(RAIZ))) / "EscritorioVeraneio" / "vigia.log"
MAX_LINHAS = 400
MANUTENCAO_VALE_S = 40 * 60  # manutenção mais velha que isso: o reinício travou, o vigia age
ESPERA_API_S = 180           # depois do Docker voltar, tempo para o contêiner subir sozinho
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DOCKER_PADRAO = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"


def log(texto: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        linhas = LOG.read_text(encoding="utf-8").splitlines()[-MAX_LINHAS:] if LOG.exists() else []
        linhas.append(f"{datetime.now():%d/%m/%Y %H:%M:%S} {texto}")
        LOG.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except OSError:
        pass


def _rodar(comando: list[str], timeout: int = 60) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, timeout=timeout,
                              creationflags=SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired):
        return None


def docker() -> str:
    return shutil.which("docker") or DOCKER_PADRAO


def docker_ok() -> bool:
    r = _rodar([docker(), "info", "--format", "{{.ServerVersion}}"], timeout=30)
    return bool(r and r.returncode == 0 and r.stdout.strip())


def api_ok() -> bool:
    try:
        with urllib.request.urlopen(SAUDE, timeout=10) as resposta:
            return resposta.status == 200
    except Exception:  # noqa: BLE001 - qualquer falha é "fora do ar"
        return False


def em_manutencao() -> bool:
    try:
        return time.time() - MANUTENCAO.stat().st_mtime < MANUTENCAO_VALE_S
    except OSError:
        return False


def _powershell(comando: str) -> subprocess.CompletedProcess | None:
    return _rodar(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", comando])


def trabalhador_ok() -> bool:
    r = _powershell(f"(Get-ScheduledTask -TaskName '{TAREFA_MAX}').State")
    return not r or r.returncode != 0 or r.stdout.strip() == "Running"  # sem resposta: não arrisca dois trabalhadores


def esperar(condicao, limite_s: int, passo_s: int = 10) -> bool:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(passo_s)
    return condicao()


def rodada() -> str:
    """Uma verificação completa; devolve o que fez (para o registro e os testes)."""
    if PAUSADO.exists():
        return "pausado"
    feito = []
    if not docker_ok():
        log("Docker parado: ligando o Docker Desktop")
        _rodar([docker(), "desktop", "start", "--timeout", "240"], timeout=300)
        if not esperar(docker_ok, 60):
            log("Docker não voltou; tento de novo na próxima rodada")
            return "docker_falhou"
        feito.append("docker")
    if not api_ok():
        if em_manutencao():
            return "manutencao"
        if not esperar(api_ok, ESPERA_API_S if feito else 30):
            log("API fora do ar: subindo os contêineres parados")
            _rodar([docker(), "compose", "up", "-d", "--no-recreate"], timeout=300)
            if not esperar(api_ok, ESPERA_API_S):
                log("API segue fora do ar; tento de novo na próxima rodada")
                return "api_falhou"
        feito.append("api")
    if not trabalhador_ok():
        log("Trabalhador do Max parado: disparando a tarefa")
        _powershell(f"Start-ScheduledTask -TaskName '{TAREFA_MAX}'")
        feito.append("trabalhador")
    if feito:
        log("Recuperado: " + ", ".join(feito))
    return ",".join(feito) or "ok"


XML_TAREFA = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Religa o Docker, a API e o trabalhador do Max do Escritório Veraneio depois de
  queda de luz ou de internet (scripts/vigia_docker.py).</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{usuario}</UserId><Delay>PT1M</Delay></LogonTrigger>
    <TimeTrigger><StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled>
      <Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{usuario}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT20M</ExecutionTimeLimit>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author"><Exec><Command>{pythonw}</Command><Arguments>"{script}"</Arguments></Exec></Actions>
</Task>
"""


def instalar() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    usuario = "\\".join(p for p in (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")) if p)
    xml = XML_TAREFA.format(pythonw=pythonw if pythonw.exists() else sys.executable, script=Path(__file__).resolve(),
                            usuario=usuario)
    arquivo = Path(os.environ.get("TEMP", str(RAIZ))) / "vigia_tarefa.xml"
    arquivo.write_text(xml, encoding="utf-16")
    r = _rodar(["schtasks", "/create", "/tn", TAREFA_VIGIA, "/xml", str(arquivo), "/f"])
    arquivo.unlink(missing_ok=True)
    print((r.stdout + r.stderr).strip() if r else "schtasks não respondeu")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--instalar", action="store_true", help="cria a tarefa agendada (uma vez)")
    if argumentos.parse_args().instalar:
        instalar()
    else:
        rodada()
