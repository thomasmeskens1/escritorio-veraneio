"""Trocar SÓ o assunto ou o pré-header de um rascunho do Brevo, sem criar outro (email_marketing-02, Onda 3).

Antes, qualquer ajuste pedido no chat depois que o Thomas mexia no rascunho dentro do Brevo (imagens, blocos) criava
um rascunho NOVO, até para trocar uma palavra do assunto. Agora o E-mail Marketing tem uma ferramenta própria (campo
explícito, sem o modelo adivinhar): manda ao Brevo só "subject" e "previewText" num PUT, sem o HTML, e o trabalho
manual fica como estava. Continua rascunho: nunca envia, agenda nem escolhe lista (a trava de ferramentas_brevo
vale aqui também). Campanha de outra empresa ou que já não é rascunho não é tocada.
"""

from datetime import datetime, timezone

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import conferente
import empresas
import tarefas
from agents import ferramentas_brevo as fb

LIMITE_ASSUNTO, LIMITE_PRE = 150, 250  # tamanhos aceitos pelo Brevo; o padrão do manual o conferente avisa


class _Troca(BaseModel):
    numero: int = Field(0, description="Número do rascunho no Brevo (ex.: 57); 0 = o último rascunho desta conversa")
    assunto: str = Field("", description="Assunto novo; vazio = não muda")
    pre_header: str = Field("", description="Pré-header novo; vazio = não muda")


def avisos(assunto: str, pre_header: str, empresa: str) -> list[str]:
    """Conferente de texto sobre o que vai mudar, mais o tamanho padrão do assunto (30 a 50)."""
    lista = conferente.conferir("\n".join(t for t in (assunto, pre_header) if t), empresa, "arte")  # sem CRECI/ficha: é só a linha
    if assunto and not 30 <= len(assunto) <= 50:
        lista.append(f"assunto com {len(assunto)} caracteres (o padrão é de 30 a 50)")
    return lista


class TrocarAssuntoBrevo(BaseTool):
    name: str = "trocar_assunto_brevo"
    description: str = ("Troca SÓ o assunto e/ou o pré-header de um rascunho de e-mail que já está no Brevo, sem "
                        "reenviar o HTML e sem criar outro rascunho (as imagens e edições feitas no Brevo ficam como "
                        "estão). Use quando o pedido muda apenas o assunto ou o pré-header. Nunca envia nem agenda. "
                        "Para mudar o corpo do e-mail, use criar_rascunho_brevo.")
    args_schema: type[BaseModel] = _Troca
    empresa: str = "casa_veraneio"
    tarefa_id: int = 0

    def _run(self, numero: int = 0, assunto: str = "", pre_header: str = "") -> str:
        assunto, pre_header = (assunto or "").strip(), (pre_header or "").strip()
        if self.empresa not in fb.NOMES:
            return "Empresa da conversa não reconhecida para o Brevo."
        if not assunto and not pre_header:
            return "Nada para trocar: diga o assunto ou o pré-header novo."
        if len(assunto) > LIMITE_ASSUNTO or len(pre_header) > LIMITE_PRE:
            return f"Assunto (até {LIMITE_ASSUNTO}) ou pré-header (até {LIMITE_PRE}) longo demais: encurte e tente de novo."
        if not (chave := fb._chave()):
            return "Brevo indisponível (chave do painel não encontrada). Entregue o assunto novo só no chat."
        if not numero:  # o último rascunho registrado nesta conversa (qualquer mês do tema)
            if not (anterior := _ultimo_da_conversa(self.tarefa_id)):
                return "Não achei rascunho desta conversa no Brevo: diga o número do rascunho."
            numero = anterior[0]
        try:
            campanha = fb._api("GET", f"/emailCampaigns/{int(numero)}", chave)
            remetente = (campanha.get("sender") or {}).get("name") or ""
            dona = fb.empresa_da_campanha(campanha.get("name"), campanha.get("subject"), remetente)
            if dona != self.empresa:
                return (f"O rascunho {numero} parece ser da {empresas.nome(dona)}, não da "
                        f"{empresas.nome(self.empresa)}: não mexi nele.")
            if campanha.get("status") != "draft":
                return f"A campanha {numero} não é mais rascunho (status {campanha.get('status')}): não mexi nela."
            corpo = {c: v for c, v in (("subject", assunto), ("previewText", pre_header)) if v}
            fb._api("PUT", f"/emailCampaigns/{int(numero)}", chave, corpo)  # só estes campos: o HTML não vai
            alterada = fb._api("GET", f"/emailCampaigns/{int(numero)}", chave).get("modifiedAt") or ""
        except fb.BrevoBloqueado as erro:
            return str(erro)
        except Exception as erro:
            return f"Não foi possível trocar o assunto no Brevo: {erro}"
        self._registrar(int(numero), campanha.get("modifiedAt") or "", alterada, assunto or campanha.get("subject") or "")
        trocados = " e ".join(n for n, v in (("o assunto", assunto), ("o pré-header", pre_header)) if v)
        linha = conferente.rodape(avisos(assunto, pre_header, self.empresa), "Conferência do assunto")
        return (f"Troquei só {trocados} do rascunho {numero} no Brevo, sem criar outro. Suas imagens e edições "
                f"ficaram como estavam. Continua como rascunho: nada foi enviado.{f' {linha}' if linha else ''}")

    def _registrar(self, numero: int, antes: str, alterada: str, assunto: str) -> None:
        """Se o rascunho era o desta conversa e ninguém tinha mexido nele à mão, a conversa continua dona dele (o
        próximo ajuste do corpo ainda o atualiza). Editado no Brevo: só registra a troca (o corpo continua
        protegido, e um ajuste do corpo cria outro rascunho, como antes)."""
        if not self.tarefa_id:
            return
        dono = _ultimo_da_conversa(self.tarefa_id)
        if dono and dono[0] == numero and dono[1] == antes:
            tarefas.registrar_evento(self.tarefa_id, "rascunho_brevo", "email_marketing",
                                     detalhe=f"campanha {numero} (alterada {alterada}) {dono[2]}: {assunto}")
        else:
            tarefas.registrar_evento(self.tarefa_id, "assunto_brevo", "email_marketing",
                                     detalhe=f"campanha {numero}: só assunto/pré-header trocados ({assunto})")


def _ultimo_da_conversa(tarefa_id: int) -> tuple[int, str, str] | None:
    """(campanha, alterada_em, mês do tema) do último rascunho registrado nesta conversa, qualquer mês."""
    atual = tarefas.obter(tarefa_id) if tarefa_id else None
    if not atual:
        return None
    desde = (datetime.now(timezone.utc) - fb.JANELA_CONVERSA).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = tarefas._db().execute(
        "SELECT e.detalhe FROM eventos e JOIN tarefas t ON t.id = e.tarefa_id WHERE e.tipo = 'rascunho_brevo' "
        "AND t.usuario = ? AND t.andar = ? AND t.agente = ? AND COALESCE(t.empresa, '') = COALESCE(?, '') "
        "AND t.id <= ? AND e.em >= ? ORDER BY e.id DESC LIMIT 1",
        (atual["usuario"], atual["andar"], atual["agente"], atual["empresa"], tarefa_id, desde)).fetchone()
    achado = fb._DETALHE.match(linhas["detalhe"] or "") if linhas else None
    return (int(achado.group(1)), achado.group(2), achado.group(3)) if achado else None
