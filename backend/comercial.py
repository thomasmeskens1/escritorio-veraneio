"""Comercial · Prospectador (Casa Veraneio Corporativo): clientes do CRM, persona e leads de prospecção ativa.

Escopo do Monday autorizado pelo Thomas (27/10/2026), só na conta dele (token do sistema):
  LER   "Leads e Clientes Corp" (Clientes Ativos Corporativos) e "[Corp] Funil de Vendas" (ganhos);
  CRIAR itens no grupo "[Corp] Prospecção Ativa" do "[Geral] Dash Comercial" (nunca altera nem apaga nada).
A pesquisa na web roda no Claude Code do plano Max (trabalho "prospeccao" do trabalhador); aqui o pedido é montado,
a resposta é validada (LGPD: só canais da empresa, com fonte) e cada lead novo vira um item no grupo.
"""

import asyncio
import json
import logging
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import config
import segredos
import tarefas
from monday import _api

log = logging.getLogger(__name__)

AGENTE = "prospectador"
ANDAR = "comercial"
EMPRESA = "cv_corporativo"
MODELO = "claude-code/max"

QUADRO_CLIENTES, GRUPO_CLIENTES = 7803554314, "topics"            # Leads e Clientes Corp
QUADRO_FUNIL, GRUPOS_GANHOS = 7803554343, ["closed", "group_mkztyx3c"]  # [Corp] Funil de Vendas
QUADRO_LEADS, GRUPO_PROSPECCAO = 7803554300, "group_mm33wy2s"       # [Geral] Dash Comercial
COLUNAS_CLIENTE = ["industry", "text_mkxj2284", "dropdown_mkxj16y9", "data_mknc1nvw", "company_domain"]
COLUNAS_GANHO = ["dropdown_mm3b42sb", "color_mm4pd1wc", "n_meros_mkmgpvds", "local_mkmgy5nb", "date_mkp5eds"]
COLUNAS_LEAD = ["lead_email", "link_mm3393tw"]
COL = {"email": "lead_email", "telefone": "text_mm33n9tc", "site": "link_mm3393tw", "segmento": "dropdown_mm33z91y",
       "uf": "dropdown_mm33agj5", "cidade": "dropdown_mm33gg5j", "origem_lead": "dropdown_mm33d01s",
       "tipo_contato": "color_mm78bx13", "porte": "dropdown_mm3354a4", "unidade": "dropdown_mm33qe6r",
       "funcionarios": "numeric_mm33vne4", "historico": "long_text_mm336tzn", "prioridade": "color_mm333rrf"}
DROPDOWNS = ("segmento", "uf", "cidade", "porte", "unidade")

MAX_LEADS = 15        # por pedido
LIMITE_S = 40 * 60    # pesquisa na web pelo Max
CACHE_S = 6 * 3600
PASTA_PERSONA = config.PASTA_CONHECIMENTO / "14_persona_corporativo.md"

# Pedido de pesquisa (o resto, como dúvidas sobre clientes ou a persona, o agente responde no chat normal).
# Verbos no imperativo/infinitivo. "Prospectador" (o nome do agente) NÃO conta: "Prospectador, você tem acesso ao
# Monday?" virou uma pesquisa no Max (teste real, 28/10/2026). Pergunta sem quantidade de empresas também não.
PEDE_PROSPECCAO = re.compile(r"\b(prospect(?:e|em|ar|ando)|prospec[çc](?:ão|ões|ao|oes)|encontre|encontrar|busque|"
                             r"buscar|pesquise|pesquisar|levante|levantar|gere|gerar|traga|novos? leads?)\b", re.I)
QUANTIDADE_EMPRESAS = re.compile(r"\b\d{1,2}\s+(?:empresas|leads|contatos|prospects?|ind[uú]strias)\b", re.I)
PEDE_PERSONA = re.compile(r"\bpersona\b", re.I)
# LGPD (Thomas, 27/10/2026): só canais da empresa. E-mail genérico do domínio, nunca nominal nem gratuito.
GRATUITOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "bol.com.br", "uol.com.br",
             "icloud.com", "live.com", "terra.com.br", "ig.com.br", "msn.com", "globo.com", "protonmail.com"}
CAIXAS_GENERICAS = re.compile(r"^(contato|comercial|vendas|eventos?|rh|recursoshumanos|gente|pessoas|talentos|hr|"
                              r"marketing|mkt|comunicacao|atendimento|sac|faleconosco|fale|info|informacoes|"
                              r"relacionamento|institucional|imprensa|parcerias?|recepcao|administrativo|adm|"
                              r"compras|suprimentos|financeiro|ouvidoria|sustentabilidade|endomarketing|"
                              r"cultura|beneficios|secretaria|diretoria|geral|corporativo|negocios)\b[\w.+-]*$", re.I)
_cache: dict[str, tuple[float, object]] = {}
_trava = threading.Lock()


# --- Monday (leitura) -----------------------------------------------------------------------------------------

def _itens(quadro: int, grupos: list[str], colunas: list[str]) -> list[dict]:
    """Todos os itens dos grupos, com o texto das colunas pedidas ({nome, coluna: texto})."""
    dados = _api("query ($b: [ID!], $g: [String], $c: [String!]) { boards(ids: $b) { groups(ids: $g) { items_page("
                 "limit: 500) { cursor items { name column_values(ids: $c) { id text } } } } } }",
                 {"b": [str(quadro)], "g": grupos, "c": colunas})
    itens = []
    for grupo in dados["boards"][0]["groups"]:
        pagina = grupo["items_page"]
        while True:
            itens += [{"nome": i["name"], **{c["id"]: c["text"] or "" for c in i["column_values"]}}
                      for i in pagina["items"]]
            if not pagina["cursor"]:
                break
            pagina = _api("query ($k: String!, $c: [String!]) { next_items_page(limit: 500, cursor: $k) { cursor "
                          "items { name column_values(ids: $c) { id text } } } }",
                          {"k": pagina["cursor"], "c": colunas})["next_items_page"]
    return itens


def _em_cache(chave: str, carregar):
    with _trava:
        if (achado := _cache.get(chave)) and time.monotonic() - achado[0] < CACHE_S:
            return achado[1]
    valor = carregar()
    with _trava:
        _cache[chave] = (time.monotonic(), valor)
    return valor


def clientes() -> dict:
    """Clientes corporativos: contas ativas e eventos ganhos (só empresa, setor, cidade e evento; sem contatos)."""
    def carregar():
        contas = _itens(QUADRO_CLIENTES, [GRUPO_CLIENTES], COLUNAS_CLIENTE)
        ganhos = [g for g in _itens(QUADRO_FUNIL, GRUPOS_GANHOS, COLUNAS_GANHO)
                  if g["dropdown_mm3b42sb"] != "PF" and "Social" not in g["color_mm4pd1wc"]]
        return {"contas": contas, "ganhos": ganhos}
    return _em_cache("clientes", carregar)


def _rotulos() -> dict[str, list[str]]:
    """Rótulos válidos de cada dropdown do quadro de leads (não criamos rótulos novos)."""
    def carregar():
        colunas = _api("query ($b: [ID!], $c: [String!]) { boards(ids: $b) { columns(ids: $c) { id settings_str } } }",
                       {"b": [str(QUADRO_LEADS)], "c": [COL[d] for d in DROPDOWNS]})["boards"][0]["columns"]
        por_id = {c["id"]: [r["name"] for r in json.loads(c["settings_str"] or "{}").get("labels", [])
                            if not r.get("is_deactivated")] for c in colunas}
        return {d: por_id.get(COL[d], []) for d in DROPDOWNS}
    return _em_cache("rotulos", carregar)


def _sem_codigo(nome: str) -> str:
    """"1124 - RICHEMONT DO BRASIL" (código da negociação no funil) -> "RICHEMONT DO BRASIL"."""
    return re.sub(r"^\s*\d+\s*-\s*", "", nome or "").strip()


def _chave(nome: str) -> str:
    """Nome comparável: sem acento, caixa, pontuação nem sufixos societários."""
    nome = unicodedata.normalize("NFKD", _sem_codigo(nome)).encode("ascii", "ignore").decode().lower()
    nome = re.sub(r"\b(ltda|s\.?\s?a|sa|me|eireli|epp|do brasil|brasil|industria e comercio|ind e com)\b", " ", nome)
    return re.sub(r"[^a-z0-9]+", "", nome)


def _dominio(texto: str) -> str:
    achou = re.search(r"(?:@|//|^)(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", (texto or "").lower().strip())
    return achou.group(1) if achou else ""


def ja_conhecidos() -> tuple[set[str], set[str]]:
    """(nomes, domínios) de clientes e de quem já está na Prospecção Ativa: não entram de novo."""
    base = clientes()
    leads = _itens(QUADRO_LEADS, [GRUPO_PROSPECCAO], COLUNAS_LEAD)  # sempre fresco: a equipe cadastra à mão
    nomes = {_chave(i["nome"]) for i in base["contas"] + base["ganhos"] + leads}
    dominios = {_dominio(i.get("company_domain", "")) for i in base["contas"]}
    dominios |= {_dominio(i.get(c, "")) for i in leads for c in COLUNAS_LEAD}
    return nomes - {""}, dominios - {""} - GRATUITOS


# --- Pedido ao Max -------------------------------------------------------------------------------------------

def _resumo_clientes(limite: int = 120) -> str:
    base = clientes()
    contas = [f"- {c['nome']} | {c['industry'] or 'setor ?'} | {c['text_mkxj2284'] or ''} "
              f"{c['dropdown_mkxj16y9'].split('–')[-1].strip()} | último evento {c['data_mknc1nvw'] or '?'}"
              for c in base["contas"][:limite]]
    unicos = list({_chave(g["nome"]): g for g in base["ganhos"]}.values())  # a mesma negociação aparece repetida
    ganhos = [f"- {_sem_codigo(g['nome'])} | {g['color_mm4pd1wc'] or 'evento'} | {g['n_meros_mkmgpvds'] or '?'} pax | "
              f"{g['local_mkmgy5nb'] or ''} | {g['date_mkp5eds'] or ''}" for g in unicos[:limite]]
    return (f"CONTAS CORPORATIVAS ATIVAS ({len(base['contas'])}):\n" + "\n".join(contas) +
            f"\n\nEVENTOS GANHOS ({len(unicos)} empresas):\n" + "\n".join(ganhos))


def _persona() -> str:
    return PASTA_PERSONA.read_text(encoding="utf-8") if PASTA_PERSONA.exists() else ""


REGRAS_CONTATO = (
    "CONTATOS PERMITIDOS (LGPD, regra do Thomas): só canais da EMPRESA publicados por ela. E-mail = caixa genérica "
    "do domínio da empresa (contato@, comercial@, eventos@, rh@, marketing@, atendimento@...); telefone = central ou "
    "unidade publicado no site oficial. NUNCA e-mail nominal de pessoa (joao.silva@...), celular pessoal, e-mail "
    "gratuito (gmail, hotmail...) nem dado de redes sociais pessoais. Não invente nada: sem fonte, deixe vazio. "
    "Use só WebSearch e WebFetch em páginas públicas; não faça login, não use bases pagas e não contorne bloqueios.")


def prompt_prospeccao(pedido: str, quantidade: int) -> str:
    nomes, _ = ja_conhecidos()
    rotulos = _rotulos()
    return "\n\n".join(filter(None, [
        "Você é o Prospectador da Casa Veraneio Corporativo (produtora de eventos corporativos 360°: do orçamento ao "
        "último convidado, em espaços de alto padrão no interior de SP e no litoral). Encontre EMPRESAS que tenham "
        "potencial para contratar eventos (confraternização, convenção, off-site, workshop, aniversário da empresa, "
        "endomarketing) e colete os canais de contato da empresa.",
        f"PEDIDO DO USUÁRIO:\n{pedido}",
        f"PERSONA DO CLIENTE IDEAL:\n{_persona()}" if _persona() else "",
        f"QUEM JÁ É CLIENTE (referência de perfil; NÃO prospectar de novo):\n{_resumo_clientes()}",
        "JÁ ESTÃO NA PROSPECÇÃO ATIVA OU SÃO CLIENTES (não repetir; nomes normalizados): " +
        ", ".join(sorted(nomes))[:6000],
        REGRAS_CONTATO,
        f"QUANTIDADE: até {quantidade} empresas novas, as melhores primeiro. Prefira quem tem sede, planta ou "
        "escritório perto dos nossos espaços (região de Campinas, Jundiaí, Atibaia, Bragança, Sorocaba e capital) e "
        "porte para eventos (100+ funcionários), salvo se o pedido disser outra coisa.",
        "SEGMENTO: use exatamente um destes rótulos (ou deixe vazio): " + " | ".join(rotulos["segmento"]),
        "SAÍDA: só este bloco JSON, depois 2 ou 3 linhas de resumo em português:\n<<LEADS>>\n"
        '[{"empresa": "NOME DA EMPRESA", "site": "https://...", "cidade": "Campinas", "uf": "SP", '
        '"segmento": "rótulo da lista", "porte": "Nacional ou Multinacional", "funcionarios": 500, '
        '"unidade": "Planta produtiva | Escritório | Centro de distribuição | Outros", "email": "eventos@empresa.com.br", '
        '"telefone": "(19) 3333-4444", "fontes": ["URL onde achou o e-mail/telefone"], '
        '"motivo": "por que é um bom alvo, em 1 ou 2 frases"}]\n<<FIM>>',
    ]))


def prompt_persona() -> str:
    return "\n\n".join([
        "Você é o Prospectador da Casa Veraneio Corporativo. Crie a PERSONA do cliente corporativo ideal a partir dos "
        "clientes reais abaixo (quem já fez evento conosco). Pode usar WebSearch/WebFetch para entender o porte e o "
        "segmento das empresas, só em páginas públicas.",
        _resumo_clientes(250),
        "Escreva em português, em Markdown, começando por \"# Persona · Cliente corporativo da Casa Veraneio "
        "Corporativo\", com as seções: 1. Resumo da persona (quem decide e quem influencia: RH, eventos, marketing, "
        "diretoria); 2. Empresas-alvo (segmentos, porte, regiões, padrões que aparecem nos clientes); 3. Tipos de "
        "evento e tamanho (pax) mais comuns; 4. Dores e motivações; 5. Gatilhos e épocas de compra; 6. Sinais de bom "
        "lead na prospecção; 7. Quem NÃO é o nosso cliente. Baseie cada ponto nos dados (cite contagens) e marque "
        "como HIPÓTESE o que não vier deles. Não cite nomes de pessoas nem contatos. Entregue só o Markdown entre "
        "<<PERSONA>> e <<FIM>>.",
    ])


def pedir_ao_max(prompt: str, limite_s: int = LIMITE_S) -> str:
    """Trabalho "prospeccao" para o trabalhador do Max (WebSearch/WebFetch) e espera a resposta (em thread)."""
    import producao  # import tardio: produção depende do orquestrador

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with producao._db() as db:
        trabalho_id = db.execute("INSERT INTO trabalhos_max (tipo, payload, status, criado_em) VALUES "
                                 "('prospeccao', ?, 'pendente', ?)",
                                 (json.dumps({"prompt": prompt, "limite_s": limite_s}, ensure_ascii=False),
                                  agora)).lastrowid
    fim = time.monotonic() + limite_s + 30 * 60  # + espera na fila do Max (produções vêm antes)
    while time.monotonic() < fim:
        linha = producao._db().execute("SELECT status, resultado FROM trabalhos_max WHERE id = ?",
                                       (trabalho_id,)).fetchone()
        if linha["status"] == "concluido":
            return linha["resultado"] or ""
        if linha["status"] == "falhou":
            raise RuntimeError(linha["resultado"] or "A pesquisa no Claude Code (Max) falhou.")
        time.sleep(5)
    raise TimeoutError("A pesquisa no Claude Code (Max) não terminou a tempo.")


def _bloco(texto: str, nome: str) -> str:
    achou = re.search(rf"<<{nome}>>(.*?)<<FIM>>", texto, re.S)
    if not achou:
        raise RuntimeError(f"O Claude Code não devolveu o bloco {nome}.")
    return achou.group(1).strip()


# --- Validação e criação dos leads -----------------------------------------------------------------------------

def email_permitido(email: str, site: str) -> bool:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}", email):
        return False
    caixa, dominio = email.split("@")
    if dominio in GRATUITOS or not CAIXAS_GENERICAS.match(caixa):
        return False
    base_site = _dominio(site)  # o e-mail tem de ser do domínio da empresa (ou de um subdomínio dele)
    return not base_site or dominio == base_site or dominio.endswith(f".{base_site}") or \
        base_site.endswith(f".{dominio}")


def telefone_permitido(telefone: str) -> bool:
    """Fixo de central/unidade ou 0800/4004; celular só quando é o número publicado da empresa (não dá para saber
    aqui, então fica de fora)."""
    digitos = re.sub(r"\D", "", telefone or "").removeprefix("55")
    if digitos.startswith(("0800", "0300", "4004", "4003", "4020")):
        return len(digitos) in (8, 10, 11)
    return len(digitos) == 10 and digitos[2] in "2345"


def validar(leads: list[dict], nomes: set[str], dominios: set[str]) -> tuple[list[dict], list[str]]:
    """(leads aceitos, motivos dos recusados). Tira contatos fora da regra e quem já é conhecido."""
    aceitos, recusados, vistos = [], [], set()
    for lead in leads:
        nome = str(lead.get("empresa") or "").strip()
        site = str(lead.get("site") or "").strip()
        chave, dominio = _chave(nome), _dominio(site)
        if not nome or not chave:
            continue
        if chave in nomes or chave in vistos or (dominio and dominio in dominios):
            recusados.append(f"{nome}: já está no CRM")
            continue
        if not email_permitido(lead.get("email", ""), site):
            lead["email"] = ""
        if not telefone_permitido(lead.get("telefone", "")):
            lead["telefone"] = ""
        if not (lead["email"] or lead["telefone"]):
            recusados.append(f"{nome}: sem canal da empresa publicado")
            continue
        vistos.add(chave)
        aceitos.append(lead)
    return aceitos[:MAX_LEADS], recusados


def _valores(lead: dict) -> dict:
    rotulos = _rotulos()
    hoje = datetime.now().strftime("%d/%m/%Y")
    fontes = "\n".join(f"- {f}" for f in (lead.get("fontes") or [])[:4])
    valores = {
        COL["origem_lead"]: {"labels": ["Prospecção Ativa"]},
        COL["tipo_contato"]: {"label": "Corporativo"},
        COL["prioridade"]: {"label": "Aguardando Definição"},
        COL["historico"]: {"text": f"{hoje} - Prospectado pelo Escritório Veraneio (Prospectador).\n"
                                   f"Por quê: {lead.get('motivo', '').strip()}\n"
                                   f"Cidade: {lead.get('cidade', '')}/{lead.get('uf', '')}\nFontes:\n{fontes}"},
    }
    if lead.get("email"):
        valores[COL["email"]] = {"email": lead["email"], "text": lead["email"]}
    if lead.get("telefone"):
        valores[COL["telefone"]] = lead["telefone"]
    if lead.get("site"):
        valores[COL["site"]] = {"url": lead["site"], "text": _dominio(lead["site"]) or lead["site"]}
    if str(lead.get("funcionarios") or "").isdigit():
        valores[COL["funcionarios"]] = str(lead["funcionarios"])
    cidade = f"{lead.get('cidade', '')}/{lead.get('uf', '')}"
    candidatos = {"segmento": [lead.get("segmento")], "uf": [lead.get("uf")], "porte": [lead.get("porte")],
                  "unidade": [lead.get("unidade")], "cidade": [cidade, lead.get("cidade")]}
    for campo, opcoes in candidatos.items():
        validos = {r.lower(): r for r in rotulos.get(campo, [])}
        if (rotulo := next((validos[o.strip().lower()] for o in opcoes if o and o.strip().lower() in validos), None)):
            valores[COL[campo]] = {"labels": [rotulo]}
    return valores


def criar_lead(lead: dict) -> int:
    """Cria o item no grupo [Corp] Prospecção Ativa (só cria; nunca altera nem apaga)."""
    criado = _api("mutation ($b: ID!, $g: String!, $n: String!, $v: JSON!) { create_item(board_id: $b, group_id: $g, "
                  "item_name: $n, column_values: $v) { id } }",
                  {"b": str(QUADRO_LEADS), "g": GRUPO_PROSPECCAO, "n": lead["empresa"].strip().upper()[:120],
                   "v": json.dumps(_valores(lead), ensure_ascii=False)})["create_item"]
    return int(criado["id"])


# --- Execução da tarefa --------------------------------------------------------------------------------------

def e_pedido_de_trabalho(texto: str) -> bool:
    """Pedido de trabalho (persona, prospecção, criar leads da prévia); o resto é conversa com o agente.
    Pergunta ("...?") só vira prospecção se pedir uma quantidade de empresas ("Pode prospectar 5 indústrias?")."""
    if PEDE_CRIACAO.search(texto):
        return True
    if texto.strip().endswith("?") and not QUANTIDADE_EMPRESAS.search(texto):
        return False
    return bool(PEDE_PERSONA.search(texto) or PEDE_PROSPECCAO.search(texto))


def _quantidade(texto: str) -> int:
    achou = re.search(r"\b(\d{1,2})\s+(?:empresas|leads|contatos|prospects?)", texto, re.I)
    return min(int(achou.group(1)), MAX_LEADS) if achou else 10


def _evento(tarefa_id: int, tipo: str, detalhe: str) -> None:
    import atividade
    atividade.evento_em_thread(tarefa_id, tipo, AGENTE, MODELO, detalhe)


def atualizar_persona(tarefa_id: int) -> str:
    _evento(tarefa_id, "consulta_cerebro", "Clientes corporativos no Monday (contas ativas e eventos ganhos)")
    persona = _bloco(pedir_ao_max(prompt_persona()), "PERSONA")
    PASTA_PERSONA.write_text(persona + "\n", encoding="utf-8")
    import cerebro
    cerebro.indexar_oficiais()  # a persona passa a valer para o Prospectador e o Cérebro do Corporativo
    base = clientes()
    return (f"Montei a persona do cliente corporativo a partir de {len(base['contas'])} contas ativas e "
            f"{len(base['ganhos'])} eventos ganhos no Monday. Ela fica guardada no Cérebro e passa a guiar cada "
            f"prospecção.\n\n{persona}")


# Prévia antes do Monday (Thomas, 28/10/2026: "ver o resultado antes de colocar em prática"): toda prospecção
# pesquisa e mostra a lista sem criar nada; os leads só vão ao Monday quando ele aprovar a prévia.
PASTA_PREVIAS = config.DADOS_DIR / "prospeccao"
PEDE_CRIACAO = re.compile(r"\b(cri[ae]r?|cadastr\w*|suba|subir|lan[cç]\w*|registr\w*)\b.{0,40}\bleads?\b|"
                          r"\bpr[ée]via\s*#?\d+|\bpode criar\b", re.I)


def _previa(tarefa_id: int) -> Path:
    return PASTA_PREVIAS / f"{tarefa_id}.json"


def _linha_lead(n: int, lead: dict) -> str:
    detalhes = " · ".join(filter(None, [f"{lead.get('cidade', '')}/{lead.get('uf', '')}".strip("/"),
                                        lead.get("segmento"), lead.get("porte"),
                                        f"~{lead['funcionarios']} funcionários" if lead.get("funcionarios") else ""]))
    contatos = " · ".join(filter(None, [f"E-mail: {lead['email']}" if lead.get("email") else "",
                                        f"Telefone: {lead['telefone']}" if lead.get("telefone") else "",
                                        lead.get("site", "")]))
    fonte = (lead.get("fontes") or [""])[0]
    return (f"{n}. **{lead['empresa'].strip().upper()}** ({detalhes})\n   {contatos}\n"
            f"   Por quê: {lead.get('motivo', '').strip()}" + (f"\n   Fonte: {fonte}" if fonte else ""))


def prospectar(tarefa_id: int, pedido: str) -> str:
    """Pesquisa e devolve a PRÉVIA (nada é criado no Monday)."""
    _evento(tarefa_id, "consulta_cerebro", "Clientes e Prospecção Ativa no Monday (para não repetir empresas)")
    resposta = pedir_ao_max(prompt_prospeccao(pedido, _quantidade(pedido)))
    if "<<LEADS>>" not in resposta:  # o Claude Code respondeu em texto (ex.: pedido ambíguo): vale como resposta
        return segredos.limpar(resposta.strip()) or "Não consegui montar a lista de empresas desta vez."
    leads = json.loads(_bloco(resposta, "LEADS"))
    nomes, dominios = ja_conhecidos()  # de novo: a equipe pode ter cadastrado alguém durante a pesquisa
    aceitos, recusados = validar(leads if isinstance(leads, list) else [], nomes, dominios)
    if not aceitos:
        return "Não encontrei empresas novas com canal de contato da empresa publicado." + (
            "\n\nFicaram de fora: " + "; ".join(recusados[:12]) + "." if recusados else "")
    PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
    tarefa = tarefas.obter(tarefa_id)
    _previa(tarefa_id).write_text(json.dumps({"usuario": tarefa["usuario"] if tarefa else "", "pedido": pedido,
                                              "leads": aceitos, "criados": []}, ensure_ascii=False), encoding="utf-8")
    texto = (f"Prévia #{tarefa_id}: {len(aceitos)} empresa(s) nova(s), ainda NÃO criadas no Monday.\n\n" +
             "\n\n".join(_linha_lead(n, l) for n, l in enumerate(aceitos, 1)))
    if recusados:
        texto += "\n\nFicaram de fora: " + "; ".join(recusados[:12]) + "."
    return texto + (f"\n\nPara colocar em prática, diga \"Crie os leads da prévia #{tarefa_id}\" (todos) ou "
                    f"\"Crie os leads 1, 3 e 5 da prévia #{tarefa_id}\". Eles vão para o grupo [Corp] Prospecção Ativa.")


def _qual_previa(texto: str, usuario: str) -> int | None:
    if (citada := re.search(r"#\s*(\d+)", texto)) and _previa(int(citada.group(1))).exists():
        return int(citada.group(1))
    previas = sorted((int(a.stem) for a in PASTA_PREVIAS.glob("*.json")), reverse=True) if PASTA_PREVIAS.exists() else []
    return next((n for n in previas if json.loads(_previa(n).read_text(encoding="utf-8"))["usuario"] == usuario), None)


def criar_da_previa(tarefa_id: int, texto: str) -> str:
    """Cria no Monday os leads aprovados de uma prévia (todos ou os números citados), sem nova pesquisa."""
    tarefa = tarefas.obter(tarefa_id)
    numero = _qual_previa(texto, tarefa["usuario"] if tarefa else "")
    if numero is None:
        return "Não achei nenhuma prévia de prospecção sua. Peça uma prospecção primeiro; eu mostro a lista antes."
    previa = json.loads(_previa(numero).read_text(encoding="utf-8"))
    escolhidos = {int(n) for n in re.findall(r"\b(\d{1,2})\b", re.sub(r"#\s*\d+", "", texto))}
    leads = [(n, l) for n, l in enumerate(previa["leads"], 1) if not escolhidos or n in escolhidos]
    nomes, dominios = ja_conhecidos()  # alguém pode ter cadastrado a empresa depois da prévia
    criados, fora = [], []
    for n, lead in leads:
        if n in previa["criados"]:
            fora.append(f"{lead['empresa']}: já criado desta prévia")
            continue
        if not validar([dict(lead)], nomes, dominios)[0]:
            fora.append(f"{lead['empresa']}: já está no CRM")
            continue
        try:
            criar_lead(lead)
        except Exception as erro:
            log.warning("Prospectador: não criou %s (%s).", lead.get("empresa"), erro)
            fora.append(f"{lead['empresa']}: erro no Monday")
            continue
        previa["criados"].append(n)
        criados.append(lead["empresa"].strip().upper())
        _evento(tarefa_id, "item_monday", criados[-1])
    _previa(numero).write_text(json.dumps(previa, ensure_ascii=False), encoding="utf-8")
    texto = (f"Criei {len(criados)} lead(s) da prévia #{numero} no grupo [Corp] Prospecção Ativa, com Origem "
             f"\"Prospecção Ativa\", Tipo \"Corporativo\" e as fontes no Histórico: {', '.join(criados)}."
             if criados else f"Nenhum lead da prévia #{numero} foi criado.")
    return texto + ("\n\nFicaram de fora: " + "; ".join(fora) + "." if fora else "")


def executar(tarefa_id: int, texto: str) -> str:
    if PEDE_PERSONA.search(texto):
        return atualizar_persona(tarefa_id)
    if PEDE_CRIACAO.search(texto):
        return criar_da_previa(tarefa_id, texto)
    return prospectar(tarefa_id, texto)


async def iniciar(login: str, agente, texto: str) -> int:
    """Pedido de prospecção/persona: roda fora do roteamento de modelos (a pesquisa no Max leva vários minutos)."""
    import atividade
    import orquestrador
    from agents.executor import Resultado

    tarefa_id = tarefas.criar(login, ANDAR, agente.id, texto, "complexa", EMPRESA)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Prospecção pelo Claude Code (Max)")
    tarefas.registrar_evento(tarefa_id, "tentativa", agente.id, MODELO)
    await atividade.ocupar(agente.id)

    async def rodar() -> None:
        inicio = time.monotonic()
        try:
            resposta = await asyncio.to_thread(executar, tarefa_id, texto)
            tarefas.registrar_tentativa(tarefa_id, time.monotonic() - inicio)
            await orquestrador._concluir(tarefa_id, MODELO, Resultado(texto=resposta))
        except Exception as erro:
            log.exception("Prospectador: tarefa %s falhou.", tarefa_id)
            orquestrador._falhar(tarefa_id, f"A prospecção falhou: {erro}")
            await orquestrador.entregar(tarefas.obter(tarefa_id))
        finally:
            await atividade.liberar(agente.id)

    orquestrador._em_segundo_plano(rodar())
    return tarefa_id
