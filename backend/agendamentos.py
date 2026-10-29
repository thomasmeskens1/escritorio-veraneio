"""Rotinas agendadas: "analise as campanhas todos os dias às 08:00" vira um job do APScheduler.

O interpretador é determinístico (regex, sem LLM). No horário, a tarefa segue o pipeline normal
(orquestrador.nova_tarefa): status no canvas, resposta no chat, histórico e registro.
"""

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import APIRouter, Header, HTTPException

import tarefas
from auth import validar_token
from conexoes import gerenciador

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
MINIMO_MINUTOS = 15
HORA_PADRAO = (9, 0)  # recorrência sem horário explícito
ESPERA_OCUPADO_S, TENTATIVAS_OCUPADO = 30, 60  # agente ocupado: tenta por até 30 min

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS agendamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL,
    andar TEXT NOT NULL,
    agente TEXT NOT NULL,
    tarefa TEXT NOT NULL,
    regra TEXT NOT NULL,          -- JSON do gatilho (cron | intervalo | data)
    descricao TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    ultima_execucao TEXT,
    execucoes INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agendamentos_ativo ON agendamentos(ativo);
"""

_agendador: AsyncIOScheduler | None = None
_esquema_ok = False


def _db():
    global _esquema_ok
    db = tarefas._db()
    if not _esquema_ok:
        db.executescript(_ESQUEMA)
        _esquema_ok = True
    return db


# --- Interpretador ------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento, com o MESMO comprimento (os índices valem no texto original)."""
    return "".join((unicodedata.normalize("NFD", c)[:1].lower()[:1] or c) for c in texto)


_DIAS = {"segunda": "mon", "terca": "tue", "quarta": "wed", "quinta": "thu", "sexta": "fri",
         "sabado": "sat", "domingo": "sun"}
_NOMES_DIAS = {"mon": "segunda", "tue": "terça", "wed": "quarta", "thu": "quinta", "fri": "sexta",
               "sat": "sábado", "sun": "domingo"}
_DIA = r"(?:segunda|terca|quarta|quinta|sexta)s?(?:[\s-]feiras?)?|sabados?|domingos?"

_HORA = re.compile(
    r"(?:\b(?:as|a|ao|pelas)\s+)?(?:"
    r"(?P<especial>meio[\s-]dia|meia[\s-]noite)"
    r"|(?P<h1>\d{1,2})\s*(?::|h)\s*(?P<m1>\d{2})\b(?:\s*(?:h|hs|horas?)\b)?"
    r"|(?P<h2>\d{1,2})\s*(?:h|hs|horas?)\b"
    r"|(?<=as\s)(?P<h3>\d{1,2})\b(?!\s*(?:/|de\s+\w+\s+de))"
    r")(?:\s+da\s+(?P<periodo>manha|tarde|noite))?"
)
_INTERVALO = re.compile(r"\b(?:a\s+)?cada\s+(?:(?P<meia>meia\s+hora)|(?:(?P<n>\d{1,3})\s*)?"
                        r"(?P<unidade>minutos?|min|horas?|h)\b)|\bde\s+hora\s+em\s+hora\b")
_MENSAL = re.compile(r"\b(?:todo\s+dia\s+(?P<d1>\d{1,2})(?!\s*(?::|h\b|hs\b|horas?\b))"
                     r"(?:\s+(?:do\s+mes|de\s+cada\s+mes|de\s+todo\s+mes))?"
                     r"|(?:todo\s+mes|mensalmente)\s*,?\s*(?:no\s+)?dia\s+(?P<d2>\d{1,2})\b)")
_UTEIS = re.compile(r"\b(?:de\s+segunda(?:[\s-]feira)?\s+a\s+sexta(?:[\s-]feira)?|(?:todos\s+os\s+|nos\s+|em\s+)?dias\s+uteis)\b")
_FDS = re.compile(r"\b(?:(?:nos|no|todos\s+os|todo|aos|em)\s+)?fins?\s+de\s+semana\b|\baos\s+sabados\s+e\s+domingos\b")
_SEMANAL = re.compile(rf"\b(?:tod[ao]s?\s+(?:as\s+|os\s+)?|nas\s+|aos\s+|as\s+)(?P<dias>(?:{_DIA})"
                      rf"(?:\s*(?:,|e)\s*(?:as\s+|os\s+|a\s+|o\s+)?(?:{_DIA}))*)\b")
_DIARIO = re.compile(r"\b(?:todos\s+os\s+dias|todo\s+(?:santo\s+)?dia|diariamente|cada\s+dia)\b")
_UNICA = re.compile(r"\b(?P<quando>depois\s+de\s+amanha|amanha|hoje)\b")
# Frequência logo depois destas palavras costuma ser conteúdo ("post para todas as segundas").
_BLOQUEIO = re.compile(r"\b(?:para|pra|de|do|da|das|dos|sobre)\s*$")
# Texto longo é briefing: frequência nele é conteúdo ("arrumadeira todos os dias", "3 stories por dia"), não pedido
# de rotina. Teste real (28/10/2026): o briefing da influenciadora virou rotina diária às 9h. Acima deste tamanho, só
# vira rotina com pedido explícito: "agende/agendar" ou "crie uma rotina". Palavras soltas como "repetir" ou
# "rotina" aparecem no conteúdo de briefings (2º teste real, 29/10/2026: "não obrigue a influenciadora a repetir
# frases" reabriu o erro).
LIMITE_SEM_PEDIDO = 300
_PEDE_ROTINA = re.compile(r"\b(?:agend(?:e|ar|ou|ado|ada|amento)|(?:crie|criar|monte|configure)\s+(?:uma\s+)?rotina)\b")


def _horarios(norm: str, livre: list[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """(hora, minuto, ini, fim) de cada horário encontrado fora dos trechos já usados."""
    achados = []
    for m in _HORA.finditer(norm):
        if any(a < m.end() and m.start() < b for a, b in livre):
            continue
        if m["especial"]:
            h, mi = (12, 0) if m["especial"].startswith("meio") else (0, 0)
        else:
            h, mi = int(m["h1"] or m["h2"] or m["h3"]), int(m["m1"] or 0)
        if m["periodo"] in ("tarde", "noite") and h < 12:
            h += 12
        if h > 23 or mi > 59:
            continue
        achados.append((h, mi, m.start(), m.end()))
    return achados


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _vocativos() -> set[str]:
    from estado import ANDARES  # import tardio: só nomes
    nomes = set()
    for agentes in ANDARES.values():
        for a in agentes.values():
            nomes |= {_normalizar(a.nome), _normalizar(a.id.replace("_", " "))}
    return nomes


def _limpar_tarefa(texto: str, trechos: list[tuple[int, int]]) -> str:
    partes, pos = [], 0
    for a, b in sorted(trechos):
        partes.append(texto[pos:a])
        pos = max(pos, b)
    resto = "".join(partes) + texto[pos:]
    resto = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", resto)).strip(" ,;:-–")
    resto = re.sub(r"^(?:e|,)\s+|\s+(?:e|as|às)$", "", resto, flags=re.IGNORECASE).strip(" ,;:-–")
    # Vocativo inicial com nome de agente: "Gestor de tráfego, analise..." / "Oi Copywriter: ..."
    m = re.match(r"^(?:(?:oi|olá|ola|ei)[\s,]+)?([^,:]{2,40})[,:]\s*", resto, flags=re.IGNORECASE)
    if m and _normalizar(m.group(1)).strip() in _vocativos():
        resto = resto[m.end():]
    elif _normalizar(resto).strip(" .!") in _vocativos():
        resto = ""  # sobrou só o nome do agente
    resto = resto.strip(" ,;:-–")
    return resto[:1].upper() + resto[1:]


def _bloqueado(norm: str, inicio: int) -> bool:
    return bool(_BLOQUEIO.search(norm[:inicio]))


def _frequencia(norm: str):
    """(regra, descrição base, trecho, usa_horario) ou None."""
    if (m := _INTERVALO.search(norm)) and not _bloqueado(norm, m.start()):
        if m["meia"]:
            minutos = 30
        elif m["unidade"] is None:  # "de hora em hora"
            minutos = 60
        else:
            n = int(m["n"] or 1)
            minutos = n * 60 if m["unidade"].startswith("h") else n
        minutos = max(minutos, MINIMO_MINUTOS)
        if minutos % 60 == 0:
            desc = "A cada hora" if minutos == 60 else f"A cada {minutos // 60} horas"
        else:
            desc = f"A cada {minutos} minutos"
        return {"tipo": "intervalo", "minutos": minutos}, desc, (m.start(), m.end()), False
    if (m := _MENSAL.search(norm)) and not _bloqueado(norm, m.start()):
        dia = int(m["d1"] or m["d2"])
        if not 1 <= dia <= 31:
            return None
        return {"tipo": "cron", "dia": dia}, f"Todo dia {dia} do mês", (m.start(), m.end()), True
    if (m := _UTEIS.search(norm)) and not _bloqueado(norm, m.start()):
        return {"tipo": "cron", "dia_semana": "mon-fri"}, "De segunda a sexta", (m.start(), m.end()), True
    if (m := _FDS.search(norm)) and not _bloqueado(norm, m.start()):
        return {"tipo": "cron", "dia_semana": "sat,sun"}, "Nos fins de semana", (m.start(), m.end()), True
    if (m := _SEMANAL.search(norm)) and not _bloqueado(norm, m.start()):
        dias = []
        for nome in re.findall(r"segunda|terca|quarta|quinta|sexta|sabado|domingo", m["dias"]):
            if _DIAS[nome] not in dias:
                dias.append(_DIAS[nome])
        nomes = [_NOMES_DIAS[d] for d in dias]
        if len(nomes) == 1:
            desc = f"{'Todo' if dias[0] in ('sat', 'sun') else 'Toda'} {nomes[0]}" + ("-feira" if dias[0] not in ("sat", "sun") else "")
        else:
            desc = "Toda " + ", ".join(nomes[:-1]) + " e " + nomes[-1]
        return {"tipo": "cron", "dia_semana": ",".join(dias)}, desc, (m.start(), m.end()), True
    if (m := _DIARIO.search(norm)) and not _bloqueado(norm, m.start()):
        return {"tipo": "cron"}, "Todos os dias", (m.start(), m.end()), True
    if (m := _UNICA.search(norm)) and not _bloqueado(norm, m.start()):
        dias = {"hoje": 0, "amanha": 1}.get(m["quando"], 2)
        return {"tipo": "data", "dias": dias}, m["quando"], (m.start(), m.end()), True
    return None


def interpretar(texto: str, agora: datetime | None = None) -> dict | None:
    """{tarefa, regra, descricao} se o texto pede uma rotina; None se é uma tarefa para já."""
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    norm = _normalizar(texto)
    achado = _frequencia(norm)
    if not achado or (len(norm) > LIMITE_SEM_PEDIDO and not _PEDE_ROTINA.search(norm)):
        return None
    regra, desc, trecho, usa_horario = achado
    trechos = [trecho]
    if usa_horario:
        horarios = _horarios(norm, [trecho])
        trechos += [(a, b) for *_, a, b in horarios]
        if regra["tipo"] == "data":
            if not horarios:
                return None  # "amanhã" sem horário é ambíguo demais
            h, mi = horarios[0][:2]
            quando = (agora + timedelta(days=regra.pop("dias"))).replace(hour=h, minute=mi, second=0, microsecond=0)
            if quando <= agora:
                return None  # "hoje às 8h" quando já passou: executa agora
            rotulo = {0: "Hoje", 1: "Amanhã"}.get((quando.date() - agora.date()).days, "Depois de amanhã")
            regra["quando"] = quando.isoformat()
            desc = f"{rotulo} ({quando:%d/%m}) às {_hhmm(h, mi)}"
        else:
            if not horarios:
                horarios = [(*HORA_PADRAO, 0, 0)]
            minuto = horarios[0][1]
            horas = sorted({h for h, mi, *_ in horarios if mi == minuto})
            regra.update(hora=",".join(map(str, horas)), minuto=minuto)
            desc += " às " + " e ".join(_hhmm(h, minuto) for h in horas)
    tarefa = _limpar_tarefa(texto, trechos)
    if len(re.sub(r"\W", "", tarefa)) < 3:
        return None
    return {"tarefa": tarefa, "regra": regra, "descricao": desc}


def e_agendamento(texto: str) -> bool:
    return interpretar(texto) is not None


# --- Agendador ----------------------------------------------------------------------------

def _gatilho(regra: dict):
    if regra["tipo"] == "intervalo":
        return IntervalTrigger(minutes=int(regra["minutos"]), timezone=FUSO)
    if regra["tipo"] == "data":
        return DateTrigger(run_date=datetime.fromisoformat(regra["quando"]), timezone=FUSO)
    return CronTrigger(day=regra.get("dia"), day_of_week=regra.get("dia_semana"),
                       hour=regra.get("hora", 9), minute=regra.get("minuto", 0), timezone=FUSO)


def proxima_execucao(regra: dict, agora: datetime | None = None) -> datetime | None:
    agora = agora or datetime.now(FUSO)
    return _gatilho(regra).get_next_fire_time(None, agora)


def _id_job(rotina_id: int) -> str:
    return f"rotina-{rotina_id}"


def _agendar(linha) -> None:
    if _agendador is None:
        return  # ainda não iniciado: iniciar() carrega do banco
    regra = json.loads(linha["regra"])
    _agendador.add_job(_executar, _gatilho(regra), args=[linha["id"]], id=_id_job(linha["id"]),
                       replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=600)


def _desagendar(rotina_id: int) -> None:
    if _agendador and _agendador.get_job(_id_job(rotina_id)):
        _agendador.remove_job(_id_job(rotina_id))


def _obter(rotina_id: int):
    return _db().execute("SELECT * FROM agendamentos WHERE id = ?", (rotina_id,)).fetchone()


def desativar(rotina_id: int) -> None:
    with _db() as db:
        db.execute("UPDATE agendamentos SET ativo = 0 WHERE id = ?", (rotina_id,))
    _desagendar(rotina_id)


async def criar(login: str, andar: str, agente_id: str, texto: str) -> dict | None:
    """Cria a rotina se o texto for um agendamento; None = seguir com a tarefa normal."""
    pedido = interpretar(texto)
    if not pedido:
        return None
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO agendamentos (usuario, andar, agente, tarefa, regra, descricao, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (login, andar, agente_id, pedido["tarefa"], json.dumps(pedido["regra"]), pedido["descricao"], tarefas._agora()),
        )
    linha = _obter(cursor.lastrowid)
    _agendar(linha)
    proxima = proxima_execucao(pedido["regra"])
    quando = f" Próxima execução: {proxima:%d/%m} às {proxima:%H:%M}." if proxima else ""
    desc = pedido["descricao"]
    await gerenciador.enviar_para_usuario(login, {
        "tipo": "aviso", "andar": andar, "agente": agente_id, "titulo": "Rotina agendada", "liberar": True,
        "texto": f"Vou executar \"{pedido['tarefa']}\" {desc[:1].lower() + desc[1:]}.{quando}",
    })
    return {**_publica(linha), "proxima_execucao": proxima.isoformat() if proxima else None}


async def _executar(rotina_id: int) -> None:
    """Disparo do job: entrega a tarefa ao pipeline normal."""
    import orquestrador  # import tardio: evita ciclo
    from estado import AGENTES_PRODUCAO, Status, buscar_agente

    linha = _obter(rotina_id)
    if not linha or not linha["ativo"]:
        return _desagendar(rotina_id)
    agente = buscar_agente(linha["andar"], linha["agente"])
    if not agente:
        log.info("Rotina %s: agente %s não existe mais; desativada.", rotina_id, linha["agente"])
        return desativar(rotina_id)
    unica = json.loads(linha["regra"])["tipo"] == "data"
    for _ in range(TENTATIVAS_OCUPADO):  # agente ocupado: espera em vez de atropelar a tarefa atual
        if agente.status != Status.trabalhando:
            break
        await asyncio.sleep(ESPERA_OCUPADO_S)
    else:
        log.warning("Rotina %s pulada: %s ocupado.", rotina_id, agente.id)
        if unica:
            desativar(rotina_id)
        return
    with _db() as db:
        db.execute("UPDATE agendamentos SET ultima_execucao = ?, execucoes = execucoes + 1"
                   + (", ativo = 0" if unica else "") + " WHERE id = ?", (tarefas._agora(), rotina_id))
    await gerenciador.enviar_para_usuario(linha["usuario"], {
        "tipo": "aviso", "andar": linha["andar"], "agente": linha["agente"], "titulo": "Rotina em execução",
        "texto": f"Executando a rotina \"{linha['tarefa']}\" ({linha['descricao']}).",
    })
    try:
        if agente.id in AGENTES_PRODUCAO:  # PNG/MP4 seguem pela produção, como no chat
            import producao
            await producao.enfileirar(linha["usuario"], linha["andar"], agente, linha["tarefa"])
        else:
            await orquestrador.nova_tarefa(linha["usuario"], linha["andar"], agente, linha["tarefa"])
    except Exception:
        log.exception("Rotina %s falhou ao iniciar.", rotina_id)


def iniciar() -> None:
    """Sobe o agendador no loop do FastAPI e recarrega as rotinas ativas."""
    global _agendador
    if _agendador is None:
        _agendador = AsyncIOScheduler(timezone=FUSO)
        _agendador.start()
    agora = datetime.now(FUSO)
    for linha in _db().execute("SELECT * FROM agendamentos WHERE ativo = 1").fetchall():
        regra = json.loads(linha["regra"])
        if regra["tipo"] == "data" and datetime.fromisoformat(regra["quando"]) <= agora:
            if agora - datetime.fromisoformat(regra["quando"]) > timedelta(hours=1):
                desativar(linha["id"])  # perdeu o horário com o servidor fora do ar
                continue
            regra["quando"] = (agora + timedelta(seconds=5)).isoformat()  # atrasou pouco: roda já
            with _db() as db:
                db.execute("UPDATE agendamentos SET regra = ? WHERE id = ?", (json.dumps(regra), linha["id"]))
            linha = _obter(linha["id"])
        _agendar(linha)
    log.info("Agendador iniciado com %d rotina(s).", len(_agendador.get_jobs()))


def parar() -> None:
    global _agendador
    if _agendador is not None:
        try:
            _agendador.shutdown(wait=False)
        except RuntimeError:  # loop já encerrado
            pass
        _agendador = None


# --- API ----------------------------------------------------------------------------------

rotas = APIRouter(prefix="/api/agendamentos")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def _publica(linha) -> dict:
    job = _agendador.get_job(_id_job(linha["id"])) if _agendador and linha["ativo"] else None
    proxima = getattr(job, "next_run_time", None) if job else None
    return {k: linha[k] for k in ("id", "usuario", "andar", "agente", "tarefa", "descricao", "ultima_execucao",
                                  "execucoes")} | {"ativo": bool(linha["ativo"]),
                                                   "proxima_execucao": proxima.isoformat() if proxima else None}


@rotas.get("")
def listar(andar: str | None = None, agente: str | None = None, inativas: bool = False,
           authorization: str = Header("")):
    usuario = _usuario(authorization)
    condicoes, params = ([] if inativas else ["ativo = 1"]), []
    if usuario["role"] != "diretoria":  # funcionário vê só as próprias
        condicoes.append("usuario = ?")
        params.append(usuario["sub"])
    for coluna, valor in (("andar", andar), ("agente", agente)):
        if valor:
            condicoes.append(f"{coluna} = ?")
            params.append(valor)
    filtro = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    linhas = _db().execute(f"SELECT * FROM agendamentos {filtro} ORDER BY id DESC LIMIT 200", params).fetchall()
    return {"agendamentos": [_publica(linha) for linha in linhas]}


@rotas.delete("/{rotina_id}")
def cancelar(rotina_id: int, authorization: str = Header("")):
    usuario = _usuario(authorization)
    linha = _obter(rotina_id)
    if not linha:
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    if linha["usuario"] != usuario["sub"] and usuario["role"] != "diretoria":
        raise HTTPException(status_code=403, detail="Só o dono ou a diretoria podem cancelar esta rotina.")
    desativar(rotina_id)
    return {"ok": True}
