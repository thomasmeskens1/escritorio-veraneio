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
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import atividade
import config
import max_texto
import monday
import segredos
import tarefas
from auth import validar_token
from conexoes import gerenciador
from estado import Agente

log = logging.getLogger("veraneio.producao")

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
CREATE TABLE IF NOT EXISTS producao_info (
    tarefa_id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,            -- nome da pasta de entrega (ex.: "Post Réveillon Lodge 1")
    base_tarefa_id INTEGER,          -- ajuste: a produção que está sendo ajustada (mesma pasta, nova versão)
    pasta TEXT                       -- pasta de entrega, gravada ao concluir
);
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
    # Item interrompido por reinício volta para a fila. O trabalhador pode continuar produzindo mesmo assim
    # (ele roda fora do servidor): por isso a conclusão também é aceita em "producao" (ver _finalizar).
    with _db() as db:
        db.execute("UPDATE tarefas SET status = 'producao' WHERE status = 'produzindo'")
        # Texto pelo Max: quem esperava a resposta não existe mais após o reinício.
        db.execute("UPDATE trabalhos_max SET status = 'falhou', resultado = 'reinício do servidor' "
                   "WHERE tipo = 'texto' AND status IN ('reservado', 'pendente', 'executando')")
        db.execute("UPDATE trabalhos_max SET status = 'pendente' WHERE status = 'executando'")


_VERBOS_INICIAIS = re.compile(
    r"^(?:(?:por favor|pfv|quero|preciso de|gostaria de|crie|criar|cria|fa[cç]a|fazer|produza|produzir|gere|gerar|"
    r"monte|montar|desenvolva|elabore|me|uma?|o|a|os|as)\s+)+", re.IGNORECASE)
_LIGACOES = {"de", "do", "da", "dos", "das", "para", "com", "e", "em", "no", "na", "o", "a", "ao", "à"}
# Ajuste explícito ("ajuste...", "corrija...") ou verbo genérico ("troque o título...") sem cara de peça nova.
PEDIDO_AJUSTE = re.compile(r"^\s*(ajuste|ajustes|ajustar|altere|alterar|corrija|corrigir|refa[cç]a)\b", re.IGNORECASE)
VERBO_GENERICO = re.compile(r"^\s*(troque|trocar|mude|mudar|aumente|diminua|tire|remova|coloque|substitua|deixe)\b",
                            re.IGNORECASE)
# "Coloque o Lodge 12 num stories de boas-vindas" é peça nova, não ajuste da anterior.
PECA_NOVA = re.compile(r"\b(posts?|stories|story|reels?|carross[eé]is|carrossel|shorts|v[ií]deo|lodges?\s*\d+)\b",
                       re.IGNORECASE)


def titulo_curto(texto: str) -> str:
    """Título da pasta a partir do pedido: "Crie a arte do post de Réveillon do Lodge 1" -> "Arte Post Réveillon Lodge 1"."""
    limpo = re.sub(r"[^\wÀ-ÿ\s#-]", " ", texto.splitlines()[0] if texto.strip() else "Produção")
    palavras = [p for p in _VERBOS_INICIAIS.sub("", limpo.strip()).split() if p.lower() not in _LIGACOES][:6]
    return " ".join(p[:1].upper() + p[1:] for p in palavras)[:60] or "Produção"


def ultima_concluida(login: str, agente_id: str, tarefa_id: int | None = None) -> int | None:
    """Produção concluída a ajustar: a citada (#id) ou a mais recente deste usuário com este agente."""
    filtro, valores = ("AND t.id = ?", (tarefa_id,)) if tarefa_id else ("", ())
    linha = _db().execute(
        "SELECT t.id FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id WHERE t.usuario = ? AND t.agente = ? "
        f"AND t.status = 'concluida' AND p.pasta IS NOT NULL {filtro} ORDER BY t.id DESC LIMIT 1",
        (login, agente_id, *valores)).fetchone()
    return linha["id"] if linha else None


def agente_da_peca(login: str, texto: str) -> str | None:
    """"Ajuste na peça #33: ..." pedido em qualquer chat -> agente que produziu a peça #33 (None se não for)."""
    citada = re.match(r"\s*ajuste na pe[cç]a #(\d+)", texto, re.IGNORECASE)
    linha = citada and _db().execute(
        "SELECT t.agente FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id WHERE t.id = ? AND t.usuario = ?",
        (int(citada.group(1)), login)).fetchone()
    return linha["agente"] if linha else None


def base_do_ajuste(login: str, agente_id: str, texto: str) -> int | None:
    """Pedido de ajuste ("Ajuste na peça #20: ...", "troque o título...") -> produção a ajustar; None = peça nova."""
    citada = re.search(r"#(\d+)", texto)
    generico = VERBO_GENERICO.search(texto) and not PECA_NOVA.search(texto)
    if not (citada or PEDIDO_AJUSTE.search(texto) or generico):
        return None
    return ultima_concluida(login, agente_id, int(citada.group(1)) if citada else None)


async def enfileirar(login: str, andar: str, agente: Agente, texto: str, anexos: list[str] | None = None,
                     titulo: str = "", base: int | None = None) -> int:
    """`anexos`: caminhos de anexos.caminhos(). `titulo`: nome da pasta de entrega (padrão: tirado do pedido).
    `base`: produção que está sendo ajustada (mesma pasta, nova versão)."""
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "complexa")
    with _db() as db:
        if base:
            titulo = _db().execute("SELECT titulo FROM producao_info WHERE tarefa_id = ?", (base,)).fetchone()["titulo"]
        db.execute("INSERT OR REPLACE INTO producao_info (tarefa_id, titulo, base_tarefa_id) VALUES (?, ?, ?)",
                   (tarefa_id, (titulo or titulo_curto(texto)).strip()[:60], base))
        if anexos:
            db.execute("INSERT OR REPLACE INTO producao_anexos (tarefa_id, caminhos) VALUES (?, ?)",
                       (tarefa_id, json.dumps(list(anexos))))
    tarefas.atualizar(tarefa_id, status="producao")
    detalhe = f"Ajuste da produção #{base}" if base else "Produção de arquivo pelo Claude Code (Max)"
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe=detalhe)
    await gerenciador.enviar_para_usuario(login, {
        "tipo": "tarefa_adiada", "andar": andar, "agente": agente.id, "tarefa_id": tarefa_id,
        "texto": (f"Ajuste da peça #{base} enviado ao Claude Code (Max): ele parte da versão anterior e salva a "
                  "nova versão na mesma pasta." if base else
                  "Pedido enviado ao Claude Code (Max) para produção. Você recebe aqui o aviso quando terminar."),
    })
    return tarefa_id


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
    dados.resultado = segredos.limpar(dados.resultado)  # o que o Max devolve nunca leva chave/token adiante
    trabalho = _finalizar_trabalho(trabalho_id, "concluido", dados.resultado)
    if trabalho["tipo"] == "anexo" and trabalho["payload"].get("anexo_id"):
        import anexos  # import tardio: anexos depende deste módulo
        anexos.salvar_descricao(trabalho["payload"]["anexo_id"], dados.resultado)
    return {"ok": True}


@rotas.post("/trabalhos/{trabalho_id}/falhar")
async def falhar_trabalho(trabalho_id: int, falha: Falha, authorization: str = Header("")):
    _exigir_operador(authorization)
    _finalizar_trabalho(trabalho_id, "falhou", segredos.limpar(falha.erro[:500]))
    return {"ok": True}


# --- Fila do trabalhador -----------------------------------------------------------------

def _retomar_orfaos() -> list[str]:
    """O trabalhador é instância única e só pede a fila quando está livre: o que ainda consta "em produção" ou
    "executando" é sobra de uma execução que caiu (PC reiniciado, processo encerrado). Volta para a fila; texto
    (alguém esperava a resposta) falha. Reservas de texto paradas há mais de 30 min também são liberadas.
    Devolve os agentes que estavam presos em "trabalhando"."""
    limite = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _db() as db:
        presos = [l["agente"] for l in db.execute("SELECT agente FROM tarefas WHERE status = 'produzindo'")]
        db.execute("UPDATE tarefas SET status = 'producao' WHERE status = 'produzindo'")
        db.execute("UPDATE trabalhos_max SET status = 'falhou', resultado = 'o trabalhador reiniciou' "
                   "WHERE tipo = 'texto' AND (status = 'executando' OR (status = 'reservado' AND criado_em < ?))",
                   (limite,))
        db.execute("UPDATE trabalhos_max SET status = 'pendente' WHERE status = 'executando'")
    return presos


@rotas.get("/proxima")
async def proxima(authorization: str = Header("")):
    """Reserva o próximo item: anexo/texto (alguém esperando) > produção > demais trabalhos. Ambos nulos = fila vazia."""
    _exigir_operador(authorization)
    max_texto.registrar_contato()  # o trabalhador está ligado
    for agente in _retomar_orfaos():  # produção que ficou pela metade não prende mais o agente nem o Max
        log.warning("Produção interrompida de %s voltou para a fila.", agente)
        await atividade.liberar(agente)
    if (trabalho := _reservar_trabalho(("anexo", "texto"))):
        return {"producao": None, "trabalho": trabalho}
    linha = _db().execute(
        "SELECT * FROM tarefas WHERE status = 'producao' ORDER BY id LIMIT 1").fetchone()
    if not linha:
        return {"producao": None, "trabalho": _reservar_trabalho(tuple(sorted(TIPOS_TRABALHO - {"anexo"})))}
    tarefas.atualizar(linha["id"], status="produzindo")
    tarefas.registrar_evento(linha["id"], "tentativa", linha["agente"], MODELO_MAX, "Claude Code (Max) iniciou a produção")
    await atividade.ocupar(linha["agente"])
    monday.andamento(linha["id"], "produzindo")
    info = _db().execute("SELECT * FROM producao_info WHERE tarefa_id = ?", (linha["id"],)).fetchone()
    base = info and info["base_tarefa_id"]
    pasta_base = base and _db().execute("SELECT pasta FROM producao_info WHERE tarefa_id = ?", (base,)).fetchone()
    return {"producao": {
        "tarefa_id": linha["id"], "agente": linha["agente"], "andar": linha["andar"],
        "pasta_andar": PASTAS_ANDAR.get(linha["andar"], linha["andar"].upper()),
        "titulo": info["titulo"] if info else titulo_curto(linha["texto"]),
        # Ajuste: mesma pasta e mesmo rascunho local da produção ajustada.
        "base": {"tarefa_id": base, "pasta": pasta_base["pasta"]} if pasta_base else None,
        "texto": linha["texto"], "criada_em": linha["criada_em"],
        "historico": [dict(h) for h in tarefas.historico(linha["usuario"], linha["andar"], linha["agente"], linha["id"])],
        "anexos": _anexos_da_producao(linha["id"]),
        # Item do Monday: referências (links novos) para baixar e envio dos criativos no fim.
        "monday": bool(monday.item_da_tarefa(linha["id"])),
        "referencias": await asyncio.to_thread(monday.referencias_da_tarefa, linha["id"]),
    }, "trabalho": None}


def _anexos_da_producao(tarefa_id: int) -> list[str]:
    linha = _db().execute("SELECT caminhos FROM producao_anexos WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return json.loads(linha["caminhos"]) if linha else []


async def _finalizar(tarefa_id: int, status: str, resposta: str, evento: str, detalhe: str) -> None:
    linha = tarefas.obter(tarefa_id)
    if not linha or linha["status"] not in ("produzindo", "producao"):
        raise HTTPException(status_code=404, detail="Produção não encontrada")
    criada = datetime.strptime(linha["criada_em"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    campos = {"status": status, "modelo": MODELO_MAX,
              "tempo_segundos": (datetime.now(timezone.utc) - criada).total_seconds()}
    campos["resposta" if status == "concluida" else "motivo"] = resposta
    tarefas.atualizar(tarefa_id, **campos)
    tarefas.registrar_evento(tarefa_id, evento, linha["agente"], MODELO_MAX, detalhe)
    await atividade.liberar(linha["agente"])

    from orquestrador import _entregar, entregar_na_origem  # entrega no chat (ou na próxima conexão do usuário)
    linha = tarefas.obter(tarefa_id)
    await _entregar(linha)
    await entregar_na_origem(linha)  # e no chat onde o usuário pediu, se foi em outro


@rotas.post("/{tarefa_id}/concluir")
async def concluir(tarefa_id: int, conclusao: Conclusao, authorization: str = Header("")):
    _exigir_operador(authorization)
    with _db() as db:  # a pasta fica registrada para os ajustes desta peça
        db.execute("UPDATE producao_info SET pasta = ? WHERE tarefa_id = ?", (conclusao.pasta, tarefa_id))
    arquivos = "\n".join(f"- {nome}" for nome in conclusao.arquivos) or "- (nenhum arquivo listado)"
    conclusao.resumo = segredos.limpar(conclusao.resumo)  # vai ao chat e ao Monday: nunca leva chave/token
    resposta = (f"✅ Pedido concluído pelo Claude Code (Max).\n\n{conclusao.resumo.strip()}\n\n"
                f"Arquivos em ESCRITÓRIO VERANEIO/{conclusao.pasta}:\n{arquivos}")
    await _finalizar(tarefa_id, "concluida", resposta, "concluida",
                     f"{len(conclusao.arquivos)} arquivo(s) em {conclusao.pasta}")
    monday.andamento(tarefa_id, "produzida", f"🎨 Criativos prontos (Claude Code).\n\n{conclusao.resumo.strip()[:3000]}"
                                             f"\n\nPasta no Drive: ESCRITÓRIO VERANEIO/{conclusao.pasta}\n{arquivos}")
    return {"ok": True}


@rotas.post("/{tarefa_id}/falhar")
async def falhar(tarefa_id: int, falha: Falha, authorization: str = Header("")):
    _exigir_operador(authorization)
    falha.erro = segredos.limpar(falha.erro)
    motivo = f"A produção pelo Claude Code (Max) falhou: {falha.erro[:300]}"
    await _finalizar(tarefa_id, "falhou", motivo, "falhou", falha.erro[:300])
    monday.andamento(tarefa_id, "falhou", motivo)
    return {"ok": True}
