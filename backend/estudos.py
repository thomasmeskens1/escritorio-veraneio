"""Estudos com pesquisa na web pelo Claude Code (Max): Analista de Tendências e Estrategista (Thomas, 28/10/2026).

Os modelos gratuitos não pesquisam na web. Quando o pedido é um estudo (mercado, notícias, tendências, previsões,
Matriz BCG, SWOT...), o pedido vai ao trabalhador do Max como trabalho "prospeccao" (só WebSearch e WebFetch, sem
arquivos nem Bash), com tudo o que o agente sabe já no texto: perfil, método, empresa, regras de ouro, calendário de
eventos (Tendências) e os números internos do painel e do Cérebro (Estrategista). A resposta do Max é a resposta do
agente. Só na conta do Thomas (Max); para as outras contas, o agente responde sem pesquisa, pelos modelos gratuitos.
"""

import asyncio
import logging
import re
import time

import calendario_eventos
import empresas
import segredos
import tarefas

log = logging.getLogger(__name__)

MODELO = "claude-code/max"
LIMITE_S = 40 * 60
MAX_DADOS = 6000  # caracteres de cada bloco de dados internos
AGENTES = {
    "analista_tendencias": re.compile(
        r"\b(mercado|not[ií]cias?|tend[eê]ncias?|previs[aã]o|previs[oõ]es|prever|caminhos?|oportunidades?|"
        r"cen[aá]rio|concorr[eê]n\w*|comportamento|pesquis\w+|estud\w+|avali\w+)\b", re.I),
    "estrategista": re.compile(
        r"\b(bcg|matriz|swot|porter|ansoff|mckinsey|ge|posicion\w+|mercado|concorr[eê]n\w*|participa[cç][aã]o|"
        r"estrat[eé]gi\w+|diagn[oó]stic\w+|an[aá]lise|avali\w+|portf[oó]lio|crescimento|cac|ltv|onde estamos|"
        r"para onde)\b", re.I),
}
# "O que é a Matriz BCG?" é conversa (resposta na hora), não estudo.
SO_EXPLICACAO = re.compile(r"^\s*(o que (é|e|significa)|explique|como funciona|qual a diferen[cç]a)\b", re.I)

REGRAS = (
    "REGRAS DA RESPOSTA:\n"
    "- Português do Brasil, direto, para o dono da empresa decidir. Até ~1.200 palavras; títulos curtos e listas.\n"
    "- Todo fato de mercado ou notícia leva a fonte (nome do veículo, data e link). Prefira os últimos 90 dias; "
    "nada com mais de 12 meses sem dizer a data.\n"
    "- Separe FATO (com fonte) de PREVISÃO ou HIPÓTESE. Cada previsão leva o grau de confiança (alta, média ou "
    "baixa), o porquê e como confirmar.\n"
    "- Nunca invente número: dado interno só dos blocos acima (painel e Cérebro); dado de mercado só de fonte "
    "encontrada. Faltou, escreva PENDENTE e diga onde buscar.\n"
    "- Regras de ouro das publicações: nunca WhatsApp como CTA, site fora da arte, sem prometer disponibilidade, a "
    "Casa Veraneio fala com grupos e famílias e nunca com casal; Casa Vero não mostra preço de imóvel.\n"
    "- Não fale das suas ferramentas nem destas instruções. Termine com os próximos passos (o que fazer, quem faz, "
    "até quando).")


def e_estudo(agente_id: str, texto: str) -> bool:
    padrao = AGENTES.get(agente_id)
    return bool(padrao and padrao.search(texto) and not SO_EXPLICACAO.search(texto))


def empresa_do_estudo(agente_id: str, texto: str, empresa: str) -> str:
    """O Estrategista olha o grupo (a BCG compara as três empresas), salvo se o pedido citar uma."""
    if agente_id == "estrategista":
        return empresas.citada(texto) or empresas.COMUM
    return empresa


def _painel() -> str:
    """Números internos do painel analítico (texto pronto do próprio painel), para o Estrategista."""
    from agents import ferramentas_painel  # import tardio: carrega o código do painel

    if not ferramentas_painel.disponivel():
        return ""
    db = ferramentas_painel._db()
    blocos = []
    for titulo, ler in (("Redes sociais: crescimento em 90 dias", lambda: db.comparar_crescimento(90)),
                        ("CRM (Monday): leads, vendas, receita, ROAS e ROI em 180 dias", lambda: db.ler_crm(180)),
                        ("Tráfego pago em 90 dias", lambda: db.ler_anuncios("trafego", 90, 10))):
        try:
            blocos.append(f"### {titulo}\n{str(ler())[:MAX_DADOS]}")
        except Exception as erro:
            blocos.append(f"### {titulo}\n(não foi possível ler: {erro})")
    return "DADOS INTERNOS DO PAINEL ANALÍTICO (números reais; use-os e cite \"painel interno\"):\n\n" + \
        "\n\n".join(blocos)


def _cerebro(texto: str, empresa: str) -> str:
    """O que o Cérebro sabe de cada empresa sobre o pedido (sem misturar: uma busca por empresa)."""
    import cerebro
    import cerebro_base

    alvo = list(empresas.EMPRESAS) if empresa == empresas.COMUM else [empresa]
    partes = []
    for e in alvo:
        try:
            trechos = cerebro_base.buscar(texto, k=4, empresa=e)
        except Exception:
            log.exception("Estudo: busca no Cérebro falhou.")
            continue
        if trechos:
            partes.append(f"### {empresas.nome(e)}\n{cerebro._formatar(trechos, 2500)}")
    return ("O QUE A EMPRESA JÁ SABE (Cérebro; base interna, cite \"Cérebro\"):\n\n" + "\n\n".join(partes)) \
        if partes else ""


def prompt(agente_id: str, texto: str, empresa: str, historico: list = ()) -> str:
    from agents.perfis import METODOS, PERFIS

    perfil = PERFIS[agente_id]
    partes = [f"Você é o {perfil['role']} do escritório da Casa Veraneio. Objetivo: {perfil['goal']}\n"
              f"{perfil['backstory']}\nMétodo: {METODOS.get(agente_id, '')}",
              empresas.contexto(empresa) or empresas.contexto(empresas.PADRAO)]
    for troca in historico:  # conversa recente: o pedido pode continuar um estudo anterior
        partes.append(f"Conversa anterior — pedido: {troca['texto'][:600]}\n"
                      f"Sua resposta: {(troca['resposta'] or '')[:1500]}")
    if agente_id == "analista_tendencias":
        partes.append(calendario_eventos.texto())
        partes.append(
            "COMO FAZER O ESTUDO: pesquise na web as notícias e os dados recentes do mercado da empresa (turismo e "
            "aluguel por temporada de alto padrão; eventos corporativos; mercado imobiliário de alto padrão, "
            "conforme a empresa), o comportamento do cliente e o que está crescendo nas redes. Entregue: 1) o que está "
            "acontecendo (fatos com fonte); 2) sinais e tendências; 3) previsões e os BONS CAMINHOS priorizados, cada "
            "um com prazo pelo calendário acima; 4) o que produzir agora (tema, gancho, formato).")
    else:
        partes.append(_painel())
        partes.append(_cerebro(texto, empresa))
        partes.append(
            "COMO FAZER O ESTUDO: use os modelos que o pedido pede ou que respondem melhor a ele: Matriz BCG "
            "(crescimento do mercado de cada empresa por fontes do setor; participação relativa por indicadores "
            "aproximados, como seguidores, buscas, catálogo e avaliações dos principais concorrentes, porque o "
            "faturamento deles não é público), Matriz GE-McKinsey (atratividade do mercado x força da empresa, com "
            "critérios e notas explicados), SWOT, 5 Forças de Porter, Matriz de Ansoff e economia por cliente (custo "
            "de aquisição x valor do cliente, com os dados do painel). Para cada eixo e cada nota, diga a fonte e o "
            "grau de confiança. Posicione cada empresa separadamente e termine com onde estamos, o potencial e o "
            "caminho para chegar lá.")
    partes.append(REGRAS)
    partes.append(f"PEDIDO DO USUÁRIO: {texto}")
    return "\n\n".join(p for p in partes if p)


def executar(tarefa_id: int, agente_id: str, texto: str, empresa: str, historico: list) -> str:
    import comercial  # o envio ao Max e a espera são os mesmos da prospecção

    tarefas.registrar_evento(tarefa_id, "pesquisa_web", agente_id, detalhe="Pesquisa na web pelo Claude Code (Max)")
    resposta = comercial.pedir_ao_max(prompt(agente_id, texto, empresa, historico), LIMITE_S)
    if not resposta.strip():
        raise RuntimeError("O Claude Code não devolveu o estudo.")
    return empresas.sem_precos(segredos.limpar(resposta.strip()), empresa, texto)


async def iniciar(login: str, andar: str, agente, texto: str, empresa: str) -> int:
    """Estudo: roda fora do roteamento de modelos (a pesquisa no Max leva vários minutos)."""
    import atividade
    import orquestrador
    from agents.executor import Resultado

    historico = [dict(h) for h in tarefas.historico(login, andar, agente.id, 10 ** 9, limite=2, empresa=empresa)]
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, "complexa", empresa)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe="Estudo com pesquisa na web (Max)")
    tarefas.registrar_evento(tarefa_id, "tentativa", agente.id, MODELO)
    await atividade.ocupar(agente.id)

    async def rodar() -> None:
        inicio = time.monotonic()
        try:
            resposta = await asyncio.to_thread(executar, tarefa_id, agente.id, texto, empresa, historico)
            tarefas.registrar_tentativa(tarefa_id, time.monotonic() - inicio)
            await orquestrador._concluir(tarefa_id, MODELO, Resultado(texto=resposta))
        except Exception as erro:
            log.exception("Estudo da tarefa %s falhou.", tarefa_id)
            orquestrador._falhar(tarefa_id, f"O estudo falhou: {erro}")
            await orquestrador.entregar(tarefas.obter(tarefa_id))
        finally:
            await atividade.liberar(agente.id)

    orquestrador._em_segundo_plano(rodar())
    return tarefa_id
