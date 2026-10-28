"""Calendário de eventos previsíveis para o Analista de Tendências (Thomas, 28/10/2026): feriados, datas comerciais,
temporadas e grandes eventos, com a data CALCULADA (nada de data inventada por modelo), o dia da semana, se vira
feriadão e quando começar o conteúdo para chegar antes do momento.
"""

from datetime import date, timedelta

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# (nome, mês, dia, antecedência do conteúdo em dias, empresas para as quais pesa mais, observação)
FIXOS = [
    ("Réveillon", 12, 31, 120, "Casa Veraneio", "maior data do ano; a reserva acontece meses antes"),
    ("Natal", 12, 25, 75, "Casa Veraneio", "casas para a família inteira"),
    ("Tiradentes", 4, 21, 45, "Casa Veraneio", ""),
    ("Dia do Trabalho", 5, 1, 45, "Casa Veraneio", ""),
    ("Dia dos Namorados", 6, 12, 0, "", "público casal: fora da comunicação da Casa Veraneio (regra de ouro)"),
    ("Independência", 9, 7, 45, "Casa Veraneio", ""),
    ("Dia do Cliente", 9, 15, 20, "todas", "relacionamento e base"),
    ("Nossa Senhora Aparecida / Dia das Crianças", 10, 12, 45, "Casa Veraneio", "famílias com crianças"),
    ("Finados", 11, 2, 45, "Casa Veraneio", ""),
    ("Proclamação da República", 11, 15, 45, "Casa Veraneio", ""),
    ("Consciência Negra", 11, 20, 45, "Casa Veraneio", "feriado nacional desde 2024"),
]
# Temporadas: (nome, mês e dia de início, mês e dia de fim, antecedência, empresas, observação)
TEMPORADAS = [
    ("Férias de verão", (12, 20), (1, 31), 90, "Casa Veraneio", "alta temporada no litoral"),
    ("Férias de julho", (7, 1), (7, 31), 60, "Casa Veraneio", "inverno: serra e campo"),
    ("Confraternizações de fim de ano", (11, 15), (12, 20), 90, "Casa Veraneio Corporativo",
     "empresas fecham o local em setembro e outubro"),
    ("Planejamento de eventos do ano (orçamento das empresas)", (1, 15), (3, 15), 30, "Casa Veraneio Corporativo",
     "convenções, kick-offs e off-sites do ano"),
    ("Festas juninas", (6, 1), (6, 30), 30, "todas", "tema de conteúdo e decoração"),
]
# Grandes eventos com data já marcada (atualizar quando houver confirmação oficial de novos).
GRANDES = [
    ("Jogos Olímpicos de Inverno (Milão-Cortina)", date(2026, 2, 6), date(2026, 2, 22)),
    ("Copa do Mundo FIFA 2026 (EUA, Canadá, México)", date(2026, 6, 11), date(2026, 7, 19)),
    ("Jogos Olímpicos de Los Angeles", date(2028, 7, 14), date(2028, 7, 30)),
]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 90) // 25
    return date(ano, mes, (h + l - 7 * m + 33 * mes + 19) % 32)


def _domingo(ano: int, mes: int, ordem: int) -> date:
    """N-ésimo domingo do mês (Dia das Mães = 2º de maio, Dia dos Pais = 2º de agosto)."""
    primeiro = date(ano, mes, 1)
    return primeiro + timedelta(days=(6 - primeiro.weekday()) % 7 + 7 * (ordem - 1))


def _feriadao(dia: date) -> str:
    """Quantos dias de folga o feriado rende (o que importa para a hospedagem)."""
    return {0: "feriadão de 3 dias (sáb a seg)", 4: "feriadão de 3 dias (sex a dom)",
            1: "feriadão de 4 dias com ponte na segunda", 3: "feriadão de 4 dias com ponte na sexta"}.get(
        dia.weekday(), "")


def eventos(ano: int) -> list[dict]:
    """Eventos datados do ano."""
    p = pascoa(ano)
    lista = [{"nome": n, "data": date(ano, m, d), "antecedencia": a, "empresas": e, "obs": o}
             for n, m, d, a, e, o in FIXOS]
    lista += [
        {"nome": "Carnaval", "data": p - timedelta(days=50), "fim": p - timedelta(days=46), "antecedencia": 90,
         "empresas": "Casa Veraneio", "obs": "sábado a quarta de cinzas: a segunda maior data de hospedagem"},
        {"nome": "Semana Santa / Páscoa", "data": p - timedelta(days=2), "fim": p, "antecedencia": 60,
         "empresas": "Casa Veraneio", "obs": "Sexta-feira Santa a domingo de Páscoa"},
        {"nome": "Corpus Christi", "data": p + timedelta(days=60), "antecedencia": 45, "empresas": "Casa Veraneio",
         "obs": "ponto facultativo nacional, feriado em muitas cidades"},
        {"nome": "Dia das Mães", "data": _domingo(ano, 5, 2), "antecedencia": 30, "empresas": "Casa Veraneio",
         "obs": "família reunida"},
        {"nome": "Dia dos Pais", "data": _domingo(ano, 8, 2), "antecedencia": 30, "empresas": "Casa Veraneio",
         "obs": "família reunida"},
    ]
    quinta = date(ano, 11, 1) + timedelta(days=(3 - date(ano, 11, 1).weekday()) % 7 + 21)  # 4ª quinta de novembro
    lista.append({"nome": "Black Friday", "data": quinta + timedelta(days=1), "antecedencia": 30, "empresas": "todas",
                  "obs": "condição especial só se a empresa decidir oferecer (nada de inventar desconto)"})
    for nome, (mi, di), (mf, df), antecedencia, empresas, obs in TEMPORADAS:
        fim = date(ano + (1 if mf < mi else 0), mf, df)
        lista.append({"nome": nome, "data": date(ano, mi, di), "fim": fim, "antecedencia": antecedencia,
                      "empresas": empresas, "obs": obs})
    return lista


def proximos(hoje: date | None = None, meses: int = 15) -> list[dict]:
    """Eventos de hoje até `meses` à frente (os em andamento também), em ordem de data."""
    hoje = hoje or date.today()
    limite = hoje + timedelta(days=30 * meses)
    lista = [e for ano in range(hoje.year - 1, limite.year + 1) for e in eventos(ano)]
    lista += [{"nome": n, "data": i, "fim": f, "antecedencia": 120, "empresas": "todas",
               "obs": "grande evento: tema de conteúdo, sem usar marca oficial do evento"} for n, i, f in GRANDES]
    return sorted((e for e in lista if e.get("fim", e["data"]) >= hoje and e["data"] <= limite),
                  key=lambda e: e["data"])


def texto(hoje: date | None = None, meses: int = 15) -> str:
    """Bloco para o contexto do agente."""
    hoje = hoje or date.today()
    linhas = []
    for e in proximos(hoje, meses):
        quando = e["data"].strftime("%d/%m/%Y") + (f" a {e['fim']:%d/%m/%Y}" if e.get("fim") else "")
        detalhes = [] if e.get("fim") else [DIAS[e["data"].weekday()]]
        if not e.get("fim") and (folga := _feriadao(e["data"])) and e["nome"] not in ("Dia das Mães", "Dia dos Pais",
                                                                                      "Black Friday", "Dia do Cliente"):
            detalhes.append(folga)
        if e["antecedencia"]:
            inicio = e["data"] - timedelta(days=e["antecedencia"])
            detalhes.append("conteúdo já deveria ter começado" if inicio <= hoje else
                            f"começar o conteúdo até {inicio:%d/%m/%Y}, daqui a {(inicio - hoje).days} dias: no prazo")
        if e["empresas"]:
            detalhes.append(f"pesa mais para: {e['empresas']}")
        if e["obs"]:
            detalhes.append(e["obs"])
        linhas.append(f"- {quando} · {e['nome']} ({'; '.join(detalhes)})")
    return (f"HOJE É {hoje:%d/%m/%Y}. CALENDÁRIO DE EVENTOS PREVISÍVEIS (datas exatas, use estas e não "
            "invente outras; feriados municipais e estaduais não estão aqui):\n" + "\n".join(linhas))
