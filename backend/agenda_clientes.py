"""Agenda de clientes sob pedido (Onda 2, item 14: prospectador-01, -18, -19, estrategista-02, -13).

"Prospectador, quem devo reativar?" ou "Estrategista, agenda de clientes": o sistema faz a conta sozinho, EM CÓDIGO,
sem IA, sem web e sem o Max (decisão 12: carteira e CRM são sigilosos). Três listas e um indicador:
  1. Reativação: clientes sem evento há mais de 12 meses, com a melhor época para procurar cada um;
  2. Recompra: data provável do próximo evento pelo ritmo de cada cliente (aniversário com 1 evento);
  3. Pré-reserva de fim de ano: quem fez evento em nov/dez nos últimos 2 anos e ainda não fechou o deste ano;
  4. Recorrência: quantos clientes compram 1, 2, 3+ vezes, intervalo médio e quantos sumiram (só contagens).
Quem chega aqui já passou no acesso do painel (acesso.pode_usar).
Nomes: todos os usuários (decisão 11, Thomas, 04/11/2026: leads e projetos são de todos). A receita somada de quem
volta x quem comprou uma vez é visão de período: só a Diretoria (ve_valores).
A versão mensal automática fica para depois das rotinas.
"""

import asyncio
import logging
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean, median

import tarefas

log = logging.getLogger(__name__)

AGENTES = {"prospectador", "estrategista"}
MODELO = "codigo/agenda-clientes"  # sem modelo de IA
SEM_EVENTO_DIAS = 365
JANELA_RECOMPRA_DIAS = 180   # recompra: próximas datas prováveis até 6 meses à frente
AVISO_ANTES_DIAS = 60        # oferecer a data até 60 dias antes (prospectador-18: 60 a 90 dias)
MESMA_COMPRA_DIAS = 30       # "Extras"/"Aditivo"/"copy" perto da compra = a mesma compra (estrategista-13)
MAX_LINHAS = 40
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

PEDE = {
    "reativacao": re.compile(r"\breativ\w*|\bquem (?:devo|devemos|posso|podemos) (?:procurar|ligar|retomar)\b|"
                             r"\bclientes? (?:sumid\w*|antig\w*|parad\w*|inativ\w*)", re.I),
    "recompra": re.compile(r"\brecompra\w*|\bdatas? (?:de|do) retorno\b|\banivers[aá]rio d[eo]s? eventos?\b|"
                           r"\bpr[oó]xim[oa]s? eventos? (?:d[oa]s? )?clientes?\b|\brenova[cç](?:ão|ao|ões|oes)\b", re.I),
    "fim_de_ano": re.compile(r"\bpr[eé][- ]?reserva\w*|\b[uú]ltima chamada\b|\bgaranta sua data\b", re.I),
    "recorrencia": re.compile(r"\brecorr[eê]ncia\b|\bclientes? (?:que )?(?:volta\w*|retorna\w*|recorrentes?)\b|"
                              r"\bclientes? que compra\w* mais de uma vez\b", re.I),
}
TUDO = re.compile(r"\bagenda (?:de|dos) clientes\b", re.I)
ESTUDO = re.compile(r"\b(bcg|swot|porter|ansoff|mckinsey|matriz)\b", re.I)  # Estrategista: aí é estudo (estudos.py)
CRIAR = re.compile(r"\b(cri[ae]r?|cadastr\w*|suba|subir)\b.{0,40}\bleads?\b", re.I)


def secoes(agente_id: str, texto: str) -> list[str]:
    """Partes da agenda pedidas ([] = não é pedido de agenda)."""
    if agente_id not in AGENTES or CRIAR.search(texto) or (agente_id == "estrategista" and ESTUDO.search(texto)):
        return []
    if TUDO.search(texto):
        return list(PEDE)
    return [nome for nome, padrao in PEDE.items() if padrao.search(texto)]


def e_pedido(agente_id: str, texto: str) -> bool:
    import funil_parado  # mutirão do funil parado (estrategista-20): mesmo caminho, sem IA

    return bool(secoes(agente_id, texto)) or funil_parado.e_pedido(agente_id, texto)


# --- Quem vê o quê -------------------------------------------------------------------------------------------

def ve_nomes(login: str) -> bool:
    """Nomes dos clientes: qualquer usuário logado (decisão 11, Thomas, 04/11/2026). Antes: a Diretoria e a lista
    "veem_nomes" de dados/agenda_clientes.json, que deixou de ser lida."""
    return bool(login)


def ve_valores(login: str) -> bool:
    """Receita somada da recorrência (visão de período, decisão 11): só a Diretoria."""
    from auth import ve_financeiro

    return ve_financeiro(login)


# --- Dados ---------------------------------------------------------------------------------------------------

def data(texto: str) -> date | None:
    """"2024-12-10", "10/12/2024" ou "2024-12-10 18:00"; o resto (vazio, "Aguardando Definição") é sem data."""
    texto = (texto or "").strip()
    try:
        if (achou := re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)):
            return date(int(achou[1]), int(achou[2]), int(achou[3]))
        if (achou := re.match(r"(\d{2})/(\d{2})/(\d{4})", texto)):
            return date(int(achou[3]), int(achou[2]), int(achou[1]))
    except ValueError:
        pass
    return None


def cliente(nome: str) -> str:
    """Chave do cliente: a do comercial, sem "copy", "Extras" e "Aditivo" (a mesma compra, estrategista-13)."""
    import comercial

    return comercial._chave(re.sub(r"\b(copy|c[oó]pia|extras?|aditivos?)\b", " ", nome or "", flags=re.I))


def _compras(datas: list[date]) -> list[date]:
    """Datas distintas, juntando o que cai a menos de 30 dias da compra anterior (aditivo, extras, duplicata)."""
    compras: list[date] = []
    for d in sorted(datas):
        if not compras or (d - compras[-1]).days > MESMA_COMPRA_DIAS:
            compras.append(d)
    return compras


def montar(base: dict, hoje: date) -> list[dict]:
    """Um registro por cliente: nome, tipo/pax/local do último evento, eventos passados e futuros (ganhos), a data
    de último evento da conta (Leads e Clientes Corp) e o segmento."""
    import comercial

    por: dict[str, dict] = defaultdict(lambda: {"passados": [], "futuros": [], "ultimo_conta": None, "nome": "",
                                                "tipo": "", "pax": "", "local": "", "segmento": "", "_base": None,
                                                "eventos": {}})
    for conta in base.get("contas", []):
        if not (chave := cliente(conta.get("nome", ""))):
            continue
        reg = por[chave]
        reg["nome"] = reg["nome"] or comercial._sem_codigo(conta["nome"])
        reg["segmento"] = (conta.get("industry") or "").strip()
        reg["ultimo_conta"] = data(conta.get("data_mknc1nvw", ""))
    for ganho in base.get("ganhos", []):
        if not (chave := cliente(ganho.get("nome", ""))):
            continue
        reg = por[chave]
        reg["nome"] = reg["nome"] or re.sub(r"\s+(copy|extras?|aditivos?)\b.*$", "",
                                            comercial._sem_codigo(ganho["nome"]), flags=re.I).strip()
        aditivo = re.search(r"\b(copy|extras?|aditivos?)\b", ganho["nome"], re.I)  # não diz o tamanho do evento
        if (quando := data(ganho.get("date_mkp5eds", ""))):
            (reg["futuros"] if quando >= hoje else reg["passados"]).append(quando)
            if not aditivo:  # detalhes de cada evento (a pré-reserva mostra o de nov/dez, não o último)
                reg["eventos"][quando] = {"tipo": (ganho.get("color_mm4pd1wc") or "").strip(),
                                          "pax": re.sub(r"\D", "", str(ganho.get("n_meros_mkmgpvds") or "")),
                                          "local": (ganho.get("local_mkmgy5nb") or "").strip()}
            if quando < hoje and not aditivo and (reg["_base"] is None or quando >= reg["_base"]):  # último evento
                reg["_base"] = quando
                reg["tipo"] = (ganho.get("color_mm4pd1wc") or "").strip()
                reg["pax"] = re.sub(r"\D", "", str(ganho.get("n_meros_mkmgpvds") or ""))
                reg["local"] = (ganho.get("local_mkmgy5nb") or "").strip()
        elif not reg["tipo"]:
            reg["tipo"] = (ganho.get("color_mm4pd1wc") or "").strip()
            reg["pax"] = re.sub(r"\D", "", str(ganho.get("n_meros_mkmgpvds") or ""))
    registros = []
    for chave, reg in por.items():
        reg["chave"] = chave
        reg["compras"] = _compras(reg["passados"])
        candidatos = reg["compras"] + ([reg["ultimo_conta"]] if reg["ultimo_conta"] and reg["ultimo_conta"] < hoje
                                       else [])
        reg["ultimo"] = max(candidatos) if candidatos else None
        reg["fonte_data"] = ("conta" if reg["ultimo"] and reg["ultimo"] == reg["ultimo_conta"]
                             and reg["ultimo"] not in reg["compras"] else "funil" if reg["ultimo"] else "")
        meses = Counter(d.month for d in reg["compras"] or ([reg["ultimo"]] if reg["ultimo"] else []))
        reg["mes"] = max(meses, key=lambda m: (meses[m], m == (reg["ultimo"].month if reg["ultimo"] else 0)),
                         default=None)
        registros.append(reg)
    return registros


# --- Cálculo das listas (sem IA) -----------------------------------------------------------------------------

def _meses_ate(hoje: date, mes: int) -> int:
    """Meses de hoje até a próxima ocorrência do mês (0 = é este mês)."""
    return (mes - hoje.month) % 12


def sugestao(mes: int, hoje: date) -> str:
    """"dez -> procurar entre ago e set" (4 a 3 meses antes); evento a 3 meses ou menos: procurar já."""
    if _meses_ate(hoje, mes) <= 3:
        return f"procurar já (o mês do evento, {MESES[mes - 1]}, está chegando)"
    return f"procurar entre {MESES[(mes - 5) % 12]} e {MESES[(mes - 4) % 12]}"


def _ordem(mes: int, hoje: date) -> int:
    """Meses até a janela de procurar abrir (-1 = procurar já)."""
    return -1 if _meses_ate(hoje, mes) <= 3 else (mes - 4 - hoje.month) % 12


def reativacao(registros: list[dict], hoje: date, em_prospeccao: set[str] = frozenset()) -> dict:
    limite = hoje - timedelta(days=SEM_EVENTO_DIAS)
    lista, sem_data = [], []
    for reg in registros:
        if reg["futuros"]:
            continue  # já tem evento marcado
        if not reg["ultimo"]:
            sem_data.append(reg)
        elif reg["ultimo"] < limite:
            lista.append({**reg, "sugestao": sugestao(reg["mes"], hoje),
                          "aviso": "já está na Prospecção Ativa" if reg["chave"] in em_prospeccao else ""})
    lista.sort(key=lambda r: (_ordem(r["mes"], hoje), r["nome"]))
    return {"lista": lista, "sem_data": sem_data}


def recompra(registros: list[dict], hoje: date) -> list[dict]:
    """Próxima data provável: último evento + ritmo (mediana dos intervalos; 1 evento = aniversário)."""
    saida = []
    for reg in registros:
        compras = reg["compras"]
        if reg["futuros"] or not compras:
            continue
        intervalos = [(b - a).days for a, b in zip(compras, compras[1:])]
        ritmo = min(max(int(median(intervalos)), 60), 730) if intervalos else 365
        confianca = ("1 evento: só o aniversário da data" if not intervalos else
                     "2 eventos: padrão fraco" if len(compras) == 2 else f"{len(compras)} eventos: padrão bom")
        proxima = compras[-1] + timedelta(days=ritmo)
        while proxima < hoje:
            proxima += timedelta(days=ritmo)
        if (proxima - hoje).days <= JANELA_RECOMPRA_DIAS:
            ate = proxima - timedelta(days=AVISO_ANTES_DIAS)
            saida.append({**reg, "proxima": proxima, "ritmo": ritmo, "confianca": confianca,
                          "oferecer": "oferecer já" if ate <= hoje else f"oferecer a data até {ate:%d/%m/%Y}"})
    return sorted(saida, key=lambda r: r["proxima"])


def fim_de_ano(registros: list[dict], hoje: date) -> dict:
    """Quem fez evento em nov/dez nos 2 últimos anos; quem já fechou o deste ano sai (conta à parte)."""
    anos = {hoje.year - 1, hoje.year - 2}
    lista, fechados = [], 0
    for reg in registros:
        antes = [d for d in reg["compras"] if d.month in (11, 12) and d.year in anos and d < hoje]
        if not antes:
            continue
        if any(d.month in (11, 12) and d.year == hoje.year for d in reg["futuros"]):
            fechados += 1
            continue
        lista.append({**reg, **reg["eventos"].get(max(antes), {}), "fim_de_ano": max(antes)})
    lista.sort(key=lambda r: (-(int(r["pax"]) if r["pax"] else 0), r["nome"]))
    return {"lista": lista, "fechados": fechados, "ultima_chamada": hoje.month >= 10}


def recorrencia(vendas: list[tuple[str, str, date, float]], hoje: date) -> dict:
    """Por negócio: clientes com 1, 2 e 3+ compras, intervalo médio, quantos estão há 12+ meses sem comprar e a
    receita de quem volta x de quem comprou uma vez (só a Diretoria vê os valores)."""
    por: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for negocio, nome, quando, valor in vendas:
        if (chave := cliente(nome)) and quando:
            por[negocio][chave].append((quando, valor or 0.0))
    saida = {}
    for negocio, clientes_ in por.items():
        faixas, intervalos, sumidos, receita = Counter(), [], 0, {"uma": 0.0, "volta": 0.0}
        juntadas = 0
        for itens in clientes_.values():
            compras = _compras([q for q, _ in itens])
            juntadas += len(itens) - len(compras)
            faixas["3+" if len(compras) >= 3 else str(len(compras))] += 1
            intervalos += [(b - a).days for a, b in zip(compras, compras[1:])]
            sumidos += (hoje - compras[-1]).days > SEM_EVENTO_DIAS
            receita["volta" if len(compras) > 1 else "uma"] += sum(v for _, v in itens)
        total = sum(faixas.values())
        saida[negocio] = {"clientes": total, "faixas": faixas, "sumidos": sumidos, "receita": receita,
                          "intervalo_medio": round(mean(intervalos)) if intervalos else None,
                          "juntadas": juntadas,
                          "confianca": "baixa" if total < 10 else "média" if total < 30 else "boa"}
    return saida


def vendas_do_painel() -> list[tuple[str, str, date, float]]:
    """Vendas do CRM no banco do painel analítico (somente leitura)."""
    import relatorios

    if not relatorios.BANCO.exists():
        return []
    try:
        with relatorios._conexao() as db:
            linhas = db.execute("SELECT negocio, nome, data, valor FROM crm_vendas WHERE nome IS NOT NULL").fetchall()
    except Exception as erro:
        log.warning("Agenda de clientes: não li o painel (%s).", erro)
        return []
    return [(n or "?", nome, data(d or ""), float(v or 0)) for n, nome, d, v in linhas if data(d or "")]


def vendas_do_funil(registros: list[dict]) -> list[tuple[str, str, date, float]]:
    """Eventos ganhos do funil do Monday (Corporativo), quando o painel não está montado. Sem valores."""
    return [("Corp (funil do Monday)", r["chave"], d, 0.0) for r in registros for d in r["compras"]]


# --- Texto da resposta ---------------------------------------------------------------------------------------

NEGOCIOS = {"Hospedagem": "Casa Veraneio (hospedagem)", "Corp": "Casa Veraneio Corporativo"}


def _mes_ano(d: date | None) -> str:
    return f"{MESES[d.month - 1]}/{d.year}" if d else "sem data"


def _pct(n: int, total: int) -> str:
    return f"{round(100 * n / total)}%" if total else "0%"


def _reais(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def _faixa_pax(pax: str) -> str:
    return "pax ?" if not pax else "até 30 pax" if int(pax) <= 30 else "31 a 100 pax" if int(pax) <= 100 \
        else "101 a 300 pax" if int(pax) <= 300 else "mais de 300 pax"


def _contagem(titulo: str, itens) -> str:
    contagem = Counter(itens)
    return f"{titulo}: " + "; ".join(f"{k} ({n})" for k, n in contagem.most_common(8)) if contagem else ""


def _evento(reg: dict) -> str:
    return " · ".join(filter(None, [reg["tipo"] or "evento", f"{reg['pax']} pax" if reg["pax"] else "",
                                    reg["local"]]))


def _bloco_reativacao(dados: dict, nomes: bool) -> str:
    lista, sem_data = dados["lista"], dados["sem_data"]
    texto = [f"## 1. Reativação: {len(lista)} cliente(s) há mais de 12 meses sem evento",
             f"Sem data de último evento no CRM: {len(sem_data)} (não deduzi; confirme com o vendedor)."]
    if not lista:
        return "\n".join(texto)
    if not nomes:
        texto += [_contagem("Quando procurar", (r["sugestao"].split(" (")[0] for r in lista)),
                  _contagem("Tipo do último evento", (r["tipo"] or "não informado" for r in lista)),
                  _contagem("Tamanho", (_faixa_pax(r["pax"]) for r in lista)),
                  _contagem("Ano do último evento", (str(r["ultimo"].year) for r in lista))]
        return "\n".join(filter(None, texto))
    for n, r in enumerate(lista[:MAX_LINHAS], 1):
        fonte = "data da conta" if r["fonte_data"] == "conta" else "data do funil"
        texto.append(f"{n}. **{r['nome'].upper()}** · {_evento(r)} · último evento {_mes_ano(r['ultimo'])} ({fonte}) → "
                     f"{r['sugestao']}" + (f" · Obs.: {r['aviso']}" if r["aviso"] else ""))
    if len(lista) > MAX_LINHAS:
        texto.append(f"(mais {len(lista) - MAX_LINHAS} na mesma regra; peça por mês para ver o resto)")
    if sem_data:
        texto.append("Sem data: " + ", ".join(r["nome"].upper() for r in sem_data[:MAX_LINHAS]) + ".")
    return "\n".join(texto)


def _bloco_recompra(lista: list[dict], nomes: bool) -> str:
    texto = [f"## 2. Recompra: {len(lista)} cliente(s) com o próximo evento provável nos próximos 6 meses",
             "Ritmo = mediana dos intervalos entre os eventos ganhos; com 1 evento, o aniversário da data."]
    if not lista:
        return "\n".join(texto)
    if not nomes:
        texto += [_contagem("Mês provável", (_mes_ano(r["proxima"]) for r in lista)),
                  _contagem("Confiança", (r["confianca"].split(":")[0] for r in lista)),
                  f"Oferecer já: {sum(r['oferecer'] == 'oferecer já' for r in lista)}"]
        return "\n".join(texto)
    for n, r in enumerate(lista[:MAX_LINHAS], 1):
        texto.append(f"{n}. **{r['nome'].upper()}** · próximo provável {_mes_ano(r['proxima'])} (ritmo ~{r['ritmo']} "
                     f"dias; {r['confianca']}) → {r['oferecer']} · último: {_evento(r)}, {_mes_ano(r['ultimo'])}")
    return "\n".join(texto)


def _bloco_fim_de_ano(dados: dict, nomes: bool, hoje: date) -> str:
    lista = dados["lista"]
    texto = [f"## 3. Pré-reserva de fim de ano: {len(lista)} cliente(s) com evento em nov/dez em "
             f"{hoje.year - 2} ou {hoje.year - 1} e sem o de {hoje.year} fechado",
             f"Já fecharam nov/dez de {hoje.year}: {dados['fechados']}."]
    if dados["ultima_chamada"]:
        texto.append("Já é a reta final: vale a versão \"última chamada\". A oferta convida a consultar as datas, "
                     "nunca promete disponibilidade.")
    if not lista:
        return "\n".join(texto)
    if not nomes:
        texto += [_contagem("Tipo", (r["tipo"] or "não informado" for r in lista)),
                  _contagem("Tamanho", (_faixa_pax(r["pax"]) for r in lista))]
        return "\n".join(texto)
    for n, r in enumerate(lista[:MAX_LINHAS], 1):
        texto.append(f"{n}. **{r['nome'].upper()}** · {_evento(r)} em {_mes_ano(r['fim_de_ano'])}")
    return "\n".join(texto)


def texto_recorrencia(dados: dict, valores: bool) -> str:
    """Só contagens e percentuais (sem nomes); receita só com `valores` (Diretoria)."""
    if not dados:
        return ""
    linhas = ["## 4. Clientes que voltam (recorrência; só contagens)"]
    for negocio, d in dados.items():
        total, f = d["clientes"], d["faixas"]
        linha = (f"- {NEGOCIOS.get(negocio, negocio)}: {total} clientes; 1 compra {f['1']} ({_pct(f['1'], total)}), "
                 f"2 compras {f['2']} ({_pct(f['2'], total)}), 3 ou mais {f['3+']} ({_pct(f['3+'], total)}); "
                 f"intervalo médio entre compras: {str(d['intervalo_medio']) + ' dias' if d['intervalo_medio'] else '—'}"
                 f"; há mais de 12 meses sem comprar: {d['sumidos']} ({_pct(d['sumidos'], total)}); confiança "
                 f"{d['confianca']}" + (f" ({d['juntadas']} registro(s) juntados como a mesma compra: copy, extras, "
                                         "aditivo ou datas a menos de 30 dias)" if d["juntadas"] else ""))
        if valores and sum(d["receita"].values()):
            soma = sum(d["receita"].values())
            linha += (f". Receita (Diretoria): quem volta {_reais(d['receita']['volta'])} "
                      f"({_pct(d['receita']['volta'], soma)}), uma compra {_reais(d['receita']['uma'])}")
        linhas.append(linha)
    return "\n".join(linhas)


def recorrencia_para_estudo(financeiro: bool) -> str:
    """Bloco do estudo do Estrategista (estrategista-13): o mesmo indicador, do banco do painel."""
    texto = texto_recorrencia(recorrencia(vendas_do_painel(), date.today()), financeiro)
    return texto.replace("## 4. Clientes", "### Clientes", 1)


# --- Execução ------------------------------------------------------------------------------------------------

def _em_prospeccao() -> set[str]:
    import comercial

    try:
        return {cliente(i["nome"]) for i in comercial._itens(comercial.QUADRO_LEADS, [comercial.GRUPO_PROSPECCAO],
                                                              comercial.COLUNAS_LEAD)}
    except Exception as erro:
        log.warning("Agenda de clientes: não li a Prospecção Ativa (%s).", erro)
        return set()


def executar(login: str, texto: str, agente_id: str = "prospectador", hoje: date | None = None,
             base: dict | None = None, vendas: list | None = None, em_prospeccao: set[str] | None = None) -> str:
    import comercial

    hoje = hoje or date.today()
    partes, nomes = secoes(agente_id, texto) or list(PEDE), ve_nomes(login)
    if base is None:
        try:
            base = comercial.clientes()
        except Exception as erro:
            log.warning("Agenda de clientes: Monday fora (%s).", erro)
            return "Não consegui ler os clientes no Monday agora. Tente de novo em alguns minutos."
    registros = montar(base, hoje)
    blocos = [f"Agenda de clientes do Corporativo em {hoje:%d/%m/%Y}: calculada no sistema com os dados do Monday "
              "(contas ativas e eventos ganhos), sem IA e sem pesquisa na web."]
    if not nomes:
        blocos.append("Sem usuário identificado: aqui vão só as contagens.")
    if "reativacao" in partes:
        prospeccao = em_prospeccao if em_prospeccao is not None else (_em_prospeccao() if nomes else set())
        blocos.append(_bloco_reativacao(reativacao(registros, hoje, prospeccao), nomes))
    if "recompra" in partes:
        blocos.append(_bloco_recompra(recompra(registros, hoje), nomes))
    if "fim_de_ano" in partes:
        blocos.append(_bloco_fim_de_ano(fim_de_ano(registros, hoje), nomes, hoje))
    if "recorrencia" in partes:
        dados_vendas = vendas if vendas is not None else vendas_do_painel()
        blocos.append(texto_recorrencia(recorrencia(dados_vendas or vendas_do_funil(registros), hoje),
                                        ve_valores(login)) or "## 4. Clientes que voltam\nSem vendas para calcular.")
    blocos.append("Datas vazias ou desatualizadas no CRM mudam a conta: confira com o vendedor antes de ligar. "
                  "Negociação aberta no funil não é conferida aqui (só a Prospecção Ativa).")
    return "\n\n".join(b for b in blocos if b)


async def iniciar(login: str, andar: str, agente, texto: str) -> int:
    """Responde na hora, sem modelo de IA. Não passa pelo _concluir: a lista não vira conhecimento no Cérebro."""
    import comercial
    import funil_parado
    import orquestrador

    funil = funil_parado.e_pedido(agente.id, texto) and not secoes(agente.id, texto)
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "simples", comercial.EMPRESA)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Mutirão do funil parado (cálculo no sistema)"
                             if funil else "Agenda de clientes (cálculo no sistema)")
    try:
        resposta = await asyncio.to_thread(funil_parado.executar, login) if funil else \
            await asyncio.to_thread(executar, login, texto, agente.id)
        tarefas.atualizar(tarefa_id, status="concluida", modelo=MODELO, resposta=resposta)
        tarefas.registrar_evento(tarefa_id, "concluida", agente.id, MODELO)
    except Exception as erro:
        log.exception("Agenda de clientes: tarefa %s falhou.", tarefa_id)
        orquestrador._falhar(tarefa_id, f"A agenda de clientes falhou: {erro}")
    await orquestrador.entregar(tarefas.obter(tarefa_id))
    return tarefa_id
