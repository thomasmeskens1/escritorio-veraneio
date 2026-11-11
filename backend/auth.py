"""Autenticação: usuários com senha em hash (PBKDF2) e tokens JWT."""

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

import config

# Provisório até o banco do Sprint 8. Fica fora do git (veja .gitignore).
ARQUIVO_USUARIOS = Path(__file__).resolve().parent / "dados" / "usuarios.json"
ITERACOES = 600_000
log = logging.getLogger("veraneio.auth")


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
        campos["sessao"] = registro.get("sessao", 0) + 1  # senha nova: as sessões abertas caem
    registro.update(campos)
    usuarios[login] = registro
    _gravar(usuarios)


def encerrar_sessoes(login: str) -> None:
    """"Sair" (ou sessão suspeita): todos os tokens já emitidos para este usuário deixam de valer."""
    usuarios = dict(carregar_usuarios())
    if login in usuarios:
        usuarios[login] = {**usuarios[login], "sessao": usuarios[login].get("sessao", 0) + 1}
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


# Trava por conta (brainstorm de novembro, construtor-07): a trava por (login, IP) do main.py não pega quem troca de
# rede. 15 senhas erradas na mesma conta em 1 h, venham de onde vierem, travam a conta por 30 min (nem a senha certa
# entra, senão a trava não serve) e avisam no Telegram. Vale também para login inexistente: a resposta igual não
# revela quais contas existem. Efeito aceito: alguém de fora consegue travar uma conta por 30 min.
MAX_FALHAS_CONTA = 15
JANELA_FALHAS_CONTA_S = 3600
BLOQUEIO_CONTA_S = 30 * 60
_falhas_conta: dict[str, list[float]] = {}  # login -> horários das falhas (time.monotonic)
_conta_travada_ate: dict[str, float] = {}
_trava_contas = threading.Lock()


def conta_travada(login: str, agora: float | None = None) -> bool:
    agora = time.monotonic() if agora is None else agora
    with _trava_contas:
        return _conta_travada_ate.get(login.strip().lower(), 0) > agora


def registrar_falha_conta(login: str, agora: float | None = None) -> bool:
    """Conta uma senha errada; True se a conta acabou de travar."""
    login, agora = login.strip().lower(), time.monotonic() if agora is None else agora
    with _trava_contas:
        if len(_falhas_conta) > 1000:  # logins aleatórios não fazem o registro crescer sem limite
            for chave in [c for c, ts in _falhas_conta.items() if not ts or agora - ts[-1] >= JANELA_FALHAS_CONTA_S]:
                del _falhas_conta[chave]
            for chave in [c for c, ate in _conta_travada_ate.items() if ate <= agora]:
                del _conta_travada_ate[chave]
        falhas = [t for t in _falhas_conta.get(login, []) if agora - t < JANELA_FALHAS_CONTA_S] + [agora]
        if len(falhas) < MAX_FALHAS_CONTA:
            _falhas_conta[login] = falhas
            return False
        _falhas_conta.pop(login, None)
        _conta_travada_ate[login] = agora + BLOQUEIO_CONTA_S
    if login in carregar_usuarios():
        _disparar_aviso(login)
    return True


def _disparar_aviso(login: str) -> None:
    threading.Thread(target=_avisar_trava, args=(login,), daemon=True).start()  # o login não espera o Telegram


def limpar_falhas_conta(login: str) -> None:
    """Login certo: as senhas erradas anteriores da conta deixam de contar."""
    with _trava_contas:
        _falhas_conta.pop(login.strip().lower(), None)


def _avisar_trava(login: str) -> None:
    import alarme_telegram  # import tardio: o alarme só entra quando há o que avisar
    if not alarme_telegram.ativo():
        return
    try:
        alarme_telegram.enviar(f"🔒 Escritório Veraneio: a conta {login} foi travada por {BLOQUEIO_CONTA_S // 60} min "
                               f"depois de {MAX_FALHAS_CONTA} senhas erradas em 1 h. Se não foi a própria pessoa, "
                               "troque a senha dela no painel de usuários.")
    except Exception:  # aviso nunca derruba o login
        log.warning("Não consegui avisar no Telegram a trava da conta", exc_info=True)


def criar_token(usuario: dict) -> str:
    expira = datetime.now(timezone.utc) + timedelta(hours=config.JWT_VALIDADE_HORAS)
    # "sv": versão da sessão do usuário (revisão de 30/10/2026, 2.28): trocar a senha ou sair muda a versão e o token
    # antigo para de valer, mesmo dentro das 8 h (antes um token roubado valia até expirar).
    payload = {"sub": usuario["login"], "nome": usuario["nome"], "role": usuario["role"],
               "master": e_master(usuario["login"]), "exp": expira,
               "sv": carregar_usuarios().get(usuario["login"], {}).get("sessao", 0)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITMO)


def validar_token(token: str) -> dict | None:
    """Payload do token com a role ATUAL e o selo de master. Usuário desativado ou removido perde o acesso na hora,
    mesmo com o token ainda dentro da validade."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITMO])
    except jwt.InvalidTokenError:
        return None
    registro = carregar_usuarios().get(payload.get("sub", ""))
    if not registro or registro.get("ativo", True) is False or payload.get("sv", 0) != registro.get("sessao", 0):
        return None
    return {**payload, "role": registro["role"], "nome": registro["nome"], "master": e_master(payload["sub"])}
