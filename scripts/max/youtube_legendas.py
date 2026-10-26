"""Legendas do YouTube da Casa Vero pela API oficial (escolha do Thomas, 26/10/2026).

O download de legendas por fora (yt-dlp) passou a ser recusado pelo YouTube (429). Pela API, o dono do canal baixa as
legendas dos próprios vídeos, mas o Google exige a permissão youtube.force-ssl (gerenciar o canal) até para isso.
Este login é SÓ do Escritório (o do painel analítico continua só leitura) e é usado SÓ para ler: lista de vídeos,
dados de cada vídeo e download de legendas. Nada é alterado no canal.

Login (uma vez, no navegador; o app do Google em modo Teste pede de novo a cada 7 dias):
  C:\\dev\\social-analytics\\venv\\Scripts\\python.exe scripts\\max\\youtube_legendas.py
Usa o cliente OAuth do painel (%LOCALAPPDATA%\\SocialAnalytics\\credenciais_google.json) e grava o login em
backend/dados/youtube_legendas.token.json (fora do git).

Cota da API: 10.000 unidades por dia; listar legendas = 50, baixar = 200, dados do vídeo = 1. LIMITE_DIARIO deixa
folga para o painel, que usa o mesmo projeto do Google.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

CANAL = "UClSXjsr4I17PslswQpLqzYQ"  # Casa Vero Imóveis
API = "https://www.googleapis.com/youtube/v3"
ESCOPO = "https://www.googleapis.com/auth/youtube.force-ssl"
CLIENTE = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", Path(os.environ.get("LOCALAPPDATA", "")) / "SocialAnalytics")) / "credenciais_google.json"
LOGIN = comum.DADOS / "youtube_legendas.token.json"
COTA = comum.DADOS / "youtube_legendas.cota.json"
LIMITE_DIARIO = 8000
CUSTO = {"captions_list": 50, "captions_download": 200, "videos": 1, "playlistItems": 1, "channels": 1}


class SemLogin(Exception):
    """Sem login válido (ainda não autorizado, ou vencido): o leitor volta ao caminho antigo."""


class CotaEsgotada(Exception):
    pass


def tem_login() -> bool:
    return LOGIN.exists()


def _token() -> str:
    login = json.loads(LOGIN.read_text(encoding="utf-8"))
    corpo = urllib.parse.urlencode({"client_id": login["client_id"], "client_secret": login["client_secret"],
                                    "refresh_token": login["refresh_token"], "grant_type": "refresh_token"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(login["token_uri"], data=corpo), timeout=30) as resposta:
            return json.load(resposta)["access_token"]
    except urllib.error.HTTPError as erro:
        raise SemLogin(f"login do YouTube vencido ou revogado ({erro.code}); rode o login de novo") from erro


def _gastar(operacao: str) -> None:
    hoje = date.today().isoformat()
    uso = json.loads(COTA.read_text(encoding="utf-8")) if COTA.exists() else {}
    if uso.get("dia") != hoje:
        uso = {"dia": hoje, "unidades": 0}
    if uso["unidades"] + CUSTO[operacao] > LIMITE_DIARIO:
        raise CotaEsgotada(f"cota diária do YouTube usada ({uso['unidades']} unidades); continua amanhã")
    uso["unidades"] += CUSTO[operacao]
    COTA.write_text(json.dumps(uso), encoding="utf-8")


def _get(caminho: str, parametros: dict, token: str, operacao: str, bruto: bool = False):
    _gastar(operacao)
    requisicao = urllib.request.Request(f"{API}/{caminho}?{urllib.parse.urlencode(parametros)}",
                                        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return resposta.read().decode("utf-8", errors="replace") if bruto else json.load(resposta)


def ids_do_canal(token: str) -> list[str]:
    """Todos os vídeos e shorts do canal (playlist de uploads)."""
    uploads = _get("channels", {"part": "contentDetails", "id": CANAL}, token, "channels")["items"][0][
        "contentDetails"]["relatedPlaylists"]["uploads"]
    ids, pagina = [], None
    while True:
        parametros = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if pagina:
            parametros["pageToken"] = pagina
        dados = _get("playlistItems", parametros, token, "playlistItems")
        ids += [i["contentDetails"]["videoId"] for i in dados.get("items", [])]
        if not (pagina := dados.get("nextPageToken")):
            return ids


def video(video_id: str, token: str) -> dict:
    """Título, data, duração, descrição e a legenda em português (VTT; "" se o vídeo não tiver)."""
    itens = _get("videos", {"part": "snippet,contentDetails", "id": video_id}, token, "videos")["items"]
    if not itens:
        return {"id": video_id, "erro": "vídeo não encontrado ou privado"}
    trecho = itens[0]["snippet"]
    faixas = _get("captions", {"part": "snippet", "videoId": video_id}, token, "captions_list").get("items", [])
    portugues = [f for f in faixas if f["snippet"]["language"].lower().startswith("pt")]
    # Prefere a legenda feita pela equipe; senão, a automática do YouTube (trackKind "asr").
    portugues.sort(key=lambda f: f["snippet"].get("trackKind", "").lower() == "asr")
    vtt = _get(f"captions/{portugues[0]['id']}", {"tfmt": "vtt"}, token, "captions_download", bruto=True) if portugues else ""
    return {"id": video_id, "titulo": trecho["title"], "data": trecho["publishedAt"][:10].replace("-", ""),
            "descricao": trecho.get("description", ""), "vtt": vtt}


def autorizar() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow  # só no login (ambiente do painel tem a biblioteca)

    print("O navegador vai abrir para o login do Google.")
    print("Escolha a conta que administra o canal 'Casa Vero Imóveis' e aceite a permissão do YouTube.")
    print("O Escritório usa este login SÓ para ler a lista de vídeos e baixar as legendas.\n")
    credenciais = InstalledAppFlow.from_client_secrets_file(str(CLIENTE), [ESCOPO]).run_local_server(port=0)
    canal = json.load(urllib.request.urlopen(urllib.request.Request(
        f"{API}/channels?part=snippet&mine=true", headers={"Authorization": f"Bearer {credenciais.token}"}), timeout=30))
    item = (canal.get("items") or [{}])[0]
    if item.get("id") != CANAL:
        print(f"\nERRO: o login foi feito em '{item.get('snippet', {}).get('title', 'conta sem canal')}', não no canal da "
              "Casa Vero Imóveis. Nada foi gravado; rode de novo e escolha o canal certo.")
        return
    LOGIN.parent.mkdir(parents=True, exist_ok=True)
    LOGIN.write_text(json.dumps({"client_id": credenciais.client_id, "client_secret": credenciais.client_secret,
                                 "refresh_token": credenciais.refresh_token, "token_uri": credenciais.token_uri}),
                     encoding="utf-8")
    print(f"\nPronto: canal '{item['snippet']['title']}' autorizado para leitura de legendas.")


if __name__ == "__main__":
    autorizar()
