"""Memória do que já foi usado nas peças (Onda 3 de novembro; criador_imagens-06, editor_video-05, sonoplasta-17).

Cada peça entregue registra de onde veio cada foto, cada take de vídeo e a faixa: o caminho no acervo dos Lodges,
no material do Marketing (LODGES ou SABORES CV), nas pastas da Casa Vero ou do Corporativo, com a peça, a empresa,
o imóvel e a data. A fonte é a receita.json da peça; o trabalhador do Max monta a lista (scripts/max/uso_material.py)
e a manda junto do /concluir.

Serve para três coisas, todas SÓ AVISO (nunca barra a entrega):
- capa ou take que já saiu: "esta capa já foi usada há N dias na peça #X" (limite em `aviso_dias`);
- o plano do Gestor e o briefing do Max recebem o que já foi usado no mesmo imóvel nos últimos `contexto_dias`,
  para variar;
- mostrar quando um Lodge precisa de foto ou filmagem nova (o mesmo material voltando sempre).

Limites configuráveis em dados/uso_material.json: {"aviso_dias": 60, "contexto_dias": 30, "ativo": true}, aprovados pelo
Thomas em 12/11/2026 como padrão: qualquer colaborador pode pedir outro material ou outro prazo na peça. Nada
aqui apaga registro (decisão 17: prazos de guarda em aberto).
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Header
from pydantic import BaseModel

import config
import tarefas

log = logging.getLogger("veraneio.uso_material")

rotas = APIRouter(prefix="/api/uso-material")

ARQUIVO_CONFIG = config.DADOS_DIR / "uso_material.json"
PADRAO = {"aviso_dias": 60, "contexto_dias": 30, "ativo": True}  # 60 dias: editor_video-05; 30: o plano
TIPOS = {"foto", "video", "faixa"}
PAPEIS = {"capa", "take", "foto", "faixa"}
FONTES = {"acervo", "marketing_lodges", "sabores", "vero", "corp", "anexo", "biblioteca", "desconhecida"}
NOMES_FONTE = {"acervo": "acervo dos Lodges", "marketing_lodges": "Marketing > LODGES", "sabores": "Marketing > SABORES CV",
               "vero": "fotos da Casa Vero", "corp": "fotos do Corporativo", "anexo": "anexo do pedido",
               "biblioteca": "biblioteca de músicas", "desconhecida": "origem não identificada"}
MAX_ORIGENS = 120   # por peça (um carrossel de 20 slides com vídeo fica bem abaixo)
MAX_NO_CONTEXTO = 12
IMOVEL = re.compile(r"\b(lodge|vero)s?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS uso_material (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarefa_id INTEGER NOT NULL,      -- a peça (produção) que usou
    raiz_id INTEGER,                 -- primeira produção da cadeia de ajustes (v2, v3 da mesma peça não se avisam)
    empresa TEXT NOT NULL,
    imovel TEXT,                     -- "lodge 12", "vero 90" (do caminho ou do pedido)
    tipo TEXT NOT NULL,              -- foto | video | faixa
    papel TEXT NOT NULL,             -- capa | take | foto | faixa
    fonte TEXT NOT NULL,             -- acervo | marketing_lodges | sabores | vero | corp | anexo | biblioteca | desconhecida
    caminho TEXT NOT NULL,           -- relativo à raiz da fonte (ou o nome do arquivo, se a origem não foi achada)
    chave TEXT NOT NULL,             -- fonte + caminho normalizados (o mesmo arquivo em peças diferentes)
    de REAL,                         -- take: segundo de início no arquivo de origem
    duracao_s REAL,                  -- take: duração do trecho
    em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uso_material_chave ON uso_material(empresa, chave);
CREATE INDEX IF NOT EXISTS idx_uso_material_imovel ON uso_material(empresa, imovel);
CREATE INDEX IF NOT EXISTS idx_uso_material_tarefa ON uso_material(tarefa_id);
"""
_esquema_criado = False


def _db():
    global _esquema_criado
    db = tarefas._db()
    if not _esquema_criado:
        db.executescript(_ESQUEMA)
        _esquema_criado = True
    return db


def ajustes_config() -> dict:
    """Os limites (dados/uso_material.json por cima do padrão)."""
    try:
        lido = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lido = {}
    return {**PADRAO, **{k: v for k, v in (lido if isinstance(lido, dict) else {}).items() if k in PADRAO}}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _texto_data(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def _data(texto: str) -> datetime:
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def imoveis_do_texto(texto: str) -> list[str]:
    """Imóveis citados ("Lodge 12" -> "lodge 12"), na ordem, sem repetir."""
    return list(dict.fromkeys(f"{tipo.lower()} {int(numero)}" for tipo, numero in IMOVEL.findall(texto or "")))


def chave(fonte: str, caminho: str) -> str:
    caminho = re.sub(r"/+", "/", str(caminho or "").replace("\\", "/")).strip("/").lower()
    return f"{fonte}:{caminho}" if fonte != "desconhecida" else f"nome:{Path(caminho).name}"


def _numero(valor) -> float | None:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


def normalizar(origens) -> list[dict]:
    """Só o que tem formato conhecido (a lista vem do trabalhador; nada de texto livre no banco)."""
    limpas = []
    for item in (origens if isinstance(origens, list) else [])[:MAX_ORIGENS]:
        if not isinstance(item, dict) or not str(item.get("caminho") or "").strip():
            continue
        tipo, papel = str(item.get("tipo") or ""), str(item.get("papel") or "")
        fonte = str(item.get("fonte") or "desconhecida")
        if tipo not in TIPOS or papel not in PAPEIS:
            continue
        fonte = fonte if fonte in FONTES else "desconhecida"
        caminho = str(item["caminho"]).replace("\\", "/")[:400]
        imovel = str(item.get("imovel") or "").lower()[:30] or None
        limpas.append({"tipo": tipo, "papel": papel, "fonte": fonte, "caminho": caminho, "chave": chave(fonte, caminho),
                       "imovel": imovel if imovel and IMOVEL.fullmatch(imovel) else None,
                       "de": _numero(item.get("de")), "duracao_s": _numero(item.get("duracao_s"))})
    return limpas


def _raiz(tarefa_id: int) -> int:
    try:
        import producao  # import tardio: producao importa este módulo
        return producao._producao_raiz(tarefa_id)
    except Exception:  # noqa: BLE001
        return tarefa_id


def registrar(tarefa_id: int, empresa: str, origens) -> int:
    """Grava as origens da peça entregue. Repetição do /concluir (a 1ª resposta se perdeu): não duplica."""
    limpas = normalizar(origens)
    if not limpas or not empresa:
        return 0
    db = _db()
    if db.execute("SELECT 1 FROM uso_material WHERE tarefa_id = ? LIMIT 1", (tarefa_id,)).fetchone():
        return 0
    raiz, em = _raiz(tarefa_id), _texto_data(_agora())
    with db:
        db.executemany("INSERT INTO uso_material (tarefa_id, raiz_id, empresa, imovel, tipo, papel, fonte, caminho, "
                       "chave, de, duracao_s, em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [(tarefa_id, raiz, empresa, o["imovel"], o["tipo"], o["papel"], o["fonte"], o["caminho"],
                         o["chave"], o["de"], o["duracao_s"], em) for o in limpas])
    return len(limpas)


def _ha(dias: int) -> str:
    return "hoje" if dias <= 0 else ("há 1 dia" if dias == 1 else f"há {dias} dias")


def _trecho(de: float | None, duracao: float | None) -> str:
    if de is None or duracao is None:
        return ""
    fmt = lambda s: f"{s:.1f}".rstrip("0").rstrip(".").replace(".", ",")  # noqa: E731
    return f", de {fmt(de)} a {fmt(de + duracao)} s"


def _sobrepoe(a: dict, b) -> bool:
    """Trechos do mesmo vídeo que se cruzam (sem trecho anotado num dos dois: o arquivo inteiro conta)."""
    if a["de"] is None or a["duracao_s"] is None or b["de"] is None or b["duracao_s"] is None:
        return True
    return a["de"] < b["de"] + b["duracao_s"] and b["de"] < a["de"] + a["duracao_s"]


def avisos(empresa: str, origens, tarefa_id: int | None = None, dias: int | None = None) -> list[str]:
    """Capa ou take desta peça que já saiu em outra peça da MESMA empresa dentro do limite. Só aviso."""
    ajustes = ajustes_config()
    if not ajustes["ativo"]:
        return []
    dias = int(dias if dias is not None else ajustes["aviso_dias"])
    desde = _texto_data(_agora() - timedelta(days=dias))
    raiz = _raiz(tarefa_id) if tarefa_id else None
    db, saida, vistos = _db(), [], set()
    for o in normalizar(origens):
        if o["papel"] not in ("capa", "take") or o["chave"] in vistos:
            continue
        vistos.add(o["chave"])
        papeis = ("capa",) if o["papel"] == "capa" else ("take",)
        linhas = db.execute(
            f"SELECT tarefa_id, raiz_id, de, duracao_s, em FROM uso_material WHERE empresa = ? AND chave = ? "
            f"AND papel IN ({','.join('?' * len(papeis))}) AND em >= ? ORDER BY em DESC",
            (empresa, o["chave"], *papeis, desde)).fetchall()
        for linha in linhas:
            if tarefa_id and (linha["tarefa_id"] == tarefa_id or (raiz and linha["raiz_id"] == raiz)):
                continue  # a própria peça ou uma versão dela (ajuste): reaproveitar é o esperado
            if o["papel"] == "take" and not _sobrepoe(o, linha):
                continue
            ha = _ha((_agora() - _data(linha["em"])).days)
            nome = Path(o["caminho"]).name
            if o["papel"] == "capa":
                saida.append(f"esta capa ({nome}) já foi usada {ha} na peça #{linha['tarefa_id']}")
            else:
                saida.append(f"este take ({nome}{_trecho(o['de'], o['duracao_s'])}) já saiu {ha} na peça "
                              f"#{linha['tarefa_id']}{_trecho(linha['de'], linha['duracao_s'])}")
            break
    return saida


def linha_do_resumo(lista: list[str]) -> str:
    if not lista:
        return ""
    return ("⚠ Material repetido (só aviso): " + "; ".join(lista[:6]) + ". Se foi de propósito, siga; se não, peça "
            "um ajuste com outra capa ou outro trecho.")


def usados(empresa: str, imovel: str, dias: int | None = None) -> list[dict]:
    """O que já saiu do imóvel nos últimos `dias` (o mais recente primeiro, um por arquivo)."""
    dias = int(dias if dias is not None else ajustes_config()["contexto_dias"])
    desde = _texto_data(_agora() - timedelta(days=dias))
    linhas = _db().execute("SELECT tarefa_id, tipo, papel, fonte, caminho, chave, de, duracao_s, em FROM uso_material "
                           "WHERE empresa = ? AND imovel = ? AND em >= ? ORDER BY em DESC, id DESC",
                           (empresa, imovel.lower(), desde)).fetchall()
    unicos: dict[str, dict] = {}
    for linha in linhas:
        unicos.setdefault(linha["chave"], dict(linha))
    return list(unicos.values())


def para_contexto(empresa: str | None, texto: str, dias: int | None = None) -> str:
    """Bloco para o plano do Gestor e o briefing do Max: o que já foi usado nos imóveis citados, para variar."""
    if not empresa or not ajustes_config()["ativo"]:
        return ""
    dias = int(dias if dias is not None else ajustes_config()["contexto_dias"])
    partes = []
    for imovel in imoveis_do_texto(texto)[:4]:
        try:
            itens = usados(empresa, imovel, dias)
        except Exception:  # noqa: BLE001 - o contexto nunca cai por isso
            log.exception("uso de material do %s não lido", imovel)
            continue
        if not itens:
            continue
        linhas = []
        for i in itens[:MAX_NO_CONTEXTO]:
            ha = _ha((_agora() - _data(i["em"])).days)
            papel = {"capa": "capa", "take": "take", "foto": "foto", "faixa": "faixa"}[i["papel"]]
            linhas.append(f"- {papel}: {i['caminho']} ({NOMES_FONTE.get(i['fonte'], i['fonte'])}"
                          f"{_trecho(i['de'], i['duracao_s'])}; peça #{i['tarefa_id']}, {ha})")
        resto = f"\n- ...e mais {len(itens) - MAX_NO_CONTEXTO}" if len(itens) > MAX_NO_CONTEXTO else ""
        partes.append(f"JÁ USADO NO {imovel.upper()} NOS ÚLTIMOS {dias} DIAS (varie: prefira outra capa e outros "
                      "trechos; é só o padrão: se o pedido citar este material ou outro prazo, siga o pedido):\n" + "\n".join(linhas) + resto)
    return "\n\n".join(partes)


AGENTES_DO_PLANO = {"gestor"}


def bloco(agente_id: str, empresa: str | None, pedido: str) -> str:
    """Bloco do contexto do chat (agents/perfis.contexto): só no plano do Gestor. Nunca derruba o contexto."""
    if agente_id not in AGENTES_DO_PLANO:
        return ""
    try:
        return para_contexto(empresa, pedido)
    except Exception:  # noqa: BLE001
        log.exception("bloco de material usado não montado")
        return ""


# --- rota do trabalhador: avisos antes do /concluir --------------------------------------------------------------

class Conferencia(BaseModel):
    empresa: str
    origens: list[dict] = []


@rotas.post("/{tarefa_id}/conferir")
async def conferir(tarefa_id: int, dados: Conferencia, authorization: str = Header("")):
    """Avisos de capa/take repetido para o resumo da peça. Não grava (o registro vem com o /concluir)."""
    import producao  # import tardio: producao importa este módulo
    producao._exigir_operador(authorization)
    return {"avisos": avisos(dados.empresa, dados.origens, tarefa_id)}
