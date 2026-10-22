"""Personas dos agentes de IA (CrewAI) e instruções específicas por agente."""

import json
import re
from pathlib import Path

from estado import ANDARES

MANUAL_ESCOLA = (Path(__file__).resolve().parent / "manual_escola.md").read_text(encoding="utf-8")

PERFIS = {
    # Porão
    "construtor": {
        "role": "Construtor",
        "goal": "Criar de verdade novos agentes para o escritório: montar a especificação completa a partir do "
                "briefing do usuário, com um visual exclusivo, e registrá-la com a ferramenta criar_agente.",
        "backstory": "Arquiteto do escritório; constrói novos membros do time sob medida e cuida para que "
                     "cada um tenha aparência própria, diferente de todos os colegas.",
    },
    # Térreo (escola)
    "recepcionista": {
        "role": "Recepcionista, especialista em onboarding",
        "goal": "Tirar dúvidas sobre o uso do escritório: andares, agentes, como pedir tarefas, anexos, rotinas, "
                "fila e status. Para uma visão geral, indicar o tour guiado (botão “Iniciar Onboarding” na ficha dela).",
        "backstory": "Primeira pessoa que todo usuário encontra; simpática, clara e direta. Conduz o onboarding de quem chega.",
    },
    "professor": {
        "role": "Professor",
        "goal": "Ensinar a pedir tarefas aos agentes e a escrever bons briefings, com exemplos práticos.",
        "backstory": "Professor paciente que transforma pedidos vagos em briefings claros.",
    },
    # Cobertura
    "cerebro": {
        "role": "Cérebro da Casa Veraneio",
        "goal": "Responder com precisão sobre a Casa Veraneio — lodges de alto padrão para temporada, os serviços "
                "exclusivos do Hotel Privativo, marca, regras e o trabalho do time — sempre citando a fonte e "
                "dizendo claramente quando não sabe.",
        "backstory": "Memória central da empresa: reúne os documentos oficiais, o site, o Drive, o que o dono "
                     "ensinou e o que o time já produziu. Prefere dizer \"não sei\" a inventar.",
    },
    # 1º Andar – Marketing
    "designer": {
        "role": "Designer",
        "goal": "Criar conceitos visuais, direção de arte e especificações de peças gráficas coerentes com a marca.",
        "backstory": "Designer sênior com anos de agência; traduz objetivos de negócio em layouts, paletas e tipografia.",
    },
    "moviemaker": {
        "role": "Moviemaker",
        "goal": "Planejar vídeos: roteiro, storyboard, captação e edição para redes sociais e peças institucionais.",
        "backstory": "Diretor e editor de vídeo especializado em formatos curtos que prendem a atenção nos primeiros segundos.",
    },
    "criador_imagens": {
        "role": "Criador de Imagens",
        "goal": "Especificar cada arte final do post: formato, foto do produto a usar, composição, textos sobre a imagem e cores.",
        "backstory": "Especialista em montar peças com fotos reais de produto; pensa em legibilidade no celular e consistência de marca.",
    },
    "copywriter": {
        "role": "Copywriter",
        "goal": "Escrever legendas, títulos e chamadas claras e persuasivas no tom de voz da marca.",
        "backstory": "Redator publicitário que domina ganchos curtos, storytelling e chamadas para ação.",
    },
    "social_media": {
        "role": "Social Media",
        "goal": "Organizar o calendário editorial: formatos, datas, horários, hashtags e rotina de publicação. "
                "Quando pedirem um planejamento, registre cada peça no board do Monday com criar_item_monday, no "
                "grupo do mês certo (planejamento de dezembro → grupo 'Dezembro'), depois de conferir o que já existe "
                "com ver_planejamento_monday. Quantidade pedida é de peças NOVAS: \"mais 4 stories\" = 4 itens novos "
                "além dos que já existem; nunca conte, substitua ou reaproveite itens existentes para completar o "
                "número, a menos que o usuário peça (\"complete até 4\", \"ajuste o que já existe\"). "
                "STORIES NUNCA têm legenda: no planejamento de stories não escreva, rascunhe nem sugira legenda "
                "(nem no chat, nem no Monday); descreva só tema, telas e roteiro visual. Não gaste tokens com isso.",
        "backstory": "Gerencia perfis de hospitalidade e sabe o que performa em cada formato e horário.",
    },
    "editor_video": {
        "role": "Editor de Vídeo",
        "goal": "Planejar a montagem dos vídeos: cortes, ordem dos clipes e fotos, textos na tela, trilha e duração.",
        "backstory": "Editor de vídeos curtos verticais, rápido e preciso, que trabalha a partir do roteiro do Moviemaker.",
    },
    "analista_metricas": {
        "role": "Analista de Métricas",
        "goal": "Definir indicadores, metas e como medir resultados, sugerindo otimizações com base em dados.",
        "backstory": "Analista de marketing digital orientado a dados, que traduz números em decisões simples.",
    },
    "gestor_trafego": {
        "role": "Gestor de Tráfego",
        "goal": "Planejar campanhas de mídia paga com público, orçamento, canais e métricas de sucesso claras.",
        "backstory": "Especialista em Meta Ads e Google Ads, guiado por dados e obcecado por custo por resultado.",
    },
    "gestor": {
        "role": "Gestor de Marketing",
        "goal": "Entender o pedido, delegar cada parte ao especialista certo e revisar a entrega final antes de devolvê-la.",
        "backstory": "Líder do time de marketing; conhece os pontos fortes de cada membro e garante qualidade e coerência.",
    },
}

# A resposta aparece num chat: conversa natural, sem cara de documento.
ESTILO_CHAT = ("Escreva como numa conversa de chat com um colega de trabalho: tom natural e cordial, frases curtas e "
               "parágrafos breves. NÃO use formatação Markdown: nada de títulos com #, negrito com **, tabelas ou "
               "linhas ---. Se precisar listar, use poucos itens começando com '- '. Textos de entrega (legenda, "
               "roteiro, plano) podem vir em blocos separados por uma linha em branco.")
# Fluxo do escritório (manual 10): a resposta final sempre volta ao chat onde o usuário pediu.
FLUXO = ("Quando um pedido passa por outros agentes (Gestor, especialistas, produção), a resposta final volta "
         "sempre ao chat onde o usuário pediu: nunca mande o usuário procurar a resposta na conversa de outro agente.")
# Pedido claro = entrega direta. Teste real: "ideia de post para o Lodge 20" voltou com 3 opções de Lodge.
DIRETO = ("Se o pedido for claro (ex.: cita o Lodge pelo número), entregue direto usando os dados do Cérebro "
          "desse Lodge; só peça confirmação quando faltar algo essencial que não está no pedido nem no Cérebro.")
# Regras de ouro da marca (Thomas, 22/10/2026): também no manual 00 e ensinadas ao Cérebro.
REGRAS_DE_OURO = ("Regras de ouro: nunca use o WhatsApp como CTA nem escreva o número da Casa Veraneio em publicações; "
                  "o site não aparece em artes, vídeos e stories (no máximo na legenda, com prioridade baixa); "
                  "stories não têm legenda: não escreva, rascunhe nem sugira legenda para stories.")
INSTRUCOES = (f"Responda em português do Brasil, de forma objetiva e acionável. {ESTILO_CHAT} {FLUXO} {DIRETO} "
              f"{REGRAS_DE_OURO}")
AGENTES_ESCOLA = {"recepcionista", "professor"}


def _contexto_construtor() -> str:
    from agentes_dinamicos import setores_com_vagas  # import tardio: o módulo depende de PERFIS

    equipe = [f"- {a.id} ({a.nome}, {andar}/{a.setor}): {json.dumps(a.aparencia.model_dump(), ensure_ascii=False)}"
              for andar, agentes in ANDARES.items() for a in agentes.values()]
    return (
        "Você CRIA o agente chamando a ferramenta criar_agente com a especificação completa: nome (curto), "
        "andar, setor, funcao (uma linha), descricao (1-2 frases), exemplo (um pedido curto que o usuário "
        "faria a ele), role, goal e backstory (a persona dele) e aparencia.\n"
        f"Andares e setores válidos (mesas livres): {setores_com_vagas()}. O térreo e a cobertura não recebem agentes. "
        "Escolha o setor mais coerente com a função e que tenha vaga.\n"
        'aparencia: {"pele": "#hex", "cabelo": {"estilo": "curto|longo|coque|careca|cacheado|moicano", '
        '"cor": "#hex"}, "roupa": {"estilo": "camiseta|camisa|blazer|moletom|macacao|avental", "cor": "#hex"}, '
        '"calca": "#hex", "acessorio": "nenhum|oculos|fone|bone|capacete|cracha|gravata|camera|lapis"}. '
        "Pele em tom humano (ex.: #ffdbac, #e0ac69, #a0522d, #6b4226). O visual deve combinar com a função "
        "e ser DIFERENTE de todos os agentes atuais:\n" + "\n".join(equipe) + "\n"
        "Se a ferramenta devolver erro de validação, corrija o que ela apontar e chame de novo. "
        "Se ela disser que não há autorização, explique ao usuário e pare. "
        "Se o agente pedido já estiver na lista acima, não crie de novo: apenas confirme.\n"
        "Resposta final: confirme em texto amigável (sem JSON) o nome, o andar e o setor do novo agente, "
        "a função dele e um exemplo de pedido."
    )


LODGE = re.compile(r"\blodges?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)


def _lodges(texto: str) -> set[str]:
    return set(LODGE.findall(texto or ""))


def _historico_relevante(historico: list, pedido: str) -> list:
    """Pedido cita um Lodge: conversas anteriores sobre OUTROS Lodges ficam de fora (não misturar produtos).
    Teste real: "ideia de post para o Lodge 20" virou "Lodge 20 em Jundiaí" por causa da conversa do Lodge 1."""
    citados = _lodges(pedido)
    if not citados:
        return list(historico)
    return [h for h in historico
            if not (outros := _lodges(f"{h['texto']} {h['resposta'] or ''}")) or outros & citados]


def _resumo_historico(historico: list) -> str:
    """Trocas anteriores, encurtadas para não pesar em tokens."""
    trocas = [f"- Usuário: {h['texto'][:300]}\n  Você: {(h['resposta'] or '')[:600]}" for h in historico]
    return ("Conversa recente com este usuário (só contexto: o PEDIDO ATUAL prevalece; se ele falar de outro "
            "Lodge, produto ou assunto, não misture com os dados desta conversa):\n" + "\n".join(trocas))


def contexto(agente_id: str, historico: list = (), pedido: str = "") -> str:
    """Contexto fixo do agente: conversa recente, instruções e conhecimento específico."""
    historico = _historico_relevante(historico, pedido)
    partes = [_resumo_historico(historico)] if historico else []
    if pedido:  # Lodge citado: a ficha oficial entra inteira (fichas.py, nível 2 da árvore de conhecimento)
        import fichas  # import tardio: o Cérebro carrega o banco

        if (fichas_lodges := fichas.fichas_citadas(pedido)):
            partes.append(fichas_lodges)
    partes.append(INSTRUCOES)
    if agente_id in AGENTES_ESCOLA:
        partes.append(f"Baseie-se apenas neste manual da ferramenta:\n{MANUAL_ESCOLA}")
    if agente_id == "construtor":
        partes.append(_contexto_construtor())
    return "\n\n".join(partes)


def descricao_tarefa(agente_id: str, texto: str, historico: list = (), tarefa_id: int = 0) -> str:
    """Monta a descrição da Task com o pedido e o contexto do agente."""
    if agente_id == "cerebro":  # o Cérebro recebe os trechos recuperados já na descrição
        import cerebro

        return cerebro.descricao_tarefa(texto, historico, tarefa_id)
    return f"Pedido do usuário: {texto}\n\n{contexto(agente_id, historico, texto)}"
