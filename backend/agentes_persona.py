"""Persona de agente novo (Construtor): completa e sem instrução perigosa, conferida sem IA (levantamento de
31/10/2026, construtor-04). A persona vira instrução permanente do agente: o Vendedor de Pacotes nasceu com 141
caracteres, sem método, prometendo "fechar vendas". A mensagem diz exatamente o que falta, para o Construtor corrigir
na mesma tarefa (mesmo laço do erro de cor inválida).
"""

import re

PARTES = {"missão": r"miss[aã]o", "regras": r"regras?", "fluxo": r"fluxo|etapas?",
          "entregáveis": r"entreg[aá]ve(?:l|is)|entregas?",
          "com quem fala": r"fala com|recebe de|entrega para|antes dele|depois dele|para quem entrega"}
REGRAS_DE_OURO = {"sem WhatsApp": r"whatsapp", "site fora dos criativos": r"\bsite\b",
                  "stories sem legenda": r"stor(?:y|ies)"}
NEGACAO = r"\b(?:nunca|sem|n[aã]o|nada de|jamais|proibid\w*|evit\w*|fora d\w*)\b[^.;\n]{0,40}"
PERIGOSOS = [
    (r"https?://|\bwww\.", "links"),
    (r"[\w.+-]+@[\w-]+\.[\w.-]+", "e-mails"),
    (r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s.]?\d{4}\b", "telefones"),
    (r"ignor\w*\s+(?:as\s+|todas\s+as\s+|quaisquer\s+)?(?:instru|regras|orienta)", "ordem para ignorar instruções"),
    (r"\.env\b|\bsenhas?\b|\btokens?\b|chaves?\s+(?:de\s+)?api|api[\s_-]?keys?|credencia", "senhas, tokens ou chaves"),
    (r"\b(?:rod\w+|execut\w+)\s+(?:os\s+|um\s+|o\s+)?(?:comandos?|scripts?|c[oó]digos?|programas?)", "comandos ou código"),
    (r"\b(?:le[ri]a?|abr\w+|acess\w+)\s+(?:os\s+|o\s+)?arquivos?|arquivos? de configura", "leitura de arquivos"),
]
# Só valem quando NÃO vêm negados ("nunca use WhatsApp" é a regra de ouro; "chame no WhatsApp" é o problema).
PROIBIDOS_SEM_NEGACAO = [
    (r"whatsapp", "WhatsApp como CTA"),
    (r"\bcasal\b|\bcasais\b", "falar com casal"),
    (r"(?:garant\w*|promet\w*|assegur\w*)\s+(?:a\s+|de\s+)?(?:disponibilidade|reserva|data)",
     "promessa de disponibilidade"),
    (r"fech\w*\s+(?:a\s+|as\s+)?vendas?", "fechar vendas (o escritório não vende)"),
]


def problema(campos: dict) -> str | None:
    """O que falta ou o que não pode na especificação; None quando está tudo certo."""
    backstory = campos.get("backstory", "")
    faltam = [nome for nome, padrao in PARTES.items() if not re.search(padrao, backstory, re.I)]
    faltam += [f"regra de ouro {nome}" for nome, padrao in REGRAS_DE_OURO.items()
               if not re.search(padrao, backstory, re.I)]
    if faltam:
        return ("a persona (backstory) está incompleta; falta escrever: " + ", ".join(faltam) + ". Monte nesta "
                "ordem: Missão; Regras (com as regras de ouro: nunca WhatsApp, site fora dos criativos, stories sem "
                "legenda); Fluxo em etapas; Entregáveis; Fala com (de quem recebe e para quem entrega).")
    texto = " ".join(v for v in campos.values() if isinstance(v, str))
    achados = [motivo for padrao, motivo in PERIGOSOS if re.search(padrao, texto, re.I)]
    for padrao, motivo in PROIBIDOS_SEM_NEGACAO:
        if any(not re.search(NEGACAO + r"$", texto[max(0, a.start() - 50):a.start()], re.I)
               for a in re.finditer(padrao, texto, re.I)):
            achados.append(motivo)
    if achados:
        return ("a especificação traz o que um agente do escritório não pode ter: " + ", ".join(achados) + ". Tire "
                "isso (sem links, contatos, comandos, arquivos ou senhas; WhatsApp, casal e disponibilidade só como "
                "proibição) e chame de novo.")
    return None
