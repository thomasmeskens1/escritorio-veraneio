"""Conferências da prospecção feitas em código, sem IA (N2-prospectador-35 e -06).

Fonte do contato (prospectador-35): a regra "só canais da empresa" (comercial.REGRAS_CONTATO) dependia de o Max
obedecer. Agora cada fonte precisa ser um endereço http(s); ao menos uma tem de ser do site da empresa ou de uma fonte
pública aceita (cadastro de CNPJ, governo, imprensa); fonte de perfil pessoal (LinkedIn /in/) derruba o e-mail e o
telefone. O endereço é gravado sem parâmetros de rastreio (utm etc.).

Possível cliente (prospectador-06): a trava contra repetição compara o nome e o domínio exatos. Um cliente com outra
razão social, outra marca do mesmo grupo ou outro domínio (.com em vez de .com.br) voltava como "empresa nova". Agora
ele ganha na prévia o aviso "possível cliente: confira" (nunca a recusa automática: quem decide é a equipe). Os grupos
de nomes equivalentes ficam em dados/apelidos_empresas.json (local, fora do git, no padrão de apelidos_imoveis.json).
"""

import json
import logging
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import config

log = logging.getLogger(__name__)

ARQUIVO_APELIDOS = config.DADOS_DIR / "apelidos_empresas.json"
AVISO_POSSIVEL_CLIENTE = "possível cliente: confira (nome ou site parecido com uma empresa que já está no CRM)"
AVISO_MESMO_GRUPO = "possível cliente: confira (do mesmo grupo de uma empresa que já está no CRM)"
AVISO_SEM_FONTE = "canal sem fonte da empresa: e-mail e telefone removidos"
AVISO_PERFIL_PESSOAL = "canal com fonte de perfil pessoal: e-mail e telefone removidos"

# Perfil de pessoa e página de busca não provam que o canal é da empresa.
PERFIL_PESSOAL = re.compile(r"(^|\.)linkedin\.com/(in|pub)/", re.I)
PAGINA_DE_BUSCA = re.compile(r"(^|\.)(google\.[a-z.]+/search|bing\.com/search|duckduckgo\.com/|search\.yahoo\.)", re.I)
# Fontes públicas aceitas além do site da empresa: cadastro de CNPJ, governo e imprensa de negócios (lista curta).
FONTES_PUBLICAS = ("gov.br", "cnpj.biz", "casadosdados.com.br", "cnpja.com", "cnpj.info", "econodata.com.br",
                   "valor.globo.com", "exame.com", "estadao.com.br", "folha.uol.com.br", "g1.globo.com",
                   "infomoney.com.br", "forbes.com.br", "istoedinheiro.com.br")
PAGINA_DA_EMPRESA_NO_LINKEDIN = re.compile(r"(^|\.)linkedin\.com/company/", re.I)
RASTREIO = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|mc_cid|mc_eid|igshid|ref|ref_src|_hs\w+)$", re.I)
SUFIXOS = {"com.br", "net.br", "org.br", "ind.br", "art.br", "eng.br", "emp.br", "co.uk", "com.ar", "com.mx"}
# Palavras de nome que muitos clientes e prospects dividem: não bastam para dizer "parecido".
COMUNS = frozenset((
    "grupo brasil brasileira industria industrias comercio servicos consultoria tecnologia solucoes digital global "
    "alimentos foods energia logistica transportes farma saude engenharia seguros investimentos participacoes "
    "holding automotiva quimica construtora incorporadora educacao sistemas software telecom agro agricola "
    "distribuidora importadora exportadora metalurgica plasticos embalagens cosmeticos hospitalar laboratorio "
    "capital partners group company international internacional nacional america latina corporativo eventos").split())


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def dominio(texto: str) -> str:
    achou = re.search(r"(?:@|//|^)(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", (texto or "").lower().strip())
    return achou.group(1) if achou else ""


def base_do_dominio(dominio_: str) -> str:
    """"www.empresa.com.br", "empresa.com" e "rh.empresa.com.br" -> "empresa"."""
    partes = [p for p in (dominio_ or "").lower().removeprefix("www.").split(".") if p]
    if len(partes) >= 3 and ".".join(partes[-2:]) in SUFIXOS:
        return partes[-3]
    return partes[-2] if len(partes) >= 2 else ""


# --- Fonte do contato (prospectador-35) ------------------------------------------------------------------------

def limpar_fonte(fonte) -> str:
    """Endereço http(s) sem parâmetros de rastreio; "" se não for um endereço válido."""
    texto = str(fonte or "").strip()
    partes = urlsplit(texto)
    if partes.scheme not in ("http", "https") or not dominio(partes.netloc or ""):
        return ""
    consulta = urlencode([(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True) if not RASTREIO.match(k)])
    return urlunsplit((partes.scheme, partes.netloc.lower(), partes.path, consulta, ""))


def _da_empresa(fonte: str, site: str) -> bool:
    alvo, origem = dominio(site), dominio(urlsplit(fonte).netloc)
    if alvo and (origem == alvo or origem.endswith(f".{alvo}") or base_do_dominio(origem) == base_do_dominio(alvo)):
        return True
    sem_esquema = fonte.split("//", 1)[-1]
    if PAGINA_DA_EMPRESA_NO_LINKEDIN.search(sem_esquema):
        return True
    return any(origem == f or origem.endswith(f".{f}") for f in FONTES_PUBLICAS)


def conferir_fontes(lead: dict) -> str:
    """Limpa as fontes do lead e devolve o aviso quando o canal não tem fonte da empresa ("" se está tudo certo).
    Quem chama remove o e-mail e o telefone quando volta aviso."""
    brutas = lead.get("fontes") or []
    brutas = [brutas] if isinstance(brutas, str) else brutas if isinstance(brutas, list) else []
    fontes = [f for f in dict.fromkeys(limpar_fonte(b) for b in brutas) if f]
    lead["fontes"] = [f for f in fontes if not PAGINA_DE_BUSCA.search(f.split("//", 1)[-1])]
    if any(PERFIL_PESSOAL.search(f.split("//", 1)[-1]) for f in lead["fontes"]):
        return AVISO_PERFIL_PESSOAL
    if not any(_da_empresa(f, str(lead.get("site") or "")) for f in lead["fontes"]):
        return AVISO_SEM_FONTE
    return ""


# --- Possível cliente (prospectador-06) ------------------------------------------------------------------------

def _chave(nome: str) -> str:
    import comercial  # mesma chave da trava contra repetição

    return comercial._chave(nome)


def apelidos() -> list[set[str]]:
    """Grupos de nomes e domínios equivalentes: {"qualquer rótulo": ["Nome A", "Marca B", "empresa.com.br"]} ou uma
    lista de listas. Arquivo ausente ou com defeito: nenhum grupo (a prospecção segue)."""
    if not ARQUIVO_APELIDOS.exists():
        return []
    try:
        dados = json.loads(ARQUIVO_APELIDOS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        log.warning("Apelidos de empresas ilegíveis (%s): ignorados.", erro)
        return []
    listas = dados.values() if isinstance(dados, dict) else dados if isinstance(dados, list) else []
    grupos = []
    for lista in listas:
        if isinstance(lista, list):
            grupo = {dominio(i) if "." in str(i) and " " not in str(i).strip() else _chave(str(i)) for i in lista}
            if len(grupo - {""}) >= 2:
                grupos.append(grupo - {""})
    return grupos


def _palavras(nome: str) -> list[str]:
    import carteira

    return [t for t in re.findall(r"[a-z0-9]+", _normal(re.sub(r"^\s*\d+\s*-\s*", "", nome or "")))
            if len(t) >= 5 and t not in COMUNS and t not in carteira.GENERICAS]


def aviso_possivel_cliente(nome: str, site: str, nomes: set[str], dominios: set[str],
                           grupos: list[set[str]] | None = None) -> str:
    """Aviso para um lead que NÃO é igual a um conhecido mas parece ser ("" quando não parece)."""
    chave, dominio_ = _chave(nome), dominio(site)
    grupos = apelidos() if grupos is None else grupos
    for grupo in grupos:
        if (chave in grupo or (dominio_ and dominio_ in grupo)) and (grupo & nomes or grupo & dominios):
            return AVISO_MESMO_GRUPO
    if any(p in conhecido for p in _palavras(nome) for conhecido in nomes):
        return AVISO_POSSIVEL_CLIENTE
    base = base_do_dominio(dominio_)
    if base and len(base) >= 4 and any(base_do_dominio(d) == base for d in dominios):
        return AVISO_POSSIVEL_CLIENTE
    return ""
