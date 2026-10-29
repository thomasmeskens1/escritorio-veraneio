"""O que cada usuário pode usar: andares e agentes (painel de usuários, só o master). Thomas, 29/10/2026.

Por padrão o usuário usa todos os agentes ("*"). O andar aparece para ele se tiver pelo menos um agente liberado
nesse andar (a Cobertura deixou de ser "só diretoria" por regra fixa: vale a lista de agentes do usuário). As
ferramentas da diretoria (modelos de IA, mapa do Cérebro, treino) e o que é exclusivo do plano Max (produção, estudos
na web, prospecção) seguem como antes.
"""

from auth import carregar_usuarios, e_master
from estado import ANDARES

TODOS = "*"


def agentes_do_usuario(login: str) -> str | list[str]:
    """TODOS ou a lista de "andar/agente" liberados."""
    if e_master(login):
        return TODOS
    return carregar_usuarios().get(login, {}).get("agentes", TODOS)


def andares_do_usuario(login: str) -> str | list[str]:
    """TODOS ou a lista de andares liberados (camada acima dos agentes: andar fechado trava todos os agentes dele)."""
    if e_master(login):
        return TODOS
    return carregar_usuarios().get(login, {}).get("andares", TODOS)


def pode_usar(usuario: dict, andar: str, agente_id: str) -> bool:
    login = usuario.get("sub", "")
    andares, agentes = andares_do_usuario(login), agentes_do_usuario(login)
    return (andares == TODOS or andar in andares) and (agentes == TODOS or f"{andar}/{agente_id}" in agentes)


def pode_ver_andar(usuario: dict, andar: str) -> bool:
    """Andar com pelo menos um agente liberado para o usuário (estagiários não contam: só circulam)."""
    return any(a.tipo != "estagiario" and pode_usar(usuario, andar, a.id) for a in ANDARES.get(andar, {}).values())


def catalogo() -> list[dict]:
    """Agentes que podem ser liberados (para o painel de usuários)."""
    return [{"andar": andar, "id": a.id, "nome": a.nome, "funcao": a.funcao}
            for andar, agentes in ANDARES.items() for a in agentes.values() if a.tipo != "estagiario"]
