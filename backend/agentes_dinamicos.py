"""Agentes criados pelo Construtor: validação, persistência (SQLite) e registro no escritório.

O agente nasce com status "construindo", vira "disponivel" após alguns segundos e sobrevive a
reinícios (`carregar()` na subida). A persona vai para `PERFIS`, então o executor o atende como os demais.
"""

import asyncio
import concurrent.futures
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import ValidationError

import atividade
import tarefas
from agents.perfis import PERFIS
from auth import carregar_usuarios, validar_token
from conexoes import gerenciador
from estado import ANDARES, Agente, Aparencia, Status, andar_do_agente, pode_acessar

log = logging.getLogger(__name__)

# Andar -> setor -> mesas no canvas (mesmos ids de frontend/js/cenario/setores.js).
# Térreo e Cobertura (Cérebro e estagiários) não recebem agentes novos.
SETORES = {
    "porao": {"oficina": 3, "operacoes": 3},
    "marketing": {"gestao": 2, "criacao": 3, "conteudo": 3, "video": 3, "performance": 3},
}
NOMES_ANDARES = {"porao": "Porão", "marketing": "Marketing", "cobertura": "Cobertura"}
NOMES_SETORES = {"oficina": "Oficina", "operacoes": "Operações", "gestao": "Gestão", "criacao": "Criação",
                 "conteudo": "Conteúdo", "video": "Vídeo", "performance": "Performance", "diretoria": "Diretoria"}

TONS_PELE = ["#ffdbac", "#f1c27d", "#e0ac69", "#c68642", "#a0522d", "#8d5524", "#6b4226", "#3b2219"]
ESTILOS_CABELO = ["curto", "longo", "coque", "careca", "cacheado", "moicano"]
ESTILOS_ROUPA = ["camiseta", "camisa", "blazer", "moletom", "macacao", "avental"]
ACESSORIOS = ["nenhum", "oculos", "fone", "bone", "capacete", "cracha", "gravata", "camera", "lapis"]

# Campo -> (mínimo, máximo) de caracteres.
LIMITES = {"nome": (2, 40), "funcao": (3, 80), "descricao": (0, 300), "exemplo": (0, 200),
           "role": (2, 80), "goal": (10, 600), "backstory": (10, 900)}
SEGUNDOS_CONSTRUINDO = 5

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS agentes_criados (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL, andar TEXT NOT NULL, setor TEXT NOT NULL, funcao TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '', exemplo TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL, goal TEXT NOT NULL, backstory TEXT NOT NULL,
    aparencia TEXT NOT NULL, criado_por TEXT NOT NULL, criado_em TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
"""
_tabela_pronta = False
_pendentes: set[asyncio.Task] = set()  # referências às tarefas "construindo -> disponivel"


class ErroValidacao(ValueError):
    """Especificação inválida (o Construtor pode corrigir e tentar de novo)."""


class SemPermissao(PermissionError):
    """Só a diretoria cria agentes."""


def _db():
    global _tabela_pronta
    db = tarefas._db()
    if not _tabela_pronta:
        db.executescript(_ESQUEMA)
        _tabela_pronta = True
    return db


# --- Validação ----------------------------------------------------------------------------

def _snake(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento).strip("_")[:40].strip("_")


def _texto(spec: dict, campo: str, padrao: str = "") -> str:
    valor = spec.get(campo)
    valor = padrao if valor is None else str(valor)
    valor = " ".join(valor.split())
    minimo, maximo = LIMITES[campo]
    if len(valor) < minimo:
        raise ErroValidacao(f"'{campo}' precisa ter ao menos {minimo} caracteres.")
    return valor[:maximo]


def _hex(valor, campo: str) -> str:
    cor = str(valor or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", cor):
        cor = "#" + "".join(c * 2 for c in cor[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", cor):
        raise ErroValidacao(f"'{campo}' deve ser uma cor hex no formato #rrggbb (recebido: {valor!r}).")
    return cor


def _rgb(cor: str) -> tuple[int, int, int]:
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def tom_de_pele(cor: str) -> str:
    """Tom humano mais próximo da paleta (evita peles como laranja ou verde)."""
    r, g, b = _rgb(cor)
    return min(TONS_PELE, key=lambda t: sum((a - c) ** 2 for a, c in zip(_rgb(t), (r, g, b))))


def _opcao(valor, opcoes: list[str], campo: str) -> str:
    escolha = _snake(str(valor or ""))
    if escolha not in opcoes:
        raise ErroValidacao(f"'{campo}' deve ser um de: {', '.join(opcoes)} (recebido: {valor!r}).")
    return escolha


def _aparencia(bruta) -> Aparencia:
    if isinstance(bruta, str):
        try:
            bruta = json.loads(bruta)
        except ValueError:
            raise ErroValidacao("'aparencia' deve ser um objeto JSON.") from None
    if not isinstance(bruta, dict):
        raise ErroValidacao("'aparencia' deve ser um objeto com pele, cabelo, roupa, calca e acessorio.")
    cabelo, roupa = bruta.get("cabelo") or {}, bruta.get("roupa") or {}
    if not isinstance(cabelo, dict) or not isinstance(roupa, dict):
        raise ErroValidacao("'cabelo' e 'roupa' devem ser objetos com 'estilo' e 'cor'.")
    try:
        return Aparencia(
            pele=tom_de_pele(_hex(bruta.get("pele"), "pele")),
            cabelo={"estilo": _opcao(cabelo.get("estilo"), ESTILOS_CABELO, "cabelo.estilo"),
                    "cor": _hex(cabelo.get("cor"), "cabelo.cor")},
            roupa={"estilo": _opcao(roupa.get("estilo"), ESTILOS_ROUPA, "roupa.estilo"),
                   "cor": _hex(roupa.get("cor"), "roupa.cor")},
            calca=_hex(bruta.get("calca"), "calca"),
            acessorio=_opcao(bruta.get("acessorio") or "nenhum", ACESSORIOS, "acessorio"),
        )
    except ValidationError as erro:
        raise ErroValidacao(f"aparência inválida: {erro.errors()[0]['msg']}") from None


def _todos_agentes() -> list[Agente]:
    return [a for agentes in ANDARES.values() for a in agentes.values()]


def _exclusiva(aparencia: Aparencia) -> Aparencia:
    """Se for idêntica à de alguém, varia o cabelo e depois a roupa até ficar única."""
    existentes = [a.aparencia.model_dump() for a in _todos_agentes()]
    if aparencia.model_dump() not in existentes:
        return aparencia
    for cabelo in ESTILOS_CABELO:
        for roupa in ESTILOS_ROUPA:
            candidata = aparencia.model_copy(deep=True)
            candidata.cabelo.estilo, candidata.roupa.estilo = cabelo, roupa
            if candidata.model_dump() not in existentes:
                return candidata
    return aparencia


def _id_livre(agente_id: str) -> bool:
    if andar_do_agente(agente_id) or agente_id in PERFIS:
        return False
    linha = _db().execute("SELECT ativo FROM agentes_criados WHERE id = ?", (agente_id,)).fetchone()
    return linha is None or not linha["ativo"]  # id de agente desativado pode ser reaproveitado


def vagas(andar: str, setor: str) -> int:
    ocupadas = sum(1 for a in ANDARES.get(andar, {}).values() if a.setor == setor)
    return SETORES.get(andar, {}).get(setor, 0) - ocupadas


def setores_com_vagas() -> str:
    """Texto para o Construtor: setores válidos por andar e vagas livres."""
    return "; ".join(f"{andar}: " + ", ".join(f"{s} ({vagas(andar, s)} vaga(s))" for s in setores)
                     for andar, setores in SETORES.items())


def validar(spec: dict) -> dict:
    """Normaliza a especificação; levanta ErroValidacao com a explicação do problema."""
    if not isinstance(spec, dict):
        raise ErroValidacao("a especificação deve ser um objeto.")
    nome = _texto(spec, "nome")
    andar = _snake(str(spec.get("andar") or ""))
    if andar not in SETORES:
        raise ErroValidacao(f"andar inválido {spec.get('andar')!r}; use um de: {', '.join(SETORES)} "
                            "(o térreo e a cobertura não recebem agentes novos).")
    setor = _snake(str(spec.get("setor") or ""))
    if setor not in SETORES[andar]:
        raise ErroValidacao(f"setor inválido {spec.get('setor')!r} para o andar {andar}; "
                            f"use um de: {', '.join(SETORES[andar])}.")
    if vagas(andar, setor) <= 0:
        raise ErroValidacao(f"o setor {setor} ({andar}) não tem mesa livre. Setores: {setores_com_vagas()}.")
    agente_id = _snake(str(spec.get("id") or "")) or _snake(nome)
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", agente_id):
        raise ErroValidacao(f"id inválido {agente_id!r}: use snake_case começando por letra (2 a 40 caracteres).")
    if not _id_livre(agente_id):
        raise ErroValidacao(f"já existe um agente com id {agente_id!r}; escolha outro nome/id.")
    return {
        "id": agente_id, "nome": nome, "andar": andar, "setor": setor,
        "funcao": _texto(spec, "funcao"), "descricao": _texto(spec, "descricao"),
        "exemplo": _texto(spec, "exemplo"), "role": _texto(spec, "role", nome),
        "goal": _texto(spec, "goal"), "backstory": _texto(spec, "backstory"),
        "aparencia": _exclusiva(_aparencia(spec.get("aparencia"))).model_dump(),
    }


# --- Registro no escritório ----------------------------------------------------------------

def _registrar(registro: dict, status: Status) -> Agente:
    agente = Agente(id=registro["id"], nome=registro["nome"], funcao=registro["funcao"],
                    setor=registro["setor"], descricao=registro["descricao"], exemplo=registro["exemplo"],
                    aparencia=Aparencia.model_validate(registro["aparencia"]), status=status)
    ANDARES[registro["andar"]][agente.id] = agente
    PERFIS[agente.id] = {k: registro[k] for k in ("role", "goal", "backstory")}
    return agente


def _da_linha(linha) -> dict:
    registro = dict(linha)
    registro["aparencia"] = json.loads(registro["aparencia"])
    registro["ativo"] = bool(registro["ativo"])
    return registro


def _role_de(login: str) -> str | None:
    return (carregar_usuarios().get((login or "").strip().lower()) or {}).get("role")


async def _concluir_construcao(agente_id: str) -> None:
    await asyncio.sleep(SEGUNDOS_CONSTRUINDO)
    andar = andar_do_agente(agente_id)
    agente = ANDARES[andar][agente_id] if andar else None
    if agente and agente.status == Status.construindo:
        agente.status = Status.disponivel
        await atividade.transmitir_estado()


async def criar(spec: dict, criado_por: str, tarefa_id: int | None = None) -> dict:
    """Valida, persiste e coloca o agente no escritório (construindo -> disponivel)."""
    if _role_de(criado_por) != "diretoria":
        raise SemPermissao("Somente a diretoria pode criar agentes.")
    registro = validar(spec)
    registro.update(criado_por=criado_por, criado_em=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    ativo=True)
    with _db() as db:
        db.execute(
            "INSERT OR REPLACE INTO agentes_criados (id, nome, andar, setor, funcao, descricao, exemplo, role, goal, "
            "backstory, aparencia, criado_por, criado_em, ativo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (*(registro[k] for k in ("id", "nome", "andar", "setor", "funcao", "descricao", "exemplo", "role",
                                     "goal", "backstory")),
             json.dumps(registro["aparencia"]), criado_por, registro["criado_em"]))
    _registrar(registro, Status.construindo)
    await atividade.transmitir_estado()

    andar, setor = NOMES_ANDARES[registro["andar"]], NOMES_SETORES[registro["setor"]]
    if tarefa_id:
        tarefas.registrar_evento(tarefa_id, "agente_criado", registro["id"],
                                 detalhe=f"{registro['nome']} criado no setor {setor} ({andar}).")
    await gerenciador.enviar_para_usuario(criado_por, {
        "tipo": "aviso", "andar": registro["andar"], "agente": registro["id"], "titulo": "Novo agente",
        "texto": f"{registro['nome']} chegou ao setor {setor} ({andar}).",
    })
    tarefa = asyncio.create_task(_concluir_construcao(registro["id"]))
    _pendentes.add(tarefa)
    tarefa.add_done_callback(_pendentes.discard)
    log.info("Agente criado: %s (%s/%s) por %s", registro["id"], registro["andar"], registro["setor"], criado_por)
    return registro


def criar_em_thread(spec: dict, criado_por: str, tarefa_id: int | None = None) -> str:
    """Para a ferramenta do CrewAI (thread): cria no loop principal e devolve texto para o LLM."""
    loop = atividade._loop
    if not loop:
        return "Erro: o servidor não está pronto para criar agentes agora. Avise o usuário."
    try:
        registro = asyncio.run_coroutine_threadsafe(criar(spec, criado_por, tarefa_id), loop).result(timeout=30)
    except ErroValidacao as erro:
        return f"Erro de validação: {erro} Corrija a especificação e chame criar_agente de novo."
    except SemPermissao as erro:
        return f"Não autorizado: {erro} Explique isso ao usuário; não tente de novo."
    except (TimeoutError, concurrent.futures.TimeoutError):
        return "Erro: a criação demorou demais. Avise o usuário para tentar novamente."
    return (f"Agente criado com sucesso: {registro['nome']} (id {registro['id']}), "
            f"setor {NOMES_SETORES[registro['setor']]} do andar {NOMES_ANDARES[registro['andar']]}. "
            f"Ele aparece como 'construindo' e fica disponível em alguns segundos. Agora confirme ao usuário.")


def carregar() -> None:
    """Na subida: devolve ao escritório e às personas os agentes criados ativos."""
    for linha in _db().execute("SELECT * FROM agentes_criados WHERE ativo = 1 ORDER BY criado_em"):
        registro = _da_linha(linha)
        if registro["andar"] not in ANDARES or andar_do_agente(registro["id"]):
            log.warning("Agente criado ignorado (andar inválido ou id repetido): %s", registro["id"])
            continue
        _registrar(registro, Status.disponivel)


async def desativar(agente_id: str) -> bool:
    with _db() as db:
        alterou = db.execute("UPDATE agentes_criados SET ativo = 0 WHERE id = ? AND ativo = 1",
                             (agente_id,)).rowcount
    if not alterou:
        return False
    andar = andar_do_agente(agente_id)
    if andar:
        ANDARES[andar].pop(agente_id, None)
    PERFIS.pop(agente_id, None)
    await atividade.transmitir_estado()
    return True


# --- Rotas ---------------------------------------------------------------------------------

rotas = APIRouter(prefix="/api/agentes-criados")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


@rotas.get("")
def listar(authorization: str = Header("")):
    usuario = _usuario(authorization)
    linhas = _db().execute("SELECT * FROM agentes_criados WHERE ativo = 1 ORDER BY criado_em").fetchall()
    return {"agentes": [_da_linha(l) for l in linhas if pode_acessar(usuario["role"], l["andar"])]}


@rotas.delete("/{agente_id}")
async def remover(agente_id: str, authorization: str = Header("")):
    if _usuario(authorization)["role"] != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria pode remover agentes.")
    if not await desativar(agente_id):
        raise HTTPException(status_code=404, detail="Agente criado não encontrado.")
    return {"ok": True, "id": agente_id}
