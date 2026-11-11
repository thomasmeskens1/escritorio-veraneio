"""Ficha de pedido do manual 16 na tela do agente (Onda 2: N2-professor-07, N2-analista_metricas-21,
N2-estrategista-25 e N2-sonoplasta-23).

Só LÊ o manual 16 (fora do git; quem escreve as fichas é o Thomas) e separa as seções "## Agente": obrigatório,
opcional, observações e os bons exemplos por empresa. Uma seção pode valer para dois agentes ("## Designer e Criador de
Imagens"). Agente sem seção não tem cartão: as 6 fichas que faltam aparecem sozinhas quando o Thomas aprovar o
rascunho. A rota entrega só a ficha do agente pedido, nunca o manual inteiro. Os exemplos vão também como modelo, com
os números de Lodge/Vero, datas e nomes trocados por lacunas, para ninguém enviar o exemplo como pedido real.
"""

import re
import unicodedata

from fastapi import APIRouter, Header, HTTPException

import acesso
import config
from auth import validar_token
from estado import ANDARES, andar_do_agente

rotas = APIRouter(prefix="/api/fichas-pedido")

EMPRESAS = {"casa veraneio": "casa_veraneio", "corporativo": "cv_corporativo", "casa vero": "casa_vero"}
_cache: dict = {"chave": None, "fichas": {}}


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def _arquivo():
    achados = sorted(config.PASTA_CONHECIMENTO.glob("16_*.md"))
    return achados[0] if achados else None


def _itens(texto: str) -> list[str]:
    """"a; b (x; y); c." -> ["a", "b (x; y)", "c"] (o ";" dentro de parênteses não separa)."""
    partes, atual, nivel = [], "", 0
    for letra in texto:
        nivel += (letra == "(") - (letra == ")")
        if letra == ";" and nivel <= 0:
            partes.append(atual)
            atual = ""
        else:
            atual += letra
    partes.append(atual)
    return [p.strip().rstrip(".;").strip() for p in partes if p.strip().rstrip(".;").strip()]


def _sem_aspas(texto: str) -> str:
    return texto.strip().strip("\"“”'").strip()


def modelo(exemplo: str) -> str:
    """Exemplo -> modelo com lacunas: "Lodges 34 e 202 para 20/11, responsável Bruna" ->
    "Lodges [nº] e [nº] para [data], responsável [nome]"."""
    # A vírgula só continua a lista quando ela fecha com "e N" ("Lodges 03, 26 e 64"; "Lodge 20, 30 s" é só o 20).
    texto = re.sub(r"\b(Lodges?|Vero)\s+(\d+(?:(?:,\s*\d+)*\s+e\s+\d+)?)",
                   lambda m: f"{m.group(1)} " + re.sub(r"\d+", "[nº]", m.group(2)), exemplo)
    texto = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", "[data]", texto)
    return re.sub(r"\b(respons[aá]vel)\s+[A-ZÀ-Ý][\wÀ-ÿ]+", r"\1 [nome]", texto)


def _secao(titulo: str, linhas: list[str]) -> dict:
    nome, _, resto = titulo.partition("(")
    ficha = {"titulo": nome.strip(), "manuais": resto.rstrip(")").strip(), "obrigatorio": [], "opcional": [],
             "notas": [], "exemplos": []}
    atual = None  # rótulo do bloco cujos subitens ("  - ...") estão sendo lidos
    for linha in linhas:
        if not linha.strip():
            continue
        sub = re.match(r"^\s{2,}[-*]\s+(.*)", linha)
        if sub and atual:
            texto = sub.group(1).strip().rstrip(";.").strip()
            if atual in ("obrigatorio", "opcional"):
                ficha[atual].append(texto)
            elif ficha["notas"]:
                ficha["notas"][-1]["texto"] = f"{ficha['notas'][-1]['texto']} {texto}".strip()
            continue
        topo = re.match(r"^[-*]\s+([^:]{2,60}):\s*(.*)", linha)
        if not topo:
            continue
        rotulo, texto = topo.group(1).strip(), topo.group(2).strip()
        chave = _normal(rotulo)
        if chave.startswith("obrigatorio"):
            atual = "obrigatorio"
            ficha["obrigatorio"] += _itens(texto)
        elif chave.startswith("opcional"):
            atual = "opcional"
            ficha["opcional"] += _itens(texto)
        elif chave.startswith("bom exemplo"):
            atual = None
            empresa = re.search(r"\(([^)]+)\)", rotulo)
            texto = _sem_aspas(texto)
            if texto:
                ficha["exemplos"].append({"empresa": EMPRESAS.get(_normal(empresa.group(1))) if empresa else None,
                                          "rotulo": empresa.group(1).strip() if empresa else "", "texto": texto,
                                          "modelo": modelo(texto)})
        else:
            atual = "nota"
            ficha["notas"].append({"rotulo": rotulo, "texto": texto})
    return ficha


def _agentes_do_titulo(titulo: str) -> list[str]:
    """"Designer e Criador de Imagens" -> ["designer", "criador_imagens"] (pelo nome de cada agente no prédio)."""
    nomes = {_normal(a.nome): a.id for agentes in ANDARES.values() for a in agentes.values() if a.tipo == "ia"}
    partes = [_normal(p) for p in re.split(r"\s+e\s+|,\s*|\s*/\s*", titulo.partition("(")[0])]
    return [nomes[p] for p in partes if p in nomes]


def interpretar(texto: str) -> dict[str, dict]:
    """Manual 16 -> {agente_id: ficha}. A regra geral (antes da primeira seção) vai em "geral" de cada ficha."""
    blocos = re.split(r"^##\s+", texto, flags=re.M)
    geral = " ".join(l.strip() for l in blocos[0].splitlines() if l.strip() and not l.startswith("#"))
    fichas = {}
    for bloco in blocos[1:]:
        titulo, *linhas = bloco.splitlines()
        ficha = _secao(titulo.strip(), linhas)
        if not (ficha["obrigatorio"] or ficha["exemplos"]):
            continue
        for agente_id in _agentes_do_titulo(titulo):
            fichas.setdefault(agente_id, {**ficha, "geral": geral})
    return fichas


def fichas() -> dict[str, dict]:
    """Lê o manual de novo só quando ele muda (data e tamanho do arquivo)."""
    arquivo = _arquivo()
    if not arquivo:
        return {}
    marca = arquivo.stat()
    chave = (str(arquivo), marca.st_mtime_ns, marca.st_size)
    if _cache["chave"] != chave:
        _cache.update(chave=chave, fichas=interpretar(arquivo.read_text(encoding="utf-8")))
    return _cache["fichas"]


def de(agente_id: str) -> dict | None:
    return fichas().get(agente_id)


@rotas.get("/{agente_id}")
def ficha_do_agente(agente_id: str, authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    andar = andar_do_agente(agente_id)
    if not andar or not acesso.pode_usar(usuario, andar, agente_id):
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    return {"ficha": de(agente_id)}
