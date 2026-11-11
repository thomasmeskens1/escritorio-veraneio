"""Conferência dos dados do imóvel ANTES de ir ao Max (despachante-05, criador_imagens-06, cerebro-09) e formulário
da Casa Vero sem campos de valor (social_media-03). Tudo em código, sem IA e sem custo.

Casos reais: tarefa 24 (Lodge 10 "em Orlando"; a ficha diz Atibaia/SP), tarefa 37 (Lodge 64 em Itu; é Serra Negra),
tarefa 61 (Vero 30 com 8 suítes; são 6), revisão de 30/10 item 1.9 (plano com o Lodge 35, pedido do Lodge 10: 12 min
de Max perdidos). O pedido (e o plano do Gestor) é comparado com a tabela de imóveis (cerebro_imoveis): número do
Lodge, cidade/UF, suítes, quartos e capacidade. Divergência vira uma pergunta com "seguir mesmo assim", nunca um
bloqueio: linguagem livre ("cabe a família toda") não é conferida, só números e "Cidade / UF".
Desde a Onda 2 de novembro (cerebro-03), a legenda final, o e-mail e o item do Monday também passam pela ficha, com a
diária da Casa Veraneio (divergencias_da_legenda, chamada pelo conferente), só como aviso.
"""

import json
import re

import cerebro_conferencia as conferencia
import cerebro_imoveis as imoveis
import empresas
import fichas
from cerebro_texto import sem_acento

# "Atibaia / SP", "Atibaia/SP", "Atibaia - SP" (o local sempre "Cidade / UF", decisão 2).
LOCAL = re.compile(r"([A-ZÀ-Ú][\wÀ-ú']+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú']+){0,3})\s*[/–-]\s*([A-Z]{2})\b")
MARCA_SEGUIR = "(Conferência de dados: seguir mesmo assim.)"
MARCA_FICHA = "(Conferência de dados: usar a ficha oficial onde houver divergência.)"
MAX_AVISOS = 6
OPCOES_GESTOR = [{"rotulo": "Usar a ficha", "texto": "Use os dados da ficha oficial onde houver divergência."},
                 {"rotulo": "Seguir mesmo assim", "texto": "Pode seguir mesmo assim, com os dados do plano."},
                 {"rotulo": "Cancelar produção", "texto": "Cancelar a produção."}]


def _padroes(empresa: str) -> list[re.Pattern]:
    return [fichas.VERO_CITADO, fichas.LODGE_CITADO] if empresa == "casa_vero" else [fichas.LODGE_CITADO]


def citados(texto: str, empresa: str) -> list[str]:
    sem_links = fichas.LINK_SITE.sub(" ", texto or "")
    return list(dict.fromkeys(str(int(n)) for p in _padroes(empresa) for n in p.findall(sem_links)))


def _trechos_por_imovel(texto: str, empresa: str) -> dict[str, str]:
    """Cada imóvel citado fica com o texto que vai da sua citação até a do próximo imóvel (com vários imóveis no
    mesmo parágrafo não dá para saber de qual é cada número; aí cada um só leva o que vem logo depois dele)."""
    marcas = sorted((m.start(), str(int(m.group(1)))) for p in _padroes(empresa) for m in p.finditer(texto or ""))
    trechos: dict[str, str] = {}
    for i, (inicio, numero) in enumerate(marcas):
        fim = marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)
        pedaco = texto[inicio:fim][:400].split("\n\n")[0]  # até o fim do parágrafo
        trechos[numero] = f"{trechos.get(numero, '')}\n{pedaco}".strip()
    return trechos


def _ficha(numero: str, empresa: str) -> dict | None:
    """Linha da tabela (Casa Veraneio) ou, nas outras empresas, os números da ficha do site."""
    linha = imoveis.linha(numero, empresa) if empresa in imoveis.ORIGENS else None
    if linha:
        return linha
    texto = fichas.ficha(numero, empresa)
    if not texto:
        return None
    achados = conferencia.fatos(texto)
    um = lambda tipo: int(next(iter(achados[tipo]))) if len(achados.get(tipo, ())) == 1 else None
    local = LOCAL.search(texto.splitlines()[0]) if texto else None
    return {"numero": int(numero), "cidade": local.group(1) if local else "", "uf": local.group(2) if local else "",
            "suites": um("suítes"), "quartos": um("quartos"), "pessoas": um("pessoas"), "fonte": "site",
            "coletado_em": ""}


def divergencias(texto: str, empresa: str, rotulo_origem: str = "o pedido") -> list[str]:
    """Frases curtas com o que `texto` afirma e a ficha desmente. Imóvel citado sem ficha também avisa."""
    rotulo = imoveis.ROTULO.get(empresa, "Lodge")
    achados = []
    for numero, trecho in _trechos_por_imovel(texto, empresa).items():
        ficha = _ficha(numero, empresa)
        if not ficha:
            achados.append(f"{rotulo} {numero}: não está na ficha da {empresas.nome(empresa)} (confira o número).")
            continue
        data = f", coleta de {imoveis._data(ficha['coletado_em'])}" if ficha.get("coletado_em") else ""
        origem = "ficha (planilha 2023" if ficha.get("fonte") == "planilha" else f"ficha (site{data}"
        fatos = conferencia.fatos(trecho)
        for tipo, campo in (("suítes", "suites"), ("quartos", "quartos")):
            if ficha.get(campo) and (errados := sorted(int(n) for n in fatos.get(tipo, ()) if int(n) != ficha[campo])):
                achados.append(f"{rotulo} {numero}: {rotulo_origem} diz {errados[0]} {tipo}; a {origem}) diz "
                               f"{ficha[campo]}.")
        # Capacidade: só o que passa do máximo (um grupo menor que a capacidade é escolha, não erro).
        if ficha.get("pessoas") and (demais := [int(n) for n in fatos.get("pessoas", ()) if int(n) > ficha["pessoas"]]):
            achados.append(f"{rotulo} {numero}: {rotulo_origem} fala em {max(demais)} pessoas; a {origem}) diz até "
                           f"{ficha['pessoas']}.")
        if ficha.get("cidade"):
            for cidade, uf in LOCAL.findall(trecho):
                if uf not in imoveis.UFS and uf != "FL":
                    continue
                if sem_acento(ficha["cidade"]) not in sem_acento(cidade) and sem_acento(cidade) not in sem_acento(
                        ficha["cidade"]) or (ficha.get("uf") and uf != ficha["uf"]):
                    achados.append(f"{rotulo} {numero}: {rotulo_origem} diz {cidade} / {uf}; a {origem}) diz "
                                   f"{ficha['cidade']} / {ficha.get('uf') or '—'}.")
                    break
    return list(dict.fromkeys(achados))[:MAX_AVISOS]


# --- Legenda final, e-mail e item do Monday contra a ficha (cerebro-03, Onda 2 de novembro) ----------------

VALOR = re.compile(r"R\$\s*([\d.]+(?:,\d{2})?)")
DATA_DA_FICHA = re.compile(r"\(dados de (\d{2})/(\d{2})/(\d{4})\)")
FICHA_VELHA_DIAS = 7


def _reais(texto: str) -> set[int]:
    return {int(v.split(",")[0].replace(".", "")) for v in VALOR.findall(texto or "") if v.strip(".")}


def _diarias(texto: str, hoje=None) -> list[str]:
    """Casa Veraneio: a diária citada na legenda precisa aparecer nos valores por época da ficha do site, e a coleta
    precisa ser recente. Na Casa Vero e no Corp nenhum valor vai para a conferência (sem dado de hospedagem)."""
    from datetime import date

    hoje = hoje or date.today()
    achados = []
    for numero, trecho in _trechos_por_imovel(texto, "casa_veraneio").items():
        sem_taxa = re.sub(r"taxa de ativa[cç][aã]o[^\n]{0,20}?R\$\s*[\d.,]+", "", trecho, flags=re.I)  # manual 01 §5
        if not (citados := _reais(sem_taxa)):
            continue
        if not (ficha := fichas.ficha(numero, "casa_veraneio") or ""):
            continue  # imóvel sem ficha: o aviso saiu antes do Max
        valores = {v for linha in ficha.splitlines() if re.search(r"di[aá]ria|R\$", linha, re.I) for v in _reais(linha)}
        if not valores:
            achados.append(f"Lodge {numero}: a legenda cita diária, mas a ficha não tem valores por época para "
                           "conferir (confirme a temporada).")
            continue
        if (fora := sorted(citados - valores)):
            achados.append(f"Lodge {numero}: a diária citada (R$ {fora[0]:,}".replace(",", ".")
                           + ") não confere com os valores da ficha.")
        if (data := DATA_DA_FICHA.search(ficha)):
            coleta = date(int(data.group(3)), int(data.group(2)), int(data.group(1)))
            if (hoje - coleta).days > FICHA_VELHA_DIAS:
                achados.append(f"Lodge {numero}: a ficha é de {coleta:%d/%m} (mais de {FICHA_VELHA_DIAS} dias): "
                               "confirme a diária antes de publicar.")
    return achados


def divergencias_da_legenda(texto: str, empresa: str, hoje=None) -> list[str]:
    """Só o que a ficha desmente (imóvel sem ficha já foi avisado antes do Max), mais a diária na Casa Veraneio.
    Nunca bloqueia: vira linha do rodapé da conferência."""
    if not empresas.valida(empresa) or not fichas.cita_imovel(texto):
        return []
    achados = [a for a in divergencias(texto, empresa, "a legenda") if "não está na ficha" not in a]
    if empresa == "casa_veraneio":
        achados += _diarias(texto, hoje)
    return list(dict.fromkeys(achados))[:MAX_AVISOS]


def imoveis_trocados(pedido: str, plano: str, empresa: str) -> list[str]:
    """O plano fala de um imóvel que o pedido não citou (o pedido citava outro)."""
    do_pedido, do_plano = set(citados(pedido, empresa)), citados(plano, empresa)
    rotulo = imoveis.ROTULO.get(empresa, "Lodge")
    novos = [n for n in do_plano if n not in do_pedido]
    if not do_pedido or not novos:
        return []
    return [f"O plano fala do {', '.join(f'{rotulo} {n}' for n in novos)}, mas o pedido cita o "
            f"{', '.join(f'{rotulo} {n}' for n in sorted(do_pedido, key=int))}. Qual vale?"]


def pergunta_do_plano(pedido: str, plano: str, empresa: str) -> str | None:
    """Gestor terminou o plano e a peça vai ao Max: a pergunta de conferência, ou None se tudo bate."""
    if not empresas.valida(empresa) or not fichas.cita_imovel(f"{pedido}\n{plano}"):
        return None
    achados = imoveis_trocados(pedido, plano, empresa) + divergencias(plano, empresa, "o plano")
    if not achados:
        return None
    return ("Conferência de dados antes do Max: " + " ".join(achados[:MAX_AVISOS])
            + " Use a ficha, siga mesmo assim ou cancele.")


def aviso_do_pedido(texto: str, empresa: str) -> dict | None:
    """Pedido de produção direto (Criador de Imagens/Editor de Vídeo): {"texto", "opcoes"} do aviso com os botões, ou
    None se nada diverge ou se a pessoa já decidiu (as marcas vão no pedido reenviado pelo botão)."""
    if MARCA_SEGUIR in (texto or "") or MARCA_FICHA in (texto or ""):
        return None
    if not empresas.valida(empresa) or not fichas.cita_imovel(texto) or not (achados := divergencias(texto, empresa)):
        return None
    return {"texto": "Antes de mandar ao Max, conferi o pedido com a ficha oficial:\n- " + "\n- ".join(achados)
                     + "\n\nO Max só começa depois da sua escolha.",
            "opcoes": [{"rotulo": "Usar a ficha", "texto": f"{texto}\n\n{MARCA_FICHA}"},
                       {"rotulo": "Seguir mesmo assim", "texto": f"{texto}\n\n{MARCA_SEGUIR}"}],
            "achados": achados}


def nota_no_briefing(texto: str, empresa: str) -> str:
    """Pedido com anexo (não dá para reenviar pelo botão): a conferência vai junto do briefing para o Max."""
    if MARCA_SEGUIR in (texto or "") or MARCA_FICHA in (texto or ""):
        return ""
    achados = divergencias(texto, empresa) if empresas.valida(empresa) and fichas.cita_imovel(texto) else []
    return ("CONFERÊNCIA DE DADOS (automática, antes do Max): " + " ".join(achados)
            + " Onde houver divergência, use a ficha oficial, salvo se o pedido disser claramente o contrário."
            ) if achados else ""


# --- Formulário da Casa Vero: sem campos de valor e com aviso de dado suspeito -------------------------

BLOCO = re.compile(r"<<FORMULARIO>>(.*?)<<FIM DO FORMULARIO>>", re.S)
CAMPO_DE_VALOR = re.compile(r"valor|pre[çc]o|condom[íi]nio|iptu|R\$|di[áa]ria|aluguel|venda|financ|comiss", re.I)
AREA = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)\b")
ZERADO = re.compile(r"\b0\s*(su[íi]tes?|quartos?|pessoas|banheiros?)\b", re.I)
AREA_MINIMA = 20


def suspeitos(ficha: str) -> list[str]:
    """Dado da ficha que parece erro do site (ex.: "2,6 m²", "0 suítes"), para avisar e corrigir no site."""
    achados = [f"área de {a} m²" for a in AREA.findall(ficha or "") if float(a.replace(",", ".")) < AREA_MINIMA]
    achados += [f"\"{m.group(0)}\"" for m in ZERADO.finditer(ficha or "")]
    return list(dict.fromkeys(achados))


def formulario_seguro(resposta: str, empresa: str, pedido: str = "") -> str:
    """Casa Vero: o formulário do agente não pede valor de venda, condomínio, IPTU nem preço (só se o pedido falar
    em valor, decisão 3), e a resposta avisa de dado suspeito na ficha dos imóveis citados."""
    if empresa != "casa_vero" or "<<FORMULARIO>>" not in (resposta or ""):
        return resposta
    tirados: list[str] = []

    def limpar(bloco: re.Match) -> str:
        try:
            dados = json.loads(bloco.group(1))
        except ValueError:
            return bloco.group(0)
        if not isinstance(dados, dict) or not isinstance(dados.get("campos"), list):
            return bloco.group(0)
        ficam = []
        for campo in dados["campos"]:
            texto = f"{campo.get('nome', '')} {campo.get('rotulo', '')}" if isinstance(campo, dict) else ""
            (tirados.append(campo.get("rotulo") or campo.get("nome")) if CAMPO_DE_VALOR.search(texto) else
             ficam.append(campo))
        if len(ficam) == len(dados["campos"]):
            return bloco.group(0)
        if not ficam:
            return ""
        return f"<<FORMULARIO>>{json.dumps({**dados, 'campos': ficam}, ensure_ascii=False)}<<FIM DO FORMULARIO>>"

    texto = resposta if empresas.PEDE_PRECO.search(pedido or "") else BLOCO.sub(limpar, resposta)
    avisos = []
    if tirados:
        avisos.append("Tirei do formulário os campos de valor (" + ", ".join(map(str, tirados[:4])) + "): na Casa "
                      "Vero, valor de venda, condomínio e IPTU não vão para a publicação.")
    for numero in citados(f"{pedido}\n{resposta}", empresa)[:fichas.MAX_FICHAS]:
        if (problemas := suspeitos(fichas.ficha(numero, empresa) or "")):
            avisos.append(f"Dado suspeito na ficha do Vero {numero}: {', '.join(problemas)}. Confira no site antes de "
                          "publicar (e peça a correção do site).")
    if not avisos:
        return texto
    aviso = "\n".join(f"⚠ {a}" for a in avisos)
    if "<<FORMULARIO>>" in texto:
        inicio = texto.index("<<FORMULARIO>>")
        return f"{texto[:inicio].rstrip()}\n\n{aviso}\n\n{texto[inicio:]}"
    return f"{texto.rstrip()}\n\n{aviso}"
