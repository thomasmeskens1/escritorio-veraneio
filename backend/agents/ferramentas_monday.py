"""Ferramentas do Social Media no board do Monday (Planejamento Automático 2026).

ver_planejamento_monday: itens de um grupo (mês ou "Definir Data"), para não duplicar.
criar_itens_monday: TODAS as peças de um planejamento numa chamada só (item a item, o limite de voltas do agente
cortava o mês no 5º item). criar_item_monday: uma peça avulsa (exige o responsável).
atualizar_item_monday: completa ou corrige um item que já existe (as respostas do usuário chegam ao Monday).
Com Data Postagem, o item vai para o grupo do mês, em ordem de data; sem data, para "Definir Data" (monday_datas).
O roteiro da peça (capa, páginas, CTA...) vai para a DESCRIÇÃO do item (se a API recusar, vira comentário).
"""

import json
import re

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import monday
import monday_datas
import tarefas

OBJETIVOS = ["Venda", "Comercial", "Interação", "Informativo/Educacional", "Criativo", "Síte"]
RESPONSAVEIS = ["Bruna", "Fran", "Luiz", "Thomas"]
CONTAS = ["Casa Veraneio", "Casa Vero", "CV Corp", "Sem definição"]
MAX_ITENS_POR_TAREFA = 40
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COL_DATA_ENTREGA, COL_HORARIO, COL_OBJETIVO, COL_RESPONSAVEL = ("date_mm0p7s2f", "hora_mkmpv7kt", "dropdown_mm8bagtr",
                                                                 "dropdown_mm8b5ds4")


def _escolher(valor: str, opcoes: list[str]) -> str | None:
    return next((o for o in opcoes if monday._chave(o) == monday._chave(valor or "")), None)


class _Grupo(BaseModel):
    grupo: str = Field(description="Grupo do board: o mês (ex. 'Dezembro') ou 'Definir Data'")


class _NovoItem(BaseModel):
    nome: str = Field(description="'TIPO | Descrição'. TIPO é um de: STORIES, POST (single post estático), CARROSSEL, "
                                  "REELS, SHORTS. Ex.: 'POST | As melhores casas para o seu Réveillon'")
    grupo: str = Field("", description="Mês do item (ex. 'Dezembro'). O grupo final sai da data_postagem; sem data, "
                                       "o item vai para 'Definir Data'.")
    data_postagem: str = Field("", description="AAAA-MM-DD. Vazio se o usuário não deu data ou disse que não tem: "
                                               "NUNCA invente.")
    data_entrega: str = Field("", description="AAAA-MM-DD; vazio se não houver data de postagem")
    horario: str = Field("", description="HH:MM, 24 h; vazio se o usuário não deu")
    objetivo: str = Field("", description=f"Um de: {', '.join(OBJETIVOS)}")
    responsavel: str = Field("", description=f"Um de: {', '.join(RESPONSAVEIS)}, sempre o que o usuário disse "
                                             "(nunca escolha por conta própria). Em planejamento de várias peças, "
                                             "vazio se ele não disse.")
    conta: str = Field("Casa Veraneio", description=f"Marca: {', '.join(CONTAS)}")
    legenda: str = Field("", description="Rascunho da legenda, só para POST, CARROSSEL, REELS e SHORTS. Para STORIES "
                                         "deixe VAZIO e não escreva nenhuma legenda (stories não têm legenda).")
    roteiro: str = Field("", description="Briefing da peça para a produção: capa, cada página/cena com o imóvel, "
                                         "local e destaque, formato (foto/vídeo e duração) e CTA. Vai para a descrição do item.")


class _NovosItens(BaseModel):
    itens: list[_NovoItem] = Field(description="TODAS as peças do planejamento, uma entrada por peça")


class _Atualizacao(BaseModel):
    item: str = Field(description="Nome exato do item no board (ex.: 'CARROSSEL | Os imóveis mais exclusivos...')")
    data_postagem: str = Field("", description="AAAA-MM-DD para definir; 'limpar' para apagar; vazio = não mexe")
    data_entrega: str = Field("", description="AAAA-MM-DD para definir; 'limpar' para apagar; vazio = não mexe")
    horario: str = Field("", description="HH:MM para definir; 'limpar' para apagar; vazio = não mexe")
    objetivo: str = Field("", description=f"Um de: {', '.join(OBJETIVOS)}; vazio = não mexe")
    responsavel: str = Field("", description=f"Um de: {', '.join(RESPONSAVEIS)} (o que o usuário disse); vazio = não mexe")
    conta: str = Field("", description=f"Marca: {', '.join(CONTAS)}; vazio = não mexe")
    legenda: str = Field("", description="Nova legenda completa (substitui a atual); vazio = não mexe")
    roteiro: str = Field("", description="Briefing completo da peça; substitui a descrição do item; vazio = não mexe")


def _valores(data_postagem: str = "", data_entrega: str = "", horario: str = "", objetivo: str = "",
             responsavel: str = "", conta: str = "", legenda: str = "", nome: str = "") -> dict | str:
    """Colunas no formato da API; "limpar" apaga a coluna. Devolve o erro (str) se algum valor for inválido."""
    valores = {}
    for rotulo, coluna, data in (("data_postagem", monday_datas.COL_DATA, data_postagem),
                                 ("data_entrega", COL_DATA_ENTREGA, data_entrega)):
        if data == "limpar":
            valores[coluna] = {}
        elif data:
            if not DATA.match(data):
                return f"{rotulo} inválida '{data}': use AAAA-MM-DD."
            valores[coluna] = {"date": data}
    if horario == "limpar":
        valores[COL_HORARIO] = {}
    elif re.match(r"^\d{1,2}:\d{2}$", horario or ""):
        hora, minuto = horario.split(":")
        valores[COL_HORARIO] = {"hour": int(hora), "minute": int(minuto)}
    if (o := _escolher(objetivo, OBJETIVOS)):
        valores[COL_OBJETIVO] = {"labels": [o]}
    if (r := _escolher(responsavel, RESPONSAVEIS)):
        valores[COL_RESPONSAVEL] = {"labels": [r]}
    if (c := _escolher(conta, CONTAS)):
        valores[monday.COL_CONTA] = {"label": c}
    # Stories não têm legenda (manual 09): não grava, mesmo que o modelo tenha escrito uma.
    if legenda.strip() and monday.tipo_do_item(nome) != "STORIES":
        valores[monday.COL_LEGENDA] = {"text": legenda.strip()[:5000]}
    return valores


VERSAO_DESCRICAO = "2026-04"  # set_item_description_content só existe a partir desta versão da API


def _descrever_roteiro(item_id: int, roteiro: str) -> None:
    """Roteiro na descrição do item (substitui a anterior); se a API recusar, vai como comentário."""
    if not roteiro.strip():
        return
    try:
        monday._api("mutation ($i: ID!, $m: String!) { set_item_description_content(item_id: $i, markdown: $m) "
                    "{ __typename } }", {"i": str(item_id), "m": roteiro.strip()[:20000]}, versao=VERSAO_DESCRICAO)
    except Exception:
        monday.comentar(item_id, f"Roteiro da peça:\n{roteiro.strip()[:5000]}")


class VerPlanejamentoMonday(BaseTool):
    name: str = "ver_planejamento_monday"
    description: str = ("Lista os itens de um grupo do board de Social Media no Monday (um mês ou 'Definir Data'), "
                        "só da empresa deste trabalho (coluna Conta), com data de postagem e status. Use antes de "
                        "criar itens, para não duplicar.")
    args_schema: type[BaseModel] = _Grupo
    tarefa_id: int = 0

    def _run(self, grupo: str) -> str:
        try:
            achado = monday.grupo_por_nome(grupo)
            if not achado:
                return f"O grupo '{grupo}' ainda não existe no board (ele é criado ao criar o primeiro item)."
            itens = monday.itens_do_grupo(achado["id"])
        except Exception as erro:
            return f"Não foi possível ler o Monday agora: {erro}"
        # Só a Conta da empresa da tarefa (levantamento de 31/10/2026): no planejamento da Casa Vero, os itens da Casa
        # Veraneio do mesmo mês entravam na conta de duplicatas e da grade.
        tarefa = tarefas.obter(self.tarefa_id) if self.tarefa_id else None
        itens, de_fora = monday.da_empresa(itens, tarefa["empresa"] if tarefa else "")
        fora = f" ({de_fora} item(ns) de outras empresas ficaram de fora)" if de_fora else ""
        if not itens:
            return f"O grupo {achado['title']} não tem itens desta empresa{fora}."
        linhas = [f"- {i['name']} | " + " | ".join(f"{c['id']}: {c['text'] or '—'}" for c in i["column_values"])
                  for i in itens]
        return f"Itens em {achado['title']} ({len(itens)}){fora}:\n" + "\n".join(linhas)


class _Contador(BaseModel):
    """Itens criados na tarefa, somando as duas ferramentas de criação."""
    criados: int = 0


def _criar(contador: _Contador, tarefa_id: int, nome: str, grupo: str = "", data_postagem: str = "",
           data_entrega: str = "", horario: str = "", objetivo: str = "", responsavel: str = "",
           conta: str = "Casa Veraneio", legenda: str = "", roteiro: str = "", exigir_responsavel: bool = False) -> str:
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
    # A Conta é a empresa da tarefa, não a que o modelo escreveu (revisão de 30/10/2026, 2.17: sem o modelo dizer,
    # uma peça da Casa Vero ia como "Casa Veraneio" e era produzida com o Cérebro e a persona da Casa Veraneio).
    import empresas

    tarefa = tarefas.obter(tarefa_id) if tarefa_id else None
    if tarefa and tarefa["empresa"] in empresas.EMPRESAS:
        conta = empresas.EMPRESAS[tarefa["empresa"]]["monday"]
    valores = _valores(data_postagem, data_entrega, horario, objetivo, responsavel, conta or "Casa Veraneio",
                       legenda, nome)
    if isinstance(valores, str):
        return valores
    valores[monday.COL_STATUS] = {"label": monday.AGUARDANDO}
    valores.setdefault(monday.COL_CONTA, {"label": "Casa Veraneio"})
    # Grupo pela data (o mês da postagem); sem data, "Definir Data" — nunca um mês escolhido sem data.
    destino = monday_datas.grupo_do_mes(data_postagem) if data_postagem else monday_datas.GRUPO_SEM_DATA
    try:
        alvo = monday.grupo_por_nome(destino, criar=True)
        item = monday.criar_item(alvo["id"], nome, valores)
    except Exception as erro:
        return f"Não foi possível criar '{nome}' no Monday: {erro}"
    contador.criados += 1
    if data_postagem:
        monday_datas.reposicionar_seguro(int(item["id"]))  # em ordem de data dentro do mês
    try:
        _descrever_roteiro(int(item["id"]), roteiro)
    except Exception:
        pass  # o item já existe; o roteiro pode ir depois por atualizar_item_monday
    if tarefa_id:
        tarefas.registrar_evento(tarefa_id, "item_monday", "social_media", detalhe=f"{alvo['title']}: {item['name']}")
    return f"Criado em {alvo['title']}: {item['name']} ({item['url']})"


class CriarItensMonday(BaseTool):
    name: str = "criar_itens_monday"
    description: str = ("Cria de uma vez TODAS as peças de um planejamento (ex.: o mês inteiro) no board de Social "
                        "Media do Monday. Com data_postagem, cada uma vai para o grupo do seu mês, em ordem de data; "
                        "sem data, para 'Definir Data'. Use sempre que forem 2 ou mais peças, numa chamada só com a "
                        "lista completa. STORIES: sem legenda. Devolve uma linha por peça: o link ou o erro.")
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
    description: str = ("Cria UMA peça avulsa no board de Social Media do Monday (com data: grupo do mês, em ordem; "
                        "sem data: 'Definir Data'); exige o responsável dito pelo usuário. Para 2 ou mais peças use "
                        "criar_itens_monday; para mudar um item que já existe, atualizar_item_monday. STORIES: sem "
                        "legenda. Devolve o link ou o erro a corrigir.")
    args_schema: type[BaseModel] = _NovoItem
    contador: _Contador
    tarefa_id: int = 0

    def _run(self, **item) -> str:
        # Já criando várias peças nesta tarefa (planejamento): o responsável deixa de ser obrigatório.
        return _criar(self.contador, self.tarefa_id, **item, exigir_responsavel=self.contador.criados == 0)


class AtualizarItemMonday(BaseTool):
    name: str = "atualizar_item_monday"
    description: str = ("Completa ou corrige um item que JÁ EXISTE no board (datas, horário, objetivo, responsável, "
                        "conta, legenda e roteiro). Use quando o usuário responder a um formulário sobre uma peça já "
                        "criada, em vez de criar outra. Mudou a data: o item vai para o mês certo, em ordem.")
    args_schema: type[BaseModel] = _Atualizacao
    tarefa_id: int = 0

    def _run(self, item: str, roteiro: str = "", **campos) -> str:
        try:
            achado = monday.buscar_item(item)
        except Exception as erro:
            return f"Não foi possível ler o Monday agora: {erro}"
        if not achado or int(achado["board"]["id"]) != monday.BOARD:
            return f"Item '{item}' não encontrado no board do planejamento. Confira o nome com ver_planejamento_monday."
        valores = _valores(nome=achado["name"], **campos)
        if isinstance(valores, str):
            return valores
        try:
            if valores:
                monday._api("mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(board_id: $b, "
                            "item_id: $i, column_values: $v) { id } }",
                            {"b": str(monday.BOARD), "i": str(achado["id"]), "v": json.dumps(valores)})
            _descrever_roteiro(int(achado["id"]), roteiro)
        except Exception as erro:
            return f"Não foi possível atualizar '{achado['name']}': {erro}"
        if monday_datas.COL_DATA in valores:  # data nova ou apagada: grupo do mês (ou Definir Data), em ordem
            monday_datas.reposicionar_seguro(int(achado["id"]))
        if self.tarefa_id:
            tarefas.registrar_evento(self.tarefa_id, "item_monday", "social_media", detalhe=f"atualizado: {achado['name']}")
        mudou = ", ".join(campo for campo, valor in campos.items() if valor) + (", roteiro" if roteiro.strip() else "")
        return f"Atualizado: {achado['name']} ({mudou or 'nada a mudar'})"


def para(agente_id: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramentas do Monday do agente (hoje, só o Social Media)."""
    if agente_id != "social_media" or not monday.ativo():
        return []
    contador = _Contador()
    return [VerPlanejamentoMonday(tarefa_id=tarefa_id), CriarItensMonday(contador=contador, tarefa_id=tarefa_id),
            CriarItemMonday(contador=contador, tarefa_id=tarefa_id), AtualizarItemMonday(tarefa_id=tarefa_id)]
