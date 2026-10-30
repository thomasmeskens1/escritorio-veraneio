"""Fichas canônicas dos Lodges (nível 2 da "árvore de compactação" do conhecimento).

Nível 1: regras de ouro (sempre no contexto, agents/perfis.py). Nível 2: esta ficha, montada do documento oficial
do site (resumo, bairro, valores por época, taxa) e colocada INTEIRA no contexto quando o pedido cita o Lodge.
Nível 3: a busca do Cérebro, para o resto.

Stress test: o Designer marcou a capacidade do Lodge 20 como "pendente" porque a busca devolveu trechos sem o
número (os dados ficam espalhados entre site, planilha e acervo). Com a ficha, o essencial chega sempre junto.
"""

import json
import re

import cerebro_base as base
import config

LODGE_CITADO = re.compile(r"\blodges?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)
VERO_CITADO = re.compile(r"\bvero\s*#?0*(\d{1,4})\b", re.IGNORECASE)  # imóveis da Casa Vero: "Vero 87"
# Onde está a ficha de cada empresa (ingestão do site de cada uma; nunca procurar na base de outra).
REF_FICHA = {"casa_veraneio": "site/lodges/lodge-{n}", "cv_corporativo": "corporativo/espacos/lodge-{n}",
             "casa_vero": "vero/imoveis/vero-{n}"}
MAX_FICHAS = 8  # um carrossel pode citar vários imóveis; acima de 3, cada ficha vem mais curta
TAMANHO_FICHA, TAMANHO_FICHA_CURTA = 1800, 900
# Link do site no pedido: a ficha vem pelo próprio link (o agente não abre páginas; teste real: "Lodge 76" com o link
# da Casa Vero ficou sem ficha porque o texto não dizia "Vero 76").
LINK_SITE = re.compile(r"https?://(?:www\.)?(?:casaveroimoveis\.com|corporativo\.casaveraneio\.com|casaveraneio\.com)"
                       r"/[^\s)\]>\"']+", re.IGNORECASE)
# Apelidos provisórios entre empresas, definidos pelo Thomas (ex.: o Vero 90 ainda não está no site da Casa Vero e
# usa os dados do Lodge 90 da Casa Veraneio): {"casa_vero": {"90": {"empresa": "casa_veraneio", "numero": "90"}}}
ARQUIVO_APELIDOS = config.DADOS_DIR / "apelidos_imoveis.json"
CABECALHO = ("FICHAS OFICIAIS DOS IMÓVEIS CITADOS, DESTA EMPRESA (dados do site; valem sobre a conversa anterior e "
             "sobre trechos soltos do Cérebro; reconfira preços antes de publicar):")


def _trechos(ref: str, empresa: str = "casa_veraneio") -> list:
    with base._trava:
        return base.db().execute("SELECT titulo, conteudo FROM conhecimento WHERE ativo = 1 AND fonte_ref = ? "
                                 "AND empresa = ? ORDER BY id", (ref, empresa)).fetchall()


def _da_empresa(numero: str, empresa: str, limite: int = TAMANHO_FICHA) -> str | None:
    """Corporativo e Casa Vero: o documento do site inteiro (já é curto e estruturado)."""
    ref = REF_FICHA.get(empresa)
    return _do_documento(ref.format(n=numero), empresa, limite) if ref else None


def _do_documento(ref: str, empresa: str, limite: int = TAMANHO_FICHA) -> str | None:
    trechos = _trechos(ref, empresa)
    if not trechos:
        return None
    titulo = trechos[0]["titulo"].split(" › ")[0]
    corpo = "\n".join(t["conteudo"] for t in trechos)
    return f"- {titulo}\n  " + "\n  ".join(l.strip() for l in corpo.splitlines() if l.strip())[:limite]


def _do_site(numero: str) -> str | None:
    trechos = _trechos(f"site/lodges/lodge-{numero}")
    if not trechos:
        return None
    linhas = []
    for trecho in trechos:
        for linha in trecho["conteudo"].splitlines():
            linha = linha.strip()
            if linha.startswith(("# ", "Fonte:", "Resumo:", "Bairro:")) or (
                    trecho["titulo"].endswith("Valores por época") and linha.startswith("- ")):
                linhas.append(linha)
    # "Lodge 20 — Praia de Iporanga - SP": o divisor de trechos leva o cabeçalho para o título do trecho.
    titulo = next((l[2:] for l in linhas if l.startswith("# ")), trechos[0]["titulo"].split(" › ")[0])
    corpo = [l for l in linhas if not l.startswith("# ")]
    return f"- {titulo}\n  " + "\n  ".join(dict.fromkeys(corpo))


def _da_planilha(numero: str) -> str | None:
    """Reserva quando o Lodge não está no site: planilha de 2023, sem o endereço exato (nunca publicar)."""
    trechos = _trechos(f"drive/planilha/info-lodges/lodge-{numero}")
    if not trechos:
        return None
    texto = "\n".join(t["conteudo"] for t in trechos)
    fatos = []
    # Do endereço só saem cidade e condomínio (rua e CEP nunca vão para peça). Antes a linha inteira era cortada e
    # a cidade sumia junto: o Social Media perguntou a cidade do Lodge 30, que estava na planilha.
    if (endereco := re.search(r"^Endere[çc]o:\s*(.+)$", texto, re.IGNORECASE | re.MULTILINE)):
        cidade = re.search(r"([A-ZÀ-Úa-zà-ú' .]+?)\s*-\s*([A-Z]{2})\b", endereco.group(1).split(",")[-2]
                           if endereco.group(1).count(",") >= 1 else endereco.group(1))
        if cidade:
            fatos.append(f"Cidade (planilha 2023): {cidade.group(1).strip()} - {cidade.group(2)}")
        if (condominio := re.search(r"condom[ií]nio\s+([^,;\n]+)", endereco.group(1), re.IGNORECASE)):
            fatos.append(f"Condomínio (planilha 2023): {condominio.group(1).strip()}")
    if (capacidade := re.search(r"(\d+)\s*(?:h[óo]spedes|pessoas)", texto, re.IGNORECASE)):
        fatos.append(f"Capacidade (planilha 2023): até {capacidade.group(1)} pessoas")
    if (suites := re.search(r"(\d+)\s*su[íi]tes", texto, re.IGNORECASE)):
        fatos.append(f"Suítes (planilha 2023): {suites.group(1)}")
    configuracao = [l.strip() for l in texto.splitlines() if re.match(r"\s*Su[íi]te \d", l)]
    if configuracao:
        fatos.append("Configuração: " + " ".join(configuracao))
    if (pasta := _pasta_do_acervo(numero)):
        fatos.append(f"Pasta de fotos no acervo: {pasta}")
        cidade_pasta = pasta.split(" - ", 1)[-1].strip() if " - " in pasta else ""
        cidade_planilha = next((f.split(": ", 1)[1].split(" - ")[0] for f in fatos if f.startswith("Cidade")), "")
        if cidade_pasta and cidade_planilha and _sem_acento(cidade_planilha).lower() not in _sem_acento(cidade_pasta).lower():
            fatos.append(f"ATENÇÃO: fontes divergem sobre o local (planilha: {cidade_planilha}; pasta de fotos: "
                         f"{cidade_pasta}). Não escolha sozinho: confirme com o usuário SÓ essa divergência.")
    return (f"- Lodge {numero} (SEM página no site; dados da planilha interna de 2023 e do acervo)\n  "
            + "\n  ".join(fatos or [texto[:400]]))


def _pasta_do_acervo(numero: str) -> str | None:
    """Nome da pasta do Lodge no acervo de fotos (ex.: "LODGE 30 - JARINU ALMARIAS"), que costuma trazer a cidade."""
    with base._trava:
        linha = base.db().execute(
            "SELECT fonte_ref FROM conhecimento WHERE ativo = 1 AND empresa = 'casa_veraneio' AND fonte_tipo = 'drive' "
            "AND fonte_ref LIKE 'drive/lodges/%' AND (fonte_ref LIKE ? OR fonte_ref LIKE ?) LIMIT 1",
            (f"%/LODGE {numero} %", f"%/Lodge {numero}")).fetchone()
    return " ".join(linha["fonte_ref"].rsplit("/", 1)[-1].split()) if linha else None


def _sem_acento(texto: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _apelido(numero: str, empresa: str) -> dict | None:
    try:
        return json.loads(ARQUIVO_APELIDOS.read_text(encoding="utf-8")).get(empresa, {}).get(numero)
    except (OSError, ValueError):
        return None


def ficha(numero: str, empresa: str = "casa_veraneio", limite: int = TAMANHO_FICHA) -> str | None:
    numero = str(int(numero))
    if empresa != "casa_veraneio":
        achada = _da_empresa(numero, empresa, limite)
        if achada or not (apelido := _apelido(numero, empresa)):
            return achada
        # Apelido definido pelo Thomas: o mesmo imóvel cadastrado em outra empresa, até entrar no site desta.
        origem = ficha(apelido["numero"], apelido["empresa"], limite)
        # Sem diárias, temporadas e taxas de hospedagem: não valem para a outra empresa.
        origem = origem and "\n".join(l for l in origem.splitlines()
                                      if not re.search(r"di[aá]ria|temporada|taxa de ativa|estadia", l, re.I))
        rotulo = "Vero" if empresa == "casa_vero" else "Lodge"
        return origem and (f"- {rotulo} {numero} (cadastro provisório definido pelo Thomas: os dados abaixo são do "
                           f"Lodge {apelido['numero']} da empresa {apelido['empresa']}; use descrição, localização "
                           f"e características; NUNCA diárias, temporadas ou regras de hospedagem)\n  {origem[2:]}")
    texto = _do_site(numero) or _da_planilha(numero)
    return texto and texto[:limite]


def _ref_do_link(link: str) -> tuple[str, str] | None:
    """(fonte_ref, empresa) do documento do site cuja linha "Fonte:" traz este link."""
    caminho = re.sub(r"^https?://(?:www\.)?", "", link.strip().rstrip("/.,;")).split("?")[0]
    with base._trava:
        linhas = base.db().execute("SELECT fonte_ref, empresa, conteudo FROM conhecimento WHERE ativo = 1 AND "
                                   "conteudo LIKE ? ORDER BY id LIMIT 50", (f"%Fonte: %{caminho}%",)).fetchall()
    # Só a página exata: "casaveraneio.com/lodges" (a listagem) não pode casar com ".../lodges/lodge-112".
    # Teste real (29/10/2026): a listagem casou com uma ficha "lodge-orlando" e o número virou erro em todo modelo.
    exato = re.compile(rf"Fonte: \S*{re.escape(caminho)}(?![\w/-])")
    linha = next((l for l in linhas if exato.search(l["conteudo"])), None)
    return (linha["fonte_ref"], linha["empresa"]) if linha else None


def _numero_da_ref(ref: str) -> str:
    return ref.rsplit("-", 1)[-1]


def cita_imovel(texto: str) -> bool:
    """O texto cita algum imóvel (Lodge N, Vero N ou link de imóvel de um dos sites)?"""
    texto = texto or ""
    return bool(LODGE_CITADO.search(texto) or VERO_CITADO.search(texto) or LINK_SITE.search(texto))


def fichas_citadas(texto: str, empresa: str = "casa_veraneio") -> str:
    """Fichas dos imóveis citados (pelo número ou pelo link do site) da empresa do trabalho; "" se nenhum.
    Link de OUTRA empresa mandado pelo usuário: a ficha entra marcada como exceção autorizada por ele.
    Citado pelo número e sem ficha nessa empresa: o agente é avisado para não usar dado de outra empresa nem inventar."""
    texto = texto or ""
    if empresa == "*":  # trabalho das três empresas (ex.: Estrategista): as fichas de cada uma, separadas
        import empresas

        blocos = [f"EMPRESA: {empresas.nome(e)}\n{f}" for e in REF_FICHA if (f := fichas_citadas(texto, e))]
        return "\n\n".join(blocos)
    links = list(dict.fromkeys(LINK_SITE.findall(texto)))[:MAX_FICHAS]
    # Na Casa Vero, "Lodge 76" é o Vero 76 (mesma numeração do grupo).
    padroes = [VERO_CITADO, LODGE_CITADO] if empresa == "casa_vero" else [LODGE_CITADO]
    sem_links = LINK_SITE.sub(" ", texto)
    numeros = list(dict.fromkeys(str(int(n)) for p in padroes for n in p.findall(sem_links)))[:MAX_FICHAS]
    if not numeros and not links:
        return ""
    limite = TAMANHO_FICHA if len(numeros) <= 3 else TAMANHO_FICHA_CURTA
    linhas, cobertos, outras = [], set(), []
    for link in links:
        if not (achado := _ref_do_link(link)) or not _numero_da_ref(achado[0]).isdigit():
            continue  # sem ficha, ou página sem número de imóvel (ex.: lodge-orlando, fora da busca)
        ref, dona = achado
        if dona == empresa:
            cobertos.add(_numero_da_ref(ref))
            linhas.append(ficha(_numero_da_ref(ref), dona, limite) if dona == "casa_veraneio"
                          else _do_documento(ref, dona, limite))
        else:
            outras.append((link, ref, dona))
    achadas = {n: ficha(n, empresa, limite) for n in numeros if n not in cobertos}
    linhas += [f for f in achadas.values() if f]
    faltando = [n for n, f in achadas.items() if not f]
    for link, ref, dona in outras:
        numero = _numero_da_ref(ref)
        if achadas.get(numero) and _apelido(numero, empresa):  # já veio pelo cadastro provisório (ex.: Vero 90)
            continue
        dados = (ficha(numero, dona, limite) if dona == "casa_veraneio" else _do_documento(ref, dona, limite)) or ""
        linhas.append(f"- EXCEÇÃO AUTORIZADA PELO USUÁRIO: ele mandou o link {link}, que é de OUTRA empresa ({dona}), "
                      "para usar neste trabalho. Use só descrição, localização e características; nunca preços, "
                      f"diárias ou condições da outra empresa.\n  {dados[2:]}")
        faltando = [n for n in faltando if n != numero]
    if faltando:
        rotulo = "Vero" if empresa == "casa_vero" else "Lodge"
        linhas.append(f"- SEM FICHA nesta empresa: {', '.join(f'{rotulo} {n}' for n in faltando)}. Não use dados de "
                      "outra empresa com o mesmo nome nem invente: pergunte ao usuário com um formulário.")
    linhas = [l for l in linhas if l]
    return f"{CABECALHO}\n" + "\n".join(linhas) if linhas else ""
