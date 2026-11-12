"""Portão entre a internet e o PC (brainstorm de novembro, despachante-05).

O acesso externo chega por Worker → Workers VPC → Tunnel → 127.0.0.1:8000, então o IP de origem é sempre local e
não serve para separar "de fora" de "de dentro". O que separa são os cabeçalhos: o Worker sempre grava
X-Forwarded-Host, X-Forwarded-For e X-Escritorio-Borda (com `set`, por cima do que o visitante mandar) e repassa os
cabeçalhos que a Cloudflare põe na entrada (CF-Connecting-IP, CF-Ray). Quem está na internet consegue ACRESCENTAR
cabeçalhos, mas não tirar os que a borda põe; o trabalhador do Max (scripts/max/comum.py) chama localhost direto e
não manda nenhum deles. Por isso: qualquer um desses cabeçalhos presente = veio de fora. Um processo local que os
mande por engano só perde acesso (falha para o lado seguro), e não depende de segredo novo nem do Worker
republicado (X-Forwarded-Host já vem hoje).

Duas travas: (1) a chave de operador (dados/operador.token) é recusada quando o pedido veio de fora; o dono segue
usando o login dele (JWT) onde a rota aceita; (2) as rotas que só o trabalhador usa respondem 404 para quem vem de
fora, como se não existissem (o Worker também as barra antes de chegar ao PC).
"""

import hmac
import logging
import re

from fastapi import Request
from fastapi.responses import JSONResponse

import config

log = logging.getLogger("veraneio.borda")

# Cabeçalhos que só existem em pedido que passou pela borda (Worker ou Cloudflare). Em minúsculas.
CABECALHOS_DE_FORA = ("x-escritorio-borda", "x-forwarded-host", "x-forwarded-for", "forwarded", "x-real-ip",
                      "cf-connecting-ip", "cf-ray", "cf-worker", "cf-ipcountry")

# Rotas que só o trabalhador do Max chama (token de operador). Manter igual a ROTAS_INTERNAS do Worker.
CAMINHOS_INTERNOS = re.compile(
    r"^/api/producao/proxima/?$"
    r"|^/api/producao/\d+/(?:progresso|concluir|bloqueios|devolver|falhar|folha)/?$"
    r"|^/api/producao/trabalhos/\d+/(?:concluir|status|falhar)/?$"
    r"|^/api/uso-material/\d+/conferir/?$"  # avisos de material repetido (uso_material.py, Onda 3)
    r"|^/api/cerebro/ingerir/?$"
    r"|^/api/integracoes/monday/criativos/\d+/?$")


def veio_de_fora(cabecalhos) -> bool:
    """True se o pedido passou pela borda (internet). `cabecalhos`: Headers do Starlette ou dict."""
    nomes = {str(nome).lower() for nome in cabecalhos.keys()}
    return any(nome in nomes for nome in CABECALHOS_DE_FORA)


def caminho_interno(caminho: str) -> bool:
    return bool(CAMINHOS_INTERNOS.match(caminho or ""))


def _e_chave_operador(authorization: str) -> bool:
    recebido = (authorization or "").removeprefix("Bearer ").strip()
    arquivo = config.DADOS_DIR / "operador.token"
    if not recebido or not arquivo.exists():
        return False
    return hmac.compare_digest(recebido.encode(), arquivo.read_text(encoding="utf-8").strip().encode())


async def portao(request: Request, chamar_proximo):
    """Middleware HTTP (main.py). Pedido local passa direto; o de fora não usa a chave nem as rotas do trabalhador."""
    if not veio_de_fora(request.headers):
        return await chamar_proximo(request)
    if caminho_interno(request.scope.get("path", "")):  # já decodificado: %2F não dribla a trava
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if _e_chave_operador(request.headers.get("authorization", "")):
        # Chave de operador vinda da internet: ou vazou, ou alguém configurou o trabalhador pelo endereço público.
        log.warning("Chave de operador recusada: pedido vindo de fora do PC (%s %s)", request.method, request.url.path)
        return JSONResponse({"detail": "A chave de operador só vale dentro do PC"}, status_code=401)
    return await chamar_proximo(request)
