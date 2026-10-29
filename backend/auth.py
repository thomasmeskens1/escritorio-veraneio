"""Autenticação: usuários com senha em hash (PBKDF2) e tokens JWT."""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

import config

# Provisório até o banco do Sprint 8. Fica fora do git (veja .gitignore).
ARQUIVO_USUARIOS = Path(__file__).resolve().parent / "dados" / "usuarios.json"
ITERACOES = 600_000


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${digest.hex()}"


def _senha_confere(senha: str, armazenado: str) -> bool:
    _, iteracoes, sal, esperado = armazenado.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(iteracoes))
    return hmac.compare_digest(digest.hex(), esperado)


# Usado quando o login não existe, para o tempo de resposta não revelar quais logins existem.
_HASH_FICTICIO = gerar_hash(secrets.token_hex(8))


_cache = {"mtime": None, "usuarios": {}}  # o arquivo é lido em cada validação de token: só relê se mudou


def carregar_usuarios() -> dict:
    """{login: {nome, role, senha, ativo?, master?, agentes?}}. `agentes`: "*" (todos, o padrão) ou lista de
    "andar/agente" que o usuário pode usar (painel de usuários, só o master)."""
    if not ARQUIVO_USUARIOS.exists():
        return {}
    mtime = ARQUIVO_USUARIOS.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["usuarios"] = json.loads(ARQUIVO_USUARIOS.read_text(encoding="utf-8"))
        _cache["mtime"] = mtime
    return _cache["usuarios"]


def _gravar(usuarios: dict) -> None:
    ARQUIVO_USUARIOS.parent.mkdir(exist_ok=True)
    temporario = ARQUIVO_USUARIOS.with_suffix(".tmp")
    temporario.write_text(json.dumps(usuarios, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(ARQUIVO_USUARIOS)  # troca atômica: um login no meio da gravação nunca lê arquivo pela metade


def salvar_usuario(login: str, nome: str, senha: str, role: str) -> None:
    usuarios = dict(carregar_usuarios())
    anterior = usuarios.get(login.strip().lower(), {})
    usuarios[login.strip().lower()] = {**anterior, "nome": nome, "role": role, "senha": gerar_hash(senha)}
    _gravar(usuarios)


def atualizar_usuario(login: str, **campos) -> None:
    """Muda nome, role, ativo, agentes ou senha (em texto, vira hash aqui) de um usuário existente."""
    usuarios = dict(carregar_usuarios())
    registro = dict(usuarios[login])
    if "senha" in campos:
        campos["senha"] = gerar_hash(campos["senha"])
    registro.update(campos)
    usuarios[login] = registro
    _gravar(usuarios)


def e_master(login: str) -> bool:
    """O master gerencia os usuários e o que cada um usa: a conta do Thomas (dono do plano Max)."""
    return login == config.DONO_MAX or bool(carregar_usuarios().get(login, {}).get("master"))


def ve_financeiro(login: str) -> bool:
    """Vendas, receita, investimento em tráfego, ROAS e CRM do painel: só a Diretoria (Thomas, 29/10/2026)."""
    return e_master(login) or carregar_usuarios().get(login, {}).get("role") == "diretoria"


def autenticar(login: str, senha: str) -> dict | None:
    """Devolve {login, nome, role} se as credenciais forem válidas (e o usuário estiver ativo)."""
    login = login.strip().lower()
    registro = carregar_usuarios().get(login)
    if not registro:
        _senha_confere(senha, _HASH_FICTICIO)
        return None
    if not _senha_confere(senha, registro["senha"]) or registro.get("ativo", True) is False:
        return None
    return {"login": login, "nome": registro["nome"], "role": registro["role"]}


def criar_token(usuario: dict) -> str:
    expira = datetime.now(timezone.utc) + timedelta(hours=config.JWT_VALIDADE_HORAS)
    payload = {"sub": usuario["login"], "nome": usuario["nome"], "role": usuario["role"],
               "master": e_master(usuario["login"]), "exp": expira}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITMO)


def validar_token(token: str) -> dict | None:
    """Payload do token com a role ATUAL e o selo de master. Usuário desativado ou removido perde o acesso na hora,
    mesmo com o token ainda dentro da validade."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITMO])
    except jwt.InvalidTokenError:
        return None
    registro = carregar_usuarios().get(payload.get("sub", ""))
    if not registro or registro.get("ativo", True) is False:
        return None
    return {**payload, "role": registro["role"], "nome": registro["nome"], "master": e_master(payload["sub"])}
