"""Rotinas agendadas: criadas SÓ pelo botão "Agendar tarefa" da ficha do agente (formulário estruturado).

Antes, um interpretador de frases criava rotinas a partir do texto do chat, e briefings longos com "todos os dias"
no conteúdo viravam rotina (testes reais de 28 e 29/10/2026). Decisão do Thomas (29/10/2026): mensagem no chat
nunca agenda nada. No horário, a tarefa segue o pipeline normal (orquestrador.nova_tarefa): status no canvas,
resposta no chat, histórico e registro.
"""

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import acesso
import empresas
import tarefas
from auth import validar_token
from conexoes import gerenciador

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
MINIMO_MINUTOS = 15
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
    execucoes INTEGER NOT NULL DEFAULT 0,
    empresa TEXT                  -- empresa da conversa (Marketing e Cérebro); NULL nas rotinas antigas
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
        if "empresa" not in {c[1] for c in db.execute("PRAGMA table_info(agendamentos)")}:
            db.execute("ALTER TABLE agendamentos ADD COLUMN empresa TEXT")
        _esquema_ok = True
    return db


# --- Regra a partir do formulário ------------------------------------------------------------

FREQUENCIAS = ("Uma vez", "Todos os dias", "De segunda a sexta", "Fins de semana", "Toda semana", "Todo mês",
               "A cada X horas")
DIAS_SEMANA = {"Segunda": "mon", "Terça": "tue", "Quarta": "wed", "Quinta": "thu", "Sexta": "fri",
               "Sábado": "sat", "Domingo": "sun"}


class Pedido(BaseModel):
    andar: str
    agente: str
    tarefa: str = Field(min_length=3)
    frequencia: str
    horario: str = ""      # "HH:MM"
    data: str = ""         # "AAAA-MM-DD" (Uma vez)
    dia_semana: str = ""   # Segunda..Domingo (Toda semana)
    dia_mes: int = 0       # 1..31 (Todo mês)
    intervalo_horas: int = 0
    empresa: str = ""


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _horario(texto: str) -> tuple[int, int]:
    try:
        valor = time.fromisoformat(texto.strip())
    except ValueError:
        raise ValueError("Informe o horário (HH:MM).") from None
    return valor.hour, valor.minute


def regra_do_formulario(dados: Pedido, agora: datetime | None = None) -> tuple[dict, str]:
    """(regra do gatilho, descrição) do formulário; ValueError com a mensagem para o usuário."""
    agora = agora or datetime.now(FUSO)
    freq = dados.frequencia
    if freq not in FREQUENCIAS:
        raise ValueError("Escolha a frequência.")
    if freq == "A cada X horas":
        if not 1 <= dados.intervalo_horas <= 168:
            raise ValueError("Informe de quantas em quantas horas (1 a 168).")
        n = dados.intervalo_horas
        return {"tipo": "intervalo", "minutos": n * 60}, "A cada hora" if n == 1 else f"A cada {n} horas"
    h, m = _horario(dados.horario)
    if freq == "Uma vez":
        try:
            dia = date.fromisoformat(dados.data)
        except ValueError:
            raise ValueError("Informe a data.") from None
        quando = datetime.combine(dia, time(h, m), FUSO)
        if quando <= agora:
            raise ValueError("A data e o horário já passaram.")
        return {"tipo": "data", "quando": quando.isoformat()}, f"Em {quando:%d/%m/%Y} às {_hhmm(h, m)}"
    regra = {"tipo": "cron", "hora": str(h), "minuto": m}
    if freq == "De segunda a sexta":
        regra["dia_semana"], desc = "mon-fri", "De segunda a sexta"
    elif freq == "Fins de semana":
        regra["dia_semana"], desc = "sat,sun", "Nos fins de semana"
    elif freq == "Toda semana":
        if dados.dia_semana not in DIAS_SEMANA:
            raise ValueError("Escolha o dia da semana.")
        regra["dia_semana"] = DIAS_SEMANA[dados.dia_semana]
        desc = f"{'Todo' if dados.dia_semana in ('Sábado', 'Domingo') else 'Toda'} {dados.dia_semana.lower()}"
    elif freq == "Todo mês":
        if not 1 <= dados.dia_mes <= 31:
            raise ValueError("Informe o dia do mês (1 a 31).")
        regra["dia"], desc = dados.dia_mes, f"Todo dia {dados.dia_mes} do mês"
    else:
        desc = "Todos os dias"
    return regra, f"{desc} às {_hhmm(h, m)}"


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


def criar(login: str, andar: str, agente_id: str, tarefa: str, regra: dict, descricao: str,
          empresa: str | None) -> dict:
    with _db() as db:
        cursor = db.execute(
            "INSERT INTO agendamentos (usuario, andar, agente, tarefa, regra, descricao, criado_em, empresa) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (login, andar, agente_id, tarefa, json.dumps(regra), descricao, tarefas._agora(), empresa),
        )
    linha = _obter(cursor.lastrowid)
    _agendar(linha)
    proxima = proxima_execucao(regra)
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
        empresa = linha["empresa"] or empresas.PADRAO
        if agente.id in AGENTES_PRODUCAO:  # PNG/MP4 seguem pela produção, como no chat
            import producao
            await producao.enfileirar(linha["usuario"], linha["andar"], agente, linha["tarefa"], empresa=empresa)
        else:
            await orquestrador.nova_tarefa(linha["usuario"], linha["andar"], agente, linha["tarefa"], empresa=empresa)
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


@rotas.post("")
def agendar(dados: Pedido, authorization: str = Header("")):
    """Botão "Agendar tarefa" da ficha do agente: o ÚNICO jeito de criar uma rotina."""
    import config
    from estado import AGENTES_PRODUCAO, buscar_agente

    usuario = _usuario(authorization)
    agente = buscar_agente(dados.andar, dados.agente)
    if not agente or agente.tipo != "ia" or not acesso.pode_usar(usuario, dados.andar, agente.id):
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    if agente.id in AGENTES_PRODUCAO and usuario["sub"] != config.DONO_MAX:
        raise HTTPException(status_code=403, detail="A produção de imagens e vídeos é exclusiva da conta do Thomas.")
    limite = 30000 if agente.id == "gestor" else 8000  # os mesmos limites do chat (main.py)
    tarefa = dados.tarefa.strip()
    if len(tarefa) > limite:
        raise HTTPException(status_code=422, detail=f"A tarefa deve ter até {limite} caracteres.")
    empresa = dados.empresa if (empresas.valida(dados.empresa) or dados.empresa == empresas.COMUM) else None
    if dados.andar == "marketing" and not empresa:
        raise HTTPException(status_code=422, detail="Escolha a empresa no seletor do topo do chat antes de agendar.")
    try:
        regra, descricao = regra_do_formulario(dados)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from None
    return criar(usuario["sub"], dados.andar, agente.id, tarefa, regra, descricao, empresa)


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
