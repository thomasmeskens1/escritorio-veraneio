"""Verificador de segredos antes do push (o repositório é PÚBLICO; despachante-30, 31/10/2026).

Olha só o que vai sair: as linhas acrescentadas nos commits do push, as mensagens dos commits e os nomes dos
arquivos. Barra chaves e tokens por formato (OpenRouter, Anthropic, Groq, Google, Brevo, Meta, GitHub, Slack, AWS,
JWT, chave privada...), arquivos que nunca podem ir (.env, backend/dados/, *.token.json, chaves) e os PADRÕES
PRIVADOS do arquivo fora do git backend/dados/padroes_segredos.txt (senhas, e-mails da equipe e outros trechos que
não podem aparecer escritos aqui). Esse arquivo é só lido: uma linha por trecho (sem diferença de maiúsculas),
"re:" no começo para expressão regular, "#" para comentário. Outro caminho: variável PADROES_SEGREDOS.

Uso:
  python scripts/verificar_segredos.py --pre-push        (o hook scripts/git_hooks/pre-push passa as linhas do git)
  python scripts/verificar_segredos.py --intervalo origin/main..HEAD
  python scripts/verificar_segredos.py --historico       (todo o histórico; ex.: varredura semanal)
Sai com 1 quando acha algo. Falso positivo: acrescente "segredos: ignorar" na própria linha.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

PADROES = [
    ("chave do OpenRouter", r"sk-or-v1-[0-9a-f]{20,}"),
    ("chave da Anthropic", r"sk-ant-[\w-]{20,}"),
    ("chave da OpenAI", r"sk-proj-[\w-]{20,}"),
    ("chave do Groq", r"\bgsk_[A-Za-z0-9]{20,}"),
    ("chave do Brevo", r"\bx(?:key|smtp)sib-[\w-]{20,}"),
    ("chave de API do Google", r"\bAIza[\w-]{30,}"),
    ("segredo OAuth do Google", r"\bGOCSPX-[\w-]{20,}"),
    ("token OAuth do Google", r"\bya29\.[\w-]{20,}|(?<![\w/])1//0[\w-]{30,}"),
    ("token da Meta", r"\bEAA[A-Za-z0-9]{40,}"),
    ("token do GitHub", r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_\w{40,}"),
    ("token do Slack", r"\bxox[abprs]-[\w-]{10,}|hooks\.slack\.com/services/T\w+/\w+/\w+"),
    ("chave da AWS", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("chave do Stripe", r"\b[rs]k_live_[0-9A-Za-z]{20,}"),
    ("token de bot do Telegram", r"\b\d{8,10}:AA[\w-]{30,}"),
    ("JWT (ex.: token do Monday)", r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}"),
    ("chave privada", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("senha em URL", r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s:/@]{6,}@"),
    # Atribuição com valor longo e misturado (letras e números), fora de exemplos e variáveis de ambiente.
    ("valor atribuído a chave/senha", r"(?i)\b[\w-]*(?:api[_-]?key|secret|senha|password|passwd|token)[\w-]*\s*[:=]\s*"
                                      r"[\"'](?=[^\"']*\d)(?=[^\"']*[A-Za-z])[^\"'\s<>${}]{20,}[\"']"),
]
ARQUIVOS_PROIBIDOS = re.compile(
    r"(^|/)\.env($|\.(?!example$))|(^|/)backend/dados/|\.token\.json$|(^|/)usuarios\.json$|(^|/)operador\.token$"
    r"|\.(pem|p12|pfx|key)$|(^|/)id_(rsa|ed25519|ecdsa)$|(^|/)padroes_segredos\.txt$|\.db$", re.I)
IGNORAR = "segredos: ignorar"
ZERO = re.compile(r"^0+$")
_COMPILADOS = [(nome, re.compile(p)) for nome, p in PADROES]


def raiz() -> Path:
    saida = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return Path(saida.stdout.strip())


def carregar_privados(caminho: Path) -> list[tuple[str, re.Pattern]]:
    """Padrões privados (fora do git). Arquivo ausente: lista vazia (o hook avisa)."""
    if not caminho.exists():
        return []
    padroes = []
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        try:
            regex = re.compile(linha[3:], re.I) if linha.startswith("re:") else re.compile(re.escape(linha), re.I)
        except re.error:
            print(f"Aviso: padrão privado inválido na linha {numero} (ignorado).", file=sys.stderr)
            continue
        padroes.append((f"padrão privado da linha {numero}", regex))
    return padroes


def _mascarar(trecho: str) -> str:
    return trecho[:4] + "…" if len(trecho) > 6 else "…"


def verificar_texto(texto: str, privados: list | None = None) -> list[tuple[str, str]]:
    """(tipo, trecho mascarado) de cada segredo no texto. O trecho nunca sai inteiro na tela."""
    achados = []
    for linha in texto.splitlines():
        if IGNORAR in linha:
            continue
        for nome, regex in _COMPILADOS + (privados or []):
            for m in regex.finditer(linha):
                achados.append((nome, _mascarar(m.group(0))))
    return achados


def linhas_adicionadas(diff: str) -> list[tuple[str, str]]:
    """(arquivo, linha) acrescentadas num `git log -p` / `git diff`."""
    arquivo, linhas = "", []
    for linha in diff.splitlines():
        if linha.startswith("+++ "):
            arquivo = linha[6:] if linha.startswith("+++ b/") else linha[4:]
        elif linha.startswith("+") and not linha.startswith("+++"):
            linhas.append((arquivo, linha[1:]))
    return linhas


def faixas_do_push(entrada: str) -> list[list[str]]:
    """Argumentos de `git log` para cada ref do push (linhas "<ref local> <sha local> <ref remota> <sha remoto>")."""
    faixas = []
    for linha in entrada.splitlines():
        partes = linha.split()
        if len(partes) != 4 or ZERO.match(partes[1]):
            continue  # linha estranha ou remoção de branch: nada sai
        local, remoto = partes[1], partes[3]
        faixas.append([local, "--not", "--remotes"] if ZERO.match(remoto) else [f"{remoto}..{local}"])
    return faixas


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def verificar_faixa(faixa: list[str], privados: list) -> list[str]:
    problemas = []
    for arquivo in sorted(set(_git("log", "--name-only", "--diff-filter=ACR", "--format=", *faixa).split("\n"))):
        if arquivo and ARQUIVOS_PROIBIDOS.search(arquivo):
            problemas.append(f"{arquivo}: arquivo que não pode ir ao repositório público")
    for arquivo, linha in linhas_adicionadas(_git("log", "-p", "--no-color", "-U0", "--format=", *faixa)):
        problemas += [f"{arquivo}: {nome} ({trecho})" for nome, trecho in verificar_texto(linha, privados)]
    for mensagem in _git("log", "--format=%H %B%x00", *faixa).split("\x00"):
        if mensagem.strip():
            commit = mensagem.strip()[:9]
            problemas += [f"mensagem do commit {commit}: {nome} ({trecho})"
                          for nome, trecho in verificar_texto(mensagem, privados)]
    return problemas


def main(argv: list[str]) -> int:
    for saida in (sys.stdout, sys.stderr):  # acentos no terminal do Git no Windows
        if hasattr(saida, "reconfigure"):
            saida.reconfigure(encoding="utf-8", errors="replace")
    pasta = raiz()
    caminho = Path(os.getenv("PADROES_SEGREDOS") or pasta / "backend" / "dados" / "padroes_segredos.txt")
    privados = carregar_privados(caminho)
    if not privados:
        print(f"Aviso: sem padrões privados ({caminho} não existe ou está vazio); só os formatos gerais.",
              file=sys.stderr)
    if "--pre-push" in argv:
        faixas = faixas_do_push(sys.stdin.read())
    elif "--intervalo" in argv and len(argv) > argv.index("--intervalo") + 1:
        faixas = [[argv[argv.index("--intervalo") + 1]]]
    elif "--historico" in argv:
        faixas = [["--all"]]
    else:
        print(__doc__)
        return 2
    problemas = [p for faixa in faixas for p in verificar_faixa(faixa, privados)]
    if problemas:
        print("Segredo ou dado sensível no que vai ser enviado ao repositório PÚBLICO:", file=sys.stderr)
        for problema in dict.fromkeys(problemas):
            print(f"  - {problema}", file=sys.stderr)
        print("Tire o trecho do commit local (ex.: git commit --amend) e tente de novo. Um commit novo que apague "
              "a linha não basta: o histórico também é enviado.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
