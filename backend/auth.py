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


def carregar_usuarios() -> dict:
    if not ARQUIVO_USUARIOS.exists():
        return {}
    return json.loads(ARQUIVO_USUARIOS.read_text(encoding="utf-8"))


def salvar_usuario(login: str, nome: str, senha: str, role: str) -> None:
    usuarios = carregar_usuarios()
    usuarios[login.strip().lower()] = {"nome": nome, "role": role, "senha": gerar_hash(senha)}
    ARQUIVO_USUARIOS.parent.mkdir(exist_ok=True)
    ARQUIVO_USUARIOS.write_text(json.dumps(usuarios, ensure_ascii=False, indent=2), encoding="utf-8")


def autenticar(login: str, senha: str) -> dict | None:
    """Devolve {login, nome, role} se as credenciais forem válidas."""
    login = login.strip().lower()
    registro = carregar_usuarios().get(login)
    if not registro:
        _senha_confere(senha, _HASH_FICTICIO)
        return None
    if not _senha_confere(senha, registro["senha"]):
        return None
    return {"login": login, "nome": registro["nome"], "role": registro["role"]}


def criar_token(usuario: dict) -> str:
    expira = datetime.now(timezone.utc) + timedelta(hours=config.JWT_VALIDADE_HORAS)
    payload = {"sub": usuario["login"], "nome": usuario["nome"], "role": usuario["role"], "exp": expira}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITMO)


def validar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITMO])
    except jwt.InvalidTokenError:
        return None
