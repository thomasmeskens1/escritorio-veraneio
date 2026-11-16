"""Google Drive pela API oficial, só leitura (Thomas, 16/11/2026): o que o Drive do PC (G:) não entrega.

O escritório lê o Drive pelo Drive para desktop (G:). Os arquivos nativos do Google (Docs, Planilhas, Apresentações)
lá são só atalhos (.gdoc, .gsheet), sem o conteúdo. Este módulo exporta esses arquivos pela API e:
- leva ao Cérebro os nativos das pastas LODGES, MARKETING e CORPORATIVO do drive "(NOVO) CASA VERANEIO" (só os novos
  ou alterados; os apagados saem do Cérebro). Nome ou pasta com cara de dado sensível (senha, token, banco, jurídico,
  cliente, financeiro, tráfego...) nunca vai, nem pela linha de comando;
- substitui o conector do claude.ai: `ler` e `buscar` na linha de comando, para o Claude Code do chat.
Nada é criado, alterado ou apagado no Drive (permissão drive.readonly).

Login (uma vez, no navegador, com a conta que vê o drive "(NOVO) CASA VERANEIO"):
  C:\\dev\\social-analytics\\venv\\Scripts\\python.exe scripts\\max\\drive_api.py
Usa o cliente OAuth do painel (%LOCALAPPDATA%\\SocialAnalytics\\credenciais_google.json; a API do Google Drive precisa
estar ativada no projeto) e grava o login em backend/dados/drive_leitura.token.json (fora do git).

Outros usos:
  python scripts/max/drive_api.py buscar "<parte do nome>"
  python scripts/max/drive_api.py ler "<link, ID ou caminho G:\\...>"
  python scripts/max/drive_api.py sincronizar
"""

import glob
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402
from comum import log  # noqa: E402

API = "https://www.googleapis.com/drive/v3"
ESCOPO = "https://www.googleapis.com/auth/drive.readonly"
CLIENTE = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", Path(os.environ.get("LOCALAPPDATA", "")) / "SocialAnalytics")) / "credenciais_google.json"
LOGIN = comum.DADOS / "drive_leitura.token.json"
ARQUIVO_HASHES = comum.DADOS / "drive_nativos.hashes.json"

RAIZ = "(NOVO) CASA VERANEIO"
PASTAS_CEREBRO = {"LODGES": "casa_veraneio", "MARKETING": "casa_veraneio", "CORPORATIVO": "cv_corporativo"}
SENSIVEL = re.compile(r"senha|token|banc[aáo]|financ|jur[ií]dic|legal|cliente|restrit|contrato|cpf|cnpj|iugu|"
                      r"tr[aá]fego|pagamento|prestador|sal[aá]rio|folha", re.IGNORECASE)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORTA = {"application/vnd.google-apps.document": "text/plain",
           "application/vnd.google-apps.presentation": "text/plain",
           "application/vnd.google-apps.spreadsheet": XLSX}
TIPO = {"application/vnd.google-apps.document": "Documento Google",
        "application/vnd.google-apps.presentation": "Apresentação Google",
        "application/vnd.google-apps.spreadsheet": "Planilha Google"}
EXTENSOES = re.compile(r"\.(gdoc|gsheet|gslides)$", re.IGNORECASE)
MAX_TEXTO = 60000      # caracteres por arquivo no Cérebro
MAX_LINHAS_ABA = 2000
LINK_OU_ID = re.compile(r"(?:/d/|[?&]id=|/folders/)([\w-]{20,80})|^([\w-]{25,80})$")


class SemLogin(Exception):
    """Sem login válido: o Drive pela API fica parado até o Thomas autorizar de novo."""


# ---------- Login e chamadas ----------
def tem_login() -> bool:
    return LOGIN.exists()


def _token() -> str:
    if not tem_login():
        raise SemLogin("o Drive pela API ainda não foi autorizado (rode scripts/max/drive_api.py)")
    login = json.loads(LOGIN.read_text(encoding="utf-8"))
    corpo = urllib.parse.urlencode({"client_id": login["client_id"], "client_secret": login["client_secret"],
                                    "refresh_token": login["refresh_token"], "grant_type": "refresh_token"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(login["token_uri"], data=corpo), timeout=30) as resposta:
            return json.load(resposta)["access_token"]
    except urllib.error.HTTPError as erro:
        raise SemLogin(f"login do Drive vencido ou revogado ({erro.code}); rode o login de novo") from erro


def _get(caminho: str, parametros: dict, token: str, bruto: bool = False):
    url = f"{API}/{caminho}?{urllib.parse.urlencode(parametros)}"
    pedido = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(pedido, timeout=120) as resposta:
            return resposta.read() if bruto else json.load(resposta)
    except urllib.error.HTTPError as erro:
        detalhe = erro.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Drive respondeu {erro.code}: {detalhe}") from erro


# ---------- Arquivos nativos conhecidos pelo Drive do PC ----------
def _banco() -> str | None:
    achados = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS", "*", "metadata_sqlite_db"))
    return achados[0] if achados else None


def nativos(banco: str | None = None) -> list[dict]:
    """Docs, Planilhas e Apresentações do Drive do PC (banco do Drive para desktop, só leitura), com a cadeia de
    pastas do topo até eles. Não chama a API."""
    banco = banco or _banco()
    if not banco:
        return []
    conexao = sqlite3.connect(f"file:{banco}?mode=ro", uri=True, timeout=5)
    conexao.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        marcas = ",".join("?" * len(EXPORTA))
        linhas = conexao.execute(f"SELECT stable_id, id, local_title, mime_type, modified_date FROM items WHERE "
                                 f"trashed = 0 AND is_folder = 0 AND mime_type IN ({marcas})", list(EXPORTA)).fetchall()
        itens = []
        for stable_id, nuvem, titulo, mime, modificado in linhas:
            if not nuvem or nuvem.startswith("local"):
                continue  # ainda não sincronizado
            pastas, atual = [], stable_id
            for _ in range(40):
                pai = conexao.execute("SELECT parent_stable_id FROM stable_parents WHERE item_stable_id = ?",
                                      (atual,)).fetchone()
                if not pai:
                    break
                atual = pai[0]
                nome = conexao.execute("SELECT local_title FROM items WHERE stable_id = ?", (atual,)).fetchone()
                pastas.append(nome[0] if nome else "?")
            itens.append({"id": nuvem, "titulo": EXTENSOES.sub("", titulo or ""), "mime": mime,
                          "modificado": str(modificado), "pastas": list(reversed(pastas))})
        return itens
    finally:
        conexao.close()


def sensivel(item: dict) -> bool:
    return any(SENSIVEL.search(parte) for parte in [*item["pastas"], item["titulo"]])


def empresa_no_cerebro(item: dict) -> str | None:
    """Empresa do documento no Cérebro, ou None se o arquivo não vai ao Cérebro."""
    pastas = item["pastas"]
    if len(pastas) < 2 or pastas[0] != RAIZ or pastas[1] not in PASTAS_CEREBRO or sensivel(item):
        return None
    return PASTAS_CEREBRO[pastas[1]]


# ---------- Exportação ----------
def _planilha_em_texto(conteudo: bytes) -> str:
    import openpyxl

    planilha = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        partes = []
        for aba in planilha.worksheets:
            linhas = []
            for linha in aba.iter_rows(values_only=True):
                celulas = ["" if v is None else str(v).strip() for v in linha]
                while celulas and not celulas[-1]:
                    celulas.pop()
                if any(celulas):
                    linhas.append(" | ".join(celulas))
                if len(linhas) >= MAX_LINHAS_ABA:
                    linhas.append("[… aba cortada]")
                    break
            if linhas:
                partes.append(f"## Aba: {aba.title}\n" + "\n".join(linhas))
        return "\n\n".join(partes)
    finally:
        planilha.close()


def exportar(arquivo_id: str, mime: str, token: str) -> str:
    """Conteúdo do arquivo nativo em texto (planilha: todas as abas, uma linha por linha)."""
    if mime not in EXPORTA:
        raise ValueError(f"tipo {mime} não é exportável como texto")
    conteudo = _get(f"files/{arquivo_id}/export", {"mimeType": EXPORTA[mime]}, token, bruto=True)
    if EXPORTA[mime] == XLSX:
        return _planilha_em_texto(conteudo)
    return conteudo.decode("utf-8-sig", "replace").strip()


def documento(item: dict, texto: str, empresa: str) -> dict:
    caminho = " > ".join(item["pastas"])
    corpo = texto if len(texto) <= MAX_TEXTO else texto[:MAX_TEXTO] + "\n[… cortado]"
    return {"fonte_tipo": "drive", "empresa": empresa, "fonte_ref": f"drive/nativo/{item['id']}",
            "titulo": f"{item['titulo']} ({TIPO.get(item['mime'], 'arquivo Google')})",
            "conteudo": f"# {item['titulo']}\n{TIPO.get(item['mime'], 'Arquivo Google')} do Drive · pasta: {caminho}\n"
                        f"Link: https://drive.google.com/open?id={item['id']}\n\n{corpo}"}


def _hash(item: dict) -> str:
    return hashlib.sha256(f"{item['id']}|{item['modificado']}|{' > '.join(item['pastas'])}".encode()).hexdigest()


def sincronizar(banco: str | None = None, enviar=comum.enviar_ao_cerebro, remover=comum.remover_do_cerebro,
                exportar_fn=exportar, token_fn=_token, arquivo_hashes: Path = ARQUIVO_HASHES) -> dict:
    """Envia ao Cérebro os nativos novos ou alterados das pastas liberadas e tira os que sumiram ou saíram delas."""
    try:
        hashes = json.loads(arquivo_hashes.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hashes = {}
    itens = [(i, e) for i in nativos(banco) if (e := empresa_no_cerebro(i))]
    atuais = {f"drive/nativo/{i['id']}" for i, _ in itens}
    mudados = [(i, e) for i, e in itens if hashes.get(f"drive/nativo/{i['id']}") != _hash(i)]
    enviados, falhas = 0, []
    token = token_fn() if mudados else None
    for item, empresa in mudados:
        ref = f"drive/nativo/{item['id']}"
        try:
            texto = exportar_fn(item["id"], item["mime"], token)
        except Exception as erro:
            falhas.append(f"{item['titulo']}: {erro}")
            continue
        if not texto.strip():
            hashes[ref] = _hash(item)  # arquivo vazio: nada a enviar, e não exporta de novo até ele mudar
        elif enviar([documento(item, texto, empresa)]):
            hashes[ref] = _hash(item)
            enviados += 1
    sumidos = [ref for ref in hashes if ref.startswith("drive/nativo/") and ref not in atuais]
    if sumidos and remover("drive", sumidos):
        for ref in sumidos:
            hashes.pop(ref, None)
    arquivo_hashes.parent.mkdir(parents=True, exist_ok=True)
    arquivo_hashes.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"liberados": len(itens), "mudados": len(mudados), "enviados": enviados, "removidos": len(sumidos),
            "falhas": falhas}


def rodar() -> None:
    """Versão tolerante a erros para o laço do trabalhador (sem login: só avisa)."""
    if not tem_login():
        return
    try:
        r = sincronizar()
        log(f"Drive (Docs e Planilhas do Google): {r['liberados']} liberado(s) ao Cérebro, {r['mudados']} alterado(s), "
            f"{r['enviados']} enviado(s), {r['removidos']} removido(s)"
            + (f"; falhas: {'; '.join(r['falhas'][:3])}" if r["falhas"] else "") + ".")
    except SemLogin as erro:
        log(f"Drive pela API parado: {erro}.")
    except Exception as erro:
        log(f"Drive (Docs e Planilhas do Google) falhou: {erro}")


# ---------- Linha de comando (no lugar do conector do claude.ai) ----------
def _resolver(alvo: str, banco: str | None = None) -> dict | None:
    """Link, ID ou caminho do G: -> {id, titulo, mime, pastas} (pelo banco do Drive do PC; ID desconhecido vai à API)."""
    achado = LINK_OU_ID.search(alvo.strip())
    itens = nativos(banco)
    if achado:
        arquivo_id = achado.group(1) or achado.group(2)
        return next((i for i in itens if i["id"] == arquivo_id), None) or {"id": arquivo_id, "pastas": []}
    partes = [p for p in re.split(r"[\\/]+", EXTENSOES.sub("", alvo.strip())) if p]
    if len(partes) < 2:
        return None

    def bate(item: dict) -> bool:  # o fim do caminho pedido = o fim do caminho do arquivo (o G: tem prefixos a mais)
        completo = [*item["pastas"], item["titulo"]]
        k = min(len(completo), len(partes))
        return completo[-k:] == partes[-k:]

    return next((i for i in itens if bate(i)), None)


def ler(alvo: str) -> str:
    item = _resolver(alvo)
    if not item:
        return "Não achei esse arquivo entre os Docs/Planilhas do Drive do PC. Passe o link ou o ID."
    token = _token()
    if "mime" not in item:  # ID que o Drive do PC não conhece: pergunta à API
        dados = _get(f"files/{item['id']}", {"fields": "id,name,mimeType", "supportsAllDrives": "true"}, token)
        item = {"id": dados["id"], "titulo": dados["name"], "mime": dados["mimeType"], "pastas": []}
    if sensivel(item):
        return f"'{item['titulo']}' tem cara de dado sensível (senha, banco, jurídico, cliente...): não leio por aqui."
    if item["mime"] not in EXPORTA:
        return f"'{item['titulo']}' não é Doc/Planilha/Apresentação do Google: leia pelo G: do PC."
    return f"# {item['titulo']}\n\n{exportar(item['id'], item['mime'], token)}"


def buscar(termo: str) -> str:
    token = _token()
    nome = termo.replace("\\", "\\\\").replace("'", "\\'")
    dados = _get("files", {"q": f"name contains '{nome}' and trashed = false", "corpora": "allDrives",
                           "includeItemsFromAllDrives": "true", "supportsAllDrives": "true", "pageSize": 25,
                           "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"}, token)
    arquivos = [a for a in dados.get("files", []) if not SENSIVEL.search(a["name"])]
    if not arquivos:
        return f"Nada com '{termo}' no nome."
    return "\n".join(f"- {a['name']} · {a['mimeType'].split('.')[-1]} · {a['modifiedTime'][:10]} · {a['webViewLink']}"
                     for a in arquivos)


def autorizar() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow  # só no login (ambiente do painel tem a biblioteca)

    print("O navegador vai abrir para o login do Google.")
    print(f"Escolha a conta que vê o drive compartilhado '{RAIZ}' e aceite a permissão de LEITURA do Drive.")
    print("O Escritório usa este login SÓ para ler: nada é criado, alterado ou apagado no seu Drive.\n")
    credenciais = InstalledAppFlow.from_client_secrets_file(str(CLIENTE), [ESCOPO]).run_local_server(port=0)
    try:
        drives = _get("drives", {"pageSize": 100}, credenciais.token).get("drives", [])
    except RuntimeError as erro:
        if "SERVICE_DISABLED" in str(erro) or "has not been used" in str(erro) or "disabled" in str(erro):
            print("\nERRO: a API do Google Drive está desativada no projeto do painel. Ative em\n"
                  "  https://console.cloud.google.com/apis/library/drive.googleapis.com\n"
                  "(mesmo projeto do painel), espere 2 minutos e rode este comando de novo. Nada foi gravado.")
        else:
            print(f"\nERRO ao conferir o Drive: {erro}\nNada foi gravado.")
        return
    if not any(d.get("name") == RAIZ for d in drives):
        print(f"\nERRO: esta conta não vê o drive '{RAIZ}'. Nada foi gravado; rode de novo com a conta certa.")
        return
    LOGIN.parent.mkdir(parents=True, exist_ok=True)
    LOGIN.write_text(json.dumps({"client_id": credenciais.client_id, "client_secret": credenciais.client_secret,
                                 "refresh_token": credenciais.refresh_token, "token_uri": credenciais.token_uri}),
                     encoding="utf-8")
    print(f"\nPronto: leitura do Drive autorizada ('{RAIZ}' encontrado).")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    comando, resto = (sys.argv[1] if len(sys.argv) > 1 else ""), " ".join(sys.argv[2:])
    if comando == "buscar":
        print(buscar(resto))
    elif comando == "ler":
        print(ler(resto))
    elif comando == "sincronizar":
        print(sincronizar())
    else:
        autorizar()
