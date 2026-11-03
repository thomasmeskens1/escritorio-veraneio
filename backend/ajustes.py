"""Ajustes pedidos pela equipe viram aprendizado (Thomas, 03/11/2026: "os ajustes devem ser armazenados para que o
Cérebro ou o Agente aprendam").

Todo ajuste já fica gravado: é uma tarefa com o texto do pedido ("Ajuste na peça #33: aumente a logo", "troque o
título...") e, na produção, ligada à peça anterior (producao_info.base_tarefa_id). Nada se apaga. Este módulo lê esses
registros de dois jeitos:
- no contexto do agente (chat e produção no Max): os últimos ajustes pedidos a ele e aos afins, na mesma empresa, para
  ele já aplicar o que se repete;
- na consolidação semanal: os ajustes da semana entram nos dados, e o padrão repetido vira "🧠 Aprendizado da semana"
  para a Diretoria aprovar como regra permanente (decisão 16: nada vira regra sozinho).
"""

import re
from datetime import timedelta

import tarefas
from correcoes import AFINS_NA_PRODUCAO

AJUSTE = re.compile(r"^\s*(ajuste na pe[cç]a #\d+|ajustes?|ajustar|altere|alterar|corrija|corrigir|refa[cç]a|troque|"
                    r"trocar|mude|mudar|aumente|diminua|tire|remova|substitua|deixe|coloque)\b", re.IGNORECASE)
DIAS_NO_CONTEXTO = 60
MAX_NO_CONTEXTO = 8
TEXTO_MAX = 300


def e_ajuste(texto: str) -> bool:
    return bool(AJUSTE.search(texto or ""))


def _pedido(texto: str) -> str:
    """Só o que a pessoa escreveu: a produção anexa o contexto do chat depois de uma linha em branco."""
    import insatisfacoes  # import tardio: carrega o Cérebro (sem contatos nem segredos)

    return insatisfacoes.texto_seguro((texto or "").split("\n\n", 1)[0].strip())[:TEXTO_MAX]


def _ajustes(agentes: tuple[str, ...], empresa: str | None, desde: str, limite: int = 200) -> list[dict]:
    marcas = ",".join("?" * len(agentes))
    filtro, valores = ("AND empresa = ?", (empresa,)) if empresa else ("", ())
    linhas = tarefas._db().execute(
        f"SELECT id, agente, empresa, texto, criada_em FROM tarefas WHERE agente IN ({marcas}) AND criada_em >= ? "
        f"AND status != 'cancelada' {filtro} ORDER BY id DESC LIMIT ?", (*agentes, desde, *valores, limite)).fetchall()
    return [{**dict(l), "pedido": _pedido(l["texto"])} for l in linhas if e_ajuste(l["texto"])]


def para_contexto(agente_id: str, empresa: str) -> str:
    """Bloco com os últimos ajustes pedidos a este agente (e afins) na empresa do trabalho ("" se não há)."""
    agentes = AFINS_NA_PRODUCAO.get(agente_id, (agente_id,))
    achados = _ajustes(agentes, empresa, tarefas._agora(-timedelta(days=DIAS_NO_CONTEXTO)))[:MAX_NO_CONTEXTO]
    if not achados:
        return ""
    return ("AJUSTES QUE A EQUIPE PEDIU NAS ÚLTIMAS PEÇAS (aprenda com eles: o que se repete, como tamanho da logo, "
            "cor, tom ou posição do texto, já entregue assim nesta peça; o que era específico de uma peça, como "
            "trocar uma foto, ignore. O pedido desta peça vale sobre eles):\n"
            + "\n".join(f"- {a['criada_em'][:10]}: {a['pedido']}" for a in reversed(achados)))


def da_semana(desde: str) -> list[dict]:
    """Ajustes de todos os agentes desde `desde` (consolidação semanal)."""
    agentes = tuple({l["agente"] for l in tarefas._db().execute(
        "SELECT DISTINCT agente FROM tarefas WHERE criada_em >= ?", (desde,))})
    return _ajustes(agentes, None, desde, limite=500) if agentes else []
