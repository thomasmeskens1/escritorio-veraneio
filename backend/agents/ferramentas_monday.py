"""Ferramentas do Social Media no board do Monday (Planejamento Automático 2026).

ver_planejamento_monday: itens de um mês (grupo), para não duplicar.
criar_itens_monday: TODAS as peças de um planejamento numa chamada só (item a item, o limite de voltas do agente
cortava o mês no 5º item). criar_item_monday: uma peça avulsa (exige o responsável).
Os itens vão para o grupo do mês certo ("planejamento de dezembro" → grupo Dezembro; o grupo é criado se ainda
não existir), com datas, horário, objetivo, conta, responsável e legenda.
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
    responsavel: str = Field("", description=f"Um de: {', '.join(RESPONSAVEIS)}, sempre o que o usuário disse "
                                             "(nunca escolha por conta própria). Em planejamento de várias peças, "
                                             "vazio se ele não disse.")
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


class _NovosItens(BaseModel):
    itens: list[_NovoItem] = Field(description="TODAS as peças do planejamento, uma entrada por peça")


class _Contador(BaseModel):
    """Itens criados na tarefa, somando as duas ferramentas de criação."""
    criados: int = 0


def _criar(contador: _Contador, tarefa_id: int, nome: str, grupo: str, data_postagem: str = "", data_entrega: str = "",
           horario: str = "", objetivo: str = "", responsavel: str = "", conta: str = "Casa Veraneio",
           legenda: str = "", exigir_responsavel: bool = False) -> str:
    if contador.criados >= MAX_ITENS_POR_TAREFA:
        return f"Limite de {MAX_ITENS_POR_TAREFA} itens por tarefa atingido."
    nome = re.sub(r"\s+", " ", nome).strip()
    if not monday.tipo_do_item(nome):
        return (f"Nome inválido '{nome}': use 'TIPO | Descrição' com TIPO um de {', '.join(monday.TIPOS)} "
                "(ex.: 'POST | Check-in no Lodge 208').")
    # O Thomas aloca a equipe. Peça avulsa: sem responsável dito por ele, não cria e o agente pergunta.
    # Planejamento de várias peças: o responsável é opcional (Thomas, 23/10/2026).
    if exigir_responsavel and not _escolher(responsavel, RESPONSAVEIS):
        return (f"Responsável não informado para esta peça avulsa. NÃO crie ainda: termine a resposta com o bloco "
                f"<<FORMULARIO>> perguntando o responsável (opções: {', '.join(RESPONSAVEIS)}) e crie depois da "
                "resposta.")
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
        return f"Não foi possível criar '{nome}' no Monday: {erro}"
    contador.criados += 1
    if tarefa_id:
        tarefas.registrar_evento(tarefa_id, "item_monday", "social_media", detalhe=f"{alvo['title']}: {item['name']}")
    return f"Criado em {alvo['title']}: {item['name']} ({item['url']})"


class CriarItensMonday(BaseTool):
    name: str = "criar_itens_monday"
    description: str = ("Cria de uma vez TODAS as peças de um planejamento (ex.: o mês inteiro) no board de Social "
                        "Media do Monday, cada uma no grupo do seu mês (dezembro → 'Dezembro'). Use sempre que "
                        "forem 2 ou mais peças, numa chamada só com a lista completa. STORIES: sem legenda. "
                        "Devolve uma linha por peça: o link ou o erro a corrigir.")
    args_schema: type[BaseModel] = _NovosItens
    contador: _Contador
    tarefa_id: int = 0  # cada item criado vira uma etapa no painel de andamento

    def _run(self, itens: list) -> str:
        linhas = [_criar(self.contador, self.tarefa_id, **(i.model_dump() if isinstance(i, BaseModel) else i))
                  for i in itens]
        criados = sum(linha.startswith("Criado") for linha in linhas)
        return f"{criados} de {len(linhas)} peça(s) criada(s):\n" + "\n".join(f"- {linha}" for linha in linhas)


class CriarItemMonday(BaseTool):
    name: str = "criar_item_monday"
    description: str = ("Cria UMA peça avulsa no board de Social Media do Monday, no grupo do mês certo (dezembro → "
                        "'Dezembro'); exige o responsável dito pelo usuário. Para 2 ou mais peças use "
                        "criar_itens_monday. STORIES: sem legenda. Devolve o link ou o erro a corrigir.")
    args_schema: type[BaseModel] = _NovoItem
    contador: _Contador
    tarefa_id: int = 0

    def _run(self, **item) -> str:
        # Já criando várias peças nesta tarefa (planejamento): o responsável deixa de ser obrigatório.
        return _criar(self.contador, self.tarefa_id, **item, exigir_responsavel=self.contador.criados == 0)


def para(agente_id: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramentas do Monday do agente (hoje, só o Social Media)."""
    if agente_id != "social_media" or not monday.ativo():
        return []
    contador = _Contador()
    return [VerPlanejamentoMonday(), CriarItensMonday(contador=contador, tarefa_id=tarefa_id),
            CriarItemMonday(contador=contador, tarefa_id=tarefa_id)]
