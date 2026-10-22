"""Andamento da tarefa ativa de um agente, para o painel lateral do popup (versão simplificada do registro).

Gestor: planejamento → cada etapa do plano (fase, especialista, status) → consolidação.
Demais: pedido recebido → modelos tentados → consultas ao Cérebro → fila/produção → resposta.
Status de cada etapa: concluida | andamento | pendente | falhou.
"""

import json
import re
from datetime import datetime, timezone

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
        etapas += _etapas_da_producao(linha["id"])
    etapas.append({"texto": "Entregar a resposta no chat", "status": "pendente"})
    return etapas


PECA = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*\|\s*(.+)$")


def _peca(linha_progresso: str) -> tuple[int, int, str] | None:
    achou = PECA.match(linha_progresso)
    return (int(achou.group(1)), int(achou.group(2)), achou.group(3).strip()) if achou else None


def _etapas_da_producao(tarefa_id: int) -> list[dict]:
    """"Criando Story 1 de 4"...: o que o Claude Code anotou; as peças que faltam aparecem como pendentes."""
    import producao  # import tardio: produção depende do orquestrador

    linhas = producao.progresso_de(tarefa_id)
    if not linhas:
        return [{"texto": "Produzindo os arquivos no Claude Code (Max)", "status": "andamento"}]
    etapas = [{"texto": (p[2] if (p := _peca(l)) else l), "status": "concluida"} for l in linhas]
    etapas[-1]["status"] = "andamento"
    if (ultima := _peca(linhas[-1])) and ultima[1] > ultima[0]:
        etapas += [{"texto": f"Peça {k} de {ultima[1]}", "status": "pendente"} for k in range(ultima[0] + 1, ultima[1] + 1)]
    return etapas


def _segundos(iso: str) -> float:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _estimativa(linha, eventos: list) -> dict | None:
    """Tempo que falta: pelo ritmo das peças já feitas (produção com progresso) ou pela média das últimas
    tarefas concluídas do mesmo agente. None se ainda não há base para estimar."""
    agora = datetime.now(timezone.utc).timestamp()
    inicio = next((_segundos(e["em"]) for e in reversed(eventos) if e["tipo"] == "tentativa"), None)
    restante = None
    if linha["status"] == "produzindo" and inicio:
        import producao

        pecas = [p for l in producao.progresso_de(linha["id"]) if (p := _peca(l))]
        if pecas and pecas[-1][0] >= 2:  # ritmo real: tempo por peça já concluída
            atual, total, _ = pecas[-1]
            restante = (agora - inicio) / (atual - 1) * (total - atual + 1)
    if restante is None:
        media = tarefas._db().execute(
            "SELECT AVG(tempo_segundos) FROM (SELECT tempo_segundos FROM tarefas WHERE agente = ? AND status = "
            "'concluida' AND tempo_segundos > 0 ORDER BY id DESC LIMIT 10)", (linha["agente"],)).fetchone()[0]
        if not media:
            return None
        restante = media - (agora - _segundos(linha["criada_em"]))
    restante = max(restante, 60)
    return {"restante_s": round(restante),
            "previsao": datetime.fromtimestamp(agora + restante, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


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
                      "agente": _nome_do_agente(linha["agente"]), "etapas": etapas,
                      "estimativa": _estimativa(linha, eventos)}}
