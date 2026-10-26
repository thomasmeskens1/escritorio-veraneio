"""Ferramenta do E-mail Marketing no Brevo: cria a campanha como RASCUNHO (decisão do Thomas, 26/10/2026).

Nunca envia, nunca agenda e não escolhe lista: o Thomas revisa, põe as imagens e dispara pelo Brevo.
A chave é a do painel analítico (Sistema Casa Veraneio), lida do .env dele, montado só leitura em PAINEL_DIR
(docker-compose.yml); nada é copiado para o Escritório. Remetente: o mesmo da última campanha enviada.
"""

import html
import json
import os
import urllib.request
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import tarefas

API = "https://api.brevo.com/v3"
ENV_PAINEL = Path(os.getenv("PAINEL_DIR", "/painel")) / ".env"
# Cores por empresa (botão e destaque); o resto do visual o Thomas ajusta no Brevo.
CORES = {"casa_veraneio": "#2f4a3a", "cv_corporativo": "#1f3b2d", "casa_vero": "#b8743f"}
NOMES = {"casa_veraneio": "Casa Veraneio", "cv_corporativo": "Casa Veraneio Corporativo", "casa_vero": "Casa Vero Imóveis"}


class _Imovel(BaseModel):
    local: str = Field(description="Cidade e capacidade, ex.: 'Atibaia, SP | Até 40 hóspedes'")
    nome: str = Field(description="Ex.: 'Lodge 16' ou 'Vero 76'")
    texto: str = Field(description="1 a 2 frases com os diferenciais da ficha")
    botao_texto: str = Field(description="Ex.: 'QUERO CONHECER O LODGE 16'")
    botao_link: str = Field(description="Página do imóvel no site da empresa")


class _Rascunho(BaseModel):
    nome_campanha: str = Field(description="Nome interno da campanha no Brevo")
    assunto: str = Field(description="30 a 50 caracteres, pergunta ou convite")
    pre_header: str = Field(description="50 a 80 caracteres, completa o assunto")
    titulo: str = Field(description="Título no topo do e-mail")
    abertura: str = Field(description="2 a 3 frases de abertura")
    botao_principal_texto: str = Field(description="CTA principal em maiúsculas, ex.: 'CONHEÇA NOSSOS LODGES'")
    botao_principal_link: str = Field(description="Link do botão principal (site da empresa)")
    imoveis: list[_Imovel] = Field(default_factory=list, description="2 a 4 imóveis em destaque")
    fecho: str = Field("", description="Frase final")


def _chave() -> str | None:
    if not ENV_PAINEL.exists():
        return None
    for linha in ENV_PAINEL.read_text(encoding="utf-8").splitlines():
        if linha.startswith("BREVO_API_KEY="):
            return linha.split("=", 1)[1].strip()
    return None


def _api(metodo: str, caminho: str, chave: str, corpo: dict | None = None) -> dict:
    requisicao = urllib.request.Request(f"{API}{caminho}", method=metodo,
                                        data=json.dumps(corpo).encode() if corpo is not None else None,
                                        headers={"api-key": chave, "accept": "application/json",
                                                 "content-type": "application/json"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        dados = resposta.read()
    return json.loads(dados) if dados else {}


def _botao(texto: str, link: str, cor: str) -> str:
    return (f'<a href="{html.escape(link, quote=True)}" style="display:inline-block;padding:14px 24px;background:{cor};'
            f'color:#ffffff;text-decoration:none;font-weight:bold;border-radius:4px;font-size:14px">'
            f"{html.escape(texto)}</a>")


def _html(r: _Rascunho, empresa: str) -> str:
    cor, e = CORES.get(empresa, "#2f4a3a"), html.escape
    blocos = "".join(
        f'<tr><td style="padding:24px 32px;border-top:1px solid #e7e1d8">'
        f'<p style="margin:0;color:#7a7065;font-size:13px">{e(i.local)}</p>'
        f'<h3 style="margin:6px 0 10px;color:#2b2b2b;font-size:20px">{e(i.nome)}</h3>'
        f'<p style="margin:0 0 16px;color:#4a4a4a;font-size:15px;line-height:1.5">{e(i.texto)}</p>'
        f"{_botao(i.botao_texto, i.botao_link, cor)}</td></tr>" for i in r.imoveis)
    fecho = f'<tr><td style="padding:24px 32px;color:#4a4a4a;font-size:15px">{e(r.fecho)}</td></tr>' if r.fecho else ""
    return (f'<!DOCTYPE html><html><body style="margin:0;background:#f6f3ee;font-family:Arial,Helvetica,sans-serif">'
            f'<span style="display:none;max-height:0;overflow:hidden">{e(r.pre_header)}</span>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;max-width:600px">'
            f'<tr><td style="padding:32px 32px 8px"><h1 style="margin:0;color:#2b2b2b;font-size:26px">{e(r.titulo)}</h1></td></tr>'
            f'<tr><td style="padding:8px 32px 24px;color:#4a4a4a;font-size:16px;line-height:1.55">{e(r.abertura)}</td></tr>'
            f'<tr><td style="padding:0 32px 32px">{_botao(r.botao_principal_texto, r.botao_principal_link, cor)}</td></tr>'
            f"{blocos}{fecho}"
            f'<tr><td style="padding:24px 32px;color:#9a9086;font-size:12px">{e(NOMES.get(empresa, "Casa Veraneio"))}</td></tr>'
            f"</table></td></tr></table></body></html>")


class CriarRascunhoBrevo(BaseTool):
    name: str = "criar_rascunho_brevo"
    description: str = ("Cria a campanha de e-mail como RASCUNHO no Brevo (nunca envia, agenda nem escolhe lista; o "
                        "Thomas revisa, põe as imagens e dispara). Use depois de escrever o e-mail completo no padrão "
                        "do manual. Devolve o número do rascunho ou o erro.")
    args_schema: type[BaseModel] = _Rascunho
    empresa: str = "casa_veraneio"
    tarefa_id: int = 0

    def _run(self, **campos) -> str:
        chave = _chave()
        if not chave:
            return "Brevo indisponível (chave do painel não encontrada). Entregue o e-mail só no chat."
        rascunho = _Rascunho(**campos)
        try:
            ultimas = _api("GET", "/emailCampaigns?status=sent&limit=1&sort=desc", chave).get("campaigns") or []
            remetente = (ultimas[0].get("sender") if ultimas else None) or {}
            if not remetente.get("email"):
                return "Não achei o remetente das campanhas anteriores no Brevo. Entregue o e-mail só no chat."
            criada = _api("POST", "/emailCampaigns", chave, {
                "name": f"[Rascunho Escritório] {rascunho.nome_campanha}"[:250], "subject": rascunho.assunto,
                "previewText": rascunho.pre_header, "htmlContent": _html(rascunho, self.empresa),
                "sender": {"name": remetente.get("name") or "Casa Veraneio", "email": remetente["email"]}})
        except Exception as erro:
            return f"Não foi possível criar o rascunho no Brevo: {erro}"
        if self.tarefa_id:
            tarefas.registrar_evento(self.tarefa_id, "rascunho_brevo", "email_marketing",
                                     detalhe=f"campanha {criada.get('id')}: {rascunho.assunto}")
        return (f"Rascunho criado no Brevo (campanha {criada.get('id')}, \"{rascunho.nome_campanha}\"). Está em "
                "Campanhas > E-mail, como rascunho: falta escolher a lista, revisar, pôr as imagens e enviar.")


def para(agente_id: str, empresa: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramenta do Brevo (só o E-mail Marketing, só na conta do Thomas e só se a chave do painel estiver montada)."""
    if agente_id != "email_marketing" or not _chave():
        return []
    return [CriarRascunhoBrevo(empresa=empresa, tarefa_id=tarefa_id)]
