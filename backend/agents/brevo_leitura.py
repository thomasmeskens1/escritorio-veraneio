"""Ler e revisar o e-mail que já está no Brevo pelo número (email_marketing-01, Onda 1 de novembro). SÓ LEITURA.

A equipe monta o e-mail sozinha no Brevo e mandava prints ou anexos para revisão; o agente via só pedaços. Agora o
E-mail Marketing lê a campanha pelo número (GET /emailCampaigns/{id}, o único caminho que esta ferramenta chama) e
recebe assunto, pré-header, os textos de cada bloco e os links dos botões, sem o código da página, mais a conferência
automática sobre o e-mail inteiro. Nunca grava: quem edita no Brevo é a equipe, e o agente devolve "trocar ESTE trecho
por ESTE". Campanha de outra empresa não é lida (as três nunca se misturam).
"""

import re
from html.parser import HTMLParser

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import conferente
import empresas
from agents import ferramentas_brevo as fb

MAX_BLOCOS, MAX_TEXTO = 40, 6000
BLOCOS = {"p", "div", "td", "h1", "h2", "h3", "h4", "li", "tr", "table", "br", "span"}
IGNORAR = {"style", "script", "head", "title"}
LODGE = re.compile(r"\b(?:lodge|vero)\s*#?0*(\d{1,4})\b", re.I)


class _Leitor(HTMLParser):
    """Textos visíveis por bloco e os links (texto do botão + endereço)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocos, self.links, self._atual, self._ignorar, self._link = [], [], [], 0, None

    def _fechar_bloco(self):
        if (texto := re.sub(r"\s+", " ", "".join(self._atual)).strip()):
            self.blocos.append(texto)
        self._atual = []

    def handle_starttag(self, tag, attrs):
        if tag in IGNORAR:
            self._ignorar += 1
        elif tag == "a":
            self._link = [dict(attrs).get("href") or "", []]
        if tag in BLOCOS:
            self._fechar_bloco()

    def handle_endtag(self, tag):
        if tag in IGNORAR:
            self._ignorar = max(0, self._ignorar - 1)
        elif tag == "a" and self._link is not None:
            self.links.append((re.sub(r"\s+", " ", "".join(self._link[1])).strip(), self._link[0].strip()))
            self._link = None
        if tag in BLOCOS:
            self._fechar_bloco()

    def handle_data(self, data):
        if self._ignorar:
            return
        self._atual.append(data)
        if self._link is not None:
            self._link[1].append(data)


def ler_html(conteudo: str) -> tuple[list[str], list[tuple[str, str]]]:
    leitor = _Leitor()
    leitor.feed(conteudo or "")
    leitor.close()
    leitor._fechar_bloco()
    return list(dict.fromkeys(leitor.blocos))[:MAX_BLOCOS], leitor.links


def _link_quebrado(endereco: str) -> bool:
    if re.fullmatch(r"\{\{\s*unsubscribe\s*\}\}", endereco or ""):
        return False
    return not re.match(r"^(https?://|mailto:)\S+$", endereco or "") or "{{" in endereco


def conferir_email(assunto: str, pre_header: str, blocos: list[str], links: list[tuple[str, str]],
                   empresa: str, conteudo: str = "") -> list[str]:
    """Avisos sobre o e-mail inteiro: as regras do conferente mais as do e-mail (links, botões, descadastro)."""
    texto = "\n".join([assunto, pre_header, *blocos])
    avisos = conferente.conferir(texto, empresa, "email")
    if (quebrados := [f"\"{t or '(sem texto)'}\" -> {e or '(vazio)'}" for t, e in links if _link_quebrado(e)]):
        avisos.append("link quebrado ou provisório: " + "; ".join(quebrados[:5]))
    botoes = " ".join(t for t, _ in links)
    if (sem_botao := sorted({n for n in LODGE.findall(texto)} - {n for n in LODGE.findall(botoes)}, key=int)):
        avisos.append("imóvel sem botão próprio: " + ", ".join(f"nº {n}" for n in sem_botao))
    if "unsubscribe" not in (conteudo or "") and not re.search(r"descadastr|sair da lista|n[aã]o quero mais", texto, re.I):
        avisos.append("sem o link de descadastro ({{ unsubscribe }}) no rodapé")
    if not 30 <= len(assunto or "") <= 50:
        avisos.append(f"assunto com {len(assunto or '')} caracteres (o padrão é de 30 a 50)")
    return avisos


def resumo(campanha: dict, empresa: str) -> str:
    blocos, links = ler_html(campanha.get("htmlContent") or "")
    assunto, pre = campanha.get("subject") or "", campanha.get("previewText") or ""
    avisos = conferir_email(assunto, pre, blocos, links, empresa, campanha.get("htmlContent") or "")
    linhas = [f"Campanha {campanha.get('id')} \"{campanha.get('name') or ''}\" (status: {campanha.get('status') or '?'}). "
              "Só li: nada foi alterado no Brevo.",
              f"ASSUNTO: {assunto}", f"PRÉ-HEADER: {pre}", "TEXTOS DOS BLOCOS (na ordem):"]
    linhas += [f"{n}. {b}" for n, b in enumerate(blocos, 1)]
    linhas.append("BOTÕES E LINKS:")
    linhas += [f"- \"{t or '(sem texto)'}\" -> {e or '(vazio)'}" for t, e in links] or ["- nenhum"]
    linhas.append(conferente.rodape(avisos, "Conferência do e-mail inteiro") or "Conferência do e-mail: nada a apontar.")
    linhas.append("Responda com uma lista curta \"trocar ESTE trecho por ESTE\"; quem aplica no editor do Brevo é a "
                  "equipe (não grave nada por cima deste e-mail).")
    return "\n".join(linhas)[:MAX_TEXTO]


class _Leitura(BaseModel):
    numero: int = Field(description="Número do rascunho ou da campanha no Brevo (ex.: 56)")


class LerRascunhoBrevo(BaseTool):
    name: str = "ler_rascunho_brevo"
    description: str = ("SÓ LEITURA. Lê um rascunho (ou campanha) de e-mail do Brevo pelo número e devolve assunto, "
                        "pré-header, os textos de cada bloco, os botões com os links e a conferência automática do "
                        "e-mail inteiro. Use quando o usuário pedir revisão de um e-mail que já está no Brevo. Nunca "
                        "altera nada.")
    args_schema: type[BaseModel] = _Leitura
    empresa: str = "casa_veraneio"

    def _run(self, numero: int) -> str:
        if self.empresa not in fb.NOMES:
            return "Empresa da conversa não reconhecida para o Brevo."
        if not (chave := fb._chave()):
            return "Brevo indisponível (chave do painel não encontrada). Peça o texto do e-mail no chat."
        try:
            campanha = fb._api("GET", f"/emailCampaigns/{int(numero)}", chave)  # só GET: nunca grava
        except fb.BrevoBloqueado as erro:
            return str(erro)
        except Exception as erro:
            return f"Não consegui ler a campanha {numero} no Brevo: {erro}"
        remetente = (campanha.get("sender") or {}).get("name") or ""
        dona = fb.empresa_da_campanha(campanha.get("name"), campanha.get("subject"), remetente)
        if dona != self.empresa:
            return (f"A campanha {numero} parece ser da {empresas.nome(dona)}, não da {empresas.nome(self.empresa)}: "
                    "não li o conteúdo. Confira o número ou troque a empresa da conversa.")
        return resumo(campanha, self.empresa)
