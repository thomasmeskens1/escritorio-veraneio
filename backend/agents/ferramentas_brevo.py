"""Ferramenta do E-mail Marketing no Brevo: cria a campanha como RASCUNHO (decisão do Thomas, 26/10/2026).

Nunca envia, nunca agenda e não escolhe lista: o Thomas revisa, põe as imagens e dispara pelo Brevo.
A chave é a do painel analítico (Sistema Casa Veraneio), lida do .env dele, montado só leitura em PAINEL_DIR
(docker-compose.yml); nada é copiado para o Escritório.
Remetente: o da última campanha enviada DA MESMA EMPRESA da tarefa (nunca o de outra marca); sem ela, um remetente
cadastrado com o nome da empresa. Um e-mail = um rascunho (31/10/2026): os ajustes na mesma conversa alteram o
rascunho já criado (PUT, só enquanto ainda é rascunho e ninguém mexeu nele à mão); outro só com "novo_email".
Rodapé com descadastro do Brevo ({{ unsubscribe }}) e o aviso de LGPD.
"""

import html
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import tarefas

API = "https://api.brevo.com/v3"
ENV_PAINEL = Path(os.getenv("PAINEL_DIR", "/painel")) / ".env"
# Cores por empresa (botão e destaque); o resto do visual o Thomas ajusta no Brevo.
CORES = {"casa_veraneio": "#2f4a3a", "cv_corporativo": "#1f3b2d", "casa_vero": "#b8743f"}
NOMES = {"casa_veraneio": "Casa Veraneio", "cv_corporativo": "Casa Veraneio Corporativo", "casa_vero": "Casa Vero Imóveis"}
# Prefixo do nome interno (o mesmo das pastas do Drive): "[Rascunho Escritório] VERANEIO | 2027-01 | Férias de janeiro"
PREFIXOS = {"casa_veraneio": "VERANEIO", "cv_corporativo": "CORP", "casa_vero": "VERO"}
MARCA = "[Rascunho Escritório]"
_NOME_PADRAO = re.compile(r"\[Rascunho Escrit[óo]rio\]\s*(?:(VERANEIO|CORP|VERO)\s*\|\s*)?(?:\d{4}-\d{2}\s*\|\s*)?", re.I)
# Mesma regra do painel (coleta/brevo.py) e de scripts/max/emails_brevo.py; a Casa Vero vem antes ("Vero 76").
_VERO = re.compile(r"\bvero\b", re.I)
_CORP = re.compile(r"\bcorp\b|corporativ|\boff-?site\b|\bempresa\b|confraterniza|\bseu time\b|\beventos?\b|"
                   r"escrit[óo]rio", re.I)
JANELA_CONVERSA = timedelta(days=3)  # ajustes de um mesmo e-mail costumam vir no mesmo dia ou no seguinte
_DETALHE = re.compile(r"campanha (\d+) \(alterada ([^)]*)\) (\d{4}-\d{2})")
RODAPE = ('<tr><td style="padding:24px 32px;border-top:1px solid #e7e1d8;color:#9a9086;font-size:12px;line-height:1.5">'
          "<strong>{nome}</strong><br>Você recebe este e-mail porque se cadastrou ou já falou com a {nome}. "
          "Seus dados são tratados conforme a LGPD (Lei 13.709/2018) e você pode sair da lista quando quiser.<br>"
          '<a href="{{{{ unsubscribe }}}}" style="color:#9a9086">Não quero mais receber estes e-mails</a></td></tr>')


class _Imovel(BaseModel):
    local: str = Field(description="Cidade e capacidade, ex.: 'Atibaia, SP | Até 40 hóspedes'")
    nome: str = Field(description="Ex.: 'Lodge 16' ou 'Vero 76'")
    texto: str = Field(description="1 a 2 frases com os diferenciais da ficha")
    botao_texto: str = Field(description="Ex.: 'QUERO CONHECER O LODGE 16'")
    botao_link: str = Field(description="Página do imóvel no site da empresa")


class _Rascunho(BaseModel):
    nome_campanha: str = Field(description="Tema do e-mail, curto, ex.: 'Férias de janeiro' (o prefixo da empresa e "
                                           "o mês entram sozinhos)")
    mes_do_tema: str = Field(description="Mês do tema no formato AAAA-MM (ex.: '2027-01' para férias de janeiro)")
    assunto: str = Field(description="30 a 50 caracteres, pergunta ou convite")
    pre_header: str = Field(description="50 a 80 caracteres, completa o assunto")
    titulo: str = Field(description="Título no topo do e-mail")
    abertura: str = Field(description="2 a 3 frases de abertura")
    botao_principal_texto: str = Field(description="CTA principal em maiúsculas, ex.: 'CONHEÇA NOSSOS LODGES'")
    botao_principal_link: str = Field(description="Link do botão principal (site da empresa)")
    imoveis: list[_Imovel] = Field(default_factory=list, description="2 a 4 imóveis em destaque")
    fecho: str = Field("", description="Frase final")
    novo_email: bool = Field(False, description="true SÓ quando o usuário pedir outro e-mail ou uma versão B; ajustes "
                                                "do mesmo e-mail alteram o rascunho já criado nesta conversa")


def empresa_da_campanha(nome: str = "", assunto: str = "", remetente: str = "") -> str:
    """Empresa de uma campanha do Brevo: pelo prefixo que esta ferramenta põe no nome ou, sem ele, pelas palavras."""
    if (achado := _NOME_PADRAO.match((nome or "").strip())) and achado.group(1):
        return {v: k for k, v in PREFIXOS.items()}[achado.group(1).upper()]
    texto = f"{_NOME_PADRAO.sub('', nome or '')} {assunto or ''} {remetente or ''}"
    if _VERO.search(texto):
        return "casa_vero"
    return "cv_corporativo" if _CORP.search(texto) else "casa_veraneio"


def mes_do_tema(valor: str, hoje: date | None = None) -> str:
    """AAAA-MM com o ano conferido: um mês que já passou vai para o ano seguinte (o modelo erra o ano, ex.: 2025)."""
    hoje = hoje or date.today()
    achado = re.search(r"(?:(\d{4})\D{0,3})?(\d{1,2})\s*$", (valor or "").strip())
    mes = int(achado.group(2)) if achado and 1 <= int(achado.group(2)) <= 12 else hoje.month
    proximo = hoje.year if mes >= hoje.month else hoje.year + 1
    ano = int(achado.group(1)) if achado and achado.group(1) and int(achado.group(1)) in (proximo, proximo + 1) else proximo
    return f"{ano:04d}-{mes:02d}"


def nome_interno(empresa: str, mes: str, tema: str) -> str:
    return f"{MARCA} {PREFIXOS[empresa]} | {mes} | {_NOME_PADRAO.sub('', tema or '').strip() or 'E-mail'}"[:250]


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


def _remetente(chave: str, empresa: str) -> dict | None:
    """Remetente da empresa da tarefa: o da última campanha enviada por ela; senão, um remetente ativo com o nome dela."""
    enviadas = _api("GET", "/emailCampaigns?status=sent&limit=50&sort=desc&excludeHtmlContent=true", chave)
    for c in enviadas.get("campaigns") or []:
        s = c.get("sender") or {}
        if s.get("email") and empresa_da_campanha(c.get("name"), c.get("subject"), s.get("name")) == empresa:
            return {"name": s.get("name") or NOMES[empresa], "email": s["email"]}
    for s in _api("GET", "/senders", chave).get("senders") or []:
        nome = s.get("name") or ""
        if (s.get("active", True) and s.get("email") and re.search(r"veraneio|vero", nome, re.I)
                and empresa_da_campanha("", "", nome) == empresa):
            return {"name": nome, "email": s["email"]}
    return None


def _rascunho_da_conversa(tarefa_id: int, mes: str) -> tuple[int, str, int] | None:
    """(campanha, alterada_em, versões) do último rascunho do mesmo e-mail nesta conversa: mesmo usuário, andar,
    agente e empresa, nos últimos dias, com o mesmo mês do tema."""
    atual = tarefas.obter(tarefa_id) if tarefa_id else None
    if not atual:
        return None
    desde = (datetime.now(timezone.utc) - JANELA_CONVERSA).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = tarefas._db().execute(
        "SELECT e.detalhe FROM eventos e JOIN tarefas t ON t.id = e.tarefa_id WHERE e.tipo = 'rascunho_brevo' "
        "AND t.usuario = ? AND t.andar = ? AND t.agente = ? AND COALESCE(t.empresa, '') = COALESCE(?, '') "
        "AND t.id <= ? AND e.em >= ? ORDER BY e.id DESC",
        (atual["usuario"], atual["andar"], atual["agente"], atual["empresa"], tarefa_id, desde)).fetchall()
    achados = [m for l in linhas if (m := _DETALHE.match(l["detalhe"] or ""))]
    if not achados or achados[0].group(3) != mes:
        return None
    campanha = int(achados[0].group(1))
    return campanha, achados[0].group(2), sum(int(m.group(1)) == campanha for m in achados)


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
    return ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
            f'<body style="margin:0;background:#f6f3ee;font-family:Arial,Helvetica,sans-serif">'
            f'<span style="display:none;max-height:0;overflow:hidden">{e(r.pre_header)}</span>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;max-width:600px">'
            f'<tr><td style="padding:32px 32px 8px"><h1 style="margin:0;color:#2b2b2b;font-size:26px">{e(r.titulo)}</h1></td></tr>'
            f'<tr><td style="padding:8px 32px 24px;color:#4a4a4a;font-size:16px;line-height:1.55">{e(r.abertura)}</td></tr>'
            f'<tr><td style="padding:0 32px 32px">{_botao(r.botao_principal_texto, r.botao_principal_link, cor)}</td></tr>'
            f"{blocos}{fecho}{RODAPE.format(nome=e(NOMES[empresa]))}"
            f"</table></td></tr></table></body></html>")


class CriarRascunhoBrevo(BaseTool):
    name: str = "criar_rascunho_brevo"
    description: str = ("Cria a campanha de e-mail como RASCUNHO no Brevo (nunca envia, agenda nem escolhe lista; o "
                        "Thomas revisa, põe as imagens e dispara). Use depois de escrever o e-mail completo no padrão "
                        "do manual. Nos ajustes do mesmo e-mail, chame de novo: o mesmo rascunho é atualizado. "
                        "Devolve o número do rascunho ou o erro.")
    args_schema: type[BaseModel] = _Rascunho
    empresa: str = "casa_veraneio"
    tarefa_id: int = 0

    def _run(self, **campos) -> str:
        if self.empresa not in NOMES:
            return "Empresa da conversa não reconhecida para o Brevo. Entregue o e-mail só no chat."
        chave = _chave()
        if not chave:
            return "Brevo indisponível (chave do painel não encontrada). Entregue o e-mail só no chat."
        r = _Rascunho(**campos)
        mes = mes_do_tema(r.mes_do_tema)
        nome = nome_interno(self.empresa, mes, r.nome_campanha)
        anterior = None if r.novo_email else _rascunho_da_conversa(self.tarefa_id, mes)
        aviso = ""
        try:
            remetente = _remetente(chave, self.empresa)
            if not remetente:
                return (f"Não achei no Brevo um remetente da {NOMES[self.empresa]} (nenhuma campanha enviada por ela "
                        "nem remetente com o nome dela). Entregue o e-mail só no chat.")
            corpo = {"name": nome, "subject": r.assunto, "previewText": r.pre_header,
                     "htmlContent": _html(r, self.empresa), "sender": remetente}
            campanha, versao = None, 1
            if anterior:
                atual = _api("GET", f"/emailCampaigns/{anterior[0]}", chave)
                if atual.get("status") == "draft" and atual.get("modifiedAt") == anterior[1]:
                    _api("PUT", f"/emailCampaigns/{anterior[0]}", chave, corpo)
                    campanha, versao = anterior[0], anterior[2] + 1
                else:
                    aviso = (f" O rascunho {anterior[0]} já foi editado no Brevo ou não é mais rascunho, então não "
                             "mexi nele: criei outro.")
            if campanha is None:
                campanha = _api("POST", "/emailCampaigns", chave, corpo).get("id")
            alterada = _api("GET", f"/emailCampaigns/{campanha}", chave).get("modifiedAt") or ""
        except Exception as erro:
            return f"Não foi possível salvar o rascunho no Brevo: {erro}"
        if self.tarefa_id:
            tarefas.registrar_evento(self.tarefa_id, "rascunho_brevo", "email_marketing",
                                     detalhe=f"campanha {campanha} (alterada {alterada}) {mes}: {r.assunto}")
        if versao > 1:
            return (f"Atualizei o rascunho {campanha} no Brevo (versão {versao}, \"{nome}\"), sem criar outro. "
                    "Continua como rascunho: falta escolher a lista, revisar, pôr as imagens e enviar.")
        return (f"Rascunho criado no Brevo (campanha {campanha}, \"{nome}\").{aviso} Está em Campanhas > E-mail, "
                "como rascunho: falta escolher a lista, revisar, pôr as imagens e enviar.")


def para(agente_id: str, empresa: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramenta do Brevo (só o E-mail Marketing, só na conta do Thomas e só se a chave do painel estiver montada)."""
    if agente_id != "email_marketing" or not _chave():
        return []
    return [CriarRascunhoBrevo(empresa=empresa, tarefa_id=tarefa_id)]
