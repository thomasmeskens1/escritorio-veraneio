"""Produção de arquivos (PNG/MP4/PDF) pelo Claude Code do dono do plano Max.

O backend só enfileira: um trabalhador no PC do dono (scripts/max/trabalhador_max.py) busca o próximo
item da fila, roda o Claude Code (Max), grava os arquivos na pasta do Drive e devolve o resultado aqui.
A rota é protegida por um token de operador que fica só no PC do dono (dados/operador.token).

Além das produções (tabela tarefas), a fila tem "trabalhos do Max" (tabela trabalhos_max):
  anexo -> o Claude Code lê uma imagem/PDF enviado pelo dono e devolve a descrição;
  site  -> o Claude Code lê www.casaveraneio.com e ensina o Cérebro.
"""

import asyncio
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import atividade
import config
import tarefas
from auth import validar_token
from conexoes import gerenciador
from estado import Agente

ARQUIVO_TOKEN = config.ARQUIVO_BANCO.parent / "operador.token"
MODELO_MAX = "claude-code/max"
TIPOS_TRABALHO = {"anexo", "site"}

# Pasta de cada andar dentro de "ESCRITÓRIO VERANEIO" no Drive.
PASTAS_ANDAR = {"marketing": "MARKETING", "porao": "PORÃO", "terreo": "TÉRREO", "cobertura": "COBERTURA"}

rotas = APIRouter(prefix="/api/producao")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabalhos_max (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,              -- anexo | site
    payload TEXT NOT NULL,           -- JSON
    status TEXT NOT NULL,            -- pendente | executando | concluido | falhou
    resultado TEXT,
    criado_em TEXT NOT NULL,
    concluido_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_trabalhos_status ON trabalhos_max(status);
CREATE TABLE IF NOT EXISTS producao_anexos (
    tarefa_id INTEGER PRIMARY KEY,
    caminhos TEXT NOT NULL           -- JSON: caminhos relativos a backend/ (ex.: dados/anexos/ab12cd34.png)
);
"""
_esquema_criado = False


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _exigir_operador_ou_dono(authorization: str) -> None:
    """Token de operador (PC do dono) ou JWT da conta dona do plano Max."""
    recebido = authorization.removeprefix("Bearer ").strip()
    if hmac.compare_digest(recebido, token_operador()):
        return
    usuario = validar_token(recebido)
    if not usuario or usuario.get("sub") != config.DONO_MAX:
        raise HTTPException(status_code=401, detail="Apenas o operador ou o dono do plano Max")


def iniciar() -> None:
    token_operador()
    with _db() as db:  # item interrompido por reinício volta para a fila
        db.execute("UPDATE tarefas SET status = 'producao' WHERE status = 'produzindo'")
        db.execute("UPDATE trabalhos_max SET status = 'pendente' WHERE status = 'executando'")


async def enfileirar(login: str, andar: str, agente: Agente, texto: str, anexos: list[str] | None = None) -> None:
    """`anexos`: caminhos de anexos.caminhos(); o trabalhador copia os arquivos para a pasta da requisição."""
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "complexa")
    if anexos:
        with _db() as db:
            db.execute("INSERT OR REPLACE INTO producao_anexos (tarefa_id, caminhos) VALUES (?, ?)",
                       (tarefa_id, json.dumps(list(anexos))))
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


class Resultado(BaseModel):
    resultado: str


class NovoTrabalho(BaseModel):
    tipo: str
    payload: dict = {}


# --- Trabalhos do Max (anexo | site) ----------------------------------------------------

async def criar_trabalho(tipo: str, payload: dict) -> int:
    if tipo not in TIPOS_TRABALHO:
        raise ValueError(f"Tipo de trabalho desconhecido: {tipo}")
    with _db() as db:
        cursor = db.execute("INSERT INTO trabalhos_max (tipo, payload, status, criado_em) VALUES (?, ?, 'pendente', ?)",
                            (tipo, json.dumps(payload, ensure_ascii=False), _agora()))
        return cursor.lastrowid


def obter_trabalho(trabalho_id: int) -> dict | None:
    linha = _db().execute("SELECT * FROM trabalhos_max WHERE id = ?", (trabalho_id,)).fetchone()
    return {**dict(linha), "payload": json.loads(linha["payload"])} if linha else None


def trabalho_em_aberto(tipo: str, campo: str, valor) -> int | None:
    """Trabalho pendente/executando cujo payload[campo] == valor (evita duplicar)."""
    if not campo.isidentifier():
        raise ValueError("Campo inválido")
    linha = _db().execute(
        "SELECT id FROM trabalhos_max WHERE tipo = ? AND status IN ('pendente', 'executando') "
        f"AND json_extract(payload, '$.{campo}') = ? ORDER BY id LIMIT 1", (tipo, valor)).fetchone()
    return linha["id"] if linha else None


async def aguardar_trabalho(trabalho_id: int, timeout: float) -> dict:
    """Espera o trabalho terminar (concluido | falhou); no tempo limite devolve o estado atual."""
    limite = time.monotonic() + timeout
    while True:
        trabalho = obter_trabalho(trabalho_id) or {"id": trabalho_id, "status": "falhou",
                                                   "resultado": "Trabalho não encontrado."}
        restante = limite - time.monotonic()
        if trabalho["status"] in ("concluido", "falhou") or restante <= 0:
            return trabalho
        await asyncio.sleep(min(1.0, max(0.05, restante)))


def _reservar_trabalho(tipos: tuple[str, ...]) -> dict | None:
    marcadores = ",".join("?" * len(tipos))
    linha = _db().execute(f"SELECT * FROM trabalhos_max WHERE status = 'pendente' AND tipo IN ({marcadores}) "
                          "ORDER BY id LIMIT 1", tipos).fetchone()
    if not linha:
        return None
    with _db() as db:
        db.execute("UPDATE trabalhos_max SET status = 'executando' WHERE id = ?", (linha["id"],))
    return {"id": linha["id"], "tipo": linha["tipo"], "payload": json.loads(linha["payload"])}


def _finalizar_trabalho(trabalho_id: int, status: str, resultado: str) -> dict:
    trabalho = obter_trabalho(trabalho_id)
    if not trabalho or trabalho["status"] != "executando":
        raise HTTPException(status_code=404, detail="Trabalho não encontrado")
    with _db() as db:
        db.execute("UPDATE trabalhos_max SET status = ?, resultado = ?, concluido_em = ? WHERE id = ?",
                   (status, resultado, _agora(), trabalho_id))
    return trabalho


@rotas.post("/trabalhos")
async def novo_trabalho(dados: NovoTrabalho, authorization: str = Header("")):
    """Cria um trabalho manualmente (ex.: {"tipo": "site"} para reler o site)."""
    _exigir_operador_ou_dono(authorization)
    if dados.tipo not in TIPOS_TRABALHO:
        raise HTTPException(status_code=422, detail=f"Tipo deve ser um de: {', '.join(sorted(TIPOS_TRABALHO))}")
    return {"id": await criar_trabalho(dados.tipo, dados.payload)}


@rotas.post("/trabalhos/{trabalho_id}/concluir")
async def concluir_trabalho(trabalho_id: int, dados: Resultado, authorization: str = Header("")):
    _exigir_operador(authorization)
    trabalho = _finalizar_trabalho(trabalho_id, "concluido", dados.resultado)
    if trabalho["tipo"] == "anexo" and trabalho["payload"].get("anexo_id"):
        import anexos  # import tardio: anexos depende deste módulo
        anexos.salvar_descricao(trabalho["payload"]["anexo_id"], dados.resultado)
    return {"ok": True}


@rotas.post("/trabalhos/{trabalho_id}/falhar")
async def falhar_trabalho(trabalho_id: int, falha: Falha, authorization: str = Header("")):
    _exigir_operador(authorization)
    _finalizar_trabalho(trabalho_id, "falhou", falha.erro[:500])
    return {"ok": True}


# --- Fila do trabalhador -----------------------------------------------------------------

@rotas.get("/proxima")
async def proxima(authorization: str = Header("")):
    """Reserva o próximo item: anexo (alguém esperando) > produção > demais trabalhos. Ambos nulos = fila vazia."""
    _exigir_operador(authorization)
    if (trabalho := _reservar_trabalho(("anexo",))):
        return {"producao": None, "trabalho": trabalho}
    linha = _db().execute(
        "SELECT * FROM tarefas WHERE status = 'producao' ORDER BY id LIMIT 1").fetchone()
    if not linha:
        return {"producao": None, "trabalho": _reservar_trabalho(tuple(sorted(TIPOS_TRABALHO - {"anexo"})))}
    tarefas.atualizar(linha["id"], status="produzindo")
    tarefas.registrar_evento(linha["id"], "tentativa", linha["agente"], MODELO_MAX, "Claude Code (Max) iniciou a produção")
    await atividade.ocupar(linha["agente"])
    return {"producao": {
        "tarefa_id": linha["id"], "agente": linha["agente"], "andar": linha["andar"],
        "pasta_andar": PASTAS_ANDAR.get(linha["andar"], linha["andar"].upper()),
        "texto": linha["texto"], "criada_em": linha["criada_em"],
        "historico": [dict(h) for h in tarefas.historico(linha["usuario"], linha["andar"], linha["agente"], linha["id"])],
        "anexos": _anexos_da_producao(linha["id"]),
    }, "trabalho": None}


def _anexos_da_producao(tarefa_id: int) -> list[str]:
    linha = _db().execute("SELECT caminhos FROM producao_anexos WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return json.loads(linha["caminhos"]) if linha else []


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
