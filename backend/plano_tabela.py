"""Planejamento do mês revisado numa tabela e gravado no Monday pelo código (Onda 2 de novembro, social_media-05).

Caso real (tarefas 45 a 54): o plano propôs 18 peças e só 5 entraram no Monday, porque quem gravava era o modelo,
item por item. Agora o Gestor fecha o planejamento com um bloco <<PLANO_TABELA>> (uma linha por peça). O bloco sai
do texto e fica no projeto (plano_tabela.json), com os avisos do conferente em cada linha; no chat aparece uma
tabela (frontend/js/plano_tabela.js) onde a pessoa marca as peças, muda datas e o Lodge. "Gravar no Monday (N peças)"
manda exatamente essas linhas para ferramentas_monday._criar, sem modelo no meio. Linha já gravada não grava de
novo (clique duplo ou "Gravar tudo" depois de uma parte). "Lance no Monday" ao Gestor também abre esta tabela.
"""

import json
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import tarefas
from auth import validar_token

rotas = APIRouter(prefix="/api/plano")

ARQUIVO = "plano_tabela.json"
BLOCO = re.compile(r"<<PLANO_TABELA>>(.*?)<<FIM DO PLANO_TABELA>>", re.S)
BLOCO_ABERTO = re.compile(r"<<PLANO_TABELA>>.*\Z", re.S)  # cortado pelo modelo: some do texto
MARCADOR = re.compile(r"\[Tabela do planejamento #(\d+): \d+ peças?[^\]]*\]")
PLANEJAMENTO = re.compile(r"\b(planejamento|calend[aá]rio|cronograma|grade)\b.{0,60}?\b(m[eê]s|mensal|semana[sl]?|"
                          r"janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|"
                          r"dezembro|temporada|feriado|r[eé]veillon|carnaval)\b", re.IGNORECASE | re.S)
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LODGE = re.compile(r"^\d{1,4}$")
MAX_LINHAS = 40  # o mesmo limite de itens por tarefa de ferramentas_monday
TIPOS = ("STORIES", "POST", "CARROSSEL", "REELS", "SHORTS", "TIKTOK", "YOUTUBE", "LINKEDIN", "NEWSLETTER")
_trava = threading.Lock()

INSTRUCAO = (
    "\n\nPLANEJAMENTO PARA O MONDAY: depois do texto final, acrescente o bloco <<PLANO_TABELA>>[...]<<FIM DO "
    "PLANO_TABELA>> com UMA linha por peça proposta (todas, sem cortar nenhuma), em JSON válido, cada uma assim: "
    '{"data": "AAAA-MM-DD (vazio se não houver data: nunca invente)", "tipo": "' + "|".join(TIPOS) + '", '
    '"tema": "<descrição curta da peça>", "lodge": "<número do Lodge ou vazio>", "papel": "<papel na jornada>", '
    '"roteiro": "<briefing curto: capa, páginas ou cenas e CTA>", "legenda": "<rascunho; vazio em STORIES>"}. '
    "A equipe revisa essa tabela no chat e o sistema grava no Monday exatamente o que ela aprovar.")


def e_planejamento(pedido: str) -> bool:
    """Pedido de planejamento de um período (mês, semana, temporada, feriado)."""
    return bool(PLANEJAMENTO.search(pedido or ""))


def instrucao(pedido: str) -> str:
    """Trecho da consolidação do Gestor que pede a tabela ("" se o pedido não é planejamento)."""
    return INSTRUCAO if e_planejamento(pedido) else ""


SOCIAL_MEDIA = "social_media"
SEM_GRAVAR = (" Nesta tarefa você NÃO grava itens no Monday: a equipe aprova na tabela e o sistema grava. Pode ler o "
              "planejamento que já está no board para não repetir peças.")


def do_social_media(agente_id: str, pedido: str) -> bool:
    """Planejamento pedido direto ao Social Media (Thomas, 12/11/2026): também sai em tabela, gravada pelo código."""
    return agente_id == SOCIAL_MEDIA and e_planejamento(pedido)


def tabela_da_tarefa(tarefa_id: int, texto: str, pedido: str) -> str:
    """com_tabela para uma tarefa fora de projeto (pasta própria na pasta de projetos)."""
    pasta = _pasta(tarefa_id)
    pasta.mkdir(parents=True, exist_ok=True)
    return com_tabela(pasta, texto, pedido)


def _pasta(tarefa_id: int) -> Path:
    from agents.projeto import PASTA_PROJETOS  # import tardio: o projeto carrega o andar inteiro

    return PASTA_PROJETOS / str(tarefa_id)


def _texto(valor, limite: int) -> str:
    return re.sub(r"[ \t]+", " ", str(valor or "")).strip()[:limite]


def _linha(bruta: dict, indice: int) -> dict | None:
    """Linha validada (tipo do board, data AAAA-MM-DD ou vazia, Lodge só número); None se não for uma peça."""
    if not isinstance(bruta, dict):
        return None
    tipo = _texto(bruta.get("tipo"), 20).upper()
    tema = _texto(bruta.get("tema"), 150)
    if tipo not in TIPOS or not tema:
        return None
    data, lodge = _texto(bruta.get("data"), 10), re.sub(r"\D", "", str(bruta.get("lodge") or ""))[:4]
    return {"indice": indice, "data": data if DATA.match(data) else "", "tipo": tipo, "tema": tema,
            "lodge": lodge.lstrip("0") or ("" if not lodge else "0"), "papel": _texto(bruta.get("papel"), 40),
            "roteiro": str(bruta.get("roteiro") or "").strip()[:3000],
            "legenda": "" if tipo == "STORIES" else str(bruta.get("legenda") or "").strip()[:3000],
            "avisos": [], "gravado": ""}


def _avisos(linha: dict, tarefa) -> list[str]:
    from agents import ferramentas_monday  # import tardio: CrewAI é pesado

    try:
        return ferramentas_monday._conferir(tarefa, "", _nome(linha), linha["legenda"], linha["roteiro"],
                                            linha["data"])
    except Exception:
        return []  # a conferência só avisa: nunca impede a tabela


def com_tabela(pasta: Path, texto: str, pedido: str = "") -> str:
    """Tira o bloco da entrega, guarda as linhas no projeto e deixa no lugar o marcador que o chat troca pela tabela.
    Bloco quebrado ou vazio: some do texto e a entrega segue sem tabela."""
    achado = BLOCO.search(texto or "")
    if not achado:
        return BLOCO_ABERTO.sub("", texto).rstrip() if BLOCO_ABERTO.search(texto or "") else texto
    try:
        brutas = json.loads(achado.group(1).strip())
    except ValueError:
        brutas = []
    linhas = [l for l in (_linha(b, 0) for b in (brutas if isinstance(brutas, list) else [])) if l][:MAX_LINHAS]
    resto = (texto[:achado.start()] + texto[achado.end():]).strip()
    if not linhas or not pasta.name.isdigit():
        return resto
    tarefa_id = int(pasta.name)
    tarefa = tarefas.obter(tarefa_id)
    for n, linha in enumerate(linhas):
        linha["indice"] = n
        linha["avisos"] = _avisos(linha, tarefa)
    dados = {"tarefa_id": tarefa_id, "pedido": (pedido or "")[:1500], "linhas": linhas}
    (pasta / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"{resto}\n\n{marcador(tarefa_id, len(linhas))}"


def marcador(tarefa_id: int, total: int) -> str:
    return (f"[Tabela do planejamento #{tarefa_id}: {total} peça{'s' if total != 1 else ''}. Marque o que vai, ajuste "
            "datas e Lodge e grave no Monday pelo botão.]")


def carregar(tarefa_id: int) -> dict | None:
    arquivo = _pasta(tarefa_id) / ARQUIVO
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None
    except ValueError:
        return None


def _nome(linha: dict) -> str:
    """'TIPO | tema' no padrão do board; o Lodge entra no nome se o tema não o citar."""
    nome = f"{linha['tipo']} | {linha['tema']}"
    if linha.get("lodge") and not re.search(rf"\blodge\s*#?0*{linha['lodge']}\b", linha["tema"], re.I):
        nome += f" (Lodge {linha['lodge']})"
    return nome


def _trocar_lodge(texto: str, antigo: str, novo: str) -> str:
    if not antigo or not novo or antigo == novo:
        return texto
    return re.sub(rf"\b(lodge\s*#?)0*{antigo}\b", rf"\g<1>{novo}", texto or "", flags=re.I)


def _aplicar(linha: dict, data: str, lodge: str) -> dict:
    """A linha com a data e o Lodge que a pessoa deixou na tabela (o Lodge novo troca o antigo no tema e no roteiro)."""
    nova = dict(linha)
    if data is not None:
        nova["data"] = data
    if lodge is not None and lodge != linha.get("lodge"):
        for campo in ("tema", "roteiro", "legenda"):
            nova[campo] = _trocar_lodge(linha[campo], linha.get("lodge", ""), lodge)
        nova["lodge"] = lodge
    return nova


def _roteiro(linha: dict) -> str:
    extras = [f"Papel na jornada: {linha['papel']}" if linha.get("papel") else "",
              f"Lodge: {linha['lodge']}" if linha.get("lodge") else ""]
    return "\n".join(p for p in (linha.get("roteiro", ""), *extras) if p).strip()


class Escolha(BaseModel):
    indice: int = Field(ge=0, lt=MAX_LINHAS)
    data: str | None = Field(None, max_length=10)
    lodge: str | None = Field(None, max_length=4)


def gravar(tarefa_id: int, escolhas: list[Escolha]) -> dict:
    """Grava no Monday exatamente as linhas escolhidas, com a data e o Lodge da tabela. ValueError: pedido inválido."""
    from agents import ferramentas_monday

    with _trava:
        dados = carregar(tarefa_id)
        if not dados:
            raise ValueError("Esta tarefa não tem tabela de planejamento.")
        linhas = {l["indice"]: l for l in dados["linhas"]}
        for e in escolhas:
            if e.indice not in linhas:
                raise ValueError(f"A linha {e.indice + 1} não existe nesta tabela.")
            if e.data and not DATA.match(e.data):
                raise ValueError(f"Data inválida na linha {e.indice + 1}: use AAAA-MM-DD.")
            if e.lodge and not LODGE.match(e.lodge):
                raise ValueError(f"Lodge inválido na linha {e.indice + 1}: só o número.")
        contador, resultado = ferramentas_monday._Contador(), []
        for e in dict((e.indice, e) for e in escolhas).values():  # a mesma linha duas vezes grava uma vez
            atual = linhas[e.indice]
            if atual.get("gravado"):
                resultado.append({"indice": e.indice, "ok": True, "texto": f"Já estava no Monday: {atual['gravado']}"})
                continue
            linha = _aplicar(atual, e.data, (e.lodge or "").lstrip("0") if e.lodge is not None else None)
            texto = ferramentas_monday._criar(contador, tarefa_id, _nome(linha), data_postagem=linha["data"],
                                              legenda=linha["legenda"], roteiro=_roteiro(linha))
            ok = texto.startswith("Criado")
            if ok:
                linhas[e.indice] = {**linha, "gravado": texto.removeprefix("Criado em ")[:300]}
            resultado.append({"indice": e.indice, "ok": ok, "texto": texto})
        (_pasta(tarefa_id) / ARQUIVO).write_text(json.dumps({**dados, "linhas": list(linhas.values())},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")
    criados = sum(r["ok"] and not r["texto"].startswith("Já estava") for r in resultado)
    tarefas.registrar_evento(tarefa_id, "plano_gravado", "gestor", detalhe=f"{criados} de {len(resultado)} no Monday")
    return {"criados": criados, "pedidas": len(resultado), "resultado": resultado,
            "linhas": list(linhas.values())}


def aviso_lancar(tarefa_id: int) -> dict | None:
    """'Lance no Monday': se o planejamento tem tabela, ela abre no chat (gravação pelo código, não pelo modelo)."""
    dados = carregar(tarefa_id)
    if not dados or not dados.get("linhas"):
        return None
    faltam = sum(not l.get("gravado") for l in dados["linhas"])
    return {"titulo": "Gravar no Monday",
            "texto": f"O planejamento da tarefa #{tarefa_id} está na tabela abaixo ({faltam} peça(s) ainda fora do "
                     "Monday). Marque as peças, ajuste datas e Lodge e clique em Gravar: o sistema grava exatamente "
                     f"o que estiver marcado.\n\n{marcador(tarefa_id, len(dados['linhas']))}"}


def _dono(tarefa_id: int, authorization: str):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return usuario


@rotas.get("/{tarefa_id}")
async def ver(tarefa_id: int, authorization: str = Header("")):
    import monday

    _dono(tarefa_id, authorization)
    if not (dados := carregar(tarefa_id)):
        raise HTTPException(status_code=404, detail="Esta tarefa não tem tabela de planejamento.")
    return {"tarefa_id": tarefa_id, "linhas": dados["linhas"], "monday": monday.ativo()}


class Gravacao(BaseModel):
    linhas: list[Escolha] = Field(min_length=1, max_length=MAX_LINHAS)


@rotas.post("/{tarefa_id}/gravar")
async def gravar_rota(tarefa_id: int, pedido: Gravacao, authorization: str = Header("")):
    import asyncio

    import monday

    _dono(tarefa_id, authorization)
    if not monday.ativo():
        raise HTTPException(status_code=503, detail="O Monday não está ligado neste servidor.")
    try:
        return await asyncio.to_thread(gravar, tarefa_id, pedido.linhas)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
