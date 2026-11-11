"""Leitura tolerante da resposta da prospecção (N2-prospectador-02, fase 1).

Antes era tudo ou nada: um bloco <<LEADS>>[...]<<FIM>> com uma vírgula a mais, cortado no fim ou dentro de ```json
derrubava a tarefa inteira (json.loads) e jogava fora até 40 minutos de Max. Agora o Max devolve uma linha
<<LEAD>>{...} por empresa; cada linha é lida sozinha, e a que vier com defeito é pulada sem derrubar as outras.
O bloco antigo continua aceito (prévia de um trabalhador desatualizado), objeto por objeto. Tudo em código, sem IA.
"""

import json
import re

MARCA_LINHA = "<<LEAD>>"
MARCA_BLOCO = "<<LEADS>>"
_CERCA = re.compile(r"```(?:json)?", re.I)
_VIRGULA_SOBRANDO = re.compile(r",\s*([}\]])")
_ASPAS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def tem_leads(texto: str) -> bool:
    """A resposta traz leads (linha ou bloco)? Sem marca, o Max respondeu em texto (ex.: pedido ambíguo)."""
    return MARCA_LINHA in (texto or "") or MARCA_BLOCO in (texto or "")


def _objeto(trecho: str) -> dict | None:
    """Um objeto JSON, com os defeitos mais comuns corrigidos (vírgula sobrando, aspas curvas)."""
    trecho = _VIRGULA_SOBRANDO.sub(r"\1", trecho.strip().rstrip(",").translate(_ASPAS))
    try:
        valor = json.loads(trecho)
    except ValueError:
        return None
    return valor if isinstance(valor, dict) and str(valor.get("empresa") or "").strip() else None


def _objetos_soltos(texto: str) -> list[str]:
    """Cada {...} de primeiro nível do texto (chaves dentro de strings não contam). Objeto cortado no fim fica de fora."""
    achados, inicio, nivel, em_texto, escape = [], -1, 0, False, False
    for i, ch in enumerate(texto):
        if em_texto:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                em_texto = False
            continue
        if ch == '"':
            em_texto, escape = True, False
        elif ch == "{":
            inicio = i if nivel == 0 else inicio
            nivel += 1
        elif ch == "}" and nivel:
            nivel -= 1
            if nivel == 0:
                achados.append(texto[inicio:i + 1])
    return achados


def ler(texto: str) -> tuple[list[dict], int]:
    """(leads lidos, quantas linhas/objetos vieram com defeito)."""
    texto = _CERCA.sub("", texto or "")
    trechos: list[str] = []
    for linha in texto.split(MARCA_LINHA)[1:]:  # formato novo: uma linha por empresa
        trechos.append(linha.split("<<", 1)[0])
    if MARCA_BLOCO in texto:  # formato antigo: o bloco inteiro, mesmo sem o <<FIM>> (resposta cortada)
        bloco = texto.split(MARCA_BLOCO, 1)[1].split("<<FIM>>", 1)[0]
        try:
            lista = json.loads(_VIRGULA_SOBRANDO.sub(r"\1", bloco.strip().translate(_ASPAS)))
            trechos += [json.dumps(i, ensure_ascii=False) for i in lista] if isinstance(lista, list) else []
        except ValueError:
            trechos += _objetos_soltos(bloco)
    leads, defeitos, vistos = [], 0, set()
    for trecho in trechos:
        objetos = _objetos_soltos(trecho) or [trecho]
        for bruto in objetos[:1]:  # uma empresa por linha
            lead = _objeto(bruto)
            if lead is None:
                defeitos += 1
                continue
            chave = json.dumps(lead, sort_keys=True, ensure_ascii=False)
            if chave not in vistos:
                vistos.add(chave)
                leads.append(lead)
    return leads, defeitos
