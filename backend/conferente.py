"""Conferente automático das regras duras (Onda 2, item 2; copywriter-01, social_media-01, email_marketing-01,
gestor_trafego-16). Código puro, sem IA e sem custo, e SÓ AVISA: não bloqueia nem corrige nada.

Roda sobre a legenda e o roteiro de cada item antes de gravar no Monday (ferramentas_monday.py) e sobre a resposta
final dos agentes de texto (executor.py). As regras por empresa ficam em conferente_regras.py.
Uma menção negada ("nunca WhatsApp", "sem a Casa Veraneio") não é aviso.
"""

import re
import threading
from datetime import date

import empresas
from conferente_regras import COMUNS, HOSPEDAGEM, REGRAS

# Agentes cuja resposta é texto de peça (o Gestor consolida e já passa pelo especialista).
AGENTES = {"copywriter", "social_media", "email_marketing", "gestor_trafego"}
NEGACAO = re.compile(r"\b(?:sem|nunca|nada de|n[aã]o|nem|proibid[oa]s?|bloquead[oa]s?|evite|evitar|jamais|"
                     r"impedid[oa]s?)\b[^.\n]{0,30}$", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⭐⭕]")
HASHTAG = re.compile(r"#[\wÀ-ÿ]+")
TRAVESSAO = re.compile(r"[—–]")
CONTAGEM = re.compile(r"\bfaltam\s+(\d{1,3})\s+(?:noites|dias)\b", re.I)
REVEILLON = re.compile(r"r[eé]veillon|\bvirada\b|ano novo", re.I)
_UF = "|".join(COMUNS["ufs"])
# Fim do nome da cidade (minúscula ou parêntese) + separador + UF: o certo é exatamente " / ". Espaço sozinho
# ("litoral de SP") e lista de UFs ("SP, RJ") não contam.
LOCAL = re.compile(rf"([a-zà-ÿ)])(\s*[,\-–—(]\s*|/\s*|\s+/(?=\S))({_UF})\b(?![a-zà-ÿ])")


def _achados(padrao: str, texto: str, flags=re.I) -> list[str]:
    """Trechos que casam com o padrão, fora de menção negada."""
    return [m.group(0) for m in re.finditer(padrao, texto, flags) if not NEGACAO.search(texto[:m.start()])]


def _unicos(lista: list[str]) -> str:
    vistos = []
    for item in lista:
        if item.lower() not in (v.lower() for v in vistos):
            vistos.append(item)
    return ", ".join(f'"{v.strip()}"' for v in vistos[:3])


def conferir(texto: str, empresa: str, campo: str = "legenda", pedido: str = "", data_postagem: str = "",
             tipo: str = "") -> list[str]:
    """Avisos curtos sobre o texto. campo: "legenda" (todas as regras), "roteiro" (briefing da arte) ou "resposta"
    (texto do chat: sem as regras de formato, que valem para a legenda). pedido: o que o usuário pediu (valores
    só com pedido). data_postagem AAAA-MM-DD confere a contagem regressiva do Réveillon."""
    texto = texto or ""
    if not texto.strip():
        return []
    regras = REGRAS.get(empresa)
    avisos = []

    if (achou := _achados(COMUNS["whatsapp"], texto)):
        avisos.append(f"WhatsApp citado ({_unicos(achou)}): proibido em tudo, use o CTA da empresa")
    if (achou := _achados(COMUNS["telefone"], texto)):
        avisos.append(f"telefone escrito ({_unicos(achou)}): sem contato escrito na peça")
    if (errados := [m.group(0) for m in LOCAL.finditer(texto)]):
        avisos.append(f"localização fora do padrão \"Cidade / UF\" ({_unicos(errados)})")
    for padrao in COMUNS["nomes_internos"]:
        if (achou := _achados(padrao, texto, 0)):
            avisos.append(f"nome interno de agente ({_unicos(achou)}): use \"nossa equipe\" ou \"a gente\"")
    for padrao in COMUNS["disponibilidade"]:
        if (achou := _achados(padrao, texto)):
            avisos.append(f"disponibilidade afirmada ({_unicos(achou)}): use \"ainda dá tempo de escolher\"")
    for padrao in COMUNS["palavras_a_dosar"] if campo != "resposta" else ():  # a resposta pode ter várias legendas
        if len(achou := _achados(padrao, texto)) >= 2:
            avisos.append(f"\"{achou[0].lower()}\" aparece {len(achou)} vezes (no máximo 1 por texto)")

    if regras and not empresas.pede_grupo(pedido):
        avisos += _da_empresa(texto, empresa, regras, campo, pedido)
    if campo == "legenda":
        avisos += _formato_legenda(texto, empresa, regras, tipo)
    if data_postagem:
        avisos += _contagem(texto, data_postagem)
    return avisos


def _da_empresa(texto: str, empresa: str, regras: dict, campo: str, pedido: str) -> list[str]:
    avisos = []
    nome = empresas.nome(empresa)
    if (achou := [a for p in regras["outras_marcas"] for a in _achados(p, texto)]):
        avisos.append(f"cita outra empresa numa peça da {nome} ({_unicos(achou)})")
    if (achou := [a for p in regras["palavras_vetadas"] for a in _achados(p, texto)]):
        avisos.append(f"palavra vetada nos manuais ({_unicos(achou)})")
    if (achou := [a for p in regras["nome_periodo_vetado"] for a in _achados(p, texto)]):
        avisos.append(f"nome do período fora do padrão ({_unicos(achou)})")
    pediu_valor = bool(empresas.PEDE_PRECO.search(pedido or ""))
    if regras["sem_hospedagem"] and (achou := _achados(HOSPEDAGEM, texto)) and not pediu_valor:
        avisos.append(f"dado de hospedagem ({_unicos(achou)}): nunca num trabalho da {nome}")
    # Casa Veraneio: a legenda leva a ficha com a diária (manual 07 §4), e a resposta do chat traz a legenda.
    valores_livres = campo in ("legenda", "resposta") and regras["valores_na_legenda"]
    if not valores_livres and not pediu_valor and (achou := _achados(empresas.PRECO.pattern, texto)):
        if empresa == "casa_vero":
            avisos.append(f"valor ({_unicos(achou)}): na Casa Vero, valor de imóvel só com autorização no pedido")
        else:
            avisos.append(f"valor ({_unicos(achou)}) sem o pedido pedir: por padrão a peça sai sem valores")
    return avisos


def _formato_legenda(texto: str, empresa: str, regras: dict | None, tipo: str) -> list[str]:
    if tipo == "STORIES":
        return ["STORIES não têm legenda: a legenda escrita foi descartada"]
    avisos = []
    if (n := len(TRAVESSAO.findall(texto))):
        avisos.append(f"{n} travessão(ões): legenda sem travessão (troque por vírgula ou ponto)")
    if ";" in texto:
        avisos.append("ponto e vírgula na legenda")
    if (n := len(EMOJI.findall(texto))) > COMUNS["max_emojis"]:
        avisos.append(f"{n} emojis (no máximo {COMUNS['max_emojis']})")
    tags = HASHTAG.findall(texto)
    if len(tags) > COMUNS["max_hashtags"]:
        avisos.append(f"{len(tags)} hashtags (até {COMUNS['max_hashtags']})")
    if (acentuadas := [t for t in tags if not t.isascii()]):
        avisos.append(f"hashtag com acento ({_unicos(acentuadas)}): escreva sem acento")
    if not regras:
        return avisos
    obrigatoria = regras["hashtag_obrigatoria"]
    if tags and obrigatoria and obrigatoria not in (t.lower() for t in tags):
        avisos.append(f"falta a hashtag {obrigatoria}")
    if (vetadas := [t for t in tags for p in regras["hashtags_vetadas"] if re.fullmatch(p, t, re.I)]):
        avisos.append(f"hashtag de outra empresa ({_unicos(vetadas)})")
    minusculo = texto.lower()
    if not any(a.lower().rstrip("!.") in minusculo for a in regras["assinatura"]):
        avisos.append(f"falta a assinatura (\"{regras['assinatura'][0]}\")")
    if not any(re.search(c, texto, re.I) for c in regras["ctas"]):
        avisos.append("CTA fora da lista aprovada da empresa")
    return avisos


def _contagem(texto: str, data_postagem: str) -> list[str]:
    """'Faltam N noites' do Réveillon contra a data de postagem (social_media-01: 30 em 02/12, o certo era 29)."""
    if not REVEILLON.search(texto):
        return []
    try:
        dia = date.fromisoformat(data_postagem)
    except ValueError:
        return []
    certo = (date(dia.year, 12, 31) - dia).days
    return [f"\"Faltam {m.group(1)}\" não bate com a postagem em {dia:%d/%m} (até 31/12 são {certo})"
            for m in CONTAGEM.finditer(texto) if int(m.group(1)) != certo]


def rodape(avisos: list[str], titulo: str = "Conferência automática") -> str:
    """Bloco curto para o fim da entrega (só aviso)."""
    if not avisos:
        return ""
    return f"{titulo} (só aviso, confira):\n" + "\n".join(f"- {a}" for a in avisos)


# Avisos dos itens do Monday de cada tarefa: a ferramenta registra, a resposta final mostra (executor.anotar).
_pendentes: dict[int, list[str]] = {}
_trava = threading.Lock()


def registrar(tarefa_id: int, item: str, avisos: list[str]) -> None:
    if not tarefa_id or not avisos:
        return
    with _trava:
        _pendentes.setdefault(tarefa_id, []).extend(f"{item}: {a}" for a in avisos)


def anotar(resposta: str, agente_id: str, empresa: str, pedido: str = "", tarefa_id: int = 0) -> str:
    """Resposta final + rodapé com os avisos (da própria resposta, nos agentes de texto, e dos itens do Monday)."""
    with _trava:
        do_monday = _pendentes.pop(tarefa_id, []) if tarefa_id else []
    avisos = conferir(resposta, empresa, "resposta", pedido) if agente_id in AGENTES else []
    blocos = [rodape(avisos), rodape(do_monday, "Conferência dos itens gravados no Monday")]
    extra = "\n\n".join(b for b in blocos if b)
    return f"{resposta}\n\n{extra}" if extra and resposta else resposta
