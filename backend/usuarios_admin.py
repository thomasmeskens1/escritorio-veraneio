"""Painel de usuários (só o master): incluir, editar perfil, desativar, redefinir senha e escolher os agentes que
cada um usa. Thomas, 29/10/2026. Os usuários ficam em dados/usuarios.json (fora do git), com a senha só em hash.
"""

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import acesso
import atividade
import tarefas
from auth import atualizar_usuario, carregar_usuarios, e_master, salvar_usuario, validar_token
from conexoes import gerenciador
from estado import ANDARES

rotas = APIRouter(prefix="/api/usuarios")

ROLES = ("diretoria", "funcionario")
LOGIN = re.compile(r"^[a-z0-9._%+-]+(@[a-z0-9.-]+\.[a-z]{2,})?$")
SENHA_MINIMA = 8


def _master(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if not usuario.get("master"):
        raise HTTPException(status_code=403, detail="Só o master gerencia os usuários.")
    return usuario


def _validos(agentes: str | list[str]) -> str | list[str]:
    if agentes == acesso.TODOS:
        return acesso.TODOS
    catalogo = {f"{a['andar']}/{a['id']}" for a in acesso.catalogo()}
    invalidos = [a for a in agentes if a not in catalogo]
    if invalidos:
        raise HTTPException(status_code=422, detail=f"Agentes desconhecidos: {', '.join(invalidos[:5])}")
    return sorted(set(agentes))


def _andares_validos(andares: str | list[str]) -> str | list[str]:
    if andares == acesso.TODOS:
        return acesso.TODOS
    invalidos = [a for a in andares if a not in ANDARES]
    if invalidos:
        raise HTTPException(status_code=422, detail=f"Andares desconhecidos: {', '.join(invalidos)}")
    return [a for a in ANDARES if a in andares]  # na ordem do prédio


def _uso(login: str) -> dict:
    """Uso do usuário (para o master acompanhar): tarefas, a última e os agentes mais usados."""
    db = tarefas._db()
    total, ultima = db.execute("SELECT COUNT(*), MAX(criada_em) FROM tarefas WHERE usuario = ?", (login,)).fetchone()
    top = db.execute("SELECT agente, COUNT(*) n FROM tarefas WHERE usuario = ? GROUP BY agente ORDER BY n DESC "
                     "LIMIT 3", (login,)).fetchall()
    return {"tarefas": total, "ultima_tarefa": ultima, "mais_usados": [f"{l['agente']} ({l['n']})" for l in top]}


@rotas.get("")
def listar(authorization: str = Header("")):
    _master(authorization)
    usuarios = [{"login": login, "nome": r["nome"], "role": r["role"], "ativo": r.get("ativo", True),
                 "master": e_master(login), "agentes": acesso.agentes_do_usuario(login),
                 "andares": acesso.andares_do_usuario(login), "status": gerenciador.status_de(login),
                 **_uso(login)}
                for login, r in sorted(carregar_usuarios().items())]
    return {"usuarios": usuarios, "agentes": acesso.catalogo(), "roles": ROLES, "andares": list(ANDARES)}


class NovoUsuario(BaseModel):
    login: str
    nome: str = Field(min_length=2, max_length=60)
    role: str = "funcionario"
    senha: str = Field(min_length=SENHA_MINIMA)
    agentes: str | list[str] = acesso.TODOS
    andares: str | list[str] = acesso.TODOS


@rotas.post("")
def incluir(dados: NovoUsuario, authorization: str = Header("")):
    _master(authorization)
    login = dados.login.strip().lower()
    if not LOGIN.match(login):
        raise HTTPException(status_code=422, detail="Login inválido: use o e-mail ou um nome de usuário sem espaços.")
    if login in carregar_usuarios():
        raise HTTPException(status_code=409, detail="Esse login já existe.")
    if dados.role not in ROLES:
        raise HTTPException(status_code=422, detail="Perfil inválido.")
    agentes, andares = _validos(dados.agentes), _andares_validos(dados.andares)
    salvar_usuario(login, dados.nome.strip(), dados.senha, dados.role)
    atualizar_usuario(login, ativo=True, agentes=agentes, andares=andares)
    return {"ok": True}


class Alteracao(BaseModel):
    nome: str | None = Field(None, min_length=2, max_length=60)
    role: str | None = None
    ativo: bool | None = None
    agentes: str | list[str] | None = None
    andares: str | list[str] | None = None
    senha: str | None = Field(None, min_length=SENHA_MINIMA)


@rotas.patch("/{login}")
async def alterar(login: str, dados: Alteracao, authorization: str = Header("")):
    master = _master(authorization)
    login = login.strip().lower()
    if login not in carregar_usuarios():
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    campos = dados.model_dump(exclude_none=True)
    if "role" in campos and campos["role"] not in ROLES:
        raise HTTPException(status_code=422, detail="Perfil inválido.")
    if login == master["sub"] and (campos.get("ativo") is False or "agentes" in campos or "andares" in campos
                                   or campos.get("role") == "funcionario"):
        raise HTTPException(status_code=422, detail="O master não pode desativar, rebaixar ou limitar a própria conta.")
    if "agentes" in campos:
        campos["agentes"] = _validos(campos["agentes"])
    if "andares" in campos:
        campos["andares"] = _andares_validos(campos["andares"])
    if campos:
        atualizar_usuario(login, **campos)
    if campos.get("ativo") is False:  # desativado: a sessão aberta cai na hora
        for ws, conectado in list(gerenciador.ativas.items()):
            if conectado["sub"] == login:
                await ws.close(code=4401, reason="Usuário desativado")
    await atividade.transmitir_estado()  # andares e agentes liberados mudam na tela de quem está conectado
    return {"ok": True}
