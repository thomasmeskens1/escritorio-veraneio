"""Datas calculadas para quem planeja e escreve (Onda 2, item 4; analista_tendencias-04/-05/-07/-27, social_media-05,
copywriter-12, gestor_trafego-13).

Dois problemas reais: a contagem "faltam 45 noites" era feita de cabeça (e pela data de HOJE, não pela da postagem),
e só o Analista de Tendências recebia o calendário. Aqui, tudo é conta em código:
- `faltam(alvo, postagem)`: noites até o momento a partir da DATA DA POSTAGEM (manual 07 §5: 01/10 → 91 noites).
- `bloco(...)`: os próximos 90 dias SÓ da empresa do trabalho, com feriados nacionais (Carnaval, Sexta-feira Santa e
  Corpus Christi calculados pela Páscoa), os estaduais e municipais das cidades de origem do público e as datas
  próprias de cada empresa, nunca misturadas.
Configurável em dados/calendario.json (fora do git): cidades de origem por empresa, feriados regionais extras e
datas próprias por empresa (substituem as padrão daquela empresa).
"""

import json
import logging
import re
from datetime import date, timedelta

import calendario_eventos as ce
import config
import empresas

log = logging.getLogger(__name__)

ARQUIVO = config.DADOS_DIR / "calendario.json"
JANELA_DIAS = 90
# Quem planeja e escreve. O Analista continua com o calendário completo de 15 meses e ganha também este bloco.
AGENTES = {"gestor", "social_media", "copywriter", "analista_tendencias", "gestor_trafego"}
# Os manuais não dizem de onde vem o público (só a persona do Corporativo: Grande São Paulo). Até o Thomas dar a
# lista (ou o CRM contar), vale SP capital, que também traz os feriados do estado de SP. "Cidade / UF" (decisão 2).
CIDADES_PADRAO = ["São Paulo / SP"]

# Feriados regionais conhecidos: chave "UF" (estadual) ou "Cidade / UF" (municipal). (mês, dia, nome) ou
# ("pascoa", deslocamento, nome) para os móveis.
REGIONAIS = {
    "SP": [(7, 9, "Revolução Constitucionalista")],
    "São Paulo / SP": [(1, 25, "Aniversário de São Paulo"), ("pascoa", 60, "Corpus Christi")],
    # Campinas e Jundiaí (Thomas, 04/11/2026: público também dessas regiões). Campinas: Imaculada Conceição (Lei
    # 3.902/1970) e Dia do Evangélico (Lei 16.785/2025). Jundiaí: decreto 36.753/2026 (feriados locais de 2027):
    # Corpus Christi e Nossa Senhora do Desterro; a Paixão já é nacional. Aniversário de Jundiaí (14/12) não é feriado.
    "Campinas / SP": [("pascoa", 60, "Corpus Christi"), (8, 12, "Dia do Evangélico"),
                      (12, 8, "Imaculada Conceição (padroeira de Campinas)")],
    "Jundiaí / SP": [("pascoa", 60, "Corpus Christi"), (8, 15, "Nossa Senhora do Desterro (padroeira de Jundiaí)")],
    "BA": [(7, 2, "Independência da Bahia")],
    "RJ": [(4, 23, "Dia de São Jorge")],
    "Rio de Janeiro / RJ": [(1, 20, "Dia de São Sebastião")],
    "Belo Horizonte / MG": [(8, 15, "Assunção de Nossa Senhora"), (12, 8, "Imaculada Conceição")],
}

A_CONFIRMAR = "rascunho: a confirmar com a equipe"
# Datas próprias de cada empresa: (nome, (mês, dia) ou "maes"/"pais", (mês, dia) do fim ou None, observação).
# As do Corporativo e da Casa Vero são proposta (analista_tendencias-05): o Thomas aprova fatos por empresa (decisão 16).
PROPRIAS = {
    "casa_veraneio": [
        ("Réveillon", (12, 31), None, "maior data do ano; a reserva acontece meses antes"),
        ("Dia das Mães", "maes", None, "família reunida"),
        ("Dia dos Pais", "pais", None, "família reunida"),
        ("Férias de verão", (12, 20), (1, 31), "alta temporada no litoral"),
        ("Férias de julho", (7, 1), (7, 31), "inverno: serra e campo"),
    ],
    "cv_corporativo": [
        ("Kick-off do ano", (1, 5), (1, 31), f"convenções e kick-offs de janeiro; {A_CONFIRMAR}"),
        ("Planejamento de eventos do ano", (1, 15), (3, 15), "orçamento das empresas: convenções e off-sites"),
        ("Dia Internacional da Mulher", (3, 8), None, f"endomarketing do RH; {A_CONFIRMAR}"),
        ("Dia do Profissional de RH", (6, 3), None, f"quem contrata o evento; {A_CONFIRMAR}"),
        ("Janela de orçamento do ano seguinte", (9, 1), (10, 31), f"empresas aprovam a verba de eventos; {A_CONFIRMAR}"),
        ("Dia da Secretária", (9, 30), None, f"quem organiza eventos internos; {A_CONFIRMAR}"),
        ("Confraternizações de fim de ano", (11, 15), (12, 20), "empresas fecham o local em setembro e outubro"),
    ],
    "casa_vero": [
        ("Começo de ano: planos de compra e mudança", (1, 2), (2, 28), f"hipótese; {A_CONFIRMAR}"),
        ("Férias de julho: visitas a imóveis", (7, 1), (7, 31), f"hipótese; {A_CONFIRMAR}"),
        ("Dia do Corretor", (8, 27), None, f"relacionamento com consultores; {A_CONFIRMAR}"),
        ("13º salário e bônus", (11, 20), (1, 31), f"comprador com dinheiro na mão; hipótese; {A_CONFIRMAR}"),
    ],
}
# Momentos com contagem regressiva ("faltam N noites"), por empresa.
ALVOS = {"casa_veraneio": ("Réveillon", "Carnaval")}

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
_DATA = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
# "- Data de postagem: 2026-11-16" (briefing do item do Monday) ou "postagem em 16/11" no chat.
DATA_POSTAGEM = re.compile(rf"data\s+(?:de\s+)?postagem\s*[:=]?\s*{_DATA}|\bpostad[oa]s?\s+(?:em|no dia|dia)\s+{_DATA}|"
                           rf"\bpostagem\s+(?:em|no dia|dia|prevista para)\s+{_DATA}", re.I)
MES_CITADO = re.compile(r"\b(" + "|".join(MESES).replace("ç", "[çc]") + r")\b", re.I)
# Pedido de planejamento ou que cita data/momento (o mesmo espírito de encaminhamento.py): só aí o bloco entra.
PEDE_DATAS = re.compile(r"planej|calend[aá]rio|cronograma|pautas?\b|grade|\bm[eê]s\b|semanas?\b|feriad|campanha|"
                        r"temporada|r[eé]veillon|carnaval|natal|p[aá]scoa|f[eé]rias|faltam|contagem|noites|\bdatas?\b|"
                        r"verba|anivers[aá]rio|dia d[aeo]s?\b", re.I)


def _config() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8")) if ARQUIVO.exists() else {}
    except (OSError, ValueError) as erro:
        log.warning("calendario.json ilegível (%s): usando os padrões.", erro)
        return {}


def cidades(empresa: str) -> list[str]:
    """Cidades de origem do público da empresa ("Cidade / UF")."""
    return list(_config().get("cidades_origem", {}).get(empresa) or CIDADES_PADRAO)


def faltam(alvo: date, postagem: date) -> int:
    """Noites (= dias) entre a postagem e o momento: postagem 29/10 → Réveillon 31/12 = 63 noites (manual 07 §5)."""
    return (alvo - postagem).days


def data_do_alvo(nome: str, a_partir: date) -> date:
    """Próxima ocorrência do momento a partir da data (Carnaval: o sábado, começo do feriadão)."""
    for ano in (a_partir.year, a_partir.year + 1):
        dia = date(ano, 12, 31) if nome == "Réveillon" else ce.pascoa(ano) - timedelta(days=50)
        if dia >= a_partir:
            return dia
    raise ValueError(nome)


def nacionais(ano: int) -> list[dict]:
    """Feriados nacionais (e os pontos facultativos que mexem com viagem), móveis calculados pela Páscoa."""
    p = ce.pascoa(ano)
    fixos = [((1, 1), "Confraternização Universal"), ((4, 21), "Tiradentes"), ((5, 1), "Dia do Trabalho"),
             ((9, 7), "Independência"), ((10, 12), "Nossa Senhora Aparecida / Dia das Crianças"),
             ((11, 2), "Finados"), ((11, 15), "Proclamação da República"), ((11, 20), "Consciência Negra"),
             ((12, 25), "Natal")]
    lista = [{"nome": n, "data": date(ano, m, d), "tipo": "feriado nacional"} for (m, d), n in fixos]
    lista += [
        {"nome": "Carnaval", "data": p - timedelta(days=50), "fim": p - timedelta(days=46),
         "tipo": "ponto facultativo nacional na segunda e na terça", "obs": "sábado a quarta-feira de cinzas"},
        {"nome": "Sexta-feira Santa", "data": p - timedelta(days=2), "tipo": "feriado nacional",
         "obs": f"Páscoa em {p:%d/%m}"},
        {"nome": "Corpus Christi", "data": p + timedelta(days=60), "tipo": "ponto facultativo nacional"},
    ]
    return lista


def regionais(ano: int, lista_cidades: list[str]) -> list[dict]:
    """Feriados estaduais e municipais das cidades (cada cidade traz também os do seu estado)."""
    extras = _config().get("feriados_regionais", {})
    chaves = []
    for cidade in lista_cidades:
        uf = cidade.split("/")[-1].strip() if "/" in cidade else ""
        chaves += [c for c in (uf, cidade.strip()) if c and c not in chaves]
    lista = []
    for chave in chaves:
        tipo = f"feriado municipal ({chave})" if "/" in chave else f"feriado estadual ({chave})"
        datas = list(REGIONAIS.get(chave, [])) + [(e["mes"], e["dia"], e["nome"]) for e in extras.get(chave, [])
                                                  if isinstance(e, dict) and {"mes", "dia", "nome"} <= set(e)]
        for a, b, nome in datas:
            dia = ce.pascoa(ano) + timedelta(days=b) if a == "pascoa" else date(ano, int(a), int(b))
            # Mesmo feriado em várias cidades (Corpus Christi em SP, Campinas e Jundiaí): uma linha só.
            if (igual := next((f for f in lista if f["data"] == dia and f["nome"] == nome), None)):
                igual["tipo"] = igual["tipo"].replace(")", f", {chave})", 1) if "municipal" in tipo else igual["tipo"]
                continue
            lista.append({"nome": nome, "data": dia, "tipo": tipo, "regional": True})
    return lista


def _proprias_da_empresa(empresa: str) -> list:
    configuradas = _config().get("datas_proprias", {}).get(empresa)
    if not isinstance(configuradas, list):
        return PROPRIAS.get(empresa, [])
    return [(e["nome"], (e["mes"], e["dia"]), (e["fim_mes"], e["fim_dia"]) if e.get("fim_mes") else None,
             e.get("obs", "")) for e in configuradas if isinstance(e, dict) and {"nome", "mes", "dia"} <= set(e)]


def proprias(ano: int, empresa: str) -> list[dict]:
    lista = []
    for nome, inicio, fim, obs in _proprias_da_empresa(empresa):
        if inicio in ("maes", "pais"):
            dia = ce._domingo(ano, 5 if inicio == "maes" else 8, 2)
        else:
            dia = date(ano, *inicio)
        evento = {"nome": nome, "data": dia, "tipo": "data da empresa", "obs": obs}
        if fim:
            evento["fim"] = date(ano + (1 if fim < inicio else 0), *fim)
        lista.append(evento)
    return lista


def eventos(empresa: str, inicio: date, fim: date) -> list[dict]:
    """Datas da empresa entre `inicio` e `fim` (as em andamento também), em ordem."""
    lista = []
    for ano in range(inicio.year - 1, fim.year + 1):
        lista += nacionais(ano) + regionais(ano, cidades(empresa)) + proprias(ano, empresa)
    return sorted((e for e in lista if e.get("fim", e["data"]) >= inicio and e["data"] <= fim),
                  key=lambda e: (e["data"], e["nome"]))


def _converter(texto: str, hoje: date) -> date | None:
    try:
        if "-" in texto:
            return date.fromisoformat(texto)
        partes = [int(p) for p in texto.split("/")]
        if len(partes) == 3:
            return date(partes[2] + (2000 if partes[2] < 100 else 0), partes[1], partes[0])
        dia = date(hoje.year, partes[1], partes[0])
        return dia if dia >= hoje - timedelta(days=60) else date(hoje.year + 1, partes[1], partes[0])
    except ValueError:
        return None


def data_postagem(texto: str, hoje: date | None = None) -> date | None:
    """Data da postagem citada no pedido (briefing do item do Monday ou texto do chat)."""
    casamento = DATA_POSTAGEM.search(texto or "")
    if not casamento:
        return None
    return _converter(next(g for g in casamento.groups() if g), hoje or date.today())


def _mes_citado(texto: str, hoje: date) -> tuple[int, int] | None:
    if not (casamento := MES_CITADO.search(texto or "")):
        return None
    mes = [m.replace("ç", "c") for m in MESES].index(casamento.group(1).lower().replace("ç", "c")) + 1
    return (hoje.year if mes >= hoje.month else hoje.year + 1), mes


def tabela_do_mes(empresa: str, ano: int, mes: int) -> list[str]:
    """Para cada dia do mês planejado, quantas noites faltam para cada momento (social_media-05)."""
    linhas = []
    primeiro = date(ano, mes, 1)
    dias = [primeiro + timedelta(days=n) for n in range(31) if (primeiro + timedelta(days=n)).month == mes]
    for nome in ALVOS.get(empresa, ()):
        alvo = data_do_alvo(nome, primeiro)
        valores = [f"{d:%d/%m}={faltam(alvo, d)}" for d in dias if d <= alvo]
        if valores:
            linhas.append(f"- {nome} ({alvo:%d/%m/%Y}), noites que faltam por data de postagem: " + ", ".join(valores))
    return linhas


def _linha(e: dict, hoje: date, postagem: date | None) -> str:
    if e.get("fim"):
        quando = f"{e['data']:%d/%m/%Y} a {e['fim']:%d/%m/%Y}"
        detalhes = [f"em andamento até {e['fim']:%d/%m/%Y}"] if e["data"] < hoje else []
    else:
        quando = f"{e['data']:%d/%m/%Y} ({ce.DIAS[e['data'].weekday()]})"
        detalhes = []
        if e["tipo"].startswith("feriado") and (folga := ce._feriadao(e["data"])):
            detalhes.append(folga)
    detalhes.append(e["tipo"])
    if e.get("regional"):
        detalhes.append("só para quem é de lá: anúncio segmentado por região e Stories, não peça para o feed todo")
    if e["data"] >= hoje:
        detalhes.append(f"daqui a {(e['data'] - hoje).days} dias")
    if postagem and e["data"] >= postagem:
        detalhes.append(f"{(e['data'] - postagem).days} dias depois da postagem")
    if e.get("obs"):
        detalhes.append(e["obs"])
    return f"- {quando} · {e['nome']} ({'; '.join(detalhes)})"


def bloco(agente_id: str, empresa: str | None, pedido: str = "", hoje: date | None = None) -> str:
    """Bloco curto para o contexto de quem planeja: só a empresa do trabalho; "" se não se aplica."""
    if agente_id not in AGENTES or empresa not in empresas.EMPRESAS:
        return ""
    hoje = hoje or date.today()
    postagem = data_postagem(pedido, hoje)
    mes = _mes_citado(pedido, hoje)
    if agente_id != "analista_tendencias" and not (postagem or mes or PEDE_DATAS.search(pedido or "")):
        return ""  # pedido sem data nem planejamento: não engorda o prompt
    fim = max(hoje, postagem or hoje) + timedelta(days=JANELA_DIAS)
    partes = [f"DATAS CALCULADAS PELO SISTEMA, só da {empresas.nome(empresa)} (hoje é {hoje:%d/%m/%Y}; até "
              f"{fim:%d/%m/%Y}). Use estas datas e contagens: não calcule de cabeça nem invente outras."]
    alvos = ALVOS.get(empresa, ())
    if postagem:
        partes.append(f"DATA DA POSTAGEM deste trabalho: {postagem:%d/%m/%Y} ({ce.DIAS[postagem.weekday()]}). Toda "
                      "contagem \"faltam N noites/dias\" parte dela, NUNCA da data de hoje; registre no texto a data "
                      "usada (ex.: \"contagem para postagem em "
                      f"{postagem:%d/%m/%Y}\"). Se a data mudar no Monday, a contagem tem de ser refeita.")
        partes += [f"- {nome} ({(alvo := data_do_alvo(nome, postagem)):%d/%m/%Y}): faltam {faltam(alvo, postagem)} "
                   "noites a partir da postagem" for nome in alvos]
    elif alvos:
        partes.append("Sem data de postagem neste pedido: \"faltam N noites\" só se escreve com a data da peça. "
                      "Sem ela, a contagem fica PENDENTE (não use a data de hoje). N = dias entre a data da postagem "
                      "e a data do momento.")
    if mes and alvos:
        partes += tabela_do_mes(empresa, *mes)
    partes.append("Datas (tipo, dia da semana, feriadão e distância):")
    partes += [_linha(e, hoje, postagem) for e in eventos(empresa, hoje, fim)]
    partes.append(f"Feriados estaduais e municipais considerados: os das cidades de origem do público "
                  f"({', '.join(cidades(empresa))}); os de outras cidades não estão aqui.")
    if agente_id == "gestor_trafego":
        partes.append("Calendário de verba: planeje por estas datas o início das rodadas, a concentração no vencedor "
                      "e o desligamento; o cliente decide semanas antes do momento, então a verba vem antes dele.")
    return "\n".join(partes)
