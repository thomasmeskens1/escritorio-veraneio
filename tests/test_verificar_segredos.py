"""Guarda do repositório público (despachante-30 e 31): verificador de segredos do pre-push e filtro segredos.limpar.
As chaves dos testes são fictícias e montadas em tempo de execução, para o próprio arquivo não disparar o verificador.
Os testes do verificador rodam quando scripts/ está montado em /repo/scripts (ou direto no host).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import config
import segredos

SCRIPTS = next((p for p in (Path("/repo/scripts"), Path(__file__).resolve().parents[1] / "scripts")
                if (p / "verificar_segredos.py").exists()), None)
if SCRIPTS:
    sys.path.insert(0, str(SCRIPTS))
    import verificar_segredos as vs
else:
    vs = None
precisa_scripts = pytest.mark.skipif(vs is None, reason="scripts/ não montado")


def _falsas() -> dict[str, str]:
    """Uma chave fictícia por formato (prefixo + enchimento)."""
    a, h = "Ab3" * 20, "a1" * 30
    return {
        "openrouter": "sk-" + "or-v1-" + h, "anthropic": "sk-" + "ant-api03-" + a, "groq": "gs" + "k_" + a,
        "brevo": "xkey" + "sib-" + h + "-" + a[:16], "google_api": "AI" + "za" + a[:35], "google_oauth": "GOC" + "SPX-" + a,
        "google_token": "ya" + "29." + a, "meta": "EA" + "AB" + a, "github": "gh" + "p_" + a[:36],
        "github_pat": "github" + "_pat_" + a, "slack": "xo" + "xb-" + "1234-" + a[:20], "aws": "AK" + "IA" + "ABCDEFGH12345678",
        "jwt": "ey" + "J" + a[:20] + ".ey" + "J" + a[:20] + "." + a[:20],
        "pem": "-----BEGIN " + "RSA PRIVATE KEY-----\n" + a + "\n-----END " + "RSA PRIVATE KEY-----",
        "telegram": "1234567890:" + "AA" + a[:35],
    }


def test_limpar_apaga_cada_formato():
    for nome, chave in _falsas().items():
        assert chave not in segredos.limpar(f"resumo: {chave} fim"), nome


def test_limpar_nao_corta_texto_comum():
    texto = "EAAlgo de teste, AIzar e gsk sem chave; Lodge 239 com 6 quartos e o arquivo 1//2."
    assert segredos.limpar(texto) == texto


def test_limpar_apaga_tokens_dos_arquivos_token_json(tmp_path, monkeypatch):
    valor = "tok" + "en-ficticio-" + "x9" * 10
    (tmp_path / "youtube.token.json").write_text('{"refresh_token": "%s", "expiry": 1}' % valor, encoding="utf-8")
    monkeypatch.setattr(config, "DADOS_DIR", tmp_path)
    assert valor not in segredos.limpar(f"o token é {valor}")


@precisa_scripts
def test_verificador_acha_cada_formato_e_mascara():
    for nome, chave in _falsas().items():
        achados = vs.verificar_texto(f"x = {chave}")
        assert achados, nome
        assert all(chave not in trecho for _, trecho in achados), nome


@precisa_scripts
def test_verificador_ignora_texto_comum_e_marcador():
    assert vs.verificar_texto("token = os.getenv('MONDAY_TOKEN')\nemail usuario.teste@exemplo.com") == []
    chave = _falsas()["groq"]
    assert vs.verificar_texto(f"exemplo {chave}  # {vs.IGNORAR}") == []


@precisa_scripts
def test_valor_atribuido_e_url_com_senha():
    assert vs.verificar_texto('API_KEY = "' + "q1W2e3R4" * 3 + '"')
    assert vs.verificar_texto("postgres://" + "admin:" + "s3nhaForte" + "@db.local/x")
    assert vs.verificar_texto('senha = "<sua senha aqui>"') == []


@precisa_scripts
def test_padroes_privados_literais_e_regex(tmp_path):
    arquivo = tmp_path / "padroes.txt"
    arquivo.write_text("# comentário\n\nMinhaSenha" + "Secreta\nre:@dominio-" + "ficticio\\.com\nre:([\n",
                       encoding="utf-8")
    privados = vs.carregar_privados(arquivo)
    assert len(privados) == 2  # o regex inválido é ignorado
    assert vs.verificar_texto("a minhasenha" + "secreta b", privados)
    assert vs.verificar_texto("fulano@dominio-" + "ficticio.com", privados)
    assert vs.verificar_texto("nada aqui", privados) == []
    assert vs.carregar_privados(tmp_path / "nao_existe.txt") == []


@precisa_scripts
def test_linhas_adicionadas_e_faixas_do_push():
    diff = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-velha\n+nova\n"
    assert vs.linhas_adicionadas(diff) == [("x.py", "nova")]
    zero = "0" * 40
    entrada = f"refs/heads/a {'1' * 40} refs/heads/a {'2' * 40}\nrefs/heads/b {'3' * 40} refs/heads/b {zero}\n" \
              f"refs/heads/c {zero} refs/heads/c {'4' * 40}\n"
    assert vs.faixas_do_push(entrada) == [[f"{'2' * 40}..{'1' * 40}"], ["3" * 40, "--not", "--remotes"]]


@precisa_scripts
def test_arquivos_proibidos():
    for caminho in (".env", "backend/.env.local", "backend/dados/usuarios.json", "x/youtube.token.json", "chave.pem",
                    "backend/dados/padroes_segredos.txt"):
        assert vs.ARQUIVOS_PROIBIDOS.search(caminho), caminho
    for caminho in (".env.example", "backend/segredos.py", "tests/test_x.py", "scripts/env_utils.py"):
        assert not vs.ARQUIVOS_PROIBIDOS.search(caminho), caminho


@precisa_scripts
@pytest.mark.skipif(not shutil.which("git"), reason="git não instalado")
def test_verificador_num_repositorio_de_verdade(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=Teste", "-c", "user.email=usuario.teste@exemplo.com", *args],
                       cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "a.txt").write_text("limpo\n", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-q", "-m", "limpo")
    (tmp_path / "a.txt").write_text("limpo\nchave " + _falsas()["openrouter"] + "\n", encoding="utf-8")
    git("commit", "-q", "-am", "com chave")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PADROES_SEGREDOS", str(tmp_path / "nao_existe.txt"))
    assert vs.main(["--intervalo", "HEAD~1..HEAD"]) == 1
    git("commit", "-q", "--allow-empty", "-m", "vazio")
    assert vs.main(["--intervalo", "HEAD~1..HEAD"]) == 0
