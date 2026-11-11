"""Texto aprovado do Copywriter que vai ao Max como TEXTO FIXO (Onda 1 de novembro, 11/11/2026; copywriter-02).

Antes, a produção no Max escrevia a própria legenda e contradizia o que o Copywriter revisou no chat (tarefas 258 e
265/266). Fase 1 (ajuste do crítico): a produção recebe o texto do Copywriter com a ordem "copie, não reescreva", e o
trabalhador confere os números antes da pasta FINAL (scripts/max/conferencia_texto.py). De onde vem o texto:
  1. projeto do Gestor: a etapa do Copywriter desse projeto (a última, se houver mais de uma);
  2. pedido direto: a última resposta do Copywriter na conversa do mesmo usuário, andar e empresa, nas últimas 24 h,
     sobre o mesmo assunto; a com 👍 vale antes da mais recente, e a com 👎 nunca vale.
Sem texto do Copywriter, nada muda (a produção segue como antes). O botão "Esta é a final" fica para a fase 2.
"""

import re
from datetime import datetime, timedelta, timezone

import config
import tarefas

COPYWRITER = "copywriter"
JANELA = timedelta(hours=24)
LIMITE = 8000
PROJETO = re.compile(r"projeto #(\d+), coordenado pelo Gestor")
PASTA_PROJETOS = config.DADOS_DIR / "projetos"  # a mesma de agents/projeto.py (sem importar o pacote de agentes)
PALAVRA = re.compile(r"[a-zà-ú0-9]{5,}", re.IGNORECASE)
COMUNS = {"sobre", "legenda", "texto", "textos", "posts", "stories", "reels", "carrossel", "crie", "criar", "fazer",
          "faca", "preciso", "quero", "para", "peca", "pecas", "favor", "casa", "veraneio", "corporativo", "imoveis",
          "arte", "artes", "video", "videos", "sobre", "nossa", "nosso", "essa", "esse", "deste", "desta", "agora"}


def _do_projeto(texto: str) -> dict | None:
    achado = PROJETO.search(texto or "")
    pasta = achado and PASTA_PROJETOS / achado.group(1) / "etapas"
    if not pasta or not pasta.is_dir():
        return None
    etapas = sorted(pasta.glob(f"*-{COPYWRITER}.md"))
    if not etapas:
        return None
    conteudo = etapas[-1].read_text(encoding="utf-8").strip()
    return {"texto": conteudo[:LIMITE], "origem": f"etapa do Copywriter no projeto #{achado.group(1)}"} if conteudo else None


def _palavras(texto: str) -> set[str]:
    return {p.lower() for p in PALAVRA.findall(texto or "")} - COMUNS


def _mesmo_assunto(pedido: str, conversa: str) -> bool:
    """Lodge citado no pedido precisa estar na conversa; sem Lodge, pelo menos 2 palavras de conteúdo em comum."""
    from agents.perfis import _lodges  # import tardio: as personas importam muita coisa

    lodges = _lodges(pedido)
    if lodges:
        return bool(lodges & _lodges(conversa))
    return len(_palavras(pedido) & _palavras(conversa)) >= 2


def _da_conversa(linha) -> dict | None:
    """Resposta do Copywriter mais adequada na conversa recente (👍 primeiro; 👎 nunca)."""
    import avaliacoes  # import tardio: avaliações importam o Cérebro

    avaliacoes._db()  # cria a tabela se ainda não existe
    desde = (datetime.now(timezone.utc) - JANELA).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = tarefas._db().execute(
        "SELECT t.id, t.texto, t.resposta, COALESCE(a.valor, 0) AS voto FROM tarefas t "
        "LEFT JOIN avaliacoes a ON a.tarefa_id = t.id WHERE t.usuario = ? AND t.andar = ? AND t.agente = ? "
        "AND t.empresa = ? AND t.status = 'concluida' AND t.id < ? AND t.criada_em >= ? ORDER BY t.id DESC LIMIT 10",
        (linha["usuario"], linha["andar"], COPYWRITER, linha["empresa"], linha["id"], desde)).fetchall()
    candidatas = [l for l in linhas if l["voto"] >= 0 and (l["resposta"] or "").strip()
                  and _mesmo_assunto(linha["texto"], f"{l['texto']} {l['resposta']}")]
    if not candidatas:
        return None
    escolhida = next((l for l in candidatas if l["voto"] > 0), candidatas[0])
    origem = f"resposta #{escolhida['id']} do Copywriter" + (", com 👍" if escolhida["voto"] > 0 else ", a mais recente")
    return {"texto": escolhida["resposta"].strip()[:LIMITE], "origem": origem, "tarefa_id": escolhida["id"]}


def da_producao(linha, texto_base: str = "") -> dict | None:
    """{"texto", "origem"[, "tarefa_id"]} do texto aprovado para esta produção, ou None. `texto_base`: o pedido da
    produção original num ajuste (é lá que está o projeto do Gestor)."""
    try:
        return _do_projeto(linha["texto"]) or _do_projeto(texto_base) or _da_conversa(linha)
    except Exception:  # noqa: BLE001 - sem o texto aprovado a produção segue como antes
        return None
