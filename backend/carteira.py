"""Carteira de clientes do Corporativo em sigilo (prospectador-15, estrategista-29, despachante-26).

Os nomes dos clientes (contas ativas e eventos ganhos no Monday) são segredo comercial:
  - só a Diretoria os vê no contexto do agente (persona, Cérebro); para os demais saem como "[cliente]";
  - nunca vão no pedido que o Max executa com pesquisa na web (uma página pode pedir a lista numa URL); no lugar,
    o perfil agregado (segmentos, cidades, tipos de evento e faixas de pax, só contagens);
  - a checagem de "já é cliente" continua só no backend (comercial.ja_conhecidos).
"""

import logging
import re
import time
import unicodedata
from collections import Counter

log = logging.getLogger(__name__)

OCULTO = "[cliente]"
ESPERA_FALHA_S = 10 * 60  # Monday fora do ar: não tenta de novo a cada pedido
# Palavras que abrem nomes de empresa sem identificá-las (o nome que identifica vem depois) e nomes nossos.
GENERICAS = frozenset((
    "grupo banco casa instituto associacao companhia cia sociedade fundacao clube club hotel the de da do das dos e "
    "sao santa santo nova novo brasil brasileira industria industrias comercio servicos consultoria eventos evento "
    "agencia escola colegio universidade hospital laboratorio editora construtora transportes tecnologia solucoes "
    "digital global international internacional company capital empresa empresas condominio igreja prefeitura "
    "secretaria federacao sindicato cooperativa rede centro copy extras aditivo festa confraternizacao projeto teste "
    "ltda sa s a me eireli epp veraneio vero corporativo corp paulo sp campinas jundiai atibaia sorocaba "
    "braganca barueri osasco guarulhos").split())

_nomes: tuple[float, frozenset[str], tuple[str, ...]] | None = None


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def _tokens(nome: str) -> list[str]:
    return re.findall(r"[a-z0-9&]+", _normal(re.sub(r"^\s*\d+\s*-\s*", "", nome or "")))


def chaves(nomes: list[str]) -> tuple[frozenset[str], tuple[str, ...]]:
    """(palavras que identificam um cliente, nomes completos com 2+ palavras). Ex.: "1124 - GRUPO FICTICIA DO BRASIL"
    -> palavra "ficticia"; "X7NOVA TECH" -> "x7nova", "x7" e o nome "x7nova tech"."""
    palavras, frases = set(), set()
    for nome in nomes:
        tokens = [t for t in _tokens(nome) if t not in GENERICAS]
        if not tokens:
            continue
        primeira = tokens[0]
        if len(primeira) >= 3 or any(ch.isdigit() for ch in primeira):
            palavras.add(primeira)
            if (inicio := re.match(r"[a-z]*\d+", primeira)) and inicio.group(0) != primeira:
                palavras.add(inicio.group(0))  # "x7nova" também aparece como "X7"
        if len(tokens) >= 2:
            frases.add(" ".join(tokens))
    return frozenset(palavras), tuple(sorted(frases, key=len, reverse=True))


def _nomes_do_crm() -> tuple[frozenset[str], tuple[str, ...]]:
    """Chaves dos clientes do Monday (o cache de 6 h do comercial), refeitas a cada 10 min; falha: nada por 10 min,
    sem travar o pedido."""
    global _nomes
    if _nomes and time.monotonic() - _nomes[0] < ESPERA_FALHA_S:
        return _nomes[1], _nomes[2]
    try:
        import comercial  # import tardio: comercial importa o Monday

        base = comercial.clientes()
        palavras, frases = chaves([i["nome"] for i in base["contas"] + base["ganhos"]])
    except Exception as erro:
        log.warning("Carteira: não li os clientes do Monday (%s); nomes não ocultados agora.", erro)
        palavras, frases = frozenset(), ()
    _nomes = (time.monotonic(), palavras, frases)
    return palavras, frases


def _trechos(texto: str, palavras: frozenset[str], frases: tuple[str, ...]) -> list[tuple[int, int]]:
    """Posições dos nomes de clientes no texto. A busca é sem acento e sem caixa, num texto normalizado com 1
    caractere por caractere do original (as posições batem)."""
    normal = "".join(_normal(ch)[:1] or "_" for ch in texto)
    trechos: list[tuple[int, int]] = []
    if frases:  # nome completo primeiro ("Red Bull" inteiro, não só "Red"); o mais longo vence
        padrao = r"\b(?:" + "|".join(r"[\s.&-]+".join(map(re.escape, f.split())) for f in frases) + r")\b"
        trechos += [a.span() for a in re.finditer(padrao, normal)]
    for achado in re.finditer(r"(?<![a-z0-9\[])[a-z0-9][a-z0-9&]*", normal):
        if achado.group(0) in palavras and not any(i < achado.end() and achado.start() < f for i, f in trechos):
            trechos.append(achado.span())
    return sorted(trechos)


def ocultar(texto: str, palavras: frozenset[str] | None = None, frases: tuple[str, ...] = ()) -> str:
    """Troca os nomes de clientes por "[cliente]"."""
    if not texto:
        return texto
    if palavras is None:
        palavras, frases = _nomes_do_crm()
    if not palavras and not frases:
        return texto
    pedacos, fim = [], 0
    for inicio, final in _trechos(texto, palavras, frases):
        pedacos += [texto[fim:inicio], OCULTO]
        fim = final
    return "".join(pedacos) + texto[fim:]


def tem_nomes(texto: str) -> bool:
    if not texto:
        return False
    palavras, frases = _nomes_do_crm()
    return bool((palavras or frases) and _trechos(texto, palavras, frases))


def perfil_agregado(base: dict) -> str:
    """Quem já é cliente, sem nomes: contagens por segmento, cidade, tipo de evento e faixa de pax."""
    contas, ganhos = base.get("contas", []), base.get("ganhos", [])
    segmentos = Counter((c.get("industry") or "não informado").strip() for c in contas)
    cidades = Counter((c.get("text_mkxj2284") or "não informada").strip() for c in contas)
    tipos = Counter((g.get("color_mm4pd1wc") or "não informado").strip() for g in ganhos)
    faixas: Counter = Counter()
    for g in ganhos:
        pax = re.sub(r"\D", "", str(g.get("n_meros_mkmgpvds") or ""))
        faixas["?" if not pax else "até 30" if int(pax) <= 30 else "31 a 100" if int(pax) <= 100
               else "101 a 300" if int(pax) <= 300 else "mais de 300"] += 1

    def linha(titulo: str, contagem: Counter) -> str:
        return f"{titulo}: " + "; ".join(f"{k} ({n})" for k, n in contagem.most_common(12))

    return "\n".join([f"PERFIL DE QUEM JÁ É CLIENTE (só contagens; {len(contas)} contas ativas e {len(ganhos)} "
                      "eventos ganhos, com repetições):",
                      linha("Segmentos", segmentos), linha("Cidades da sede", cidades),
                      linha("Tipos de evento", tipos), linha("Pax por evento", faixas)])
