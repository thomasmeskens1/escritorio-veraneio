"""E-mails marketing já enviados (Brevo) para o Cérebro: o modelo de como os nossos e-mails são construídos.

Liberado pelo Thomas (26/10/2026) junto com o painel analítico (C:\\dev\\social-analytics): a chave do Brevo é lida
do .env do painel na hora (nunca copiada para o Escritório) e a API é usada SÓ para leitura.
Cada campanha enviada vira um documento da empresa dela: assunto, pré-header, remetente, o texto do e-mail na
ordem em que aparece, os botões (CTAs), quantas imagens e o desempenho (abertura e cliques, do painel analítico).
Marca: o prefixo que o Escritório põe nos rascunhos ("[Rascunho Escritório] VERO | ..."); senão Casa Vero pelo nome
("Vero 76", remetente Casa Vero) e a regra do painel (nome com Corp, off-site, empresa, confraternização...) mais o
assunto (painel_analitico). O resto é da Casa Veraneio.
Telefones e WhatsApp saem do texto (regra de ouro).

Uso: python scripts/max/emails_brevo.py (também roda no ciclo de 6 h do trabalhador).
"""

import html
import json
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

import comum
from comum import log
from painel_analitico import BANCO, EMAIL_CORP
from sites_empresas import TELEFONE

ENV_PAINEL = BANCO.parent / ".env"
API = "https://api.brevo.com/v3"
# Mesmo critério de backend/agents/ferramentas_brevo.py (empresa_da_campanha).
PREFIXOS = {"VERANEIO": "casa_veraneio", "CORP": "cv_corporativo", "VERO": "casa_vero"}
NOME_PADRAO = re.compile(r"\[Rascunho Escrit[óo]rio\]\s*(?:(VERANEIO|CORP|VERO)\s*\|\s*)?(?:\d{4}-\d{2}\s*\|\s*)?", re.I)
VERO = re.compile(r"\bvero\b", re.I)


def _chave() -> str | None:
    if not ENV_PAINEL.exists():
        return None
    for linha in ENV_PAINEL.read_text(encoding="utf-8").splitlines():
        if linha.startswith("BREVO_API_KEY="):
            return linha.split("=", 1)[1].strip()
    return None


def empresa_da_campanha(nome: str, assunto: str, remetente: str = "", marca_painel: str | None = None) -> str:
    if (achado := NOME_PADRAO.match((nome or "").strip())) and achado.group(1):
        return PREFIXOS[achado.group(1).upper()]
    texto = f"{NOME_PADRAO.sub('', nome or '')} {assunto or ''} {remetente or ''}"
    if VERO.search(texto):
        return "casa_vero"
    return "cv_corporativo" if marca_painel == "corp" or EMAIL_CORP.search(texto) else "casa_veraneio"


# Trava (prospectador-16, 31/10/2026): este script só LÊ campanhas enviadas. Nunca cria, importa nem lê contatos ou
# listas (o Brevo só recebe contato com consentimento; lead da Prospecção Ativa nunca vira lista).
CAMINHOS_PERMITIDOS = ("/emailCampaigns",)


def _get(caminho: str, chave: str) -> dict:
    if not caminho.startswith(CAMINHOS_PERMITIDOS) or re.search(r"/(contacts|lists|import)\b", caminho, re.I):
        raise PermissionError(f"Brevo: {caminho.split('?')[0]} não é permitido (só leitura de campanhas).")
    requisicao = urllib.request.Request(f"{API}{caminho}", headers={"api-key": chave, "accept": "application/json"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.load(resposta)


def _texto(trecho: str) -> str:
    sem_codigo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", trecho, flags=re.S | re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", sem_codigo)).replace("\u00ad", " ")
    return TELEFONE.sub("", re.sub(r"\s+", " ", texto)).strip()


def _botoes(conteudo: str) -> list[str]:
    """Texto dos links com cara de botão (CTA), na ordem do e-mail, sem repetir."""
    textos = [_texto(t) for t in re.findall(r"<a\b[^>]*>(.*?)</a>", conteudo, flags=re.S | re.I)]
    return list(dict.fromkeys(t for t in textos if 3 <= len(t) <= 80 and not t.lower().startswith(("http", "www"))))


def _desempenho() -> dict[int, dict]:
    if not BANCO.exists():
        return {}
    banco = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    banco.row_factory = sqlite3.Row
    try:
        return {l["campanha_id"]: dict(l) for l in banco.execute("SELECT * FROM brevo_campanhas")}
    finally:
        banco.close()


def documentos() -> list[dict]:
    chave = _chave()
    if not chave:
        log("E-mails do Brevo: chave não encontrada no .env do painel analítico.")
        return []
    campanhas = _get("/emailCampaigns?status=sent&limit=100&sort=desc&excludeHtmlContent=false", chave).get("campaigns", [])
    numeros = _desempenho()
    lista = []
    for c in campanhas:
        conteudo = c.get("htmlContent") or ""
        if not conteudo or (numeros.get(c["id"]) or {}).get("teste"):
            continue
        assunto, nome = c.get("subject") or "", c.get("name") or ""
        empresa = empresa_da_campanha(nome, assunto, (c.get("sender") or {}).get("name") or "",
                                      numeros.get(c["id"], {}).get("marca"))
        enviado = (c.get("sentDate") or c.get("scheduledAt") or "")[:10]
        partes = [f"Fonte: Brevo, campanha {c['id']} \"{nome}\" (e-mail marketing enviado em {enviado})",
                  f"Assunto: {assunto}", f"Pré-header: {c.get('previewText') or '—'}",
                  f"Remetente: {(c.get('sender') or {}).get('name') or '—'}",
                  f"Imagens no e-mail: {len(re.findall(r'<img', conteudo, re.I))} · botões/links: "
                  f"{len(re.findall(r'<a ', conteudo, re.I))}"]
        if (botoes := _botoes(conteudo)):
            partes.append("Botões (CTAs), na ordem: " + " | ".join(botoes[:15]))
        if (n := numeros.get(c["id"])) and n.get("entregues"):
            entregues = n["entregues"]
            partes.append(f"Desempenho: {entregues} entregues, abertura {100 * (n['aberturas'] or 0) / entregues:.1f}% "
                          f"(inclui aberturas automáticas do Apple Mail), cliques {100 * (n['cliques'] or 0) / entregues:.1f}%, "
                          f"descadastros {n['descadastros'] or 0}")
        partes.append(f"Texto do e-mail, na ordem: {_texto(conteudo)[:6000]}")
        lista.append({"fonte_tipo": "dados", "empresa": empresa, "fonte_ref": f"brevo/{empresa}/{c['id']}",
                      "titulo": f"E-mail marketing: {assunto[:120]}", "conteudo": "\n".join(partes)})
    return lista


def rodar() -> None:
    try:
        lista = documentos()
    except Exception as erro:  # Brevo fora do ar não derruba o trabalhador
        log(f"E-mails do Brevo: não foi possível ler ({erro}).")
        return
    if lista:
        enviados = comum.enviar_ao_cerebro(lista)
        log(f"E-mails do Brevo: {len(lista)} e-mail(s) para o Cérebro{'' if enviados else ' (envio adiado)'}.")


if __name__ == "__main__":
    rodar()
