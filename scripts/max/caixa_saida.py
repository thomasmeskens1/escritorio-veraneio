"""Caixa de saída do trabalhador (brainstorm de 11/11/2026, despachante-07): peça entregue nunca é produzida de novo.

Antes, quando o backend não confirmava o /concluir (API reiniciando, PC acordando, túnel), o trabalhador desistia
depois de 6 tentativas; na consulta seguinte a tarefa voltava à fila como órfã e o Max refazia a peça (janela de 5 h
gasta e pasta "(2)" no Drive). Agora a conclusão fica guardada num arquivo na pasta de trabalho até o backend
confirmar, e é reenviada ANTES de pedir a próxima peça: enquanto houver pendência, o trabalhador não pede a fila
(é o pedido da fila que devolve as órfãs). O /concluir já aceita repetição sem efeito duplo.
"""

import json
import time
import urllib.error
from pathlib import Path

import comum

PASTA = comum.TRABALHO / "caixa_saida"
VALIDADE_S = 7 * 24 * 3600     # pendência mais velha que isso (tarefa apagada?) sai com aviso no log
MAX_RECUSAS_DO_SERVIDOR = 10   # erro 5xx repetido na mesma pendência: desiste dela (não trava a fila para sempre)


def _arquivo(tarefa_id: int) -> Path:
    return PASTA / f"{int(tarefa_id)}.json"


def guardar(tarefa_id: int, corpo: dict) -> None:
    """Grava a conclusão antes do primeiro /concluir (se o PC cair no meio, ela sobrevive)."""
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        temporario = _arquivo(tarefa_id).with_suffix(".tmp")
        temporario.write_text(json.dumps({"tarefa_id": int(tarefa_id), "corpo": corpo, "em": time.time(),
                                          "recusas": 0}, ensure_ascii=False), encoding="utf-8")
        temporario.replace(_arquivo(tarefa_id))
    except OSError as erro:  # sem a caixa, segue como antes (só as tentativas na hora)
        comum.log(f"   não consegui guardar a conclusão #{tarefa_id} na caixa de saída ({erro})")


def remover(tarefa_id: int) -> None:
    _arquivo(tarefa_id).unlink(missing_ok=True)


def pendentes() -> list[dict]:
    if not PASTA.is_dir():
        return []
    itens = []
    for arquivo in sorted(PASTA.glob("*.json")):
        try:
            itens.append(json.loads(arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            comum.log(f"   caixa de saída: {arquivo.name} ilegível; descartado")
            arquivo.unlink(missing_ok=True)
    return itens


def reenviar(chamar=comum.chamar, agora: float | None = None) -> bool:
    """Reenvia as conclusões pendentes. True = caixa vazia (pode pedir a próxima peça); False = o backend ainda não
    confirmou e a fila espera (pedir a fila agora devolveria a peça para ser feita de novo)."""
    agora = time.time() if agora is None else agora
    for item in pendentes():
        tarefa_id = item["tarefa_id"]
        if agora - item.get("em", agora) > VALIDADE_S:
            comum.log(f"AVISO: a conclusão da peça #{tarefa_id} nunca foi aceita em 7 dias; saiu da caixa de saída.")
            remover(tarefa_id)
            continue
        try:
            chamar("POST", f"/api/producao/{tarefa_id}/concluir", item["corpo"])
        except urllib.error.HTTPError as erro:
            if erro.code < 500:  # 404 (tarefa apagada ou já encerrada) ou 422: repetir não adianta
                comum.log(f"   caixa de saída: o backend recusou a conclusão #{tarefa_id} ({erro.code}); descartada")
                remover(tarefa_id)
                continue
            item["recusas"] = item.get("recusas", 0) + 1
            if item["recusas"] >= MAX_RECUSAS_DO_SERVIDOR:
                comum.log(f"AVISO: o backend deu erro {erro.code} {item['recusas']} vezes na conclusão #{tarefa_id}; "
                          "saiu da caixa de saída.")
                remover(tarefa_id)
                continue
            guardar_recusa(item)
            return False
        except Exception as erro:  # backend fora do ar: tenta na próxima volta
            comum.log(f"   caixa de saída: a conclusão #{tarefa_id} ainda não foi aceita ({erro})")
            return False
        comum.log(f"   caixa de saída: conclusão #{tarefa_id} confirmada pelo backend (sem produzir de novo)")
        remover(tarefa_id)
    return True


def guardar_recusa(item: dict) -> None:
    try:
        _arquivo(item["tarefa_id"]).write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
