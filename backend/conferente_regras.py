"""Regras duras do conferente automático, por empresa (Onda 2, item 2; 31/10/2026). Só dados, sem lógica.

Tudo aqui saiu dos manuais (backend/dados/conhecimento) ou das decisões do Thomas; cada bloco diz de onde. Mudou o
manual, muda aqui. O conferente (conferente.py) só AVISA: nada é bloqueado nem corrigido sozinho.
Sem dado sensível: nenhum valor, contato ou cliente (o repositório é público).
"""

# Decisões que valem para as três empresas (Thomas, 31/10/2026).
COMUNS = {
    # Decisão 8 e manuais 01 §4, 02 §6, 08 §3: WhatsApp proibido em tudo (CTA, legenda, arte, roteiro).
    "whatsapp": r"\bwhats\s?app\b|\bwpp\b|\bzap(?:zap)?\b|wa\.me/|api\.whatsapp",
    # Telefone escrito (manual 01 §4: "convite direto, sem contato escrito").
    "telefone": r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-.\s]?\d{4}(?!\d)",
    # Decisão 2: localização sempre "Cidade / UF".
    "ufs": ("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO").split(),
    # Manual 00, regra 10: nunca nome interno de agente em texto público.
    "nomes_internos": [r"\bVera\b"],
    # Manual 00, regra 9: nunca afirmar disponibilidade.
    "disponibilidade": [r"\bcasas? livres?\b", r"\bdatas? livres?\b"],
    # Manual 00, regra 11: no máximo uma vez no mesmo texto.
    "palavras_a_dosar": [r"\bperfeit[oa]s?\b", r"\bincr[ií]ve(?:l|is)\b", r"\bexperi[eê]ncias?\b",
                         r"\bref[uú]gios?\b", r"\bexclusiv[oa]s?\b"],
    # Manual 07, regras de formato das legendas (§3) e limite de hashtags (manual 02 §8).
    "max_emojis": 1,
    "max_hashtags": 5,
    # Urgência de data só com prazo "fechar até" válido (copywriter-01, 11/11/2026; prazos_comerciais.py).
    "urgencia": [r"\b[uú]ltim[oa]s\s+(?:dias|datas|vagas|casas|chances?|semanas?|oportunidades?)\b",
                 r"\bainda\s+d[aá]\s+tempo\b", r"\bcorra\b", r"\breta\s+final\b", r"\bn[aã]o\s+perca\b",
                 r"\best[aá]\s+acabando\b", r"\bs[oó]\s+at[eé]\s+(?:o\s+dia|dia|\d{1,2}/\d{1,2}|amanh[aã]|domingo|"
                 r"segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|o\s+fim)\b"],
}

# Casa Vero é imobiliária: anúncio sem o CRECI fere a Lei 6.530/78 (estrategista-38). Só AVISA. O número não fica
# aqui: vem de CRECI_VERO no ambiente ou do manual 12 (fora do git), lido por conferente.creci_vero().
CRECI = r"\bCRECI\b"

# Fim de todo plano de mídia (gestor_trafego-03, 11/11/2026). Cita a área ("melhorias do criativo"), não o nome exato
# de cada botão, que a Meta muda; conferir no Gerenciador antes de gravar no manual 02.
CHECKLIST_META_TITULO = "Configuração de marca (checklist de quem sobe o anúncio)"
CHECKLIST_META = (
    f"{CHECKLIST_META_TITULO}\n"
    "- [ ] Melhorias automáticas da Meta desligadas, na conta e em cada anúncio: melhorias do criativo (expansão ou "
    "recorte da imagem por IA, fundo gerado, variações de texto, sobreposições), música automática e navegação de "
    "produtos.\n"
    "- [ ] O anúncio no ar é a peça aprovada: mesma foto ou vídeo, mesma música da biblioteca da marca e mesmo texto.\n"
    "- [ ] Conferir de novo depois de duplicar ou editar o anúncio: essas opções costumam voltar marcadas.\n"
    "- [ ] Uma vez por mês: print da tela de melhorias de cada conta para o Gestor de Tráfego conferir.")

# Dados de hospedagem (manuais 11 §1 e 12 §1: nunca num trabalho do Corporativo ou da Casa Vero).
HOSPEDAGEM = r"\bdi[aá]rias?\b|\bestadia m[ií]nima\b|\bm[ií]nimo de \d+ noites\b|\btaxa de ativa[cç][aã]o\b"

REGRAS = {
    "casa_veraneio": {
        # Manual 01 §4 e 07 §4.
        "assinatura": ["Casa Veraneio. A casa inteira é de vocês. O resto, a gente cuida."],
        "ctas": [r"link da bio", r"pelo direct", r"reserve a data"],
        "hashtag_obrigatoria": "#casaveraneio",
        "hashtags_vetadas": [r"#casavero\w*", r"#casaveraneiocorp\w*", r"#cvcorp\w*"],
        # Outras marcas no texto (empresa errada). "Corporativo" sozinho é comum demais: só a marca.
        "outras_marcas": [r"\bcasa vero\b", r"\bcasa veraneio corp(?:orativo|\.)?", r"\bcv corp\b"],
        # Manual 07 §7 (negativas) e §2; manual 00, regra 6 (nunca casal) e 11 (promoção).
        "palavras_vetadas": [r"\bpousadas?\b", r"\bcasal\b", r"\blua de mel\b", r"\bmaravilhos[oa]s?\b",
                             r"\bpromo[cç](?:[aã]o|[oõ]es)\b"],
        # Legenda leva a ficha com diária (manual 07 §4); a arte, só com pedido (decisão 3).
        "valores_na_legenda": True,
        "sem_hospedagem": False,
        # Manual 01 §5: o período se chama "Réveillon 2027" (Thomas, 04/11/2026), nunca "2026/27".
        "nome_periodo_vetado": [r"\bR[eé]veillon\s+(?:20)?26\s*/\s*(?:20)?27\b"],
    },
    "cv_corporativo": {
        # Manual 11 §5.
        "assinatura": ["Casa Veraneio Corporativo. Do orçamento ao último convidado, a gente produz."],
        "ctas": [r"especialistas?", r"or[cç]amento", r"briefing"],
        "hashtag_obrigatoria": "",
        "hashtags_vetadas": [r"#casaveraneio\b(?!corp)", r"#casavero\w*", r"#casasdeveraneio\b"],
        # "Casa Veraneio" sem "Corp"/"Corporativo" é a outra empresa (empresas.CITACOES).
        "outras_marcas": [r"\bcasa vero\b", r"\bcasa veraneio\b(?!\s+corp)"],
        # Manual 11 §5 ("o que nunca dizer").
        "palavras_vetadas": [r"\baluguel de espa[cç]os?\b", r"\bpromo[cç](?:[aã]o|[oõ]es)\b"],
        "valores_na_legenda": False,
        "sem_hospedagem": True,
        "nome_periodo_vetado": [],
    },
    "casa_vero": {
        # Manual 12 §3 (alternando as duas versões).
        "assinatura": ["Fale com um especialista agora!", "Fale com um consultor agora!"],
        "ctas": [r"especialistas?", r"consultor", r"agende a visita"],
        "hashtag_obrigatoria": "",
        # Manual 12 §2.2: hashtags e menções só da Casa Vero.
        "hashtags_vetadas": [r"#casaveraneio\w*", r"#casasdeveraneio\b", r"#cvcorp\w*"],
        # Manual 12 §1 e §2.1: "Lodge" é da Casa Veraneio; na Vero o imóvel é "Vero N".
        "outras_marcas": [r"\bcasa veraneio\b", r"\blodges?\s*\d+", r"\bcv corp\b"],
        # Manual 12 §3 ("o que nunca dizer").
        "palavras_vetadas": [r"\badquir[ae] sua casa com facilidade\b", r"\bbaixo padr[aã]o\b",
                             r"\bfinanciamentos?\b", r"\bflexibiliza[cç][aã]o de contratos?\b"],
        # Manual 12 §3: valor de venda, condomínio e IPTU nunca sem autorização no pedido.
        "valores_na_legenda": False,
        "sem_hospedagem": True,
        "nome_periodo_vetado": [],
    },
}

# A lista que o Max confere nos PNGs finais fica em scripts/max/conferencia_arte.py (roda no PC, sem o backend).
