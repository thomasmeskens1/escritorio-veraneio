"""Ferramentas do Social Media no board do Monday (Planejamento Automático 2026).

ver_planejamento_monday: itens de um mês (grupo), para não duplicar.
criar_item_monday: cria o elemento no grupo do mês certo ("planejamento de dezembro" → grupo Dezembro;
o grupo é criado se ainda não existir), com datas, horário, objetivo, conta, responsável e legenda.
"""

import re

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import monday
import tarefas

OBJETIVOS = ["Venda", "Comercial", "Interação", "Informativo/Educacional", "Criativo", "Síte"]
RESPONSAVEIS = ["Bruna", "Fran", "Luiz", "Thomas"]
CONTAS = ["Casa Veraneio", "Casa Vero", "CV Corp", "Sem definição"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]
MAX_ITENS_POR_TAREFA = 40
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _escolher(valor: str, opcoes: list[str]) -> str | None:
    return next((o for o in opcoes if monday._chave(o) == monday._chave(valor or "")), None)


class _Grupo(BaseModel):
    grupo: str = Field(description="Mês do planejamento, exatamente como o grupo: ex. 'Dezembro'")


class _NovoItem(BaseModel):
    nome: str = Field(description="'TIPO | Descrição'. TIPO é um de: STORIES, POST (single post estático), CARROSSEL, "
                                  "REELS, SHORTS. Ex.: 'POST | As melhores casas para o seu Réveillon'")
    grupo: str = Field(description="Mês do item = grupo do board: ex. 'Dezembro'")
    data_postagem: str = Field("", description="AAAA-MM-DD")
    data_entrega: str = Field("", description="AAAA-MM-DD (alguns dias antes da postagem)")
    horario: str = Field("", description="HH:MM, 24 h")
    objetivo: str = Field("", description=f"Um de: {', '.join(OBJETIVOS)}")
    responsavel: str = Field("", description=f"Um de: {', '.join(RESPONSAVEIS)}. Obrigatório e sempre o que o "
                                             "usuário disse: nunca escolha por conta própria.")
    conta: str = Field("Casa Veraneio", description=f"Marca: {', '.join(CONTAS)}")
    legenda: str = Field("", description="Rascunho da legenda, só para POST, CARROSSEL, REELS e SHORTS. Para STORIES "
                                         "deixe VAZIO e não escreva nenhuma legenda (stories não têm legenda).")


class VerPlanejamentoMonday(BaseTool):
    name: str = "ver_planejamento_monday"
    description: str = ("Lista os itens já planejados num mês (grupo) do board de Social Media no Monday, com data "
                        "de postagem e status. Use antes de criar itens, para não duplicar.")
    args_schema: type[BaseModel] = _Grupo

    def _run(self, grupo: str) -> str:
        try:
            achado = monday.grupo_por_nome(grupo)
            if not achado:
                return f"O grupo '{grupo}' ainda não existe no board (ele é criado ao criar o primeiro item)."
            itens = monday.itens_do_grupo(achado["id"])
        except Exception as erro:
            return f"Não foi possível ler o Monday agora: {erro}"
        if not itens:
            return f"O grupo {achado['title']} está vazio."
        linhas = [f"- {i['name']} | " + " | ".join(f"{c['id']}: {c['text'] or '—'}" for c in i["column_values"])
                  for i in itens]
        return f"Itens em {achado['title']} ({len(itens)}):\n" + "\n".join(linhas)


class CriarItemMonday(BaseTool):
    name: str = "criar_item_monday"
    description: str = ("Cria um elemento (peça do planejamento) no board de Social Media do Monday, DENTRO do "
                        "grupo do mês certo (planejamento de dezembro → grupo 'Dezembro'). Um item por peça. "
                        "STORIES: sem legenda (campo vazio). "
                        "Devolve a confirmação com o link ou o erro a corrigir.")
    args_schema: type[BaseModel] = _NovoItem
    criados: int = 0
    tarefa_id: int = 0  # cada item criado vira uma etapa no painel de andamento

    def _run(self, nome: str, grupo: str, data_postagem: str = "", data_entrega: str = "", horario: str = "",
             objetivo: str = "", responsavel: str = "", conta: str = "Casa Veraneio", legenda: str = "") -> str:
        if self.criados >= MAX_ITENS_POR_TAREFA:
            return f"Limite de {MAX_ITENS_POR_TAREFA} itens por tarefa atingido."
        nome = re.sub(r"\s+", " ", nome).strip()
        if not monday.tipo_do_item(nome):
            return (f"Nome inválido: use 'TIPO | Descrição' com TIPO um de {', '.join(monday.TIPOS)} "
                    "(ex.: 'POST | Check-in no Lodge 208').")
        # O Thomas aloca a equipe: sem responsável dito por ele, o item não é criado e o agente pergunta.
        if not _escolher(responsavel, RESPONSAVEIS):
            return (f"Responsável não informado. NÃO crie os itens ainda: apresente o plano e pergunte ao usuário, "
                    f"com um formulário (um campo de opções por peça: {', '.join(RESPONSAVEIS)}), quem é o "
                    "responsável por cada peça. Crie depois da resposta.")
        mes = _escolher(grupo, MESES)
        if not mes:
            return f"Grupo inválido '{grupo}': use o nome do mês (ex.: {', '.join(MESES[10:])})."
        for rotulo, data in (("data_postagem", data_postagem), ("data_entrega", data_entrega)):
            if data and not DATA.match(data):
                return f"{rotulo} inválida '{data}': use AAAA-MM-DD."
        valores = {monday.COL_STATUS: {"label": monday.AGUARDANDO}}
        if data_postagem:
            valores["data"] = {"date": data_postagem}
        if data_entrega:
            valores["date_mm0p7s2f"] = {"date": data_entrega}
        if re.match(r"^\d{1,2}:\d{2}$", horario or ""):
            hora, minuto = horario.split(":")
            valores["hora_mkmpv7kt"] = {"hour": int(hora), "minute": int(minuto)}
        if (o := _escolher(objetivo, OBJETIVOS)):
            valores["dropdown_mm8bagtr"] = {"labels": [o]}
        if (r := _escolher(responsavel, RESPONSAVEIS)):
            valores["dropdown_mm8b5ds4"] = {"labels": [r]}
        valores[monday.COL_CONTA] = {"label": _escolher(conta, CONTAS) or "Casa Veraneio"}
        # Stories não têm legenda (manual 09): não grava, mesmo que o modelo tenha escrito uma.
        if legenda.strip() and monday.tipo_do_item(nome) != "STORIES":
            valores[monday.COL_LEGENDA] = {"text": legenda.strip()[:5000]}
        try:
            alvo = monday.grupo_por_nome(mes, criar=True)
            item = monday.criar_item(alvo["id"], nome, valores)
        except Exception as erro:
            return f"Não foi possível criar no Monday: {erro}"
        self.criados += 1
        if self.tarefa_id:
            tarefas.registrar_evento(self.tarefa_id, "item_monday", "social_media", detalhe=f"{alvo['title']}: {item['name']}")
        return f"Criado em {alvo['title']}: {item['name']} ({item['url']})"


def para(agente_id: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramentas do Monday do agente (hoje, só o Social Media)."""
    if agente_id != "social_media" or not monday.ativo():
        return []
    return [VerPlanejamentoMonday(), CriarItemMonday(tarefa_id=tarefa_id)]
