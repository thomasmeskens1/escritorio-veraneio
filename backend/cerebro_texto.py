"""Cérebro: texto em português — termos, divisão em trechos, BM25 e comparação de assunto (sem LLM)."""

import math
import re
import unicodedata
from collections import Counter

TRECHO_MIN = 800
TRECHO_MAX = 1200

_PALAVRAS_VAZIAS = set("""a o as os de da do das dos e em no na nos nas um uma uns umas para por com sem que qual
quais como se ao aos ou mais menos muito sobre entre ser ter sua seu suas seus nosso nossa isso este esta esse essa
pelo pela pelos pelas ele ela eles elas voce voces nao sim foi sao esta estao tem tambem quando onde porque ate
mas ja seja sera muito pode podem deve devem cada todo toda todos todas qualquer""".split())


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def _radical(palavra: str) -> str:
    """Radical leve: plural e gênero simples (suítes→suite, lodges→lodge, casas→casa)."""
    for sufixo in ("oes", "aes", "ais", "eis", "s"):
        if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 4:
            return palavra[: -len(sufixo)] + {"oes": "ao", "aes": "ao", "ais": "al", "eis": "el", "s": ""}[sufixo]
    return palavra


def termos(texto: str) -> list[str]:
    """Palavras com radical leve; números sem zeros à esquerda ("01" = "1"). "Lodge 1" / "Lodge 01" também
    vira o termo único "lodge#1", para a busca achar o lodge exato e não qualquer página com "lodge"."""
    texto = sem_acento(texto)
    palavras = [(p.lstrip("0") or "0") if p.isdigit() else _radical(p) for p in re.findall(r"[a-z0-9]+", texto)
                if p not in _PALAVRAS_VAZIAS and (len(p) >= 3 or p.isdigit())]
    return palavras + [f"lodge#{int(n)}" for n in re.findall(r"\blodges?\s*(?:n[ºo.]*\s*)?0*(\d+)", texto)]


def nomes_proprios(texto: str) -> set[str]:
    """Palavras com inicial maiúscula fora do começo da frase (nomes de lodges, pessoas, lugares)."""
    nomes = set()
    for frase in re.split(r"[.!?\n:]+", texto):
        palavras = re.findall(r"[A-Za-zÀ-ÿ]+", frase)
        nomes.update(sem_acento(p) for p in palavras[1:] if p[0].isupper() and len(p) > 2)
    return nomes


def mesmo_assunto(a: str, b: str) -> bool:
    """Guarda léxica para versões: muitos termos em comum e nomes próprios compatíveis.
    (Evita que o Lodge A substitua o Lodge B só porque os textos são parecidos.)"""
    ta, tb = set(termos(a)), set(termos(b))
    ta = {t for t in ta if not t.isdigit()}
    tb = {t for t in tb if not t.isdigit()}
    if not ta or not tb:
        return False
    sobreposicao = len(ta & tb) / min(len(ta), len(tb))
    na, nb = nomes_proprios(a), nomes_proprios(b)
    nomes_ok = not na or not nb or na <= nb or nb <= na
    return sobreposicao >= 0.5 and nomes_ok


# --- Divisão em trechos ----------------------------------------------------------------------

def _quebrar_longo(paragrafo: str) -> list[str]:
    """Parágrafo maior que o máximo: quebra por frases (e, em último caso, por tamanho)."""
    partes, atual = [], ""
    for frase in re.split(r"(?<=[.!?])\s+", paragrafo):
        while len(frase) > TRECHO_MAX:
            partes.append(frase[:TRECHO_MAX])
            frase = frase[TRECHO_MAX:]
        if atual and len(atual) + len(frase) + 1 > TRECHO_MAX:
            partes.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        partes.append(atual)
    return partes


def dividir(titulo: str, conteudo: str) -> list[tuple[str, str]]:
    """(título, texto) de cada trecho: por seção (#) e parágrafo, juntando até ~800–1200 caracteres."""
    trechos = []
    for secao in re.split(r"\n(?=#{1,4} )", conteudo.replace("\r\n", "\n")):
        secao = secao.strip()
        if not secao:
            continue
        titulo_secao = titulo
        if secao.startswith("#"):
            cabecalho, _, secao = secao.partition("\n")
            titulo_secao = f"{titulo} › {cabecalho.lstrip('# ').strip()}" if titulo else cabecalho.lstrip("# ").strip()
            secao = secao.strip()
            if not secao:
                continue
        atual = ""
        for paragrafo in re.split(r"\n\s*\n", secao):
            paragrafo = paragrafo.strip()
            if not paragrafo:
                continue
            pedacos = _quebrar_longo(paragrafo) if len(paragrafo) > TRECHO_MAX else [paragrafo]
            for pedaco in pedacos:
                if atual and len(atual) + len(pedaco) + 2 > TRECHO_MAX:
                    trechos.append((titulo_secao, atual))
                    atual = pedaco
                else:
                    atual = f"{atual}\n\n{pedaco}".strip()
                if len(atual) >= TRECHO_MIN:
                    trechos.append((titulo_secao, atual))
                    atual = ""
        if atual:
            # Sobra curta da seção junta-se ao trecho anterior da mesma seção, se couber.
            if trechos and trechos[-1][0] == titulo_secao and len(trechos[-1][1]) + len(atual) + 2 <= TRECHO_MAX:
                trechos[-1] = (titulo_secao, f"{trechos[-1][1]}\n\n{atual}")
            else:
                trechos.append((titulo_secao, atual))
    return trechos


# --- BM25 ------------------------------------------------------------------------------------

class BM25:
    """BM25 clássico (k1=1.5, b=0.75) sobre as listas de termos dos trechos."""

    def __init__(self, documentos: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.contagens = [Counter(d) for d in documentos]
        self.tamanhos = [len(d) for d in documentos]
        self.media = (sum(self.tamanhos) / len(documentos)) if documentos else 0.0
        df = Counter(t for c in self.contagens for t in c)
        n = len(documentos)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def cobertura_maxima(self, consulta: list[str]) -> float:
        """Nota de um trecho médio com cada termo da pergunta uma vez: normaliza o BM25 pela pergunta
        (um único termo comum em comum não vale tanto quanto a pergunta inteira)."""
        n = len(self.tamanhos)
        return sum(self.idf.get(t, math.log(1 + (n + 0.5) / 0.5)) for t in set(consulta))

    def pontuar(self, consulta: list[str]) -> list[float]:
        termos_consulta = set(consulta)
        notas = []
        for contagem, tamanho in zip(self.contagens, self.tamanhos):
            nota = 0.0
            for t in termos_consulta:
                f = contagem.get(t)
                if f:
                    norma = self.k1 * (1 - self.b + self.b * tamanho / (self.media or 1))
                    nota += self.idf[t] * f * (self.k1 + 1) / (f + norma)
            notas.append(nota)
        return notas
