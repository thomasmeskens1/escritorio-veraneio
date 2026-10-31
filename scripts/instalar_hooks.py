"""Liga os hooks versionados do Git (scripts/git_hooks: pre-push com o verificador de segredos).

Uso (na raiz do repositório):  python scripts/instalar_hooks.py            liga (core.hooksPath = scripts/git_hooks)
                               python scripts/instalar_hooks.py --desfazer  volta aos hooks de .git/hooks
Vale para este clone (e os worktrees dele). Com core.hooksPath, os hooks antigos de .git/hooks deixam de rodar:
o script avisa se houver algum que não seja exemplo.
"""

import subprocess
import sys
from pathlib import Path

PASTA = "scripts/git_hooks"


def _git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check).stdout.strip()


def main(argv: list[str]) -> int:
    raiz = Path(_git("rev-parse", "--show-toplevel"))
    if "--desfazer" in argv:
        _git("config", "--unset", "core.hooksPath", check=False)
        print("core.hooksPath removido: valem de novo os hooks de .git/hooks.")
        return 0
    if not (raiz / PASTA / "pre-push").exists():
        print(f"Não achei {PASTA}/pre-push em {raiz}.")
        return 1
    antigos = [h.name for h in (Path(_git("rev-parse", "--git-common-dir")).resolve() / "hooks").glob("*")
               if h.is_file() and not h.name.endswith(".sample")]
    if antigos:
        print(f"Aviso: estes hooks de .git/hooks deixam de rodar: {', '.join(antigos)}. Copie-os para {PASTA} "
              "se ainda forem necessários.")
    anterior = _git("config", "--get", "core.hooksPath", check=False)
    _git("config", "core.hooksPath", PASTA)
    print(f"Hooks ligados: core.hooksPath = {PASTA}" + (f" (antes: {anterior})" if anterior else "") + ".")
    print("O pre-push roda o gitleaks (se instalado) e scripts/verificar_segredos.py antes de cada push.")
    if not (raiz / "backend" / "dados" / "padroes_segredos.txt").exists():
        print("Falta o arquivo de padrões privados backend/dados/padroes_segredos.txt (fora do git): um trecho por "
              "linha (senhas, e-mails da equipe...), 're:' para expressão regular.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
