"""Anexos do chat: imagens (PNG, JPG, WEBP) e PDF enviados junto com a mensagem.

Upload por POST /api/anexos (multipart, campo `arquivos`), arquivos em dados/anexos/<id>.<ext>.
Antes da tarefa rodar, `descrever()` transforma cada anexo em texto para o contexto do agente:
  - dono do plano Max -> o Claude Code (Max) do PC dele lê o arquivo (trabalho "anexo" na fila);
  - demais usuários   -> Haiku pela API da Anthropic (imagem/PDF em base64).
"""

import asyncio
import base64
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

import config
import producao
import tarefas
from auth import validar_token

log = logging.getLogger("veraneio.anexos")

BACKEND_DIR = config.ARQUIVO_BANCO.parent.parent  # backend/ (caminhos gravados são relativos a ela)
PASTA = BACKEND_DIR / "dados" / "anexos"
TAMANHO_MAX = 15 * 1024 * 1024
MAX_POR_MENSAGEM = 4
TEMPO_MAX_DONO = 180          # segundos esperando o Claude Code do PC do dono
LADO_MAX_API = 1568           # imagens maiores são reduzidas antes de ir para a API
TAMANHO_MAX_IMAGEM_API = 3_700_000  # ~5 MB em base64 (limite da API)

# mime -> extensões aceitas (a primeira é a usada no disco)
TIPOS = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
    "application/pdf": (".pdf",),
}
_ID_VALIDO = re.compile(r"^[0-9a-f]{12}$")

PROMPT_DESCRICAO = (
    "Descreva este anexo enviado por um usuário do Escritório Veraneio (equipe da Casa Veraneio, empresa de "
    "lodges e casas de temporada). Responda em português do Brasil, de forma objetiva, em até 12 linhas, "
    "sem introdução.\n"
    "- Imagem: o que aparece (ambiente, produto, pessoas, objetos), cores predominantes, estilo e "
    "enquadramento; transcreva entre aspas todo texto visível.\n"
    "- PDF: resumo do conteúdo e os dados importantes (preços, datas, nomes, endereços, quantidades, "
    "condições, contatos).\n"
    "Não invente nada que não esteja no arquivo."
)

rotas = APIRouter(prefix="/api/anexos")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS anexos (
    id TEXT PRIMARY KEY,
    usuario TEXT NOT NULL,
    nome_original TEXT NOT NULL,
    mime TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    caminho TEXT NOT NULL,           -- relativo a backend/ (ex.: dados/anexos/ab12cd34ef56.png)
    descricao TEXT,
    status TEXT NOT NULL,            -- pendente | descrito | falhou
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anexos_usuario ON anexos(usuario);
"""
_esquema_criado = False


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def _tipo_pelo_conteudo(inicio: bytes) -> str | None:
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "image/webp"
    if inicio.lstrip(b"\r\n\t ").startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _nome_seguro(nome: str) -> str:
    nome = Path(nome or "arquivo").name.replace("\\", "/").split("/")[-1]
    nome = re.sub(r"[\x00-\x1f<>:\"|?*]", "", nome).strip() or "arquivo"
    return nome[:120]


def _absoluto(caminho: str) -> Path:
    return BACKEND_DIR / caminho


# --- Rotas -------------------------------------------------------------------------------

@rotas.post("")
async def enviar_anexos(arquivos: list[UploadFile] = File(...), authorization: str = Header("")):
    """Valida tudo antes de gravar: ou entram todos, ou nenhum."""
    usuario = _usuario(authorization)
    if not arquivos:
        raise HTTPException(status_code=422, detail="Nenhum arquivo enviado.")
    if len(arquivos) > MAX_POR_MENSAGEM:
        raise HTTPException(status_code=422, detail=f"Envie no máximo {MAX_POR_MENSAGEM} arquivos por mensagem.")

    validados = []
    for arquivo in arquivos:
        nome = _nome_seguro(arquivo.filename)
        conteudo = await arquivo.read(TAMANHO_MAX + 1)
        if len(conteudo) > TAMANHO_MAX:
            raise HTTPException(status_code=413, detail=f"{nome}: o limite é 15 MB por arquivo.")
        if not conteudo:
            raise HTTPException(status_code=422, detail=f"{nome}: arquivo vazio.")
        mime = _tipo_pelo_conteudo(conteudo[:16])
        extensao = Path(nome).suffix.lower()
        if not mime or extensao not in TIPOS[mime]:
            raise HTTPException(status_code=415, detail=f"{nome}: envie apenas imagens PNG, JPG, WEBP ou PDF.")
        validados.append((nome, mime, conteudo))

    PASTA.mkdir(parents=True, exist_ok=True)
    criados = []
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for nome, mime, conteudo in validados:
        anexo_id = uuid.uuid4().hex[:12]
        relativo = f"dados/anexos/{anexo_id}{TIPOS[mime][0]}"
        _absoluto(relativo).write_bytes(conteudo)
        with _db() as db:
            db.execute("INSERT INTO anexos (id, usuario, nome_original, mime, tamanho, caminho, status, criado_em) "
                       "VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?)",
                       (anexo_id, usuario["sub"], nome, mime, len(conteudo), relativo, agora))
        criados.append({"id": anexo_id, "nome": nome, "mime": mime, "tamanho": len(conteudo)})
    return criados


@rotas.get("/{anexo_id}")
def servir_anexo(anexo_id: str, authorization: str = Header("")):
    """Arquivo original (miniaturas do chat). Só o dono do anexo ou a diretoria."""
    usuario = _usuario(authorization)
    linha = _db().execute("SELECT * FROM anexos WHERE id = ?", (anexo_id,)).fetchone() \
        if _ID_VALIDO.match(anexo_id) else None
    if not linha or (linha["usuario"] != usuario["sub"] and usuario.get("role") != "diretoria"):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    caminho = _absoluto(linha["caminho"])
    if not caminho.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do anexo não encontrado")
    return FileResponse(caminho, media_type=linha["mime"], filename=linha["nome_original"],
                        content_disposition_type="inline", headers={"Cache-Control": "private, max-age=3600"})


# --- Uso pelo coordenador ----------------------------------------------------------------

def _linhas(ids: list[str], login: str | None = None) -> list:
    """Anexos na ordem pedida; ids inválidos/de outro usuário são ignorados."""
    ids = [i for i in dict.fromkeys(str(i) for i in ids or []) if _ID_VALIDO.match(i)][:MAX_POR_MENSAGEM]
    if not ids:
        return []
    marcadores = ",".join("?" * len(ids))
    linhas = {l["id"]: l for l in _db().execute(f"SELECT * FROM anexos WHERE id IN ({marcadores})", ids)}
    return [linhas[i] for i in ids if i in linhas and (login is None or linhas[i]["usuario"] == login)]


def caminhos(ids: list[str]) -> list[str]:
    """Caminhos relativos a backend/ (ex.: dados/anexos/ab12cd34ef56.png), para a produção PNG/MP4."""
    return [linha["caminho"] for linha in _linhas(ids)]


def salvar_descricao(anexo_id: str, descricao: str, status: str = "descrito") -> None:
    with _db() as db:
        db.execute("UPDATE anexos SET descricao = ?, status = ? WHERE id = ?",
                   (descricao.strip()[:4000], status, anexo_id))


def _tamanho_legivel(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


async def descrever(ids: list[str], login: str) -> str:
    """Bloco de texto com a descrição de cada anexo do usuário ("" se não houver anexos válidos)."""
    linhas = _linhas(ids, login)
    if not linhas:
        return ""
    pelo_max = login == config.DONO_MAX
    descricoes = await asyncio.gather(*(
        _descricao(linha, pelo_max) for linha in linhas), return_exceptions=True)
    partes = ["Anexos enviados pelo usuário:"]
    for n, (linha, descricao) in enumerate(zip(linhas, descricoes), start=1):
        if isinstance(descricao, BaseException):
            log.warning("Falha ao descrever o anexo %s: %s", linha["id"], descricao)
            descricao = "(não foi possível ler o conteúdo deste anexo)"
        tipo = "PDF" if linha["mime"] == "application/pdf" else "imagem"
        arquivo = Path(linha["caminho"]).name
        partes.append(f"[{n}] {linha['nome_original']} ({tipo}, {_tamanho_legivel(linha['tamanho'])}, "
                      f"arquivo {arquivo}) — {descricao.strip()}")
    return "\n".join(partes)


async def _descricao(linha, pelo_max: bool) -> str:
    if linha["status"] == "descrito" and linha["descricao"]:
        return linha["descricao"]
    if pelo_max:
        return await _descrever_pelo_max(linha)
    try:
        texto = await _descrever_pela_api(linha)
    except Exception as erro:
        salvar_descricao(linha["id"], f"Falha: {erro}"[:300], "falhou")
        raise
    salvar_descricao(linha["id"], texto)
    return texto


async def _descrever_pelo_max(linha) -> str:
    trabalho_id = producao.trabalho_em_aberto("anexo", "anexo_id", linha["id"]) or await producao.criar_trabalho(
        "anexo", {"anexo_id": linha["id"], "arquivo": linha["caminho"], "nome": linha["nome_original"],
                  "mime": linha["mime"], "prompt": PROMPT_DESCRICAO})
    trabalho = await producao.aguardar_trabalho(trabalho_id, TEMPO_MAX_DONO)
    if trabalho["status"] == "concluido" and trabalho.get("resultado"):
        return trabalho["resultado"]  # já salvo em anexos.descricao pela rota de conclusão
    if trabalho["status"] == "falhou":
        salvar_descricao(linha["id"], f"Falha: {trabalho.get('resultado') or ''}"[:300], "falhou")
        return "(o Claude Code não conseguiu ler este anexo)"
    return ("(descrição ainda indisponível: o Claude Code (Max) do PC do Thomas não respondeu a tempo; "
            "considere o anexo pelo nome e pelo pedido)")


# --- API da Anthropic (Haiku) --------------------------------------------------------------

def _cliente_anthropic():
    """Separado para os testes poderem substituir."""
    import anthropic
    return anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


def _imagem_para_api(dados: bytes, mime: str) -> tuple[bytes, str]:
    """Reduz imagens grandes (limite de tamanho da API e economia de tokens)."""
    try:
        from PIL import Image
    except ImportError:
        return dados, mime
    with Image.open(io.BytesIO(dados)) as imagem:
        if max(imagem.size) <= LADO_MAX_API and len(dados) <= TAMANHO_MAX_IMAGEM_API:
            return dados, mime
        imagem.thumbnail((LADO_MAX_API, LADO_MAX_API))
        saida = io.BytesIO()
        imagem.convert("RGB").save(saida, "JPEG", quality=85)
        return saida.getvalue(), "image/jpeg"


async def _descrever_pela_api(linha) -> str:
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada")
    if not tarefas.api_liberada():  # o orçamento do mês vale também para a leitura de anexos
        raise RuntimeError("orçamento da API pausado")
    dados = await asyncio.to_thread(_absoluto(linha["caminho"]).read_bytes)
    if linha["mime"] == "application/pdf":
        bloco = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.b64encode(dados).decode()}}
    else:
        dados, mime = await asyncio.to_thread(_imagem_para_api, dados, linha["mime"])
        bloco = {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": base64.b64encode(dados).decode()}}
    modelo = config.MODELO_FILA_PADRAO.split("/", 1)[-1]
    resposta = await _cliente_anthropic().messages.create(
        model=modelo, max_tokens=700,
        messages=[{"role": "user", "content": [bloco, {"type": "text", "text": PROMPT_DESCRICAO}]}],
    )
    tarefas.registrar_gasto(None, "anexos", config.MODELO_FILA_PADRAO, tarefas.custo_estimado(
        config.MODELO_FILA_PADRAO, resposta.usage.input_tokens, resposta.usage.output_tokens))
    texto = "".join(getattr(b, "text", "") for b in resposta.content).strip()
    if not texto:
        raise RuntimeError("Resposta vazia do modelo")
    return texto
