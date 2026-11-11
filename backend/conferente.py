"""Conferente automático das regras duras (Onda 2, item 2; copywriter-01, social_media-01, email_marketing-01,
gestor_trafego-16). Código puro, sem IA e sem custo, e SÓ AVISA: não bloqueia nem corrige nada.

Roda sobre a legenda e o roteiro de cada item antes de gravar no Monday (ferramentas_monday.py), sobre a resposta
final dos agentes de texto (executor.py) e sobre a legenda que vem dentro dela (Onda 2 de novembro, copywriter-03:
com o botão "Corrigir o mecânico", conferente_rotas.py). As regras por empresa ficam em conferente_regras.py e o motor
comum (o mesmo da entrega no PC), em conferente_motor.py. Uma menção negada ("nunca WhatsApp") não é aviso.
"""

import os
import re
import threading
from datetime import date

import config
import empresas
import conferente_motor as motor
from conferente_motor import EMOJI, HASHTAG, LOCAL, TRAVESSAO  # noqa: F401 (nomes antigos deste módulo)
from conferente_regras import (CHECKLIST_META, CHECKLIST_META_TITULO, COMUNS, CRECI, HOSPEDAGEM, REGRAS,
                               VETOS_FOTO_CORP)

# Agentes cuja resposta é texto de peça (o Gestor consolida e já passa pelo especialista).
AGENTES = {"copywriter", "social_media", "email_marketing", "gestor_trafego"}
NEGACAO = re.compile(r"\b(?:sem|nunca|nada de|n[aã]o|nem|proibid[oa]s?|bloquead[oa]s?|evite|evitar|jamais|"
                     r"impedid[oa]s?)\b[^.\n]{0,30}$", re.I)
CONTAGEM = re.compile(r"\bfaltam\s+(\d{1,3})\s+(?:noites|dias)\b", re.I)
REVEILLON = re.compile(r"r[eé]veillon|\bvirada\b|ano novo", re.I)
TITULO_LEGENDA = "Conferência automática da legenda"  # o botão "Corrigir o mecânico" (js/conferencia.js) procura


NUMERO_CRECI = re.compile(r"CRECI\s*(?:n[ºo°.]*\s*)?([\d][\d.\-/ ]{3,15}-?\s?[A-Z]?)\b", re.I)


def creci_vero() -> str:
    """Número do CRECI da Casa Vero: CRECI_VERO no ambiente ou o do manual 12 (fora do git); "" se não achar."""
    if (configurado := os.getenv("CRECI_VERO", "").strip()):
        return configurado
    for caminho in sorted(config.PASTA_CONHECIMENTO.glob("12_*.md"))[:1]:
        try:
            if (achado := NUMERO_CRECI.search(caminho.read_text(encoding="utf-8"))):
                return achado.group(1).strip()
        except OSError:
            pass
    return ""


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
            # "ainda dá tempo de escolher" virou a frase repetida nas três marcas (copywriter-26): sugestão neutra.
            avisos.append(f"disponibilidade afirmada ({_unicos(achou)}): convide sem prometer data livre (ex.: "
                          "\"escolha a casa do seu grupo com a nossa equipe\")")
    if (urgente := [a for p in COMUNS["urgencia"] for a in _achados(p, texto)]) and empresas.valida(empresa):
        import prazos_comerciais  # import tardio: lê o calendario.json

        if not prazos_comerciais.vigente(empresa, texto):
            avisos.append(f"urgência de data ({_unicos(urgente)}) sem prazo de fechamento válido cadastrado para a "
                          f"{empresas.nome(empresa)}: confirme o \"fechar até\" ou convide sem prazo")
    if empresa == "casa_vero" and campo in ("legenda", "email") and tipo != "STORIES" \
            and not re.search(CRECI, texto, re.I):
        numero = creci_vero()
        avisos.append(f"falta o CRECI{f' ({numero})' if numero else ''}: anúncio imobiliário da Casa Vero sai com o "
                      "número do CRECI (Lei 6.530/78)")
    if campo == "roteiro":
        import direcao_visual

        avisos += direcao_visual.conferir(texto, empresa)
        if empresa == "cv_corporativo" and (achou := [a for p in VETOS_FOTO_CORP for a in _achados(p, texto)]):
            avisos.append(f"foto com pessoas ou marca de cliente ({_unicos(achou)}): rosto reconhecível só com "
                          "autorização de imagem e nenhuma logo ou crachá de cliente (manual 04 §4)")
    if campo in ("legenda", "email"):
        avisos += motor.grafia(texto)
    for padrao in COMUNS["palavras_a_dosar"] if campo != "resposta" else ():  # a resposta pode ter várias legendas
        if len(achou := _achados(padrao, texto)) >= 2:
            avisos.append(f"\"{achou[0].lower()}\" aparece {len(achou)} vezes (no máximo 1 por texto)")

    if regras and not empresas.pede_grupo(pedido):
        avisos += _da_empresa(texto, empresa, regras, campo, pedido)
    if campo == "legenda":
        avisos += _formato_legenda(texto, empresa, regras, tipo)
    if campo in ("legenda", "email") and tipo != "STORIES":
        avisos += _com_a_ficha(texto, empresa)
    if data_postagem:
        avisos += _contagem(texto, data_postagem)
    return avisos


def _com_a_ficha(texto: str, empresa: str) -> list[str]:
    """Legenda final e e-mail contra a ficha do imóvel (cerebro-03): capacidade, suítes, local e diária."""
    try:
        import cerebro_conferir  # import tardio: lê a base do Cérebro

        return cerebro_conferir.divergencias_da_legenda(texto, empresa)
    except Exception:  # noqa: BLE001 - a conferência nunca derruba a entrega
        return []


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
    """As regras de formato ficam no motor comum (as mesmas da legenda entregue pelo Max)."""
    return motor.formato_legenda(texto, empresa if regras else "", tipo)


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
    da_legenda = conferir_legenda_do_chat(resposta, empresa, pedido, avisos) if agente_id in AGENTES else []
    blocos = [rodape(avisos), rodape(da_legenda, TITULO_LEGENDA),
              rodape(do_monday, "Conferência dos itens gravados no Monday"),
              *_complementos(resposta, agente_id, empresa, pedido)]
    extra = "\n\n".join(b for b in blocos if b)
    return f"{resposta}\n\n{extra}" if extra and resposta else resposta


def conferir_legenda_do_chat(resposta: str, empresa: str, pedido: str = "", ja_avisados: list[str] = ()) -> list[str]:
    """Copywriter-03: a legenda dentro da resposta do chat passa pelas regras de legenda (antes só no Monday).
    Sem bloco de legenda, a resposta inteira é conferida com a ficha do imóvel (cerebro-03)."""
    legenda = motor.legenda_do_texto(resposta)
    if not legenda:
        return [a for a in _com_a_ficha(resposta, empresa) if a not in ja_avisados]
    return [a for a in conferir(legenda, empresa, "legenda", pedido) if a not in ja_avisados]


PLANO_DE_MIDIA = re.compile(r"\b(plano de m[ií]dia|campanhas?|conjuntos? de an[uú]ncios|p[uú]blicos?|verba|"
                            r"or[cç]amento|criativos?|segmenta[cç][aã]o)\b", re.I)


def _complementos(resposta: str, agente_id: str, empresa: str, pedido: str) -> list[str]:
    """Blocos fixos que o código garante no fim da resposta (Onda 1 de novembro)."""
    extras = []
    # gestor_trafego-03: todo plano de mídia fecha com o checklist da Meta.
    if agente_id == "gestor_trafego" and CHECKLIST_META_TITULO not in resposta \
            and len({m.group(1).lower()[:6] for m in PLANO_DE_MIDIA.finditer(resposta)}) >= 2:
        extras.append(CHECKLIST_META)
    # moviemaker-02: o modelo esqueceu a pergunta de um clique sobre o pedido fora do padrão.
    import pedido_video

    if agente_id in ("moviemaker", "editor_video") and "<<FORMULARIO>>" not in resposta \
            and (achados := pedido_video.conflitos(pedido, empresa)):
        extras.append(pedido_video.formulario(achados))
    # analista_tendencias-32: a resposta rápida oferece aprofundar com a pesquisa.
    import estudos

    if (oferta := estudos.oferta_de_aprofundar(agente_id, pedido)):
        extras.append(oferta)
    return extras
