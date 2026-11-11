"""Consulta repetida ao Cérebro na mesma tarefa recebe um aviso curto (Onda 2 de novembro, cerebro-35).

Caso real (tarefa 239): o Social Media mandou 4 vezes a mesma pergunta e recebeu 4 vezes uns 3 mil caracteres, sem
nada novo. Por tarefa e agente, guarda as perguntas feitas e a resposta que voltou. Pergunta igual ou muito parecida
(termos em comum acima de 0,8) com a mesma resposta: volta só o aviso. Se a base mudou, a resposta vai inteira; na
terceira repetição também (modelo fraco que "esqueceu"), e o caso fica no registro de atividade.
"""

import hashlib
import threading

PARECIDA = 0.8
MAX_TAREFAS = 200  # só a memória das tarefas recentes (o processo da API vive dias)
_vistas: dict[tuple[int, str], list[dict]] = {}
_trava = threading.Lock()


def _termos(texto: str) -> set[str]:
    from cerebro_texto import termos

    return set(termos(texto or ""))


def _parecidas(a: set[str], b: set[str]) -> bool:
    return bool(a and b) and len(a & b) / len(a | b) >= PARECIDA


def aviso(tarefa_id: int, agente: str, pergunta: str, resposta: str) -> str | None:
    """Aviso curto no lugar da resposta repetida; None: a resposta vai inteira (e fica registrada)."""
    if not tarefa_id or not (resposta or "").strip():
        return None
    termos, marca = _termos(pergunta), hashlib.sha1(resposta.encode("utf-8")).hexdigest()
    with _trava:
        vistas = _vistas.setdefault((tarefa_id, agente), [])
        igual = next((v for v in vistas if v["marca"] == marca and _parecidas(termos, v["termos"])), None)
        if not igual:
            vistas.append({"termos": termos, "marca": marca, "vezes": 1})
            while len(_vistas) > MAX_TAREFAS:
                _vistas.pop(next(iter(_vistas)))
            return None
        igual["vezes"] += 1
        vezes = igual["vezes"]
    if vezes >= 3:  # na 3ª, vai inteira: o caso fica no registro
        import tarefas

        tarefas.registrar_evento(tarefa_id, "consulta_repetida", agente, detalhe=f"{vezes}x: {pergunta[:200]}")
        return None
    return ("Você já recebeu isso na consulta anterior desta tarefa (as mesmas fontes, sem nada novo na base). Use o "
            "que já tem ou pergunte um fato específico.")
