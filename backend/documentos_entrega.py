"""Documento como anexo da resposta (Onda 3, item 8): a planilha do catálogo pelo chat do Cérebro e o .docx do estudo
do Estrategista e do plano/relatório do Gestor de Tráfego.

O arquivo vira um anexo do dono do pedido (dados/anexos, mesma tabela e mesma rota das miniaturas do chat, como a folha
de aprovação da Onda 2) e aparece junto com a resposta. A rota de anexos só entrega ao dono ou à Diretoria, então o
documento com dado financeiro (decisão 12) fica com quem já via aquilo no chat. Tudo em código: nada vai a modelo
nenhum, e a descrição do anexo já nasce gravada (se a pessoa reenviar o arquivo, nenhuma IA o lê).

Drive: a API não enxerga o Drive (só o PC do trabalhador do Max). Gravar em ESCRITÓRIO VERANEIO/<andar>/ fica para
quando houver a montagem (ver relatório da Onda 3); a pasta FINAL é da produção do Max e não é usada aqui.
"""

import logging
import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

import anexos
import cerebro_imoveis as imoveis
import documentos
import empresas
import tarefas

log = logging.getLogger(__name__)

rotas = APIRouter(prefix="/api/documentos")

_ESQUEMA = ("CREATE TABLE IF NOT EXISTS anexos_resposta (tarefa_id INTEGER NOT NULL, anexo_id TEXT NOT NULL, "
            "PRIMARY KEY (tarefa_id, anexo_id))")
_pronto = False
EXTENSOES = {documentos.MIME_XLSX: ".xlsx", documentos.MIME_DOCX: ".docx"}

# "planilha do catálogo", "me manda em Excel a lista de Lodges com piscina", "xlsx dos imóveis"
PEDE_PLANILHA = re.compile(r"\b(planilhas?|excel|xlsx)\b", re.I)
FALA_DE_CATALOGO = re.compile(r"\b(cat[aá]logo|lodges?|casas|im[oó]veis|propriedades)\b", re.I)
# Gestor de Tráfego: plano/relatório de campanha. Estrategista: estudo (pela web) ou pedido explícito de documento.
PEDE_DOCUMENTO = re.compile(r"\b(documento|docx|word|arquivo)\b", re.I)
PLANO_TRAFEGO = re.compile(r"\b(plano|campanhas?|relat[oó]rio|estrutura|conjuntos?|p[uú]blicos?|utms?)\b", re.I)
MIN_CARACTERES = 1200  # resposta curta (pergunta, conversa) não vira documento
FORMULARIO = re.compile(r"<<FORMULARIO>>.*?<<FIM DO FORMULARIO>>", re.S)
TEM_VALOR = re.compile(r"R\$\s?\d|\b(receita|faturamento|roas|roi|cac|ltv|investimento)\b", re.I)


def _db():
    global _pronto
    db = anexos._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def _nome_arquivo(*partes: str, extensao: str) -> str:
    nome = " - ".join(re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", p).strip() for p in partes if p and p.strip())
    return anexos._nome_seguro(re.sub(r"\s+", " ", nome)[:110] + extensao)


def anexar(tarefa_id: int, conteudo: bytes, nome: str, mime: str, descricao: str) -> str:
    """Grava o arquivo como anexo do dono da tarefa e o liga à resposta; devolve o id do anexo."""
    linha = tarefas.obter(tarefa_id)
    if not linha:
        raise ValueError(f"tarefa {tarefa_id} não existe")
    if not conteudo or len(conteudo) > anexos.TAMANHO_MAX:
        raise ValueError("documento vazio ou maior que 15 MB")
    anexo_id = uuid.uuid4().hex[:12]
    relativo = f"dados/anexos/{anexo_id}{EXTENSOES[mime]}"
    anexos.PASTA.mkdir(parents=True, exist_ok=True)
    anexos._absoluto(relativo).write_bytes(conteudo)
    with _db() as db:
        db.execute("INSERT INTO anexos (id, usuario, nome_original, mime, tamanho, caminho, descricao, status, "
                   "criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, 'descrito', ?)",
                   (anexo_id, linha["usuario"], anexos._nome_seguro(nome), mime, len(conteudo), relativo,
                    descricao[:4000], tarefas._agora()))
        db.execute("INSERT OR IGNORE INTO anexos_resposta (tarefa_id, anexo_id) VALUES (?, ?)", (tarefa_id, anexo_id))
    return anexo_id


def de(tarefa_id: int) -> list[dict]:
    """Documentos da resposta (no formato dos anexos do chat) ou []."""
    linhas = _db().execute("SELECT a.id, a.nome_original, a.mime, a.tamanho FROM anexos_resposta d JOIN anexos a "
                           "ON a.id = d.anexo_id WHERE d.tarefa_id = ? ORDER BY a.criado_em", (tarefa_id,)).fetchall()
    return [{"id": l["id"], "nome": l["nome_original"], "mime": l["mime"], "tamanho": l["tamanho"]} for l in linhas]


# --- Planilha do catálogo (cerebro-21) ------------------------------------------------------------------

def pede_planilha(texto: str) -> bool:
    return bool(PEDE_PLANILHA.search(texto or "") and FALA_DE_CATALOGO.search(texto or "")
                and not imoveis.UM_IMOVEL.search(texto or ""))


def planilha_do_catalogo(texto: str, empresa: str) -> tuple[bytes, dict, str] | None:
    """(bytes do .xlsx, resultado do filtro, descrição do filtro); None se a empresa não tem tabela ou está vazia.
    Os filtros do pedido ("com piscina", "para 16 pessoas") valem também para a planilha."""
    filtros = (imoveis.interpretar(texto, empresa) or {}) if empresa in imoveis.ORIGENS and texto else {}
    chaves = ("cidade", "uf", "suites_min", "quartos_min", "pessoas_min", "pessoas_max", "comodidade", "orlando")
    resultado = imoveis.filtrar(empresa, **{k: filtros[k] for k in chaves if k in filtros})
    if not resultado or not resultado["total_base"]:
        return None
    filtro = imoveis._descricao(filtros)
    return documentos.planilha(resultado, filtro), resultado, filtro


def planilha_no_chat(tarefa_id: int, texto: str, empresa: str) -> str | None:
    """Pedido de planilha no chat do Cérebro: gera o .xlsx, anexa à resposta e devolve o resumo em 3 linhas.
    None se o pedido não é de planilha (segue o caminho normal)."""
    if not pede_planilha(texto):
        return None
    if empresa not in imoveis.ORIGENS:
        return (f"A planilha do catálogo da {empresas.nome(empresa)} ainda não está pronta: por enquanto só a Casa "
                "Veraneio tem a tabela de imóveis. Corporativo e Casa Vero entram na próxima etapa.")
    pronta = planilha_do_catalogo(texto, empresa)
    if not pronta:
        return None  # tabela vazia (coleta ainda não chegou): a busca normal responde
    conteudo, resultado, filtro = pronta
    rotulo = imoveis.ROTULO[empresa]
    nome = _nome_arquivo(documentos.hoje().replace("/", "-"), f"Catálogo {empresas.nome(empresa)}", filtro,
                         extensao=".xlsx")
    anexar(tarefa_id, conteudo, nome, documentos.MIME_XLSX,
           f"Planilha do catálogo da {empresas.nome(empresa)} ({resultado['total']} {rotulo}s, coleta de "
           f"{resultado['coletado_em']}), gerada em código, sem preços.")
    conferido = (f"{resultado['no_site']} de {resultado['total_no_site']} do resumo do site"
                 if resultado["total_no_site"] else f"{resultado['no_site']} no site")
    return (f"**Planilha do catálogo da {empresas.nome(empresa)}**: {resultado['total']} {rotulo}s"
            + (f" (filtro: {filtro})" if filtro else "") + f"; base de {resultado['total_base']} ({conferido}).\n"
            f"Arquivo anexado abaixo: Excel com filtro em cada coluna, link de cada {rotulo} e a aba \"Fonte e data\".\n"
            f"Fonte: site, coleta de {resultado['coletado_em']}. Sem preços. Reconfira antes de publicar.")


@rotas.get("/catalogo.xlsx")
def baixar_catalogo(empresa: str = "casa_veraneio", authorization: str = Header("")):
    """Planilha do catálogo inteiro (sem preço: vale para qualquer usuário logado, como GET /api/cerebro/imoveis)."""
    from auth import validar_token

    if not validar_token(authorization.removeprefix("Bearer ").strip()):
        raise HTTPException(status_code=401, detail="Token inválido")
    if not empresas.valida(empresa):
        raise HTTPException(status_code=422, detail="Empresa inválida.")
    pronta = planilha_do_catalogo("", empresa)
    if not pronta:
        raise HTTPException(status_code=404, detail=f"A tabela da {empresas.nome(empresa)} ainda não foi montada.")
    nome = _nome_arquivo(documentos.hoje().replace("/", "-"), f"Catálogo {empresas.nome(empresa)}", extensao=".xlsx")
    return Response(pronta[0], media_type=documentos.MIME_XLSX, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}", "Cache-Control": "private, no-store"})


# --- Documento .docx da resposta (estrategista-16, gestor_trafego-07) -----------------------------------------

def _tipo(linha) -> str | None:
    """"estudo", "plano" ou None (a resposta fica só no chat)."""
    resposta = linha["resposta"] or ""
    if linha["status"] != "concluida" or len(resposta) < MIN_CARACTERES or FORMULARIO.search(resposta):
        return None
    import estudos

    texto = linha["texto"] or ""
    if linha["agente"] == "estrategista" and (linha["modelo"] == estudos.MODELO or PEDE_DOCUMENTO.search(texto)):
        return "estudo"
    if linha["agente"] == "gestor_trafego" and (PLANO_TRAFEGO.search(texto) or PEDE_DOCUMENTO.search(texto)):
        return "plano"
    return None


def _confidencial(linha) -> str:
    """Decisão 12: resposta de quem vê o financeiro, com valores ou indicadores de venda, sai marcada."""
    from auth import ve_financeiro

    if ve_financeiro(linha["usuario"]) and TEM_VALOR.search(linha["resposta"] or ""):
        return "CONFIDENCIAL: contém dados financeiros. Só Diretoria; não compartilhe nem envie a ferramentas externas."
    return ""


def documento_da_resposta(linha) -> str | None:
    """Gera o .docx do estudo/plano e o anexa à resposta; devolve o id do anexo ou None. Nunca derruba a entrega."""
    try:
        if not (tipo := _tipo(linha)) or de(linha["id"]):
            return None
        import encaminhamento

        empresa = linha["empresa"] or empresas.PADRAO
        pedido = re.sub(r"\s+", " ", encaminhamento.pedido_original(linha["texto"] or "")).strip()
        assunto = pedido[:70] + ("…" if len(pedido) > 70 else "")
        data = documentos.hoje()
        if tipo == "estudo":
            titulo, selo = "Estudo estratégico", f"ESTUDO de {data}: contém estimativas; não usar como fato em peça pública"
            rotulo = "Estudo"
        else:
            titulo, selo, rotulo = "Plano de campanha", "", "Plano de campanha"
        resposta = FORMULARIO.sub("", linha["resposta"] or "")
        conteudo = documentos.documento(titulo, f"## Pedido\n{pedido}\n\n{resposta}", empresa, subtitulo=assunto,
                                        selo=selo, confidencial=_confidencial(linha))
        nome = _nome_arquivo(data.replace("/", "-"), rotulo, assunto.rstrip("…"), extensao=".docx")
        return anexar(linha["id"], conteudo, nome, documentos.MIME_DOCX,
                      f"{rotulo} da tarefa #{linha['id']} em .docx (mesmo texto da resposta no chat), gerado em código.")
    except Exception:
        log.exception("Documento da tarefa %s não foi gerado.", linha["id"])
        return None
