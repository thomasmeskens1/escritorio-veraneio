"""Cérebro que não aprende os próprios erros (levantamento de 31/10/2026, cerebro-03, -07 e -13). Tudo em código,
sem IA e sem custo:

- fatos de imóvel numa resposta de tarefa são conferidos com a ficha oficial antes de virarem conhecimento;
- cada [n] da resposta do Cérebro é conferido com o trecho n que ele recebeu (começa só marcando, sem apagar);
- uma correção aprovada aponta os trechos que a contradizem, para a Diretoria desativar com um clique.
"""

import re

import cerebro_texto as texto_br

# Fato de imóvel: tipo -> padrão com o número. "até 16 pessoas", "16 hóspedes", "8 suítes", "5 quartos".
FATOS = {
    "suítes": re.compile(r"(\d{1,3})\s*su[ií]tes?", re.I),
    "quartos": re.compile(r"(\d{1,3})\s*(?:quartos?|dormit[oó]rios?)", re.I),
    "banheiros": re.compile(r"(\d{1,3})\s*banheiros?", re.I),
    "pessoas": re.compile(r"(\d{1,3})\s*(?:pessoas|h[oó]spedes|convidados)", re.I),
}
EXTENSO = {"uma": "1", "um": "1", "duas": "2", "dois": "2", "três": "3", "tres": "3", "quatro": "4", "cinco": "5",
           "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10", "onze": "11", "doze": "12",
           "treze": "13", "catorze": "14", "quatorze": "14", "quinze": "15", "dezesseis": "16", "vinte": "20"}
_EXTENSO = re.compile(r"\b(" + "|".join(EXTENSO) + r")\b(?=\s+(?:su[ií]tes?|quartos?|banheiros?|pessoas|h[oó]spedes))",
                      re.I)


def _normal(texto: str) -> str:
    return _EXTENSO.sub(lambda m: EXTENSO[m.group(1).lower()], texto or "")


def fatos(texto: str) -> dict[str, set[str]]:
    texto = _normal(texto)
    return {tipo: {str(int(n)) for n in padrao.findall(texto)} for tipo, padrao in FATOS.items()
            if padrao.search(texto)}


def divergencias(resposta: str, ficha: str) -> list[str]:
    """Fatos da resposta que a ficha oficial desmente (só tipos que a ficha traz: sem dado na ficha, não acusa)."""
    da_ficha = fatos(ficha)
    return [f"{n} {tipo} (ficha: {', '.join(sorted(da_ficha[tipo], key=int))})"
            for tipo, valores in fatos(resposta).items() if tipo in da_ficha
            for n in sorted(valores - da_ficha[tipo], key=int)]


# --- [n] da resposta x trecho n -----------------------------------------------------------------

CITACAO = re.compile(r"\[(\d{1,2})\]")
NUMERO = re.compile(r"(?<![\w/.,])\d{1,4}(?:[.,]\d{3})*(?![\w/])")
MARCADOR = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")  # "1. " / "- " de lista não é dado
CIDADE = re.compile(r"([A-ZÀ-Ú][\wÀ-ú']+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú']+){0,3})\s*[-–]\s*[A-Z]{2}\b")
NAO_CONFIRMADO = " (não confirmado na fonte citada)"


def _numeros(texto: str) -> set[str]:
    return {re.sub(r"[.,]", "", n).lstrip("0") or "0" for n in NUMERO.findall(_normal(texto))}


def conferir_citacoes(resposta: str, trechos: list[str]) -> tuple[str, list[str]]:
    """Marca as linhas cujo [n] não existe ou cujo número/cidade não está no trecho n. Devolve (texto, problemas)."""
    problemas, linhas = [], []
    for linha in (resposta or "").splitlines():
        refs = [int(n) for n in CITACAO.findall(linha)]
        if not refs or NAO_CONFIRMADO in linha:
            linhas.append(linha)
            continue
        fora = [n for n in refs if not 1 <= n <= len(trechos)]
        fontes = " ".join(trechos[n - 1] for n in refs if 1 <= n <= len(trechos))
        afirmacao = MARCADOR.sub("", CITACAO.sub(" ", linha))
        sem_apoio = sorted(_numeros(afirmacao) - _numeros(fontes), key=lambda n: (len(n), n)) if fontes else []
        cidades = [c.strip() for c in CIDADE.findall(afirmacao)
                   if texto_br.sem_acento(c.strip()) not in texto_br.sem_acento(fontes)] if fontes else []
        if fora or sem_apoio or cidades:
            motivo = (f"[{', '.join(map(str, fora))}] não existe na lista de fontes" if fora else
                      "sem apoio na fonte: " + ", ".join([*sem_apoio, *cidades]))
            problemas.append(f"{linha.strip()[:80]}… ({motivo})")
            linha = linha.rstrip() + NAO_CONFIRMADO
        linhas.append(linha)
    texto = "\n".join(linhas)
    if problemas:
        texto += (f"\n\nConferência automática: marquei {len(problemas)} linha(s) com \"não confirmado\": o dado não "
                  "aparece na fonte citada. Reconfira antes de usar.")
    return texto, problemas


# --- Correção aprovada x trechos que a contradizem -----------------------------------------------------

def contradizem(correcao: str, candidatos: list[dict], limite: int = 6) -> list[dict]:
    """Trechos do mesmo assunto da correção que trazem outro número ou não trazem o que ela afirma. Ordem: mais
    termos em comum primeiro. Quem decide desativar é a Diretoria (pode ser falso alarme)."""
    termos = {t for t in texto_br.termos(correcao) if not t.isdigit()}
    numeros = _numeros(correcao)
    achados = []
    for c in candidatos:
        comuns = termos & set(texto_br.termos(c["conteudo"]))
        if not termos or len(comuns) < max(1, min(3, len(termos) // 3)):
            continue
        outros = _numeros(c["conteudo"]) - numeros
        if c.get("da_tarefa") or (numeros and outros and not numeros <= _numeros(c["conteudo"])):
            achados.append({**c, "comuns": len(comuns)})
    achados.sort(key=lambda c: (not c.get("da_tarefa"), -c["comuns"]))
    return achados[:limite]
