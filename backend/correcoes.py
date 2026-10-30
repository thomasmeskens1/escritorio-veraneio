"""Correções do dono viram regras (padrão adaptado de rebelytics/one-skill-to-rule-them-all).

1. Detectar: quando o Thomas corrige um agente logo depois de uma resposta ("não é assim...", "na verdade...",
   "nunca...", "prefiro..."), a correção vira uma OBSERVAÇÃO (agente, texto, trecho da resposta corrigida).
   O pedido segue normal: o agente corrige na hora.
2. Revisar: no popup do Cérebro, o Thomas edita a regra e aprova (para o agente ou para todos) ou descarta.
3. Aplicar: regra aprovada entra SEMPRE no contexto do agente (ou de todos) e é ensinada ao Cérebro.
4. Lembrar: uma vez por semana, se houver correções pendentes, aviso no chat do Cérebro.
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import config
import tarefas
from auth import carregar_usuarios, validar_token
from estado import andar_do_agente, buscar_agente

rotas = APIRouter(prefix="/api/correcoes")

CORRECAO = re.compile(
    r"^\s*(n[aã]o\s+(é|era|foi|está|use|usa|coloque|ponha|escreva|fa[cç]a|mencione|quero)|na\s+verdade|"
    r"est[aá]\s+errad|errou|errado|corrij|corrigindo|nunca|sempre|prefiro|evite|cuidado|isso\s+n[aã]o|"
    r"o\s+certo\s+[ée]|o\s+correto\s+[ée]|lembre(-se)?\s+que)", re.IGNORECASE)
# Elogio com intenção de repetir (teste real, 29/10/2026, Francielle: "adorei, podemos seguir assim nas próximas,
# exatamente o que eu quero"): vira observação "elogio" para a Diretoria aprovar como padrão a seguir.
ELOGIO = re.compile(
    r"\b(adorei|amei|ficou (ótim|otim|lind|show|incr[ií]vel)|gostei muito|"
    r"exatamente (o que|isso)|(podemos|pode|vamos) seguir (assim|nesse|neste|desse|deste)|"
    r"(é|e) (isso|esse) (mesmo|a[ií])|mandou bem)", re.IGNORECASE)
# Adjetivo solto ("perfeito", "excelente") só é elogio em mensagem curta: num texto colado como exemplo ele é
# conteúdo ("...área gourmet, perfeita para reunir a família", Francielle, 29/10/2026, falso elogio).
ELOGIO_CURTO = re.compile(r"\b(perfeit[oa]|excelente|aprovad[oa]|ótimo|otimo|show)\b", re.IGNORECASE)
TAMANHO_CURTO = 150
BORDA_COMENTARIO = 250  # o comentário da pessoa fica no começo ou no fim; o meio é o texto colado


def e_elogio(texto: str) -> bool:
    texto = (texto or "").strip()
    if len(texto) <= TAMANHO_CURTO:
        return bool(ELOGIO.search(texto) or ELOGIO_CURTO.search(texto))
    bordas = f"{texto[:BORDA_COMENTARIO]}\n{texto[-BORDA_COMENTARIO:]}"
    return bool(ELOGIO.search(bordas))
JANELA_H = 24             # a correção precisa vir até 24 h depois da resposta do agente
MAX_REGRAS_NO_CONTEXTO = 15
LEMBRETE_DIAS = 7

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS observacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, usuario TEXT NOT NULL, andar TEXT NOT NULL,
    agente TEXT NOT NULL, tarefa_anterior INTEGER, correcao TEXT NOT NULL, resposta_anterior TEXT,
    status TEXT NOT NULL DEFAULT 'nova', regra TEXT, escopo TEXT, decidido_em TEXT);
CREATE TABLE IF NOT EXISTS regras_aprendidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT NOT NULL, regra TEXT NOT NULL, criada_em TEXT NOT NULL,
    observacao_id INTEGER, ativa INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS correcoes_lembrete (id INTEGER PRIMARY KEY CHECK (id = 1), em TEXT NOT NULL);
"""
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.executescript(_ESQUEMA)
        if "tipo" not in {c[1] for c in db.execute("PRAGMA table_info(observacoes)")}:
            db.execute("ALTER TABLE observacoes ADD COLUMN tipo TEXT NOT NULL DEFAULT 'correcao'")
        # Empresa da regra (revisão de 30/10/2026, item 1.7): regra de uma empresa não vale para as outras.
        if "empresa" not in {c[1] for c in db.execute("PRAGMA table_info(regras_aprendidas)")}:
            db.execute("ALTER TABLE regras_aprendidas ADD COLUMN empresa TEXT NOT NULL DEFAULT '*'")
        _pronto = True
    return db


def registrar_se_correcao(usuario: str, andar: str, agente_id: str, texto: str) -> bool:
    """Guarda a observação quando um usuário corrige OU elogia uma resposta recente deste agente. Desde 29/10/2026
    vale para TODOS os usuários (Thomas); quem aprova e vira regra é só a Diretoria. Roda em segundo plano (main.py):
    nunca atrasa a resposta."""
    if CORRECAO.search(texto or ""):
        tipo = "correcao"
    elif e_elogio(texto):
        tipo = "elogio"
    else:
        return False
    desde = (datetime.now(timezone.utc) - timedelta(hours=JANELA_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    anterior = _db().execute(
        "SELECT id, resposta FROM tarefas WHERE usuario = ? AND andar = ? AND agente = ? AND status = 'concluida' "
        "AND concluida_em >= ? ORDER BY id DESC LIMIT 1", (usuario, andar, agente_id, desde)).fetchone()
    if not anterior:
        return False
    with _db() as db:
        db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, resposta_anterior, "
                   "tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (tarefas._agora(), usuario, andar, agente_id, anterior["id"], texto.strip()[:1000],
                    (anterior["resposta"] or "")[:400], tipo))
    import atividade  # import tardio: roda em thread; o aviso vai pelo loop do servidor

    atividade._no_loop(avisar_diretoria(tipo))
    return True


def pendentes() -> int:
    return _db().execute("SELECT COUNT(*) FROM observacoes WHERE status = 'nova'").fetchone()[0]


async def avisar_diretoria(tipo: str = "") -> None:
    """Notificação do ratinho do Cérebro (canto inferior direito) para a Diretoria e o master conectados
    (Thomas, 29/10/2026): há correções ou elogios esperando aprovação."""
    from auth import e_master
    from conexoes import gerenciador

    total = pendentes()
    for ws, usuario in list(gerenciador.ativas.items()):
        if usuario.get("role") == "diretoria" or e_master(usuario["sub"]):
            await gerenciador.enviar(ws, {"tipo": "correcao_nova", "total": total, "ultima": tipo})


def regras_para(agente_id: str, empresa: str = "*") -> str:
    """Regras aprovadas pelo Thomas para este agente e para todos (sempre no contexto), da empresa do trabalho e as
    que valem para as três."""
    linhas = _db().execute(
        "SELECT regra FROM regras_aprendidas WHERE ativa = 1 AND agente IN (?, '*') AND empresa IN (?, '*') "
        "ORDER BY id DESC LIMIT ?", (agente_id, empresa, MAX_REGRAS_NO_CONTEXTO)).fetchall()
    if not linhas:
        return ""
    return "Regras aprovadas pelo Thomas a partir de correções (valem sobre os manuais):\n" + "\n".join(
        f"- {l['regra']}" for l in reversed(linhas))


def pendentes() -> int:
    return _db().execute("SELECT COUNT(*) FROM observacoes WHERE status = 'nova'").fetchone()[0]


def lembrete_semanal() -> str | None:
    """Texto do aviso semanal (no máximo um a cada LEMBRETE_DIAS), ou None."""
    n = pendentes()
    if not n:
        return None
    ultimo = _db().execute("SELECT em FROM correcoes_lembrete WHERE id = 1").fetchone()
    limite = (datetime.now(timezone.utc) - timedelta(days=LEMBRETE_DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if ultimo and ultimo["em"] > limite:
        return None
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO correcoes_lembrete (id, em) VALUES (1, ?)", (tarefas._agora(),))
    return (f"Revisão semanal: há {n} correção(ões) suas esperando para virar regra. Abra a ficha do Cérebro, "
            "seção \"Correções para revisar\", e aprove ou descarte cada uma.")


# --- Rotas (só a Diretoria) -------------------------------------------------------------------

def _dono(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if usuario["role"] != "diretoria" and not usuario.get("master"):
        raise HTTPException(status_code=403, detail="Só a Diretoria revisa as correções.")
    return usuario


def _nome(agente_id: str) -> str:
    if agente_id == "*":
        return "Todos os agentes"
    andar = andar_do_agente(agente_id)
    agente = buscar_agente(andar, agente_id) if andar else None
    return agente.nome if agente else agente_id


class Decisao(BaseModel):
    regra: str = Field(min_length=5, max_length=500)
    escopo: str = Field("agente", pattern="^(agente|todos)$")
    todas_as_empresas: bool = False  # padrão: só a empresa da tarefa que motivou a correção

# Regra que é o texto inteiro da conversa (ex.: uma legenda colada com "adorei") não é regra: vira cópia de um caso.
REGRA_CRUA_MIN = 200


def empresa_da_observacao(obs) -> str:
    """Empresa da tarefa que motivou a observação; '*' quando não há tarefa (ex.: consolidação semanal)."""
    tarefa = obs["tarefa_anterior"] and tarefas.obter(obs["tarefa_anterior"])
    return (tarefa["empresa"] if tarefa and tarefa["empresa"] else "*")


@rotas.get("")
def listar(authorization: str = Header("")):
    _dono(authorization)
    novas = _db().execute("SELECT * FROM observacoes WHERE status = 'nova' ORDER BY id DESC LIMIT 50").fetchall()
    regras = _db().execute("SELECT * FROM regras_aprendidas WHERE ativa = 1 ORDER BY id DESC").fetchall()
    nomes = {login: dados["nome"] for login, dados in carregar_usuarios().items()}
    import empresas

    return {"observacoes": [{"id": o["id"], "em": o["em"], "agente": o["agente"], "agente_nome": _nome(o["agente"]),
                             "empresa_nome": empresas.nome(empresa_da_observacao(o)),
                             "autor": "Cérebro" if o["usuario"] == "cerebro" else nomes.get(o["usuario"], o["usuario"]),
                             "tipo": o["tipo"],
                             "correcao": o["correcao"], "resposta_anterior": o["resposta_anterior"]} for o in novas],
            "regras": [{"id": r["id"], "agente": r["agente"], "agente_nome": _nome(r["agente"]), "regra": r["regra"],
                        "empresa_nome": empresas.nome(r["empresa"]), "criada_em": r["criada_em"]} for r in regras]}


@rotas.post("/{observacao_id}/aprovar")
async def aprovar(observacao_id: int, decisao: Decisao, authorization: str = Header("")):
    import cerebro  # import tardio: o Cérebro carrega o banco e os embeddings

    usuario = _dono(authorization)
    obs = _db().execute("SELECT * FROM observacoes WHERE id = ? AND status = 'nova'", (observacao_id,)).fetchone()
    if not obs:
        raise HTTPException(status_code=404, detail="Correção não encontrada ou já revisada.")
    agente = "*" if decisao.escopo == "todos" else obs["agente"]
    regra = decisao.regra.strip()
    crua = (obs["correcao"] or "").strip()
    if len(crua) >= REGRA_CRUA_MIN and crua in regra:
        raise HTTPException(status_code=422, detail="Escreva a regra em uma ou duas frases: o texto inteiro da conversa "
                                                    "não serve de regra para os próximos pedidos.")
    empresa = "*" if decisao.todas_as_empresas else empresa_da_observacao(obs)
    with _db() as db:
        db.execute("UPDATE observacoes SET status = 'aprovada', regra = ?, escopo = ?, decidido_em = ? WHERE id = ?",
                   (regra, decisao.escopo, tarefas._agora(), observacao_id))
        db.execute("INSERT INTO regras_aprendidas (agente, regra, criada_em, observacao_id, empresa) "
                   "VALUES (?, ?, ?, ?, ?)", (agente, regra, tarefas._agora(), observacao_id, empresa))
    alvo = "todos os agentes" if agente == "*" else _nome(agente)
    # Pelo login do dono do Cérebro: a Diretoria aprova, mas só a conta do Thomas grava no Cérebro (antes, com João ou
    # Lucca aprovando, a regra ficava ativa sem entrar no Cérebro e a tela recebia erro 500; revisão de 30/10, 2.14).
    quem = usuario.get("nome") or usuario["sub"]
    await cerebro.ensinar(config.DONO_MAX, f"Aprenda: Regra aprovada por {quem} para {alvo}: {regra}", empresa)
    return {"ok": True}


@rotas.post("/{observacao_id}/descartar")
def descartar(observacao_id: int, authorization: str = Header("")):
    _dono(authorization)
    with _db() as db:
        db.execute("UPDATE observacoes SET status = 'descartada', decidido_em = ? WHERE id = ? AND status = 'nova'",
                   (tarefas._agora(), observacao_id))
    return {"ok": True}


@rotas.post("/regras/{regra_id}/desativar")
def desativar_regra(regra_id: int, authorization: str = Header("")):
    _dono(authorization)
    with _db() as db:
        db.execute("UPDATE regras_aprendidas SET ativa = 0 WHERE id = ?", (regra_id,))
    return {"ok": True}
