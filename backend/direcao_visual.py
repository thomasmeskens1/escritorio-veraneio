"""Direção visual no fim de cada roteiro (social_media-18, Onda 1 de novembro).

Cada produção reinterpretava a marca, e o padrão aprovado numa peça se perdia na seguinte (na Casa Vero foram 4
versões do editável até aprovar). Agora todo roteiro fecha com 3 linhas:
  DIREÇÃO VISUAL
  Referência: peça #N (uma peça já aprovada da MESMA empresa) ou "sem referência aprovada"
  Formato: código do repertório (F1 a F6, R1 a R4) ou o formato da peça
  Evitar: até 2 itens (ex.: sem caixa preta, sem texto no miolo)
Peça aprovada = produção entregue no Drive (pasta FINAL com link) e com 👍 no chat. O código só confere (aviso, sem
bloquear): se o bloco existe, se a peça citada existe, se foi entregue e se é da mesma empresa; pasta citada pelo
nome tem de ter o prefixo da empresa ("VERANEIO |", "CORP |", "VERO |"). Sem IA e sem custo.
"""

import logging
import re
import sqlite3

import empresas

log = logging.getLogger(__name__)

AGENTES = {"social_media", "moviemaker"}
PREFIXOS = {"casa_veraneio": "VERANEIO", "cv_corporativo": "CORP", "casa_vero": "VERO"}
LIMITE = 3
SEM_REFERENCIA = "sem referência aprovada"
PEDE_ROTEIRO = re.compile(r"roteir|planej|briefing|pe[cç]as?\b|carross|reels?\b|stories|post\b|v[ií]deo|capa", re.I)
BLOCO = re.compile(r"DIRE[CÇ][AÃ]O\s+VISUAL", re.I)
REFERENCIA = re.compile(r"Refer[eê]ncia\s*:\s*([^\n]+)", re.I)
PECA = re.compile(r"#\s?(\d{1,6})\b")
PASTA = re.compile(r"\b(VERANEIO|CORP|VERO)\s*\|", re.I)


def aprovadas(empresa: str, limite: int = LIMITE) -> list[dict]:
    """Peças entregues no Drive e com 👍, da empresa (mais recentes primeiro)."""
    import tarefas  # import tardio: usa o banco

    try:
        linhas = tarefas._db().execute(
            "SELECT t.id, p.titulo FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id "
            "JOIN avaliacoes a ON a.tarefa_id = t.id WHERE t.empresa = ? AND p.link IS NOT NULL AND p.link != '' "
            "AND a.valor > 0 ORDER BY t.id DESC LIMIT ?", (empresa, limite)).fetchall()
    except sqlite3.OperationalError:  # banco novo, sem produção ou sem avaliação ainda
        return []
    return [{"id": l["id"], "titulo": l["titulo"]} for l in linhas]


def bloco(agente_id: str, empresa: str | None, pedido: str = "") -> str:
    """Instrução para o contexto de quem escreve roteiro, com as referências aprovadas da empresa."""
    if agente_id not in AGENTES or not empresas.valida(empresa) or not PEDE_ROTEIRO.search(pedido or ""):
        return ""
    lista = aprovadas(empresa)
    opcoes = ("; ".join(f"peça #{p['id']} ({p['titulo']})" for p in lista) if lista else
              f"nenhuma peça aprovada desta empresa ainda: escreva \"{SEM_REFERENCIA}\"")
    return ("DIREÇÃO VISUAL: todo roteiro de peça (no chat e no campo roteiro do Monday) fecha com o bloco "
            "\"DIREÇÃO VISUAL\" em 3 linhas: \"Referência: peça #N\" (uma peça já aprovada da "
            f"{empresas.nome(empresa)}, nunca de outra empresa) ou \"{SEM_REFERENCIA}\" para o Gestor decidir; "
            "\"Formato: <código do repertório (F1 a F6, R1 a R4) ou o formato>\"; \"Evitar: <até 2 itens>\". Um "
            f"modelo por peça. Peças aprovadas desta empresa: {opcoes}.")


def conferir(roteiro: str, empresa: str) -> list[str]:
    """Avisos sobre o bloco de direção visual de um roteiro (só aviso)."""
    texto = roteiro or ""
    if len(texto.strip()) < 80 or not empresas.valida(empresa):  # roteiro de uma linha (ex.: "a definir")
        return []
    if not BLOCO.search(texto):
        return ["roteiro sem o bloco DIREÇÃO VISUAL (referência aprovada, formato e o que evitar)"]
    referencia = (m.group(1) if (m := REFERENCIA.search(texto[BLOCO.search(texto).start():])) else "").strip()
    if not referencia:
        return ["DIREÇÃO VISUAL sem a linha \"Referência:\""]
    if SEM_REFERENCIA in referencia.lower():
        return []
    if (pasta := PASTA.search(referencia)) and pasta.group(1).upper() != PREFIXOS[empresa]:
        return [f"referência visual de outra empresa (pasta \"{pasta.group(1).upper()} |\"): use uma peça da "
                f"{empresas.nome(empresa)}"]
    if not (peca := PECA.search(referencia)):
        return [] if pasta else [f"referência visual sem o número da peça (\"{referencia[:60]}\")"]
    return _conferir_peca(int(peca.group(1)), empresa)


def _conferir_peca(numero: int, empresa: str) -> list[str]:
    import tarefas

    try:
        linha = tarefas.obter(numero)
        entregue = tarefas._db().execute("SELECT link FROM producao_info WHERE tarefa_id = ?", (numero,)).fetchone()
    except sqlite3.OperationalError:
        linha, entregue = tarefas.obter(numero), None
    if not linha:
        return [f"referência visual: a peça #{numero} não existe"]
    if linha["empresa"] != empresa:
        return [f"referência visual: a peça #{numero} é da {empresas.nome(linha['empresa'])}, não da "
                f"{empresas.nome(empresa)}"]
    if not entregue or not entregue["link"]:
        return [f"referência visual: a peça #{numero} não tem pasta FINAL entregue no Drive"]
    return []
