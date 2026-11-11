"""Uma fila só de aprovações (Onda 2: N2-construtor-12, N2-designer-20, N2-estrategista-04 e N2-construtor-01).

Junta, na aba "Para aprovar" da Caixa de entrada, o que espera uma decisão:
  - proposta de agente novo do Construtor (decide quem pediu; o Thomas vê como informativo);
  - pedido de obra do Construtor (agente com ferramentas; só o Thomas);
  - rascunho da persona do Corporativo (manual 14; só o Thomas);
  - decisão de estudo ("Me ajude a decidir: ..." ao Estrategista; o Thomas registra a decisão);
  - folha de aprovação da peça sem 👍 (dono do pedido).
Cada item vence em 7 dias. Vencer só destaca: nada é apagado e nada é aprovado sozinho. Aprovar e recusar chamam as
funções de cada módulo (agentes_dinamicos.decidir, pedido_obra.decidir, persona_corporativo.aprovar/recusar,
avaliacoes.avaliar); só a decisão de estudo, que não tinha onde ficar, é gravada aqui.
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import agentes_dinamicos
import avaliacoes
import config
import encaminhamento
import folha_aprovacao
import pedido_obra
import persona_corporativo
import tarefas
from auth import validar_token

rotas = APIRouter(prefix="/api/aprovacoes")

PRAZO_DIAS = 7
# Folhas de antes da fila não entram (configurável): a partir do "Produzir a semana" (04/11/2026).
FOLHAS_DESDE = "2026-11-04"
DECIDIR = re.compile(r"^\s*(?:me\s+)?ajud\w*(?:-me)?\s+a\s+decidir\b", re.I)
_ESQUEMA = ("CREATE TABLE IF NOT EXISTS decisoes_estudo (tarefa_id INTEGER PRIMARY KEY, situacao TEXT NOT NULL, "
            "decisao TEXT NOT NULL DEFAULT '', por TEXT NOT NULL, em TEXT NOT NULL)")
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def _data(iso: str) -> datetime | None:
    try:
        data = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def _item(tipo: str, ident, titulo: str, resumo: str, criado_em: str, acoes: list[dict], agora: datetime,
          chat: dict | None = None, texto: str = "") -> dict:
    criado = _data(criado_em)
    vence = criado + timedelta(days=PRAZO_DIAS) if criado else None
    return {"tipo": tipo, "id": str(ident), "titulo": titulo, "resumo": resumo[:200], "criado_em": criado_em,
            "vence_em": vence.isoformat(timespec="seconds") if vence else "", "vencido": bool(vence and agora > vence),
            "dias": (agora - criado).days if criado else 0, "acoes": acoes, "chat": chat, "texto": texto,
            "informativo": not acoes}


def _acao(acao: str, rotulo: str, **extra) -> dict:
    return {"acao": acao, "rotulo": rotulo, **extra}


CONSTRUTOR = {"andar": "porao", "agente": "construtor"}


def _agentes(login: str, dono: bool, agora: datetime) -> list[dict]:
    itens = []
    for linha in agentes_dinamicos._db().execute("SELECT * FROM agentes_criados WHERE ativo = 1 AND situacao = ? "
                                                 "ORDER BY criado_em", (agentes_dinamicos.PROPOSTA,)):
        meu = linha["criado_por"] == login
        if not meu and not dono:
            continue
        setor = agentes_dinamicos.NOMES_SETORES.get(linha["setor"], linha["setor"])
        andar = agentes_dinamicos.NOMES_ANDARES.get(linha["andar"], linha["andar"])
        acoes = [_acao("aprovar", "Aprovar"),
                 _acao("ajustar", "Pedir ajuste", preencher=f"Ajuste o agente proposto {linha['id']}: "),
                 _acao("descartar", "Descartar")] if meu else []
        resumo = f"{setor} ({andar}): {linha['funcao']}" + ("" if meu else f" · pedido por {linha['criado_por']}")
        itens.append(_item("agente", linha["id"], f"Agente proposto: {linha['nome']}", resumo, linha["criado_em"],
                           acoes, agora, CONSTRUTOR, f"Objetivo: {linha['goal']}\n\nPersona:\n{linha['backstory']}"))
    return itens


def _obras(login: str, dono: bool, agora: datetime) -> list[dict]:
    itens = []
    for linha in pedido_obra.pendentes():
        if not dono and linha["criado_por"] != login:
            continue
        acoes = [_acao("aprovar", "Aceitar (vou montar)"), _acao("recusar", "Recusar")] if dono else []
        itens.append(_item("obra", linha["id"], f"Pedido de obra #{linha['id']}: {linha['nome']}",
                           f"Agente com ferramentas pedido por {linha['criado_por']}: copie o texto para o Claude Code."
                           if dono else "Aguarda o Thomas.", linha["criado_em"], acoes, agora, CONSTRUTOR,
                           linha["texto"]))
    return itens


def _personas(dono: bool, agora: datetime) -> list[dict]:
    if not dono:
        return []
    return [_item("persona", r["numero"], f"Persona nova do Corporativo (rascunho #{r['numero']})",
                  "O manual 14 só muda se você aprovar; a versão atual fica guardada com a data.", r["criado_em"],
                  [_acao("aprovar", "Aprovar a persona"), _acao("recusar", "Recusar")], agora,
                  {"andar": "comercial", "agente": "prospectador"}, r["texto"][:4000])
            for r in persona_corporativo.rascunhos_pendentes()]


def _estudos(login: str, dono: bool, agora: datetime) -> list[dict]:
    linhas = _db().execute(
        "SELECT t.* FROM tarefas t LEFT JOIN decisoes_estudo d ON d.tarefa_id = t.id WHERE t.agente = 'estrategista' "
        "AND t.status = 'concluida' AND d.tarefa_id IS NULL ORDER BY t.id").fetchall()
    itens = []
    for linha in linhas:
        pedido = encaminhamento.pedido_original(linha["texto"])
        if not DECIDIR.search(pedido) or (not dono and linha["usuario"] != login):
            continue
        acoes = [_acao("decidir", "Registrar a decisão", campo="Decisão do Thomas"),
                 _acao("arquivar", "Arquivar sem decidir")] if dono else []
        itens.append(_item("estudo", linha["id"], "Decisão de estudo", pedido, linha["concluida_em"] or
                           linha["criada_em"], acoes, agora, _chat(linha)))
    return itens


def _chat(linha) -> dict:
    """Chat onde o pedido nasceu (como na Caixa de entrada)."""
    andar, agente = encaminhamento.origem(linha["id"]) or (linha["andar"], linha["agente"])
    return {"andar": andar, "agente": agente}


def _folhas(login: str, agora: datetime) -> list[dict]:
    folha_aprovacao._db()
    avaliacoes._db()
    linhas = _db().execute(
        "SELECT t.* FROM folhas_aprovacao f JOIN tarefas t ON t.id = f.tarefa_id LEFT JOIN avaliacoes a ON "
        "a.tarefa_id = t.id WHERE t.usuario = ? AND t.status = 'concluida' AND a.tarefa_id IS NULL AND "
        "t.concluida_em >= ? ORDER BY t.concluida_em", (login, FOLHAS_DESDE)).fetchall()
    return [_item("folha", linha["id"], f"Folha de aprovação da peça #{linha['id']}",
                  encaminhamento.pedido_original(linha["texto"]), linha["concluida_em"],
                  [_acao("aprovar", "Aprovar (👍)"), _acao("abrir", "Pedir ajuste no chat")], agora, _chat(linha))
            for linha in linhas]


def itens(login: str) -> list[dict]:
    """A fila de quem está logado, do mais antigo (vencidos primeiro) ao mais novo."""
    login = (login or "").strip().lower()
    dono, agora = login == config.DONO_MAX, datetime.now(timezone.utc)
    todos = (_agentes(login, dono, agora) + _obras(login, dono, agora) + _personas(dono, agora) +
             _estudos(login, dono, agora) + _folhas(login, agora))
    return sorted(todos, key=lambda i: (i["informativo"], not i["vencido"], i["criado_em"]))


def registrar_decisao(tarefa_id: int, login: str, acao: str, texto: str = "") -> str:
    """Decisão do Thomas sobre um estudo "Me ajude a decidir" (ou arquivado sem decidir). Nada é apagado."""
    if (login or "").strip().lower() != config.DONO_MAX:
        return "Só o Thomas registra a decisão de um estudo."
    linha = tarefas.obter(tarefa_id)
    if not linha or linha["agente"] != "estrategista":
        return "Estudo não encontrado."
    if acao == "decidir" and len(texto.strip()) < 2:
        return "Escreva a decisão (por exemplo: \"Opção B, revisar em 60 dias\")."
    situacao = "decidido" if acao == "decidir" else "arquivado"
    with _db() as db:
        db.execute("INSERT OR IGNORE INTO decisoes_estudo VALUES (?, ?, ?, ?, ?)",
                   (tarefa_id, situacao, texto.strip()[:1000], login, tarefas._agora()))
    tarefas.registrar_evento(tarefa_id, "decisao_thomas", "estrategista",
                             detalhe=f"Decisão do Thomas: {texto.strip()}" if situacao == "decidido" else "Arquivado")
    return "Decisão registrada." if situacao == "decidido" else "Estudo arquivado sem decisão (continua no histórico)."


async def decidir(tipo: str, ident: str, login: str, acao: str, texto: str = "") -> str:
    """Encaminha ao módulo de cada item; levanta ValueError para tipo ou ação que não existem."""
    if tipo == "agente" and acao in ("aprovar", "descartar"):
        return await agentes_dinamicos.decidir(ident, login, acao)
    if tipo == "obra" and acao in ("aprovar", "recusar") and ident.isdigit():
        return pedido_obra.decidir(int(ident), login, acao)
    if tipo == "persona" and ident.isdigit() and acao == "aprovar":
        return await asyncio.to_thread(persona_corporativo.aprovar,
                                       f"{persona_corporativo.FRASE_APROVAR} #{ident}", login)
    if tipo == "persona" and ident.isdigit() and acao == "recusar":
        return persona_corporativo.recusar(int(ident), login)
    if tipo == "estudo" and ident.isdigit() and acao in ("decidir", "arquivar"):
        return registrar_decisao(int(ident), login, acao, texto)
    if tipo == "folha" and ident.isdigit() and acao == "aprovar":
        linha = tarefas.obter(int(ident))
        if not linha or linha["usuario"] != login or linha["status"] != "concluida":
            return "Só quem pediu a peça aprova a folha."
        await asyncio.to_thread(avaliacoes.avaliar, linha, login, 1)
        return "Folha aprovada (👍 na resposta da peça)."
    raise ValueError("ação inválida")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


class Decisao(BaseModel):
    texto: str = Field("", max_length=1000)


@rotas.get("")
def ver(authorization: str = Header("")):
    return {"itens": itens(_usuario(authorization)["sub"]), "prazo_dias": PRAZO_DIAS}


@rotas.post("/{tipo}/{ident}/{acao}")
async def decidir_rota(tipo: str, ident: str, acao: str, dados: Decisao, authorization: str = Header("")):
    login = _usuario(authorization)["sub"]
    try:
        mensagem = await decidir(tipo, ident[:60], login, acao, dados.texto)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ação inválida para este item.") from None
    return {"ok": True, "mensagem": mensagem}
