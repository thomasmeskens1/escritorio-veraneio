"""Rotas de leitura da interface: painel do Despachante, detalhes dos agentes, registro e aprendizado."""

from fastapi import APIRouter, Header, HTTPException

import aprendizado
import config
import saude
import tarefas
from auth import validar_token
from estado import ANDARES, AGENTES_PRODUCAO, andar_do_agente, buscar_agente, pode_acessar

rotas = APIRouter(prefix="/api")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def _filtro(usuario: dict) -> str | None:
    """Diretoria vê tudo; os demais, só as próprias tarefas."""
    return None if usuario["role"] == "diretoria" else usuario["sub"]


def _nome_do_agente(agente_id: str) -> str:
    andar = andar_do_agente(agente_id)
    agente = buscar_agente(andar, agente_id) if andar else None
    return agente.nome if agente else agente_id


@rotas.get("/tarefas")
def listar_tarefas(authorization: str = Header("")):
    filtro = _filtro(_usuario(authorization))
    contagem = tarefas.contagem_por_status(filtro)
    return {
        "resumo": {
            "por_status": contagem,
            "fila_anthropic": contagem["adiada"],
            "anthropic": {
                "gasto_mes_usd": round(tarefas.gasto_mes_usd(), 4),
                "credito_mensal_usd": config.CREDITO_MENSAL_ANTHROPIC_USD,
                "liberado_ate_hoje_usd": round(tarefas.liberado_ate_hoje_usd(), 2),
                "pausado": tarefas.orcamento_pausado(),  # Claude pausado; a fila segue em contingência
            },
            "modelos_fora": saude.resumo(),
            "modelos_7d": saude.estatisticas(7),  # saúde de cada modelo: tentativas, falhas, tempo médio
            "aprendizado": aprendizado.resumo(_nome_do_agente),
        },
        "tarefas": [_tarefa_publica(linha) for linha in tarefas.listar(filtro)],
    }


def _tarefa_publica(linha) -> dict:
    return {
        "id": linha["id"], "usuario": linha["usuario"], "andar": linha["andar"], "agente": linha["agente"],
        "agente_nome": _nome_do_agente(linha["agente"]), "texto": linha["texto"][:140],
        "dificuldade": linha["dificuldade"], "status": linha["status"], "modelo": linha["modelo"],
        "tentativas": linha["tentativas"], "tempo_segundos": round(linha["tempo_segundos"], 1) or None,
        "custo_usd": round(linha["custo_usd"], 4), "criada_em": linha["criada_em"],
        "concluida_em": linha["concluida_em"], "motivo": linha["motivo"],
    }


@rotas.get("/equipe")
def listar_equipe(authorization: str = Header("")):
    """Tela "Equipe" (contadores do topo): agentes dos andares acessíveis com função e descrição.
    O status ao vivo vem do WebSocket; aqui vai só o que não muda a cada segundo."""
    usuario = _usuario(authorization)
    return {"andares": [
        {"andar": andar, "agentes": [
            {"id": a.id, "nome": a.nome, "funcao": a.funcao, "descricao": a.descricao, "tipo": a.tipo}
            for a in agentes.values()]}
        for andar, agentes in ANDARES.items() if pode_acessar(usuario["role"], andar)]}


@rotas.get("/agentes/{andar}/{agente_id}")
def detalhar_agente(andar: str, agente_id: str, authorization: str = Header("")):
    """Dados do popup do agente."""
    usuario = _usuario(authorization)
    agente = buscar_agente(andar, agente_id)
    if not agente or not pode_acessar(usuario["role"], andar):
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    concluidas, total = tarefas.contagem_do_agente(agente_id)
    resumo = aprendizado.resumo(_nome_do_agente)
    return {
        **agente.model_dump(mode="json", exclude={"aparencia", "visitando"}),
        "tarefas_concluidas": concluidas + tarefas.etapas_do_agente(agente_id),
        "tarefas_total": total,
        "aprendizado": {
            "tarefas_registradas": resumo["tarefas_registradas"],
            "proximo_treino_em": resumo["proximo_treino_em"],
            "modelo_ativo": bool(resumo["modelo"] and resumo["modelo"]["ativo"]),
            "ajustes": aprendizado.ajustes_do_agente(agente_id),
        },
        "pode_treinar": usuario["role"] == "diretoria",
        "producao_restrita": agente_id in AGENTES_PRODUCAO and usuario["sub"] != config.DONO_MAX,
    }


@rotas.post("/aprendizado/treinar")
async def treinar_agora(authorization: str = Header("")):
    if _usuario(authorization)["role"] != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria pode treinar o modelo.")
    meta = await aprendizado.talvez_treinar(forcar=True)
    if not meta:
        return {"ok": False, "modelo": None, "mensagem": "Ainda não há tarefas finalizadas para treinar."}
    if meta["acuracia"] is None:
        return {"ok": True, "modelo": None, "mensagem": meta.get("observacao", "Dados insuficientes.")}
    estado = "ativado" if meta["ativo"] else "mantido inativo (as regras ainda acertam mais)"
    return {"ok": True, "modelo": {k: meta[k] for k in ("amostras", "acuracia", "acuracia_regras", "ativo")},
            "mensagem": f"Treinado com {meta['amostras']} tarefas: modelo {estado}."}


@rotas.get("/registro")
def registro(limite: int = 50, authorization: str = Header("")):
    """Registro de atividade: uma linha por pedido, com a linha do tempo dos eventos."""
    usuario = _usuario(authorization)
    linhas = tarefas.listar(_filtro(usuario), min(max(limite, 1), 200))
    eventos = tarefas.eventos_de([l["id"] for l in linhas])
    nomes = {}
    if usuario["role"] == "diretoria":
        from auth import carregar_usuarios
        nomes = {login: dados["nome"] for login, dados in carregar_usuarios().items()}

    itens = []
    for linha in linhas:
        eventos_tarefa = eventos.get(linha["id"], [])
        acionados = list(dict.fromkeys([linha["agente"], *(e["agente"] for e in eventos_tarefa if e["agente"])]))
        itens.append({
            "tarefa_id": linha["id"], "em": linha["criada_em"], "usuario": linha["usuario"],
            "usuario_nome": nomes.get(linha["usuario"], usuario.get("nome") if linha["usuario"] == usuario["sub"] else linha["usuario"]),
            "agentes": [{"id": a, "nome": _nome_do_agente(a)} for a in acionados],
            "resumo": linha["texto"][:160], "modelo": linha["modelo"], "status": linha["status"],
            "dificuldade": linha["dificuldade"], "tempo_segundos": round(linha["tempo_segundos"], 1),
            "custo_usd": round(linha["custo_usd"], 4),
            "eventos": [{"em": e["em"], "tipo": e["tipo"], "agente": e["agente"], "modelo": e["modelo"],
                         "detalhe": e["detalhe"]} for e in eventos_tarefa],
        })
    return {"itens": itens}
