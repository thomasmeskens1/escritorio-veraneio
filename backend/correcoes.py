"""Correções do dono viram regras (padrão adaptado de rebelytics/one-skill-to-rule-them-all).

1. Detectar: quando o Thomas corrige um agente logo depois de uma resposta ("não é assim...", "na verdade...",
   "nunca...", "prefiro..."), a correção vira uma OBSERVAÇÃO (agente, texto, trecho da resposta corrigida).
   O pedido segue normal: o agente corrige na hora.
2. Revisar: no popup do Cérebro, o Thomas edita a regra e aprova (para o agente ou para todos) ou descarta.
3. Aplicar: regra aprovada entra SEMPRE no contexto do agente (ou de todos) e é ensinada ao Cérebro.
4. Lembrar: uma vez por semana, se houver correções pendentes, aviso no chat do Cérebro.
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import config
import regras_parecidas
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
# Onda 2 (email_marketing-05, 31/10/2026): "ficou ótimo, salva", "pode salvar para os próximos e-mails", "guarda como
# referência", "aprovei", "pode disparar" também contam (tarefa 129: o pedido de guardar se perdia no histórico).
ELOGIO = re.compile(
    r"\b(adorei|amei|ficou (muito )?(ótim|otim|lind|show|incr[ií]vel|perfeit|excelente|sensacional|top|"
    r"maravilh|bom|boa|legal)\w*\b(?!\s*\?)|gostei (muito|demais|bastante)|curti (muito|demais)|"
    r"exatamente (o que|isso)|(podemos|pode|vamos) seguir (assim|nesse|neste|desse|deste)|"
    r"(é|e) (isso|esse) (mesmo|a[ií])|mandou bem|arrasou|sensacional|maravilhos[oa]|nota 10|parab[ée]ns|"
    r"(salv|guard)(a|e|ar|em)\s+(isso|essa|esse|est[ae]s?|para|pra|nos|nas|de\s+refer|como\s+(refer|modelo|padr))|"
    r"(use|usar|usem|fica|vale)\s+(isso|esse|essa|este|esta)?\s*como\s+(refer[eê]ncia|modelo|padr[aã]o)|"
    r"aprovei|aprovad[oa]s?\s+(pela|por|pra|para)|pode\s+(publicar|disparar))", re.IGNORECASE)
# Adjetivo solto ("perfeito", "excelente") só é elogio em mensagem curta: num texto colado como exemplo ele é
# conteúdo ("...área gourmet, perfeita para reunir a família", Francielle, 29/10/2026, falso elogio).
ELOGIO_CURTO = re.compile(r"\b(perfeit[oa]|excelente|aprovad[oa]|ótimo|otimo|show|top|lindo|linda)\b", re.IGNORECASE)
# "não ficou bom", "não precisa salvar"; "ficou bom, mas troca o título" é ajuste, não elogio.
NEGA_ELOGIO = re.compile(r"\bn[aã]o\s+(\w+\s+){0,2}(ficou|gostei|curti|salv|guard)", re.IGNORECASE)
ELOGIO_COM_AJUSTE = re.compile(r"\b(mas|por[ée]m|s[oó] que)\b.{0,60}?\b(troc|mud|ajust|tir|coloc|corrij|corrig|"
                               r"faltou|refa[cç]|diminu|aument)", re.IGNORECASE)
# Direcionamento para as próximas peças no meio da mensagem (tarefa 287, 12/11/2026, João: "quero que considerem os
# direcionamentos ... para quando forem produzir outros pedidos futuros"): vira observação como a correção.
DIRECIONAMENTO = re.compile(r"\b(considerem|considere|levem em conta|leve em conta|tenham em mente|guardem|lembrem|"
                            r"memorizem|aprendam)\b.{0,120}?\b(pr[oó]xim\w*|futur\w*|daqui (?:pra|para) frente)",
                            re.IGNORECASE | re.DOTALL)
TAMANHO_CURTO = 150
BORDA_COMENTARIO = 250  # o comentário da pessoa fica no começo ou no fim; o meio é o texto colado


def e_elogio(texto: str) -> bool:
    import insatisfacoes  # "não ficou bom", "não gostei muito" nunca são elogio

    texto = (texto or "").strip()
    inicio = texto[:BORDA_COMENTARIO]
    if insatisfacoes.e_negativa(texto) or NEGA_ELOGIO.search(inicio) or ELOGIO_COM_AJUSTE.search(inicio):
        return False
    if len(texto) <= TAMANHO_CURTO:
        return bool(ELOGIO.search(texto) or ELOGIO_CURTO.search(texto))
    bordas = f"{texto[:BORDA_COMENTARIO]}\n{texto[-BORDA_COMENTARIO:]}"
    return bool(ELOGIO.search(bordas))


# Linha aprovada do e-mail (email_marketing-05): o elogio guarda assunto, pré-header, título e botões da resposta
# elogiada, onde quer que estejam nela (antes só os 400 primeiros caracteres iam para a Diretoria).
GANCHO = re.compile(r"^[\W_]*(assunto|pr[ée]-?header|t[ií]tulo|bot[aã]o(?:\s+principal)?|cta|chamada)\b[^:\n]{0,30}:"
                    r"[\s*_]*(.+)$", re.IGNORECASE | re.MULTILINE)
AGENTES_COM_GANCHOS = {"email_marketing"}


def ganchos_aprovados(resposta: str) -> str:
    """"Assunto: ... | Pré-header: ..." tirado da resposta (até 6 linhas), ou ""."""
    vistos = []
    for rotulo, valor in GANCHO.findall(resposta or ""):
        linha = f"{rotulo.strip().capitalize()}: {valor.strip(' *_')[:150]}"
        if linha not in vistos:
            vistos.append(linha)
    return " | ".join(vistos[:6])


def resposta_da_observacao(agente_id: str, tipo: str, resposta: str) -> str:
    """Trecho da resposta guardado com a observação; no elogio do E-mail Marketing, a linha aprovada vem primeiro."""
    if tipo == "elogio" and agente_id in AGENTES_COM_GANCHOS and (ganchos := ganchos_aprovados(resposta)):
        return f"Linha aprovada: {ganchos}\n\n{(resposta or '')[:400]}"[:1200]
    return (resposta or "")[:400]
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
        # Regra parecida (Onda 2, cerebro-21): a substituída fica guardada (ativa = 0) com a que entrou no lugar.
        if "substituida_por" not in {c[1] for c in db.execute("PRAGMA table_info(regras_aprendidas)")}:
            db.execute("ALTER TABLE regras_aprendidas ADD COLUMN substituida_por INTEGER")
        _pronto = True
    return db


def registrar_se_correcao(usuario: str, andar: str, agente_id: str, texto: str) -> bool:
    """Guarda a observação quando um usuário corrige OU elogia uma resposta recente deste agente. Desde 29/10/2026
    vale para TODOS os usuários (Thomas); quem aprova e vira regra é só a Diretoria. Roda em segundo plano (main.py):
    nunca atrasa a resposta."""
    if CORRECAO.search(texto or "") or DIRECIONAMENTO.search(texto or ""):
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
                    resposta_da_observacao(agente_id, tipo, anterior["resposta"]), tipo))
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


# Produção no Max (brainstorm de 31/10/2026, editor_video-09 e moviemaker-14): quem monta o arquivo também segue o
# que a equipe aprovou para quem planeja aquele formato (vídeo: Editor + Moviemaker; arte: Criador + Designer).
AFINS_NA_PRODUCAO = {"editor_video": ("editor_video", "moviemaker"), "criador_imagens": ("criador_imagens", "designer")}


def regras_da_producao(agente_id: str, empresa: str = "*") -> str:
    """Regras aprovadas que valem para a peça produzida no Max por `agente_id` ("" se não há)."""
    agentes = AFINS_NA_PRODUCAO.get(agente_id, (agente_id,))
    marcadores = ",".join("?" * len(agentes))
    linhas = _db().execute(
        f"SELECT regra FROM regras_aprendidas WHERE ativa = 1 AND agente IN ({marcadores}, '*') AND empresa IN (?, '*') "
        "ORDER BY id DESC LIMIT ?", (*agentes, empresa, MAX_REGRAS_NO_CONTEXTO)).fetchall()
    if not linhas:
        return ""
    return ("REGRAS APROVADAS PELA EQUIPE a partir de correções (valem sobre os manuais; o pedido desta peça vale "
            "sobre elas):\n" + "\n".join(f"- {l['regra']}" for l in reversed(linhas)))


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
    substituir: int | None = None    # regra parecida (cerebro-21) que sai do contexto no lugar desta (fica guardada)


class Rascunho(BaseModel):
    regra: str = Field("", max_length=500)
    escopo: str = Field("agente", pattern="^(agente|todos)$")
    todas_as_empresas: bool = False

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
    # O aprendizado da semana já vem escrito como regra pelo Cérebro: a trava vale só para correções e elogios.
    if obs["tipo"] not in ("aprendizado", "estudo") and len(crua) >= REGRA_CRUA_MIN and crua in regra:
        raise HTTPException(status_code=422, detail="Escreva a regra em uma ou duas frases: o texto inteiro da conversa "
                                                    "não serve de regra para os próximos pedidos.")
    empresa = "*" if decisao.todas_as_empresas else empresa_da_observacao(obs)
    if decisao.substituir and not _db().execute("SELECT 1 FROM regras_aprendidas WHERE id = ? AND ativa = 1",
                                                (decisao.substituir,)).fetchone():
        raise HTTPException(status_code=404, detail=f"A regra #{decisao.substituir} não está mais ativa.")
    parecidas = await asyncio.to_thread(regras_parecidas.parecidas, regra, agente, empresa, observacao_id)
    with _db() as db:
        db.execute("UPDATE observacoes SET status = 'aprovada', regra = ?, escopo = ?, decidido_em = ? WHERE id = ?",
                   (regra, decisao.escopo, tarefas._agora(), observacao_id))
        nova = db.execute("INSERT INTO regras_aprendidas (agente, regra, criada_em, observacao_id, empresa) "
                          "VALUES (?, ?, ?, ?, ?)", (agente, regra, tarefas._agora(), observacao_id, empresa)).lastrowid
        if decisao.substituir:  # escolha de quem aprova; a antiga continua guardada
            db.execute("UPDATE regras_aprendidas SET ativa = 0, substituida_por = ? WHERE id = ?",
                       (nova, decisao.substituir))
    alvo = "todos os agentes" if agente == "*" else _nome(agente)
    # Pelo login do dono do Cérebro: a Diretoria aprova, mas só a conta do Thomas grava no Cérebro (antes, com João ou
    # Lucca aprovando, a regra ficava ativa sem entrar no Cérebro e a tela recebia erro 500; revisão de 30/10, 2.14).
    quem = usuario.get("nome") or usuario["sub"]
    await cerebro.ensinar(config.DONO_MAX, f"Aprenda: Regra aprovada por {quem} para {alvo}: {regra}", empresa)
    return {"ok": True, "regra_id": nova, "substituida": decisao.substituir,
            "parecidas": [c for c in parecidas if c["id"] != decisao.substituir or c["tipo"] != "regra"]}


@rotas.post("/{observacao_id}/parecidas")
def ver_parecidas(observacao_id: int, rascunho: Rascunho, authorization: str = Header("")):
    """Aviso "parecida com a regra #N" (cerebro-21) para o pop-up, antes de aprovar; por embedding ou por texto."""
    _dono(authorization)
    obs = _db().execute("SELECT * FROM observacoes WHERE id = ?", (observacao_id,)).fetchone()
    if not obs:
        raise HTTPException(status_code=404, detail="Correção não encontrada.")
    agente = "*" if rascunho.escopo == "todos" else obs["agente"]
    empresa = "*" if rascunho.todas_as_empresas else empresa_da_observacao(obs)
    achadas = regras_parecidas.parecidas(rascunho.regra.strip() or obs["correcao"], agente, empresa,
                                         ignorar_observacao=observacao_id)
    return {"parecidas": [{**c, "agente_nome": _nome(c["agente"])} for c in achadas],
            "aviso": regras_parecidas.aviso(achadas)}


@rotas.get("/sinais")
def ver_sinais(authorization: str = Header("")):
    """Sinais de aprendizado só registrados (cerebro-20): contagem por tipo, agente e empresa; nada é treinado."""
    import sinais

    _dono(authorization)
    return sinais.resumo()


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
