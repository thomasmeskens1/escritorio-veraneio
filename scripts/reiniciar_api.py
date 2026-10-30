"""Reinicia a API sem derrubar trabalho em andamento (revisão de 30/10/2026, item 2.11).

Uso (no PC, na pasta do projeto):  python scripts/reiniciar_api.py [--esperar-min 20]

1. Liga o modo manutenção (backend/dados/manutencao): mensagens novas no chat recebem "o escritório vai reiniciar
   em instantes, envie de novo em 2 ou 3 minutos" e nenhuma tarefa nova começa.
2. Espera não haver tarefa executando, produção na fila ou trabalho do Max pendente (até --esperar-min minutos).
3. Reinicia o contêiner da API; na subida, o servidor apaga o arquivo de manutenção.
Se o tempo acabar com trabalho em andamento, desliga a manutenção e NÃO reinicia.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MANUTENCAO = RAIZ / "backend" / "dados" / "manutencao"
CONSULTA = ("import sqlite3; db = sqlite3.connect('file:/var/lib/escritorio/escritorio.db?mode=ro', uri=True); "
            "print(db.execute(\"SELECT COUNT(*) FROM tarefas WHERE status IN ('executando','producao','produzindo',"
            "'adiada')\").fetchone()[0] + db.execute(\"SELECT COUNT(*) FROM trabalhos_max WHERE status IN "
            "('pendente','executando','reservado')\").fetchone()[0])")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def em_andamento() -> int:
    saida = subprocess.run(["docker", "exec", "escritorio-veraneio-api-1", "python", "-c", CONSULTA],
                           capture_output=True, text=True, check=True, creationflags=SEM_JANELA).stdout
    return int(saida.strip())


def main() -> None:
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--esperar-min", type=int, default=20)
    limite = time.monotonic() + argumentos.parse_args().esperar_min * 60
    MANUTENCAO.write_text("reinício em andamento", encoding="utf-8")
    print("Modo manutenção ligado: tarefas novas são recusadas com aviso.")
    try:
        while (ocupados := em_andamento()):
            if time.monotonic() > limite:
                MANUTENCAO.unlink(missing_ok=True)
                sys.exit(f"Ainda há {ocupados} trabalho(s) em andamento: manutenção desligada, nada foi reiniciado.")
            print(f"Esperando {ocupados} trabalho(s) terminar...")
            time.sleep(15)
    except Exception:
        MANUTENCAO.unlink(missing_ok=True)
        raise
    subprocess.run(["docker", "compose", "restart", "api"], cwd=RAIZ, check=True, creationflags=SEM_JANELA)
    print("API reiniciada (a manutenção se desliga sozinha na subida).")


if __name__ == "__main__":
    main()
