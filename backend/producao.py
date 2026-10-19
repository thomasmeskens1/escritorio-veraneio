"""Produção de arquivos (PNG/MP4/PDF) pelo Claude Code do dono do plano Max.

O backend só enfileira: um trabalhador no PC do dono (scripts/trabalhador_max.py) busca a próxima
produção, roda o Claude Code (Max), grava os arquivos na pasta do Drive e devolve o resultado aqui.
A rota é protegida por um token de operador que fica só no PC do dono (dados/operador.token).
"""

import hmac
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import atividade
import config
import tarefas
from conexoes import gerenciador
from estado import Agente

ARQUIVO_TOKEN = config.ARQUIVO_BANCO.parent / "operador.token"
MODELO_MAX = "claude-code/max"

# Pasta de cada andar dentro de "ESCRITÓRIO VERANEIO" no Drive.
PASTAS_ANDAR = {"marketing": "MARKETING", "porao": "PORÃO", "terreo": "TÉRREO", "cobertura": "COBERTURA"}

rotas = APIRouter(prefix="/api/producao")


def token_operador() -> str:
    """Cria o token na primeira subida; o trabalhador lê o mesmo arquivo pela pasta compartilhada."""
    if not ARQUIVO_TOKEN.exists():
        ARQUIVO_TOKEN.parent.mkdir(exist_ok=True)
        ARQUIVO_TOKEN.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()


def _exigir_operador(authorization: str) -> None:
    recebido = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(recebido, token_operador()):
        raise HTTPException(status_code=401, detail="Token de operador inválido")


def iniciar() -> None:
    token_operador()
    with tarefas._db() as db:  # produção interrompida por reinício volta para a fila
        db.execute("UPDATE tarefas SET status = 'producao' WHERE status = 'produzindo'")


async def enfileirar(login: str, andar: str, agente: Agente, texto: str) -> None:
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "complexa")
    tarefas.atualizar(tarefa_id, status="producao")
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Produção de arquivo pelo Claude Code (Max)")
    await gerenciador.enviar_para_usuario(login, {
        "tipo": "tarefa_adiada", "andar": andar, "agente": agente.id, "tarefa_id": tarefa_id,
        "texto": "Pedido enviado ao Claude Code (Max) para produção. Você recebe aqui o aviso quando terminar.",
    })


class Conclusao(BaseModel):
    resumo: str
    pasta: str               # caminho relativo dentro de "ESCRITÓRIO VERANEIO"
    arquivos: list[str] = []


class Falha(BaseModel):
    erro: str


@rotas.get("/proxima")
async def proxima(authorization: str = Header("")):
    """O trabalhador reserva a próxima produção pendente (ou recebe null)."""
    _exigir_operador(authorization)
    linha = tarefas._db().execute(
        "SELECT * FROM tarefas WHERE status = 'producao' ORDER BY id LIMIT 1").fetchone()
    if not linha:
        return {"producao": None}
    tarefas.atualizar(linha["id"], status="produzindo")
    tarefas.registrar_evento(linha["id"], "tentativa", linha["agente"], MODELO_MAX, "Claude Code (Max) iniciou a produção")
    await atividade.ocupar(linha["agente"])
    return {"producao": {
        "tarefa_id": linha["id"], "agente": linha["agente"], "andar": linha["andar"],
        "pasta_andar": PASTAS_ANDAR.get(linha["andar"], linha["andar"].upper()),
        "texto": linha["texto"], "criada_em": linha["criada_em"],
        "historico": [dict(h) for h in tarefas.historico(linha["usuario"], linha["andar"], linha["agente"], linha["id"])],
    }}


async def _finalizar(tarefa_id: int, status: str, resposta: str, evento: str, detalhe: str) -> None:
    linha = tarefas.obter(tarefa_id)
    if not linha or linha["status"] != "produzindo":
        raise HTTPException(status_code=404, detail="Produção não encontrada")
    criada = datetime.strptime(linha["criada_em"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    campos = {"status": status, "modelo": MODELO_MAX,
              "tempo_segundos": (datetime.now(timezone.utc) - criada).total_seconds()}
    campos["resposta" if status == "concluida" else "motivo"] = resposta
    tarefas.atualizar(tarefa_id, **campos)
    tarefas.registrar_evento(tarefa_id, evento, linha["agente"], MODELO_MAX, detalhe)
    await atividade.liberar(linha["agente"])

    from orquestrador import _entregar  # entrega no chat (ou na próxima conexão do usuário)
    await _entregar(tarefas.obter(tarefa_id))


@rotas.post("/{tarefa_id}/concluir")
async def concluir(tarefa_id: int, conclusao: Conclusao, authorization: str = Header("")):
    _exigir_operador(authorization)
    arquivos = "\n".join(f"- {nome}" for nome in conclusao.arquivos) or "- (nenhum arquivo listado)"
    resposta = (f"✅ Pedido concluído pelo Claude Code (Max).\n\n{conclusao.resumo.strip()}\n\n"
                f"Arquivos em ESCRITÓRIO VERANEIO/{conclusao.pasta}:\n{arquivos}")
    await _finalizar(tarefa_id, "concluida", resposta, "concluida",
                     f"{len(conclusao.arquivos)} arquivo(s) em {conclusao.pasta}")
    return {"ok": True}


@rotas.post("/{tarefa_id}/falhar")
async def falhar(tarefa_id: int, falha: Falha, authorization: str = Header("")):
    _exigir_operador(authorization)
    motivo = f"A produção pelo Claude Code (Max) falhou: {falha.erro[:300]}"
    await _finalizar(tarefa_id, "falhou", motivo, "falhou", falha.erro[:300])
    return {"ok": True}
