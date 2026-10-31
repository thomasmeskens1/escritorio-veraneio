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
import correcoes
import max_texto
import saude
import fichas
import monday
import segredos
import tarefas
from auth import validar_token
from conexoes import gerenciador
from agents.perfis import _historico_relevante
from estado import Agente

log = logging.getLogger("veraneio.producao")

ARQUIVO_TOKEN = config.DADOS_DIR / "operador.token"
MODELO_MAX = "claude-code/max"
TIPOS_TRABALHO = {"anexo", "site", "prospeccao"}  # prospeccao: pesquisa na web do Prospectador (comercial.py)

# Pasta de cada andar dentro de "ESCRITÓRIO VERANEIO" no Drive.
PASTAS_ANDAR = {"marketing": "MARKETING", "comercial": "COMERCIAL", "porao": "PORÃO", "terreo": "TÉRREO", "cobertura": "COBERTURA"}

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
    pasta TEXT,                      -- pasta de entrega, gravada ao concluir
    link TEXT                        -- URL da pasta no Google Drive (botão "Visualizar" do chat)
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
        if "link" not in {c["name"] for c in db.execute("PRAGMA table_info(producao_info)")}:  # banco anterior
            db.execute("ALTER TABLE producao_info ADD COLUMN link TEXT")
        _esquema_criado = True
    return db


LINK_DRIVE = re.compile(r"https://drive\.google\.com/drive/folders/[\w-]{10,80}")


def link_de(tarefa_id: int) -> str | None:
    """Pasta da entrega no Google Drive (botão "Visualizar"), se a produção já foi concluída com o link."""
    linha = _db().execute("SELECT link FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return linha["link"] if linha and linha["link"] else None


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


RETENCAO_PAYLOAD_DIAS = 14  # revisão de 30/10/2026: prompts de até 80 KB ficavam para sempre no banco


def iniciar() -> None:
    token_operador()
    limite = (datetime.now(timezone.utc) - timedelta(days=RETENCAO_PAYLOAD_DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _db() as db:  # trabalhos antigos e terminados: o pedido some, o registro (tipo, status, datas) fica
        db.execute("UPDATE trabalhos_max SET payload = '{}' WHERE criado_em < ? AND payload != '{}' "
                   "AND status IN ('concluido', 'falhou', 'cancelado')", (limite,))
    # O que está "produzindo" NÃO volta para a fila no reinício do servidor: o trabalhador roda fora dele e
    # continua produzindo (antes, o painel mostrava "na fila" uma peça em produção). Se o trabalhador caiu de
    # verdade, a sobra é recuperada quando ele pede o próximo item (_retomar_orfaos).
    with _db() as db:
        # Texto, pesquisa e anexo pelo Max: quem esperava a resposta não existe mais após o reinício (antes as
        # pesquisas continuavam e gastavam até 40 min de Max para ninguém; revisão de 30/10/2026, 2.2).
        db.execute("UPDATE trabalhos_max SET status = 'cancelado', resultado = 'reinício do servidor' "
                   "WHERE tipo IN ('texto', 'prospeccao', 'anexo') AND status IN ('reservado', 'pendente', 'executando')")


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
    # Peça citada (#id): vale mesmo que outro agente de produção a tenha feito (o ajuste pode ir ao especialista do
    # formato: peça de vídeo feita pelo Criador de Imagens é ajustada pelo Editor de Vídeo).
    filtro, valores = ("AND t.id = ?", (tarefa_id,)) if tarefa_id else ("AND t.agente = ?", (agente_id,))
    linha = _db().execute(
        "SELECT t.id FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id WHERE t.usuario = ? "
        f"AND t.status = 'concluida' AND p.pasta IS NOT NULL {filtro} ORDER BY t.id DESC LIMIT 1",
        (login, *valores)).fetchone()
    return linha["id"] if linha else None


# Quem produz é o especialista do formato, não quem recebeu o pedido (Thomas, 27/10/2026): vídeo (reels, shorts, MP4,
# cenas, páginas em vídeo) = Editor de Vídeo; imagem estática = Criador de Imagens. Uma peça, um produtor.
E_VIDEO = re.compile(r"\b(reels?|shorts?|v[ií]deos?|mp4|cenas?|anima[cç][aã]o|motion|clipes?|em\s+v[ií]deo)\b",
                     re.IGNORECASE)


FORMATO_DECLARADO = re.compile(r"FORMATO DA PE[ÇC]A \(obrigat[óo]rio\):\s*([A-Z]+)")


def produtor_da_peca(texto: str, pedido: str = "") -> str:
    """"editor_video" se a peça é (ou tem partes em) vídeo; senão "criador_imagens".

    O formato declarado decide primeiro. A descrição padrão do CARROSSEL cita "vídeo", "MP4" e "Editor de Vídeo" (as
    páginas PODEM ser vídeo), e isso mandava todo carrossel ao Editor de Vídeo (teste real, #84 -> #86, 28/10/2026).
    """
    import monday  # import tardio: monday depende da produção

    texto = texto or ""
    sem_descricoes = texto
    for descricao in monday.TIPOS.values():
        sem_descricoes = sem_descricoes.replace(descricao, "")
    formato = (m.group(1) if (m := FORMATO_DECLARADO.search(texto)) else "")
    if formato in ("REELS", "SHORTS"):
        return "editor_video"
    if formato == "POST":
        return "criador_imagens"
    if formato in ("CARROSSEL", "STORIES"):  # vídeo só se o próprio pedido pedir páginas/telas em vídeo
        base = pedido or sem_descricoes
        for descricao in monday.TIPOS.values():
            base = base.replace(descricao, "")
        return "editor_video" if E_VIDEO.search(base) else "criador_imagens"
    return "editor_video" if E_VIDEO.search(sem_descricoes) else "criador_imagens"


# Tipo de entrega da peça (brainstorm de 31/10/2026, despachante-02 e criador_imagens-28): "preciso criar uma legenda
# nesse estilo" (#114) foi ao Max como arte e falhou sem PNG. Regra sem IA, só nas pontas do pedido do usuário (no meio
# de um briefing longo, "fotos" é conteúdo). Na dúvida, "visual", como antes.
SO_TEXTO = re.compile(r"\b(legendas?|textos?|copy|roteiros?|personas?|t[ií]tulos?|hashtags?|descri[cç][aã]o|"
                      r"descri[cç][oõ]es|scripts?)\b", re.IGNORECASE)
DOCUMENTO = re.compile(r"\b(docx|pptx|word|powerpoint|apresenta[cç][aã]o|apresenta[cç][oõ]es|documentos?|"
                       r"relat[oó]rios?)\b", re.IGNORECASE)
_BRIEFING_DO_GESTOR = re.compile(r"Pedido original: (.*?)\n\nResultado consolidado do Gestor", re.DOTALL)


def tipo_de_entrega(texto: str) -> str:
    """"visual" (PNG/MP4/PDF), "documento" (.docx/.pptx) ou "texto" (o texto do Max é a entrega)."""
    import encaminhamento
    from orquestrador import PEDE_ARQUIVO  # import tardio: o orquestrador importa este módulo

    texto = texto or ""
    if "FORMATO DA PEÇA" in texto:  # item do Monday: sempre peça
        return "visual"
    do_gestor = _BRIEFING_DO_GESTOR.search(texto)
    pedido = encaminhamento.pedido_original(do_gestor.group(1) if do_gestor else texto)
    linhas = [l for l in pedido.strip().splitlines() if l.strip()]
    pontas = f"{linhas[0][:300]}\n{linhas[-1][-300:]}" if linhas else ""
    if PEDE_ARQUIVO.search(pontas) or E_VIDEO.search(pontas):
        return "visual"
    if DOCUMENTO.search(pontas):
        return "documento"
    if do_gestor:  # o orquestrador já decidiu produzir (pedido de peça ou confirmação do usuário)
        return "visual"
    so_texto, peca = SO_TEXTO.search(pontas), encaminhamento.PECAS.search(pontas)
    return "texto" if so_texto and (not peca or so_texto.start() < peca.start()) else "visual"


def agente_da_peca(login: str, texto: str) -> str | None:
    """"Ajuste na peça #33: ..." pedido em qualquer chat -> agente que produziu a peça #33 (None se não for)."""
    citada = re.match(r"\s*ajuste na pe[cç]a #(\d+)", texto, re.IGNORECASE)
    linha = citada and _db().execute(
        "SELECT t.agente FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id WHERE t.id = ? AND t.usuario = ?",
        (int(citada.group(1)), login)).fetchone()
    return linha["agente"] if linha else None


def _producao_raiz(tarefa_id: int) -> int:
    """Primeira produção da cadeia de ajustes (#67 ajusta #66, que ajustou #63 -> 63): é onde fica o rascunho local.
    Antes, o ajuste de um ajuste abria um rascunho vazio e terminava sem arquivos (teste real, #67, 27/10/2026)."""
    vistos = set()
    while tarefa_id not in vistos:
        vistos.add(tarefa_id)
        linha = _db().execute("SELECT base_tarefa_id FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
        if not linha or not linha["base_tarefa_id"]:
            break
        tarefa_id = linha["base_tarefa_id"]
    return tarefa_id


def base_do_ajuste(login: str, agente_id: str, texto: str) -> int | None:
    """Pedido de ajuste ("Ajuste na peça #20: ...", "troque o título...") -> produção a ajustar; None = peça nova."""
    citada = re.search(r"#(\d+)", texto)
    generico = VERBO_GENERICO.search(texto) and not PECA_NOVA.search(texto)
    if not (citada or PEDIDO_AJUSTE.search(texto) or generico):
        return None
    return ultima_concluida(login, agente_id, int(citada.group(1)) if citada else None)


async def enfileirar(login: str, andar: str, agente: Agente, texto: str, anexos: list[str] | None = None,
                     titulo: str = "", base: int | None = None, ao_criar=None, empresa: str = "casa_veraneio") -> int:
    """`anexos`: caminhos de anexos.caminhos(). `titulo`: nome da pasta de entrega (padrão: tirado do pedido).
    `base`: produção que está sendo ajustada (mesma pasta, nova versão).
    `ao_criar(tarefa_id)`: vínculos (Monday, chat de origem) gravados ANTES de a tarefa entrar na fila; antes, o
    trabalhador podia pegá-la sem o vínculo e os criativos não voltavam ao item do Monday."""
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "complexa", empresa)
    with _db() as db:
        if base:
            titulo = _db().execute("SELECT titulo FROM producao_info WHERE tarefa_id = ?", (base,)).fetchone()["titulo"]
        db.execute("INSERT OR REPLACE INTO producao_info (tarefa_id, titulo, base_tarefa_id) VALUES (?, ?, ?)",
                   (tarefa_id, (titulo or titulo_curto(texto)).strip()[:60], base))
        if anexos:
            db.execute("INSERT OR REPLACE INTO producao_anexos (tarefa_id, caminhos) VALUES (?, ?)",
                       (tarefa_id, json.dumps(list(anexos))))
    if ao_criar:
        ao_criar(tarefa_id)
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


class Progresso(BaseModel):
    linhas: list[str] = []


_ESQUEMA_PROGRESSO = ("CREATE TABLE IF NOT EXISTS producao_progresso (tarefa_id INTEGER PRIMARY KEY, linhas TEXT NOT NULL, "
                      "atualizado_em TEXT NOT NULL)")


def progresso_de(tarefa_id: int) -> list[str]:
    """Linhas "k/n | o que está fazendo" que o Claude Code anotou nesta produção (painel de andamento)."""
    db = _db()
    db.execute(_ESQUEMA_PROGRESSO)
    linha = db.execute("SELECT linhas FROM producao_progresso WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return json.loads(linha["linhas"]) if linha else []


@rotas.post("/{tarefa_id}/progresso")
async def registrar_progresso(tarefa_id: int, progresso: Progresso, authorization: str = Header("")):
    _exigir_operador(authorization)
    linhas = [segredos.limpar(l)[:160] for l in progresso.linhas[-30:]]
    with _db() as db:
        db.execute(_ESQUEMA_PROGRESSO)
        db.execute("INSERT OR REPLACE INTO producao_progresso VALUES (?, ?, ?)",
                   (tarefa_id, json.dumps(linhas, ensure_ascii=False), _agora()))
    return {"ok": True}


class Conclusao(BaseModel):
    resumo: str
    pasta: str               # caminho relativo dentro de "ESCRITÓRIO VERANEIO"
    arquivos: list[str] = []
    link: str = ""           # pasta no Google Drive (botão "Visualizar"); vazio se o Drive ainda não sincronizou
    so_texto: bool = False   # pedido só de texto: o resumo É a entrega (sem arquivo nem pasta no Drive)


class Falha(BaseModel):
    erro: str
    texto: str = ""          # o que o Max escreveu antes de falhar (ex.: o motivo de não ter gerado o arquivo)


class Bloqueios(BaseModel):
    linhas: list[str] = []


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
        if trabalho["status"] in ("concluido", "falhou", "cancelado") or restante <= 0:
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


def cancelar_trabalho(trabalho_id: int, motivo: str) -> None:
    """Ninguém espera mais o resultado (tempo esgotado): sai da fila e, se já estiver rodando, o trabalhador encerra."""
    with _db() as db:
        db.execute("UPDATE trabalhos_max SET status = 'cancelado', resultado = ? WHERE id = ? "
                   "AND status IN ('reservado', 'pendente', 'executando')", (motivo, trabalho_id))


def _finalizar_trabalho(trabalho_id: int, status: str, resultado: str) -> dict | None:
    trabalho = obter_trabalho(trabalho_id)
    if trabalho and trabalho["status"] == "cancelado":  # terminou depois de cancelado: aceito e descartado
        return None
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
    if trabalho and trabalho["tipo"] == "anexo" and trabalho["payload"].get("anexo_id"):
        import anexos  # import tardio: anexos depende deste módulo
        anexos.salvar_descricao(trabalho["payload"]["anexo_id"], dados.resultado)
    return {"ok": True}


@rotas.get("/trabalhos/{trabalho_id}/status")
async def status_do_trabalho(trabalho_id: int, authorization: str = Header("")):
    """O trabalhador confere durante a execução se o trabalho foi cancelado (aí encerra o Claude Code)."""
    _exigir_operador(authorization)
    trabalho = obter_trabalho(trabalho_id)
    return {"status": trabalho["status"] if trabalho else "cancelado"}


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
async def proxima(sem_producao: bool = False, authorization: str = Header("")):
    """Reserva o próximo item: anexo/texto (alguém esperando) > produção > demais trabalhos. Ambos nulos = fila vazia.
    `sem_producao`: o Drive do PC está fora; o trabalhador só atende trabalhos (as peças esperam na fila)."""
    _exigir_operador(authorization)
    max_texto.registrar_contato()  # o trabalhador está ligado
    for agente in _retomar_orfaos():  # produção que ficou pela metade não prende mais o agente nem o Max
        log.warning("Produção interrompida de %s voltou para a fila.", agente)
        await atividade.liberar(agente)
    if (trabalho := _reservar_trabalho(("anexo", "texto"))):
        return {"producao": None, "trabalho": trabalho}
    if sem_producao:
        return {"producao": None, "trabalho": None}
    linha = _db().execute(
        "SELECT * FROM tarefas WHERE status = 'producao' ORDER BY id LIMIT 1").fetchone()
    if not linha:
        return {"producao": None, "trabalho": _reservar_trabalho(tuple(sorted(TIPOS_TRABALHO - {"anexo"})))}
    # Tudo montado ANTES de mudar o estado (revisão de 30/10/2026, 2.5): um erro aqui devolvia a mesma peça a cada 30 s,
    # duplicando eventos e status no Monday. Três erros seguidos: a peça falha com o motivo.
    try:
        producao = await _montar_producao(linha)
    except Exception as erro:
        log.exception("Produção %s: não foi possível montar o pedido.", linha["id"])
        _falhas_ao_montar[linha["id"]] = _falhas_ao_montar.get(linha["id"], 0) + 1
        if _falhas_ao_montar[linha["id"]] >= MAX_FALHAS_AO_MONTAR:
            _falhas_ao_montar.pop(linha["id"], None)
            tarefas.atualizar(linha["id"], status="produzindo")
            await _finalizar(linha["id"], "falhou", f"A produção não pôde ser montada: {str(erro)[:200]}", "falhou",
                             str(erro)[:300])
        return {"producao": None, "trabalho": None}
    _falhas_ao_montar.pop(linha["id"], None)
    tarefas.atualizar(linha["id"], status="produzindo")
    tarefas.registrar_evento(linha["id"], "tentativa", linha["agente"], MODELO_MAX, "Claude Code (Max) iniciou a produção")
    await atividade.ocupar(linha["agente"])
    monday.andamento(linha["id"], "produzindo")
    return {"producao": producao, "trabalho": None}


MAX_FALHAS_AO_MONTAR = 3
_falhas_ao_montar: dict[int, int] = {}


async def _montar_producao(linha) -> dict:
    info = _db().execute("SELECT * FROM producao_info WHERE tarefa_id = ?", (linha["id"],)).fetchone()
    base = info and info["base_tarefa_id"]
    pasta_base = base and _db().execute("SELECT pasta FROM producao_info WHERE tarefa_id = ?", (base,)).fetchone()
    return {
        "tarefa_id": linha["id"], "agente": linha["agente"], "andar": linha["andar"],
        "pasta_andar": PASTAS_ANDAR.get(linha["andar"], linha["andar"].upper()),
        "titulo": info["titulo"] if info else titulo_curto(linha["texto"]),
        # Ajuste: mesma pasta e mesmo rascunho local da produção ajustada.
        "base": {"tarefa_id": base, "pasta": pasta_base["pasta"], "raiz": _producao_raiz(base)} if pasta_base else None,
        "texto": linha["texto"], "criada_em": linha["criada_em"],
        # Sem conversas sobre outros Lodges (mesmo filtro do chat: perfis._historico_relevante).
        "historico": [dict(h) for h in _historico_relevante(
            tarefas.historico(linha["usuario"], linha["andar"], linha["agente"], linha["id"]), linha["texto"])],
        "anexos": _anexos_da_producao(linha["id"]),
        # Item do Monday: referências (links novos) para baixar e envio dos criativos no fim.
        "monday": bool(monday.item_da_tarefa(linha["id"])),
        "referencias": await asyncio.to_thread(monday.referencias_da_tarefa, linha["id"]),
        "fichas": await asyncio.to_thread(fichas.fichas_citadas, linha["texto"], linha["empresa"]),  # da empresa
        "empresa": linha["empresa"],  # o trabalhador escolhe manuais e acervo da empresa (nunca misturar)
        "entrega": "visual" if base else tipo_de_entrega(linha["texto"]),  # ajuste: sempre sobre a peça
        "regras": correcoes.regras_da_producao(linha["agente"], linha["empresa"]),  # correções aprovadas
    }


def _anexos_da_producao(tarefa_id: int) -> list[str]:
    linha = _db().execute("SELECT caminhos FROM producao_anexos WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    return json.loads(linha["caminhos"]) if linha else []


class Descartada(Exception):
    """A peça foi parada pelo usuário enquanto o Max produzia: a conclusão é aceita e descartada."""


async def _finalizar(tarefa_id: int, status: str, resposta: str, evento: str, detalhe: str) -> None:
    linha = tarefas.obter(tarefa_id)
    if linha and tarefas.parada(tarefa_id):  # antes: 404, e o trabalhador insistia por ~10 min com a fila parada
        raise Descartada
    if linha and linha["status"] == status:  # repetição (a resposta da 1ª chamada se perdeu): já registrado
        raise Descartada
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
    so_texto = conclusao.so_texto and not conclusao.arquivos
    with _db() as db:  # a pasta fica registrada para os ajustes desta peça (entrega só de texto: sem pasta)
        link = conclusao.link if LINK_DRIVE.fullmatch(conclusao.link or "") else None
        db.execute("UPDATE producao_info SET pasta = ?, link = ? WHERE tarefa_id = ?",
                   (None if so_texto else conclusao.pasta, link, tarefa_id))
    arquivos = "\n".join(f"- {nome}" for nome in conclusao.arquivos) or "- (nenhum arquivo listado)"
    conclusao.resumo = segredos.limpar(conclusao.resumo)  # vai ao chat e ao Monday: nunca leva chave/token
    if so_texto:  # brainstorm de 31/10/2026 (despachante-01): pedido só de texto não vira "falha sem PNG"
        resposta = f"✅ Pedido concluído pelo Claude Code (Max), entregue como texto.\n\n{conclusao.resumo.strip()}"
        local = "texto no chat"
    else:
        resposta = (f"✅ Pedido concluído pelo Claude Code (Max).\n\n{conclusao.resumo.strip()}\n\n"
                    f"Arquivos em ESCRITÓRIO VERANEIO/{conclusao.pasta}:\n{arquivos}")
        local = f"Pasta no Drive: ESCRITÓRIO VERANEIO/{conclusao.pasta}\n{arquivos}"
    try:
        await _finalizar(tarefa_id, "concluida", resposta, "concluida",
                         "entregue como texto" if so_texto else f"{len(conclusao.arquivos)} arquivo(s) em {conclusao.pasta}")
    except Descartada:
        return {"ok": True, "descartada": True}
    monday.andamento(tarefa_id, "produzida", f"🎨 {'Texto pronto' if so_texto else 'Criativos prontos'} (Claude Code)."
                                             f"\n\n{conclusao.resumo.strip()[:3000]}\n\n{local}")
    return {"ok": True}


# --- Caixa de areia: tentativas barradas (brainstorm de 31/10/2026, despachante-27) ------------------------------
# Antes a caixa barrava calada; agora cada peça com bloqueio aparece nos avisos de operação do painel da Diretoria
# (saude.avisos_da_operacao), com tarefa, usuário e item do Monday. Na primeira fase só avisa: não segura a entrega.
_ESQUEMA_BLOQUEIOS = ("CREATE TABLE IF NOT EXISTS bloqueios_caixa (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                      "tarefa_id INTEGER NOT NULL, em TEXT NOT NULL, linhas TEXT NOT NULL)")
JANELA_BLOQUEIOS = timedelta(hours=24)


def bloqueios_recentes() -> list[dict]:
    """Peças com tentativa barrada nas últimas 24 h: tarefa, usuário, item do Monday, quantidade e a primeira linha."""
    db = _db()
    db.execute(_ESQUEMA_BLOQUEIOS)
    desde = (datetime.now(timezone.utc) - JANELA_BLOQUEIOS).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = db.execute("SELECT b.tarefa_id, b.linhas, t.usuario FROM bloqueios_caixa b LEFT JOIN tarefas t "
                        "ON t.id = b.tarefa_id WHERE b.em >= ? ORDER BY b.id", (desde,)).fetchall()
    return [{"tarefa_id": l["tarefa_id"], "usuario": l["usuario"] or "?", "monday": monday.item_da_tarefa(l["tarefa_id"]),
             "total": len(json.loads(l["linhas"])), "exemplo": (json.loads(l["linhas"]) or [""])[0]} for l in linhas]


@rotas.post("/{tarefa_id}/bloqueios")
async def registrar_bloqueios(tarefa_id: int, dados: Bloqueios, authorization: str = Header("")):
    _exigir_operador(authorization)
    linhas = [segredos.limpar(l)[:200] for l in dados.linhas[-50:] if l.strip()]
    if not linhas:
        return {"ok": True}
    with _db() as db:
        db.execute(_ESQUEMA_BLOQUEIOS)
        db.execute("INSERT INTO bloqueios_caixa (tarefa_id, em, linhas) VALUES (?, ?, ?)",
                   (tarefa_id, _agora(), json.dumps(linhas, ensure_ascii=False)))
    linha = tarefas.obter(tarefa_id)
    tarefas.registrar_evento(tarefa_id, "bloqueio_caixa", linha["agente"] if linha else None, MODELO_MAX,
                             f"{len(linhas)} tentativa(s) barrada(s) pela caixa de areia: {linhas[0]}")
    log.warning("Produção %s: a caixa de areia barrou %s tentativa(s): %s", tarefa_id, len(linhas), linhas[0])
    return {"ok": True}


@rotas.post("/{tarefa_id}/devolver")
async def devolver(tarefa_id: int, falha: Falha, authorization: str = Header("")):
    """Max sem cota (ou deslogado) no meio da peça: ela volta para a fila em vez de virar falha e o Max sai da rota
    até a janela voltar (revisão de 30/10/2026: 5 peças da fila falhavam em 1 minuto quando a cota acabava)."""
    _exigir_operador(authorization)
    linha = tarefas.obter(tarefa_id)
    if not linha or linha["status"] != "produzindo":
        raise HTTPException(status_code=404, detail="Produção não encontrada")
    erro = segredos.limpar(falha.erro)[:300]
    tarefas.atualizar(tarefa_id, status="producao")
    tarefas.registrar_evento(tarefa_id, "adiada", linha["agente"], MODELO_MAX,
                             f"Max sem cota agora; a peça voltou para a fila ({erro})")
    saude.registrar_falha(MODELO_MAX, erro)
    await atividade.liberar(linha["agente"])
    monday.andamento(tarefa_id, "adiada")  # item do Monday volta para "Na fila"
    return {"ok": True}


@rotas.post("/{tarefa_id}/falhar")
async def falhar(tarefa_id: int, falha: Falha, authorization: str = Header("")):
    _exigir_operador(authorization)
    falha.erro = segredos.limpar(falha.erro)
    motivo = f"A produção pelo Claude Code (Max) falhou: {falha.erro[:300]}"
    if (texto := segredos.limpar(falha.texto or "").strip()):  # o motivo nas palavras do Max (despachante-01)
        motivo += f"\n\nO que o Max escreveu:\n{texto[:1500]}"
    try:
        await _finalizar(tarefa_id, "falhou", motivo, "falhou", falha.erro[:300])
    except Descartada:
        return {"ok": True, "descartada": True}
    monday.andamento(tarefa_id, "falhou", motivo)
    return {"ok": True}
