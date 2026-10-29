"""Relatório do "Treinar agora" (Thomas, 29/10/2026): o que foi aprendido e por quê, desde o treino anterior.

Duas frentes, que antes ficavam escondidas atrás de "N amostras · acurácia":
1. Roteamento: o classificador que decide se um pedido é simples, médio ou complexo (e, com isso, a rota de modelos)
   e os ajustes estatísticos por agente.
2. Cérebro: o conhecimento que entrou (de onde, de qual empresa), o que mais foi usado nas tarefas, as regras
   aprovadas a partir de correções e elogios e o que espera aprovação.
"""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

import aprendizado
import tarefas

FONTES = {"ensinado": "ensinado pelo Thomas", "oficial": "manuais oficiais", "site": "site", "drive": "Drive",
          "dados": "painel analítico", "rede": "redes sociais (YouTube/Instagram)", "tarefa": "tarefas concluídas"}
EMPRESAS = {"casa_veraneio": "Casa Veraneio", "cv_corporativo": "Corporativo", "casa_vero": "Casa Vero", "*": "Comum"}
NIVEIS = {"simples": "simples", "media": "média", "complexa": "complexa"}


def _desde(anterior: str | None) -> str:
    if anterior:
        return anterior
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _roteamento(meta: dict, nome_do_agente) -> dict:
    linhas = aprendizado._finalizadas(aprendizado.JANELA)
    observados = Counter(aprendizado.rotulo_observado(l) for l in linhas)
    previstos = Counter(l["dificuldade"] for l in linhas)
    acertos = sum(l["dificuldade"] == aprendizado.rotulo_observado(l) for l in linhas)
    if meta.get("acuracia") is None:
        porque = meta.get("observacao", "Ainda não há variedade de tarefas para treinar.")
    elif meta["ativo"]:
        porque = (f"O modelo acertou {meta['acuracia']:.0%} das dificuldades, mais que as regras fixas "
                  f"({meta['acuracia_regras']:.0%}): ele passa a decidir a rota dos próximos pedidos.")
    else:
        porque = (f"O modelo acertou {meta['acuracia']:.0%}, menos que as regras fixas ({meta['acuracia_regras']:.0%}). "
                  "As regras continuam decidindo; o modelo volta a ser testado no próximo treino, com mais tarefas.")
    ajustes = [{"agente": nome_do_agente(agente), "de": NIVEIS.get(de, de), "para": NIVEIS.get(a["para"], a["para"]),
                "motivo": a["motivo"]} for (agente, de), a in sorted(aprendizado._ajustes.items())]
    return {"amostras": meta.get("amostras", 0), "acuracia": meta.get("acuracia"),
            "acuracia_regras": meta.get("acuracia_regras"), "ativo": bool(meta.get("ativo")), "porque": porque,
            "acertos_regras": acertos, "observado": {NIVEIS[k]: observados.get(k, 0) for k in NIVEIS},
            "classificado": {NIVEIS[k]: previstos.get(k, 0) for k in NIVEIS}, "ajustes": ajustes}


def _cerebro(desde: str, nome_do_agente) -> dict:
    db = tarefas._db()
    novos = db.execute("SELECT fonte_tipo, empresa, titulo, criado_em FROM conhecimento WHERE ativo = 1 AND "
                       "criado_em >= ? ORDER BY id DESC", (desde,)).fetchall()
    por_fonte = Counter(FONTES.get(l["fonte_tipo"], l["fonte_tipo"]) for l in novos)
    por_empresa = Counter(EMPRESAS.get(l["empresa"], l["empresa"]) for l in novos)
    consultas = db.execute("SELECT agente, ids_conhecimento, resultado FROM consultas_cerebro WHERE em >= ?",
                           (desde,)).fetchall()
    usados: Counter = Counter()
    for c in consultas:
        if c["resultado"] == "sucesso":
            usados.update(json.loads(c["ids_conhecimento"] or "[]"))
    titulos = {}
    if usados:
        ids = [i for i, _ in usados.most_common(6)]
        marcadores = ",".join("?" * len(ids))
        titulos = {l["id"]: (l["titulo"], FONTES.get(l["fonte_tipo"], l["fonte_tipo"]))
                   for l in db.execute(f"SELECT id, titulo, fonte_tipo FROM conhecimento WHERE id IN ({marcadores})", ids)}
    regras = db.execute("SELECT agente, regra, criada_em FROM regras_aprendidas WHERE ativa = 1 AND criada_em >= ? "
                        "ORDER BY id DESC", (desde,)).fetchall()
    pendentes = db.execute("SELECT tipo, COUNT(*) n FROM observacoes WHERE status = 'nova' GROUP BY tipo").fetchall()
    return {
        "novos_total": len(novos),
        "por_fonte": dict(por_fonte.most_common()),
        "por_empresa": dict(por_empresa.most_common()),
        "ultimos": [{"titulo": l["titulo"], "fonte": FONTES.get(l["fonte_tipo"], l["fonte_tipo"]),
                     "empresa": EMPRESAS.get(l["empresa"], l["empresa"])} for l in novos[:8]],
        "consultas": len(consultas),
        "consultas_sucesso": sum(c["resultado"] == "sucesso" for c in consultas),
        "por_agente": dict(Counter(nome_do_agente(c["agente"]) for c in consultas).most_common(6)),
        "mais_usados": [{"titulo": titulos[i][0], "fonte": titulos[i][1], "vezes": n}
                        for i, n in usados.most_common(6) if i in titulos],
        "regras_aprovadas": [{"agente": "Todos os agentes" if r["agente"] == "*" else nome_do_agente(r["agente"]),
                              "regra": r["regra"]} for r in regras],
        "pendentes": {{"elogio": "elogios", "aprendizado": "aprendizados da semana"}.get(p["tipo"], "correções"): p["n"]
                      for p in pendentes},
    }


def montar(meta: dict, anterior: str | None, nome_do_agente) -> dict:
    desde = _desde(anterior)
    return {"desde": desde, "primeiro_treino": anterior is None, "roteamento": _roteamento(meta, nome_do_agente),
            "cerebro": _cerebro(desde, nome_do_agente)}
