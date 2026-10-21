"""Andamento da tarefa ativa de um agente, para o painel lateral do popup (versão simplificada do registro).

Gestor: planejamento → cada etapa do plano (fase, especialista, status) → consolidação.
Demais: pedido recebido → modelos tentados → consultas ao Cérebro → fila/produção → resposta.
Status de cada etapa: concluida | andamento | pendente | falhou.
"""

import json

from fastapi import APIRouter, Header, HTTPException

import encaminhamento
import tarefas
from api_painel import _filtro, _nome_do_agente, _usuario
from estado import buscar_agente, pode_acessar

rotas = APIRouter(prefix="/api")

ATIVAS = ("executando", "adiada", "producao", "produzindo")


def _modelo_curto(modelo: str | None) -> str:
    if modelo == "claude-code/max":
        return "Claude Code (Max)"
    return (modelo or "modelo").split("/")[-1].split(":")[0]


def _etapas_do_gestor(tarefa_id: int, eventos: list) -> list[dict] | None:
    from agents.projeto import PASTA_PROJETOS, _arquivo_etapa

    pasta = PASTA_PROJETOS / str(tarefa_id)
    if not (pasta / "plano.json").exists():
        return None
    plano = json.loads((pasta / "plano.json").read_text(encoding="utf-8"))
    iniciadas = {e["detalhe"].split(":")[0] for e in eventos if e["tipo"] == "etapa_iniciada" and e["detalhe"]}
    etapas = [{"texto": "Gestor montou o plano", "status": "concluida"}]
    for n, passo in enumerate(plano, 1):
        if _arquivo_etapa(pasta, n, passo["agente"]).exists():
            status = "concluida"
        elif f"Etapa {n}" in iniciadas:
            status = "andamento"
        else:
            status = "pendente"
        etapas.append({"texto": f"Fase {passo.get('fase', n)} · {_nome_do_agente(passo['agente'])}: "
                                f"{passo['instrucao'][:110]}", "status": status})
    todas = all(e["status"] == "concluida" for e in etapas)
    etapas.append({"texto": "Gestor revisa e consolida a entrega",
                   "status": "concluida" if (pasta / "final.md").exists() else ("andamento" if todas else "pendente")})
    return etapas


def _etapas_por_eventos(linha, eventos: list) -> list[dict]:
    etapas = [{"texto": "Pedido recebido", "status": "concluida"}]
    for i, e in enumerate(eventos):
        seguinte = eventos[i + 1:]
        if e["tipo"] == "tentativa" and e["modelo"] == "claude-code/max" and linha["status"] in ("producao", "produzindo"):
            continue  # a produção no Max já aparece na etapa de status, logo abaixo
        if e["tipo"] == "tentativa":
            falhou = any(s["tipo"] == "falha_modelo" and s["modelo"] == e["modelo"] for s in seguinte[:3])
            status = "falhou" if falhou else ("andamento" if not seguinte else "concluida")
            etapas.append({"texto": f"Trabalhando com {_modelo_curto(e['modelo'])}", "status": status})
        elif e["tipo"] == "consulta_cerebro":
            etapas.append({"texto": f"Consultou o Cérebro: {(e['detalhe'] or '')[:90]}", "status": "concluida"})
        elif e["tipo"] == "adiada":
            etapas.append({"texto": f"Na fila ({e['detalhe'] or 'aguardando modelo'})",
                           "status": "andamento" if linha["status"] == "adiada" else "concluida"})
    if linha["status"] == "producao":
        etapas.append({"texto": "Na fila do Claude Code (Max) para produzir os arquivos", "status": "andamento"})
    elif linha["status"] == "produzindo":
        etapas.append({"texto": "Produzindo os arquivos no Claude Code (Max)", "status": "andamento"})
    etapas.append({"texto": "Entregar a resposta no chat", "status": "pendente"})
    return etapas


@rotas.get("/agentes/{andar}/{agente_id}/andamento")
def andamento(andar: str, agente_id: str, authorization: str = Header("")):
    """Tarefa ativa do agente (do usuário; diretoria vê todas) com as etapas e o status de cada uma."""
    usuario = _usuario(authorization)
    if not buscar_agente(andar, agente_id) or not pode_acessar(usuario["role"], andar):
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    filtro = _filtro(usuario)
    marcadores = ",".join("?" * len(ATIVAS))
    # Também a tarefa que nasceu neste chat e roda em outro agente (Gestor, produção no Max).
    vindas = list(encaminhamento.tarefas_do_chat(andar, agente_id))
    ids = ",".join("?" * len(vindas)) or "NULL"
    linha = tarefas._db().execute(
        f"SELECT * FROM tarefas WHERE ((andar = ? AND agente = ?) OR id IN ({ids})) AND status IN ({marcadores}) "
        + ("AND usuario = ? " if filtro else "") + "ORDER BY id DESC LIMIT 1",
        (andar, agente_id, *vindas, *ATIVAS, *([filtro] if filtro else []))).fetchone()
    if not linha:
        return {"ativa": None}
    eventos = tarefas.eventos_de([linha["id"]]).get(linha["id"], [])
    etapas = (_etapas_do_gestor(linha["id"], eventos) if linha["agente"] == "gestor" else None) \
        or _etapas_por_eventos(linha, eventos)
    return {"ativa": {"tarefa_id": linha["id"], "status": linha["status"],
                      "pedido": encaminhamento.pedido_original(linha["texto"])[:140],
                      "agente": _nome_do_agente(linha["agente"]), "etapas": etapas}}
