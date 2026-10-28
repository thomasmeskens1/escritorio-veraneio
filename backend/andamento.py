"""Andamento da tarefa ativa de um agente, para o painel lateral do popup (versão simplificada do registro).

Gestor: planejamento → cada etapa do plano (fase, especialista, status) → consolidação.
Demais: pedido recebido → modelos tentados → consultas ao Cérebro → fila/produção → resposta.
Status de cada etapa: concluida | andamento | pendente | falhou.
"""

import json
import re
from collections import Counter
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


def _etapas_no_projeto(tarefa_id: int, agente_id: str, eventos: list) -> list[dict] | None:
    """O especialista dentro de um projeto do Gestor: as etapas DELE (fila, Cérebro, modelo, entrega). Antes, o log
    do especialista ficava vazio enquanto ele trabalhava para o Gestor (Thomas, 28/10/2026)."""
    from agents.projeto import PASTA_PROJETOS, _arquivo_etapa

    pasta = PASTA_PROJETOS / str(tarefa_id)
    if not (pasta / "plano.json").exists():
        return None
    plano = json.loads((pasta / "plano.json").read_text(encoding="utf-8"))
    minhas = [(n, p) for n, p in enumerate(plano, 1) if p["agente"] == agente_id]
    if not minhas:
        return None
    etapas = [{"texto": f"Pedido do Gestor (projeto #{tarefa_id})", "status": "concluida"}]
    for n, passo in minhas:
        marca = f"Etapa {n}:"
        inicio = next((i for i, e in enumerate(eventos) if e["tipo"] == "etapa_iniciada"
                       and e["agente"] == agente_id and (e["detalhe"] or "").startswith(marca)), None)
        pronta = _arquivo_etapa(pasta, n, agente_id).exists()
        if inicio is None and not pronta:
            etapas.append({"texto": f"Etapa {n} na fila: começa na fase {passo.get('fase', n)}, depois das anteriores",
                           "status": "pendente"})
            continue
        etapas.append({"texto": f"Etapa {n}: {passo['instrucao'][:110]}", "status": "concluida"})
        fim = next((i for i, e in enumerate(eventos) if i > (inicio or 0) and e["tipo"] == "etapa_salva"
                    and e["agente"] == agente_id and (e["detalhe"] or "").startswith(marca)), len(eventos))
        for e in eventos[inicio or 0:fim]:
            if e["agente"] != agente_id:
                continue
            if e["tipo"] == "etapa_modelo":
                etapas.append({"texto": f"Trabalhando com {_modelo_curto(e['modelo'])}",
                               "status": "concluida" if pronta else "andamento"})
            elif e["tipo"] == "consulta_cerebro":
                etapas.append({"texto": f"Consultou o Cérebro: {(e['detalhe'] or '')[:90]}", "status": "concluida"})
        if not any(e["status"] == "andamento" for e in etapas) and not pronta:
            etapas.append({"texto": f"Trabalhando na etapa {n}", "status": "andamento"})
        etapas.append({"texto": f"Entregar a etapa {n} ao Gestor", "status": "concluida" if pronta else "pendente"})
    etapas.append({"texto": "Gestor revisa e consolida a entrega",
                   "status": "concluida" if (pasta / "final.md").exists()
                   else ("andamento" if all(_arquivo_etapa(pasta, i, p["agente"]).exists()
                                            for i, p in enumerate(plano, 1)) else "pendente")})
    return _sem_repeticao(etapas)


def _projeto_do_gestor(andar: str, agente_id: str, filtro: str | None):
    """Projeto ativo do Gestor que tem etapa deste especialista (o mais recente)."""
    if agente_id == "gestor":
        return None
    marcadores = ",".join("?" * len(ATIVAS))
    linhas = tarefas._db().execute(
        f"SELECT * FROM tarefas WHERE andar = ? AND agente = 'gestor' AND status IN ({marcadores}) "
        + ("AND usuario = ? " if filtro else "") + "ORDER BY id DESC LIMIT 5",
        (andar, *ATIVAS, *([filtro] if filtro else []))).fetchall()
    for linha in linhas:
        eventos = tarefas.eventos_de([linha["id"]]).get(linha["id"], [])
        if (etapas := _etapas_no_projeto(linha["id"], agente_id, eventos)):
            return linha, eventos, etapas
    return None


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
        elif e["tipo"] == "item_monday":  # Social Media: cada peça do planejamento criada no board
            etapas.append({"texto": f"Criou no Monday — {e['detalhe']}", "status": "concluida"})
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
    return _sem_repeticao(etapas)


def _sem_repeticao(etapas: list[dict]) -> list[dict]:
    """Mesma etapa principal mais de uma vez (o modelo tentado de novo, a mesma consulta ao Cérebro): fica uma linha
    só, na posição da última vez e com o status dela, e a contagem no texto (auditoria de todos os agentes,
    27/10/2026). As partes da produção (sub) já chegam sem repetição de _etapas_da_producao."""
    vezes = Counter(e["texto"] for e in etapas if not e.get("sub"))
    vistas, saida = Counter(), []
    for etapa in etapas:
        texto = etapa["texto"]
        if not etapa.get("sub") and vezes[texto] > 1:
            vistas[texto] += 1
            if vistas[texto] < vezes[texto]:
                continue
            etapa = {**etapa, "texto": f"{texto} ({vezes[texto]} vezes)"}
        saida.append(etapa)
    return saida


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
    # Níveis: peça ("1/1 | Carrossel"), fase da peça ("> Geração dos vídeos") e parte ("- 2/8 | Slide 2 — Vero 90").
    # A fase dá nome a cada rodada pelos slides (teste, montagem, vídeos): sem ela, os slides se repetiam sem
    # explicação (teste real, 26/10/2026). As pendências são da fase atual.
    # Parte repetida no mesmo bloco (o Claude Code voltou aos slides sem anotar uma fase nova): a mesma linha é
    # reaproveitada com a contagem de passadas, em vez de repetir "Slide 1, Slide 8, Slide 1..." (teste real, #68).
    etapas, pecas, subs = [], [], []
    tem_fase, atual, vistas = False, None, {}
    for linha in linhas:
        limpa = linha.lstrip()
        fase = limpa.startswith(">")
        sub = limpa.startswith(("-", "↳"))
        texto = limpa.lstrip(">-↳ ").strip()
        peca = _peca(texto)
        nome = peca[2] if peca else texto
        if fase:
            tem_fase, subs, vistas = True, [], {}
        elif sub:
            subs.append(peca)
            if (repetida := vistas.get(nome)):
                repetida["passadas"] += 1
                repetida["texto"] = f"{nome} · {repetida['passadas']}ª passada"
                atual = repetida
                continue
        else:
            pecas.append(peca)
            tem_fase, subs, vistas = False, [], {}
        nivel = 1 if fase else (2 if sub and tem_fase else 1 if sub else 0)
        atual = {"texto": nome, "status": "concluida", "sub": nivel > 0, "nivel": nivel, "fase": fase, "passadas": 1}
        etapas.append(atual)
        if sub:
            vistas[nome] = atual
    repetiu = any(e["passadas"] > 1 for e in vistas.values())  # nova passada: não há "próximas" partes a prever
    for etapa in etapas:
        etapa.pop("passadas")
    atual["status"] = "andamento"
    if atual["nivel"]:  # parte ou fase em andamento: quem está acima dela também está
        posicao = etapas.index(atual)
        for nivel in range(atual["nivel"] - 1, -1, -1):
            # A produção pode começar direto por uma fase, sem a linha da peça (teste real: "> Ajuste v3: ...").
            if (acima := next((e for e in reversed(etapas[:posicao]) if e["nivel"] == nivel), None)):
                acima["status"] = "andamento"
        if subs and (ultimo := subs[-1]) and ultimo[1] > ultimo[0] and not repetiu:
            etapas += [{"texto": f"{k} de {ultimo[1]}", "status": "pendente", "sub": True, "nivel": atual["nivel"],
                        "fase": False} for k in range(ultimo[0] + 1, ultimo[1] + 1)]
    if pecas and (ultima := pecas[-1]) and ultima[1] > ultima[0]:
        etapas += [{"texto": f"Peça {k} de {ultima[1]}", "status": "pendente", "sub": False, "nivel": 0, "fase": False}
                   for k in range(ultima[0] + 1, ultima[1] + 1)]
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
        # Desde o início desta tentativa (uma produção retomada não conta as horas em que ficou parada).
        restante = media - (agora - (inicio or _segundos(linha["criada_em"])))
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
        # Sem tarefa própria: pode estar trabalhando numa etapa de projeto do Gestor.
        if not (no_projeto := _projeto_do_gestor(andar, agente_id, filtro)):
            return {"ativa": None}
        projeto, eventos, etapas = no_projeto
        return {"ativa": {"tarefa_id": projeto["id"], "status": projeto["status"],
                          "pedido": encaminhamento.pedido_original(projeto["texto"])[:140],
                          "agente": f"{_nome_do_agente(agente_id)} (projeto do Gestor)", "etapas": etapas,
                          "estimativa": None}}
    eventos = tarefas.eventos_de([linha["id"]]).get(linha["id"], [])
    etapas = (_etapas_do_gestor(linha["id"], eventos) if linha["agente"] == "gestor" else None) \
        or _etapas_por_eventos(linha, eventos)
    return {"ativa": {"tarefa_id": linha["id"], "status": linha["status"],
                      "pedido": encaminhamento.pedido_original(linha["texto"])[:140],
                      "agente": _nome_do_agente(linha["agente"]), "etapas": etapas,
                      "estimativa": _estimativa(linha, eventos)}}
