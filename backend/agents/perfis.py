"""Personas dos agentes de IA (CrewAI) e instruções específicas por agente."""

import json
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
        "goal": "Organizar o calendário editorial: formatos, datas, horários, hashtags e rotina de publicação.",
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

INSTRUCOES = "Responda em português do Brasil, de forma objetiva e acionável."
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


def _resumo_historico(historico: list) -> str:
    """Trocas anteriores, encurtadas para não pesar em tokens."""
    trocas = [f"- Usuário: {h['texto'][:300]}\n  Você: {(h['resposta'] or '')[:600]}" for h in historico]
    return "Conversa recente com este usuário (use como contexto):\n" + "\n".join(trocas)


def contexto(agente_id: str, historico: list = ()) -> str:
    """Contexto fixo do agente: conversa recente, instruções e conhecimento específico."""
    partes = [_resumo_historico(historico)] if historico else []
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
    return f"Pedido do usuário: {texto}\n\n{contexto(agente_id, historico)}"
