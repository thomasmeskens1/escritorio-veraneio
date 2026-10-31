"""Catálogo de imóveis em tabela (cerebro-01): listas, contagens e filtros completos, na hora e sem IA.

A busca do Cérebro devolve 6 a 9 pedaços de texto; num pedido de lista ("todas as cidades onde tenho Lodges",
"quais recebem 16 pessoas") ele via uns 10 dos 257 Lodges, inventava linhas e errava o total (tarefas 90 a 92,
29/10/2026). Aqui os documentos que a coleta do site e da planilha já manda ao Cérebro viram linhas de uma tabela de
verdade ("imoveis"), por empresa, e o pedido de lista é respondido por consulta direta, com o total conferido e a
data da coleta. SEM PREÇO: diárias, taxas e valores ficam fora da tabela (empresas.sem_precos e regra 3).

A tabela é refeita sozinha quando a base muda (assinatura: quantidade e maior id dos trechos de origem). Por ora só
a Casa Veraneio tem a tabela; Corporativo e Casa Vero entram em ORIGENS quando o formato dos sites deles for
conferido (cada empresa na sua linha, nunca misturadas).
"""

import re
import threading

from fastapi import APIRouter, Header, HTTPException

import cerebro_base as base
import empresas
from cerebro_texto import sem_acento

# Empresa -> (prefixo do documento do site, prefixo da planilha interna). Corp e Vero: depois (ver docstring).
ORIGENS = {"casa_veraneio": ("site/lodges/lodge-", "drive/planilha/info-lodges/lodge-")}
ROTULO = {"casa_veraneio": "Lodge", "cv_corporativo": "Lodge", "casa_vero": "Vero"}
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
ESTADOS = {"sao paulo": "SP", "rio de janeiro": "RJ", "minas gerais": "MG", "santa catarina": "SC", "parana": "PR",
           "bahia": "BA", "espirito santo": "ES", "goias": "GO", "pernambuco": "PE", "rio grande do sul": "RS",
           "ceara": "CE", "alagoas": "AL", "rio grande do norte": "RN", "paraiba": "PB", "sergipe": "SE",
           "mato grosso do sul": "MS", "mato grosso": "MT", "distrito federal": "DF", "florida": "FL"}
MAX_LINHAS_CHAT, MAX_CARACTERES_FERRAMENTA = 300, 6000
LISTA_NA_CONTAGEM = 40  # "quantos..." com mais que isso: contagem por cidade em vez da lista inteira

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS imoveis (
    empresa TEXT NOT NULL, numero INTEGER NOT NULL, nome TEXT, cidade TEXT, uf TEXT, bairro TEXT,
    quartos INTEGER, suites INTEGER, banheiros INTEGER, pessoas INTEGER, categorias TEXT, comodidades TEXT,
    link TEXT, fonte TEXT NOT NULL,          -- site | planilha (Lodge fora do site, dados internos de 2023)
    coletado_em TEXT, PRIMARY KEY (empresa, numero));
CREATE TABLE IF NOT EXISTS imoveis_coleta (
    empresa TEXT PRIMARY KEY, assinatura TEXT NOT NULL, montada_em TEXT NOT NULL, coletado_em TEXT,
    total_no_site INTEGER);
"""
_trava = threading.Lock()
_pronto = False


def _db():
    global _pronto
    conexao = base.db()
    if not _pronto:
        with base._trava:
            conexao.executescript(_ESQUEMA)
        _pronto = True
    return conexao


# --- Montagem a partir da base do Cérebro ------------------------------------------------------------

def _int(texto) -> int | None:
    return int(texto) if texto and str(texto).isdigit() else None


def _uf(estado: str) -> str:
    estado = (estado or "").strip()
    return estado.upper() if estado.upper() in UFS or estado.upper() == "FL" else ESTADOS.get(sem_acento(estado), estado)


def _documentos(empresa: str, prefixo: str) -> dict[int, dict]:
    """{número: {"texto", "secoes", "atualizado"}} dos documentos ativos com esse prefixo (trechos juntados)."""
    with base._trava:
        linhas = base.db().execute(
            "SELECT fonte_ref, titulo, conteudo, atualizado_em FROM conhecimento WHERE ativo = 1 AND empresa = ? "
            "AND fonte_ref LIKE ? ORDER BY id", (empresa, prefixo + "%")).fetchall()
    docs: dict[int, dict] = {}
    for l in linhas:
        if (numero := _int(l["fonte_ref"][len(prefixo):])) is None:
            continue  # lodge-orlando e outras páginas sem número ficam fora da tabela
        doc = docs.setdefault(numero, {"titulo": l["titulo"].split(" › ")[0], "texto": "", "secoes": {},
                                       "atualizado": ""})
        secao = l["titulo"].split(" › ")[-1] if " › " in l["titulo"] else ""
        doc["secoes"][secao] = (doc["secoes"].get(secao, "") + "\n" + l["conteudo"]).strip()
        doc["texto"] += "\n" + l["conteudo"]
        doc["atualizado"] = max(doc["atualizado"], l["atualizado_em"] or "")
    return docs


def _do_site(numero: int, doc: dict) -> dict:
    """Linha da tabela a partir do documento do site (formato de scripts/max/site_api.py e site_lodges.py)."""
    texto = doc["texto"]
    cabecalho = next((l[2:] for l in texto.splitlines() if l.startswith("# ")), doc["titulo"])
    nome, _, local = cabecalho.partition(" — ")
    cidade, _, estado = local.rpartition(" - ") if " - " in local else (local, "", "")
    resumo = next((l for l in texto.splitlines() if l.startswith("Resumo:")), "")
    achar = lambda padrao, onde=resumo: _int(m.group(1)) if (m := re.search(padrao, onde, re.I)) else None
    categorias = (m.group(1).strip() if (m := re.search(r"categoria:\s*([^|\n]+)", resumo, re.I)) else "")
    acomodacoes = doc["secoes"].get("Acomodações", "")
    suites = achar(r"(\d+)\s*su[íi]tes", f"{resumo}\n{acomodacoes}")
    if suites is None and (rotulos := set(re.findall(r"su[íi]te\s*(\d+)", acomodacoes, re.I))):
        suites = len(rotulos)  # "Suíte 1 = ...", "Suíte 2 = ..."
    link = (m.group(1) if (m := re.search(r"Fonte:\s*(https?://\S+)", texto)) else "")
    bairro = next((l.split(":", 1)[1].strip() for l in texto.splitlines() if l.startswith("Bairro:")), "")
    return {"numero": numero, "nome": nome.strip() or f"Lodge {numero}", "cidade": cidade.strip(), "uf": _uf(estado),
            "bairro": bairro, "quartos": achar(r"(\d+)\s*quartos?"), "suites": suites,
            "banheiros": achar(r"(\d+)\s*banheiros?"), "pessoas": achar(r"at[ée]\s*(\d+)\s*pessoas"),
            "categorias": categorias, "comodidades": doc["secoes"].get("Comodidades", "").replace("\n", " ")[:600],
            "link": link, "fonte": "site", "coletado_em": doc["atualizado"]}


def _da_planilha(numero: int, doc: dict) -> dict:
    """Lodge que está só na planilha de 2023: cidade, suítes e capacidade (endereço exato nunca entra)."""
    import fichas  # mesma leitura de endereço da ficha (só cidade e UF)

    ficha = fichas._da_planilha(str(numero)) or ""
    achar = lambda padrao: m.group(1).strip() if (m := re.search(padrao, ficha)) else ""
    cidade, _, uf = achar(r"Cidade \(planilha 2023\): (.+)").rpartition(" - ")
    return {"numero": numero, "nome": f"Lodge {numero}", "cidade": cidade, "uf": uf, "bairro": "",
            "quartos": None, "suites": _int(achar(r"Suítes \(planilha 2023\): (\d+)")), "banheiros": None,
            "pessoas": _int(achar(r"até (\d+) pessoas")), "categorias": "", "comodidades": "", "link": "",
            "fonte": "planilha", "coletado_em": doc["atualizado"]}


def _assinatura(empresa: str) -> str:
    partes = []
    with base._trava:
        for prefixo in ORIGENS.get(empresa, ()):
            n, maior = base.db().execute("SELECT COUNT(*), MAX(id) FROM conhecimento WHERE ativo = 1 AND empresa = ? "
                                         "AND fonte_ref LIKE ?", (empresa, prefixo + "%")).fetchone()
            partes.append(f"{n}:{maior}")
        resumo = base.db().execute("SELECT MAX(id) FROM conhecimento WHERE ativo = 1 AND fonte_ref = 'site/resumo-lodges' "
                                   "AND empresa = ?", (empresa,)).fetchone()[0]
    return "|".join(partes) + f"|{resumo}"


def _total_no_site(empresa: str) -> int | None:
    """"Lodges: 257" do resumo que a coleta do site grava: confere o total da tabela."""
    with base._trava:
        linhas = base.db().execute("SELECT conteudo FROM conhecimento WHERE ativo = 1 AND fonte_ref = 'site/resumo-lodges' "
                                   "AND empresa = ? ORDER BY id", (empresa,)).fetchall()
    achado = next((m for l in linhas if (m := re.search(r"^Lodges:\s*(\d+)", l["conteudo"], re.M))), None)
    return int(achado.group(1)) if achado else None


def atualizar(empresa: str = "casa_veraneio", forcar: bool = False) -> bool:
    """Refaz a tabela da empresa se a base mudou desde a última montagem. Devolve True se refez."""
    if empresa not in ORIGENS:
        return False
    with _trava:
        assinatura = _assinatura(empresa)
        atual = _db().execute("SELECT assinatura FROM imoveis_coleta WHERE empresa = ?", (empresa,)).fetchone()
        if atual and atual["assinatura"] == assinatura and not forcar:
            return False
        prefixo_site, prefixo_planilha = ORIGENS[empresa]
        linhas = {n: _do_site(n, d) for n, d in _documentos(empresa, prefixo_site).items()}
        for numero, doc in _documentos(empresa, prefixo_planilha).items():
            linhas.setdefault(numero, _da_planilha(numero, doc))
        coletado = max((l["coletado_em"] for l in linhas.values() if l["fonte"] == "site"), default="")
        colunas = ("numero", "nome", "cidade", "uf", "bairro", "quartos", "suites", "banheiros", "pessoas",
                   "categorias", "comodidades", "link", "fonte", "coletado_em")
        with base._trava, _db() as conexao:
            conexao.execute("DELETE FROM imoveis WHERE empresa = ?", (empresa,))
            conexao.executemany(f"INSERT INTO imoveis (empresa, {', '.join(colunas)}) VALUES (?{', ?' * len(colunas)})",
                                [(empresa, *(l[c] for c in colunas)) for l in linhas.values()])
            conexao.execute("INSERT OR REPLACE INTO imoveis_coleta VALUES (?, ?, ?, ?, ?)",
                            (empresa, assinatura, base.agora(), coletado, _total_no_site(empresa)))
        return True


# --- Consulta ------------------------------------------------------------------------------------

def _data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else "—"


def linha(numero: int | str, empresa: str = "casa_veraneio") -> dict | None:
    """A linha de um imóvel (para a conferência de dados do pedido); None se não está na tabela."""
    atualizar(empresa)
    with base._trava:
        achada = _db().execute("SELECT * FROM imoveis WHERE empresa = ? AND numero = ?",
                               (empresa, int(numero))).fetchone()
    return dict(achada) if achada else None


def cidades(empresa: str = "casa_veraneio") -> set[str]:
    atualizar(empresa)
    with base._trava:
        return {l[0] for l in _db().execute("SELECT DISTINCT cidade FROM imoveis WHERE empresa = ? AND cidade != ''",
                                            (empresa,))}


def filtrar(empresa: str = "casa_veraneio", cidade: str = "", uf: str = "", suites_min: int | None = None,
            quartos_min: int | None = None, pessoas_min: int | None = None, pessoas_max: int | None = None,
            categoria: str = "", comodidade: str = "", orlando: bool = False) -> dict | None:
    """Imóveis que passam nos filtros, com o total da base e a data da coleta; None se a empresa não tem tabela."""
    if empresa not in ORIGENS:
        return None
    atualizar(empresa)
    with base._trava:
        todas = [dict(l) for l in _db().execute("SELECT * FROM imoveis WHERE empresa = ? ORDER BY numero", (empresa,))]
        coleta = _db().execute("SELECT * FROM imoveis_coleta WHERE empresa = ?", (empresa,)).fetchone()
    if not orlando:  # Lodges de Orlando: só quando citados (mesma regra da busca)
        todas = [l for l in todas if "orlando" not in sem_acento(f"{l['cidade']} {l['nome']}")]
    contem = lambda campo, alvo: sem_acento(alvo) in sem_acento(campo or "")
    achadas = [l for l in todas
               if (not cidade or sem_acento(l["cidade"] or "") == sem_acento(cidade))
               and (not uf or (l["uf"] or "").upper() == uf.upper())
               and (suites_min is None or (l["suites"] or 0) >= suites_min)
               and (quartos_min is None or (l["quartos"] or 0) >= quartos_min)
               and (pessoas_min is None or (l["pessoas"] or 0) >= pessoas_min)
               and (pessoas_max is None or (l["pessoas"] is not None and l["pessoas"] <= pessoas_max))
               and (not categoria or contem(l["categorias"], categoria))
               and (not comodidade or contem(f"{l['comodidades']} {l['categorias']}", comodidade))]
    return {"empresa": empresa, "linhas": achadas, "total": len(achadas),
            "total_base": len(todas), "no_site": sum(l["fonte"] == "site" for l in todas),
            "total_no_site": coleta["total_no_site"] if coleta else None,
            "sem_cidade": sum(not l["cidade"] for l in achadas),
            "coletado_em": _data(coleta["coletado_em"]) if coleta else "—"}


# --- Pedido em linguagem natural -> filtros ---------------------------------------------------------

PEDE_LISTA = re.compile(r"\b(quant[oa]s|tod[oa]s\s+(?:os|as)|liste|listar|lista\s+(?:de|dos|das|completa|com)|"
                        r"rela[çc][ãa]o\s+(?:de|dos|das|completa)|por\s+(?:cidade|estado|uf|regi[ãa]o)|planilha|"
                        r"tabela|quais\s+(?:s[ãa]o\s+)?(?:os\s+|as\s+)?(?:lodges|casas|im[óo]veis))\b", re.I)
FALA_DE_IMOVEL = re.compile(r"\b(lodges?|casas?|im[óo]veis|im[óo]vel|propriedades|cidades)\b", re.I)
# Pedido de UM Lodge ("o Lodge 20 tem quantas suítes?") é da ficha, não da lista.
UM_IMOVEL = re.compile(r"\b(?:lodge|vero)\s*#?\d{1,4}\b", re.I)
_NUMERO = r"(\d{1,3})"
_ANTES_MIN = r"(?:para|pra|com|acima\s+de|mais\s+de|a\s+partir\s+de|pelo\s+menos|m[íi]nimo\s+de|recebem|cabem)?\s*"
COMODIDADES = ("piscina", "pet", "churrasqueira", "sauna", "jacuzzi", "hidromassagem", "lareira", "quadra",
               "beach tennis", "academia", "spa", "praia", "lago", "cachoeira")


def _limite(texto: str, unidade: str) -> tuple[int | None, int | None]:
    """(mínimo, máximo) para "12 ou mais pessoas", "acima de 20 pessoas", "até 10 pessoas", "16 pessoas"."""
    if (m := re.search(rf"at[ée]\s+{_NUMERO}\s*{unidade}", texto, re.I)):
        return None, int(m.group(1))
    if (m := re.search(rf"(acima\s+de|mais\s+de)\s+{_NUMERO}\s*{unidade}", texto, re.I)):
        return int(m.group(2)) + 1, None
    if (m := re.search(rf"{_ANTES_MIN}{_NUMERO}\s*(?:ou\s+mais\s+)?{unidade}", texto, re.I)):
        return int(m.group(1)), None
    return None, None


def interpretar(texto: str, empresa: str = "casa_veraneio") -> dict | None:
    """Filtros do pedido de lista/contagem; None se não é um pedido desse tipo (vai para a busca normal)."""
    texto = texto or ""
    if not (PEDE_LISTA.search(texto) and FALA_DE_IMOVEL.search(texto)) or UM_IMOVEL.search(texto):
        return None
    filtros: dict = {"orlando": "orlando" in texto.lower()}
    filtros["pessoas_min"], filtros["pessoas_max"] = _limite(texto, r"(?:pessoas|h[óo]spedes)")
    filtros["suites_min"] = _limite(texto, r"su[íi]tes")[0]
    filtros["quartos_min"] = _limite(texto, r"quartos")[0]
    normal = f" {sem_acento(texto)} "
    achada = sorted((c for c in cidades(empresa) if re.search(rf"\b{re.escape(sem_acento(c))}\b", normal)), key=len)
    filtros["cidade"] = achada[-1] if achada else ""  # "Praia de Iporanga" vence "Iporanga"
    uf = re.search(r"(?:\b(?:em|no|na|de|do|da)\s+|/\s*|-\s*)([A-Z]{2})\b", texto)
    estado = next((s for nome, s in ESTADOS.items() if re.search(rf"\b(?:estado\s+d[eo]\s+|em\s+)?{nome}\b", normal)
                   and sem_acento(filtros["cidade"]) != nome), "")
    filtros["uf"] = uf.group(1) if uf and uf.group(1) in UFS else ("" if filtros["cidade"] else estado)
    filtros["comodidade"] = next((c for c in COMODIDADES if re.search(rf"\b{c}\b", normal)), "")
    filtros["agrupar"] = ("uf" if re.search(r"\bpor\s+(estado|uf)\b", normal) else
                          "cidade" if re.search(r"\b(por\s+cidade|quais\s+cidades|cidades\s+onde|em\s+que\s+cidades)\b",
                                                normal) else "")
    filtros["so_contagem"] = bool(re.search(r"\bquant[oa]s\b", normal)) and not re.search(
        r"\b(liste|listar|lista|quais|tabela|planilha|relacao)\b", normal)
    return filtros


def _descricao(filtros: dict) -> str:
    partes = [f"cidade {filtros['cidade']}" if filtros.get("cidade") else "",
              f"UF {filtros['uf']}" if filtros.get("uf") else "",
              f"{filtros['pessoas_min']}+ pessoas" if filtros.get("pessoas_min") else "",
              f"até {filtros['pessoas_max']} pessoas" if filtros.get("pessoas_max") else "",
              f"{filtros['suites_min']}+ suítes" if filtros.get("suites_min") else "",
              f"{filtros['quartos_min']}+ quartos" if filtros.get("quartos_min") else "",
              f"com {filtros['comodidade']}" if filtros.get("comodidade") else ""]
    return ", ".join(p for p in partes if p)


def _celula(valor) -> str:
    return "—" if valor in (None, "") else str(valor).replace("|", "/")


def responder(texto: str, empresa: str = "casa_veraneio", limite: int | None = None) -> str | None:
    """Resposta pronta (markdown) para pedido de lista/contagem/filtro; None se não é esse tipo de pedido ou se a
    empresa ainda não tem tabela. `limite`: tamanho máximo (ferramenta dos agentes)."""
    if empresa not in ORIGENS or not (filtros := interpretar(texto, empresa)):
        return None
    chaves = ("cidade", "uf", "suites_min", "quartos_min", "pessoas_min", "pessoas_max", "comodidade", "orlando")
    resultado = filtrar(empresa, **{k: filtros[k] for k in chaves})
    if not resultado or not resultado["total_base"]:
        return None  # tabela vazia (coleta ainda não chegou): a busca normal responde
    rotulo, nome_empresa = ROTULO[empresa], empresas.nome(empresa)
    filtro = _descricao(filtros)
    conferido = (f"{resultado['no_site']} de {resultado['total_no_site']} do resumo do site"
                 if resultado["total_no_site"] else f"{resultado['no_site']} no site")
    topo = (f"**{resultado['total']} {rotulo}s da {nome_empresa}**" + (f" com o filtro: {filtro}" if filtro else "")
            + f" (base: {resultado['total_base']} {rotulo}s na tabela; {conferido}).")
    linhas = resultado["linhas"]
    # Agrupado ("por cidade", "quais cidades") ou contagem grande: uma linha por cidade/UF. Senão: a lista inteira.
    agrupar = filtros["agrupar"] or ("cidade" if filtros["so_contagem"] and len(linhas) > LISTA_NA_CONTAGEM else "")
    corpo: list[str] = []
    if agrupar:
        grupos: dict[str, int] = {}
        for l in linhas:
            chave = (f"{l['cidade']} / {l['uf']}" if agrupar == "cidade" and l["cidade"] else l[agrupar]) or "—"
            grupos[chave] = grupos.get(chave, 0) + 1
        corpo = [f"| {'Cidade / UF' if agrupar == 'cidade' else 'UF'} | {rotulo}s |", "|---|---:|"]
        corpo += [f"| {_celula(c)} | {n} |" for c, n in sorted(grupos.items(), key=lambda g: (-g[1], g[0]))]
    else:
        corpo = [f"| {rotulo} | Cidade / UF | Bairro | Quartos | Suítes | Pessoas | Categorias | Fonte |",
                 "|---:|---|---|---:|---:|---:|---|---|"]
        for l in linhas[:MAX_LINHAS_CHAT]:
            local = f"{l['cidade']} / {l['uf']}" if l["cidade"] else "—"
            fonte = "fora do site (planilha 2023)" if l["fonte"] == "planilha" else (l["link"] or "site")
            corpo.append(f"| {l['numero']} | {_celula(local)} | {_celula(l['bairro'])} | {_celula(l['quartos'])} | "
                         f"{_celula(l['suites'])} | {_celula(l['pessoas'])} | {_celula(l['categorias'])} | {fonte} |")
        if len(linhas) > MAX_LINHAS_CHAT:
            corpo.append(f"\n(mostrando {MAX_LINHAS_CHAT} de {len(linhas)}; refine o filtro para ver o resto)")
    notas = [f"Fonte: site, coleta de {resultado['coletado_em']}"
             + (" (os marcados \"fora do site\" vêm da planilha interna de 2023)" if any(
                 l["fonte"] == "planilha" for l in linhas) else "") + ". Reconfira antes de publicar. Sem preços."]
    if resultado["sem_cidade"]:
        notas.append(f"{resultado['sem_cidade']} {rotulo}(s) sem cidade cadastrada aparecem como \"—\".")
    resposta = "\n".join([topo, "", *corpo, "", *notas]).replace("\n\n\n", "\n\n")
    if limite and len(resposta) > limite:
        corte = resposta[:limite].rsplit("\n", 1)[0]
        resposta = (f"{corte}\n\n(lista cortada para caber aqui: {resultado['total']} no total; peça um filtro mais "
                    f"específico, ex.: cidade ou número de pessoas)\n{notas[0]}")
    return resposta


# --- API (consulta com filtros; sem preço, então vale para qualquer usuário logado) ----------------------

rotas = APIRouter()


@rotas.get("/imoveis")
def listar(empresa: str = "casa_veraneio", cidade: str = "", uf: str = "", suites_min: int | None = None,
           quartos_min: int | None = None, pessoas_min: int | None = None, pessoas_max: int | None = None,
           categoria: str = "", comodidade: str = "", authorization: str = Header("")):
    from auth import validar_token

    if not validar_token(authorization.removeprefix("Bearer ").strip()):
        raise HTTPException(status_code=401, detail="Token inválido")
    if not empresas.valida(empresa):
        raise HTTPException(status_code=422, detail="Empresa inválida.")
    resultado = filtrar(empresa, cidade[:80], uf[:2], suites_min, quartos_min, pessoas_min, pessoas_max,
                        categoria[:40], comodidade[:40])
    if resultado is None:
        return {"empresa": empresa, "disponivel": False,
                "mensagem": f"A tabela da {empresas.nome(empresa)} ainda não foi montada (fica para a próxima etapa)."}
    return {**resultado, "disponivel": True}
