"""As três empresas do grupo e o que separa uma da outra. Os dados de uma NUNCA entram no trabalho de outra.

Cada trecho do Cérebro, ficha, tarefa e produção leva a empresa. O "Lodge 31" do Corporativo e o "Lodge 31" da
Casa Veraneio são entidades distintas (mesmo que seja a mesma casa física): cada empresa tem a sua ficha. O que é
comum às três (regras de ouro, formatos, Monday, fluxo do escritório) usa COMUM.
"""

import re

COMUM = "*"
PADRAO = "casa_veraneio"  # só para dados antigos, anteriores à separação (todos eram da Casa Veraneio)

EMPRESAS = {
    "casa_veraneio": {
        "nome": "Casa Veraneio", "site": "casaveraneio.com", "monday": "Casa Veraneio",
        "resumo": "aluguel por temporada de casas de alto padrão (os Lodges) para grupos, com os serviços do Hotel "
                  "Privativo cobrados à parte; foco em Réveillon, Carnaval, feriados e férias.",
    },
    "cv_corporativo": {
        "nome": "Casa Veraneio Corporativo", "site": "corporativo.casaveraneio.com", "monday": "CV Corp",
        "resumo": "eventos em espaços de alto padrão para empresas e pessoas físicas: de workshop, convenção, "
                  "off-site e confraternização a aniversário e mini wedding, com produção completa (serviços como "
                  "decoração, som, gastronomia e staff).",
    },
    "casa_vero": {
        "nome": "Casa Vero Imóveis", "site": "casaveroimoveis.com", "monday": "Casa Vero",
        "resumo": "imobiliária de casas de veraneio de alto padrão: assessoria exclusiva ao proprietário, que cuida "
                  "de consultores, clientes e informações para ele vender sem dor de cabeça; catálogo seleto e "
                  "próprio (imóveis identificados por código \"Vero N\").",
    },
}


def valida(empresa: str | None) -> bool:
    return empresa in EMPRESAS


def nome(empresa: str) -> str:
    return EMPRESAS.get(empresa, {}).get("nome", "todas as empresas" if empresa == COMUM else empresa)


def da_conta_monday(conta: str) -> str | None:
    """Coluna Conta do Monday -> empresa (None se não reconhecida)."""
    return next((e for e, d in EMPRESAS.items() if d["monday"].lower() == (conta or "").strip().lower()), None)


# Empresa dita no pedido ("A empresa é a Casa Veraneio"). "Casa Veraneio" sozinha não pode ser o começo de
# "Casa Veraneio Corporativo".
CITACOES = {
    "cv_corporativo": re.compile(r"\bcasa veraneio corp(?:orativ[oa])?\b|\bcv corp\b", re.I),
    "casa_vero": re.compile(r"\bcasa vero\b", re.I),
    "casa_veraneio": re.compile(r"\bcasa veraneio\b(?!\s+corp)|\bcasaveraneio\b(?!\.com/corp)", re.I),
}


def citada(texto: str) -> str | None:
    """A única empresa citada no texto (None se nenhuma ou mais de uma)."""
    achadas = [e for e, padrao in CITACOES.items() if padrao.search(texto or "")]
    return achadas[0] if len(achadas) == 1 else None


def contexto(empresa: str) -> str:
    """Bloco que abre o contexto de todo agente: de qual empresa é o trabalho e a proibição de misturar."""
    if empresa == COMUM:  # visão do grupo (Analista de Métricas): as três, sempre separadas
        return ("TRABALHO DO GRUPO INTEIRO: " + "; ".join(f"{d['nome']} ({d['site']})" for d in EMPRESAS.values())
                + ". Analise cada empresa separadamente e mostre lado a lado; nunca some números de empresas "
                "diferentes como se fossem um só, e não leve dados de uma para a outra. Não invente fatos: o que "
                "faltar fica PENDENTE.")
    if not valida(empresa):
        return ""
    dados = EMPRESAS[empresa]
    outras = ", ".join(d["nome"] for e, d in EMPRESAS.items() if e != empresa)
    return (f"EMPRESA DESTE TRABALHO: {dados['nome']} ({dados['site']}) — {dados['resumo']}\n"
            f"Use SOMENTE dados da {dados['nome']}. Não use, cite nem misture nada de {outras}: imóveis com o mesmo "
            "nome em outra empresa são OUTRAS casas. Não invente fatos (preço, capacidade, datas): o que faltar fica "
            "PENDENTE; escolhas editoriais você faz e explica.")


# Casa Vero: a regra geral é NÃO mostrar o valor de venda; vale só quando o usuário pede ou autoriza no próprio pedido
# (Thomas, 26/10/2026). O teste de estresse de 28/10/2026 achou o valor vazando em roteiro e resposta do Cérebro: o
# filtro roda nos trechos do Cérebro e na resposta final, não depende do modelo obedecer.
PRECO = re.compile(r"R\$\s?\d+(?:[.,]\d+)*(?:\s?(?:mil|milh(?:ão|ões|oes)|mi)\b)?", re.I)
PEDE_PRECO = re.compile(r"\b(pre[çc]os?|valor(?:es)?|quanto custa|quanto vale)\b|R\$", re.I)


def sem_precos(texto: str, empresa: str, pedido: str = "") -> str:
    if empresa != "casa_vero" or not texto or PEDE_PRECO.search(pedido or ""):
        return texto
    return PRECO.sub("valor sob consulta", texto)
