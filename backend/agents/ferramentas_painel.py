"""Ferramentas do Analista de Métricas (e, nos anúncios, do Gestor de Tráfego) ligadas ao painel analítico (Sistema
Casa Veraneio), pedido do Thomas (26/10/2026): os números do momento, com as MESMAS análises que o painel e o agente
analista dele usam.

O código do painel (C:\\dev\\social-analytics) e a pasta de dados dele (analytics.db, .env) estão montados SÓ
LEITURA no container (docker-compose.yml: SISTEMA_DIR e SOCIAL_ANALYTICS_DADOS). Cada ferramenta chama a função
de leitura do painel (db_manager.ler_*), sem duplicar cálculo nem tocar nas APIs.
Para todos os usuários; as análises financeiras (vendas, receita, investimento) só para a Diretoria.
"""

import os
import re
import sys
import types
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, create_model

import tarefas

SISTEMA = Path(os.getenv("SISTEMA_DIR", "/sistema"))
MAX_SAIDA = 12000  # caracteres por resposta de ferramenta (cabe no contexto dos modelos)

_DIAS = (int, Field(30, description="Período: últimos X dias"))
_LIMITE = (int, Field(10, description="Quantos itens no ranking"))
# nome -> (descrição, função do db_manager, parâmetros, chamada)
ANALISES = {
    "obter_metricas_hoje": ("Números mais recentes de cada conta (seguidores, visualizações; última coleta).",
                            {}, lambda db: db.ler_metricas_mais_recentes()),
    "comparar_redes": ("Crescimento de seguidores por conta e rede no período, já com ganho, variação % e média diária.",
                       {"dias": _DIAS}, lambda db, dias: db.comparar_crescimento(dias)),
    "analisar_crescimento": ("Série dia a dia de seguidores e visualizações de todas as contas (picos e quedas).",
                             {"dias": (int, Field(7, description="Últimos X dias"))}, lambda db, dias: db.ler_crescimento(dias)),
    "analisar_historico_instagram": ("Histórico mensal do Instagram por conta: alcance, visualizações, interações, "
                                     "salvamentos, quem seguiu/deixou de seguir e seguidores.",
                                     {"meses": (int, Field(12, description="Últimos X meses"))},
                                     lambda db, meses: db.ler_historico_instagram(meses)),
    "analisar_historico_youtube": ("Histórico mensal do YouTube da Casa Vero: views, horas, inscritos ganhos/perdidos.",
                                   {"meses": (int, Field(12, description="Últimos X meses"))},
                                   lambda db, meses: db.ler_historico_youtube(meses)),
    # Por conta (analista_metricas-08): no ranking das três juntas, a Casa Veraneio, bem maior, ocupava o top 10 inteiro.
    "analisar_melhores_publicacoes": ("Ranking das publicações do Instagram de UMA conta no período (padrão: a "
                                      "empresa do trabalho), com filtro opcional por formato.",
                                      {"dias": _DIAS, "limite": _LIMITE,
                                       "metrica": (str, Field("taxa_valor", description="taxa_valor ((salvamentos + "
                                                              "compartilhamentos) / alcance), visualizacoes, alcance, "
                                                              "interacoes, salvamentos, compartilhamentos, comentarios ou "
                                                              "curtidas")),
                                       "conta": (str, Field("", description="casaveraneio, casaveraneiocorp ou "
                                                            "casaveroimoveis; vazio = a empresa do trabalho")),
                                       "formato": (str, Field("", description="REELS, CARROSSEL, FOTO ou VIDEO; vazio = "
                                                              "todos"))},
                                      None),
    "analisar_engajamento_videos": ("Vídeos, Shorts e lives do YouTube no período: views, engajamento, horas, inscritos.",
                                    {"dias": (int, Field(90, description="Últimos X dias")), "limite": _LIMITE},
                                    lambda db, dias, limite: db.ler_videos_recentes(dias, limite)),
    "analisar_impulsionamentos": ("Posts turbinados pelo botão do Instagram: investimento, impressões, CPM, cliques.",
                                  {"dias": _DIAS, "limite": _LIMITE},
                                  lambda db, dias, limite: db.ler_anuncios("impulsionamento", dias, limite)),
    "analisar_trafego_pago": ("Tráfego pago (Meta Gerenciador e Google Ads): investimento, CPM, CPC, leads/conversões e "
                              "custo por resultado, por conta, e as campanhas com mais investimento.",
                              {"dias": _DIAS, "limite": _LIMITE},
                              lambda db, dias, limite: db.ler_anuncios("trafego", dias, limite)),
    "analisar_google_ads": ("Google Ads a fundo (até 90 dias). Sem campanha: resumo por campanha com leads/vendas do CRM. "
                            "Com campanha (id ou parte do nome): grupos, anúncios, palavras-chave (QS), termos de "
                            "pesquisa, cidades e oportunidades.",
                            {"dias": _DIAS, "campanha": (str, Field("", description="Id ou parte do nome; vazio = todas"))},
                            lambda db, dias, campanha: db.ler_google_ads(dias, campanha)),
    "analisar_crm": ("CRM (Monday): leads por origem e tipo, qualificação por campanha, vendas, receita via tráfego, "
                     "ROAS e ROI.", {"dias": _DIAS}, lambda db, dias: db.ler_crm(dias)),
    "analisar_brevo": ("E-mail marketing (Brevo): campanhas, entregues, abertura, cliques, descadastros e bounces.",
                       {"dias": _DIAS}, lambda db, dias: db.ler_brevo(dias)),
}


def disponivel() -> bool:
    return (SISTEMA / "db_manager.py").exists() and Path(os.getenv("SOCIAL_ANALYTICS_DADOS", "/painel"), "analytics.db").exists()


def _db():
    if str(SISTEMA) not in sys.path:
        sys.path.insert(0, str(SISTEMA))
    # As análises de anúncios fazem "from coleta import config" (contas de anúncio por marca). O __init__ do pacote
    # coleta carrega o motor de coleta inteiro (Google, Meta, Monday...), que não é preciso aqui: registra o pacote
    # sem o __init__, e só o config.py é carregado.
    if "coleta" not in sys.modules:
        pacote = types.ModuleType("coleta")
        pacote.__path__ = [str(SISTEMA / "coleta")]
        sys.modules["coleta"] = pacote
    import db_manager  # código do painel (só leitura); o banco vem de SOCIAL_ANALYTICS_DADOS

    return db_manager


BANCO = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", "/painel")) / "analytics.db"
CONTAS = {"casa_veraneio": "casaveraneio", "cv_corporativo": "casaveraneiocorp", "casa_vero": "casaveroimoveis"}
METRICAS_RANKING = {"taxa_valor", "visualizacoes", "alcance", "interacoes", "salvamentos", "compartilhamentos",
                    "comentarios", "curtidas"}
TAXA_VALOR = "(COALESCE(salvamentos, 0) + COALESCE(compartilhamentos, 0)) * 1.0 / NULLIF(alcance, 0)"


def ranking_publicacoes(empresa: str, dias: int = 30, limite: int = 10, metrica: str = "taxa_valor",
                        conta: str = "", formato: str = "") -> str:
    """Ranking de uma conta só (só leitura no banco do painel, sem mexer no código dele). Empresa "*" (grupo): um
    bloco por conta, na ordem Veraneio, Corp, Vero."""
    if metrica not in METRICAS_RANKING:
        return f"Métrica inválida. Use uma de: {', '.join(sorted(METRICAS_RANKING))}."
    conta = conta.strip().lstrip("@").lower()
    if conta and conta not in CONTAS.values():
        return f"Conta inválida. Use uma de: {', '.join(CONTAS.values())}."
    contas = [conta] if conta else list(CONTAS.values()) if empresa == "*" else [CONTAS.get(empresa, "casaveraneio")]
    ordem = TAXA_VALOR if metrica == "taxa_valor" else metrica  # metrica validada acima: nunca texto livre no SQL
    import sqlite3

    blocos = []
    with sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True) as db:
        for c in contas:
            filtro, valores = ("AND upper(tipo) = ?", [formato.strip().upper()]) if formato.strip() else ("", [])
            linhas = db.execute(
                "SELECT substr(publicado_em, 1, 10), tipo, visualizacoes, alcance, salvamentos, compartilhamentos, "
                f"comentarios, {TAXA_VALOR}, legenda, link FROM instagram_posts WHERE nome_conta = ? "
                f"AND substr(publicado_em, 1, 10) >= date('now', 'localtime', ?) {filtro} "
                f"ORDER BY {ordem} IS NULL, {ordem} DESC LIMIT ?", (c, f"-{int(dias)} days", *valores, int(limite))
            ).fetchall()
            if not linhas:
                blocos.append(f"@{c}: nenhuma publicação{' ' + formato.upper() if formato else ''} nos últimos {dias} dias.")
                continue
            itens = [f"{k}. {data} · {tipo} · taxa de valor {f'{taxa * 100:.1f}%' if taxa is not None else '—'} · "
                     f"alcance {alcance} · views {views} · salvamentos {salv} · compartilhamentos {comp} · "
                     f"comentários {coment}\n   \"{(legenda or '')[:120]}\" {link or ''}"
                     for k, (data, tipo, views, alcance, salv, comp, coment, taxa, legenda, link) in enumerate(linhas, 1)]
            blocos.append(f"@{c} — top {len(linhas)} por {metrica} nos últimos {dias} dias:\n" + "\n".join(itens))
    return ("Métricas acumuladas desde a publicação (posts recentes ainda estão crescendo); compare cada conta com "
            "ela mesma, nunca números absolutos entre contas de tamanhos diferentes.\n\n" + "\n\n".join(blocos))


def _ferramenta(nome: str, descricao: str, parametros: dict, chamada, tarefa_id: int, agente_id: str) -> BaseTool:
    esquema = create_model(f"_{nome}", **parametros) if parametros else create_model(f"_{nome}")

    def _run(self, **argumentos) -> str:
        try:
            if chamada is None:  # ranking por conta: leitura do próprio escritório, na empresa da tarefa
                import cerebro

                resposta = ranking_publicacoes(cerebro.empresa_da_tarefa(tarefa_id), **argumentos)
            else:
                resposta = str(chamada(_db(), **argumentos))
        except Exception as erro:
            return f"Não foi possível ler o painel agora: {erro}"
        if tarefa_id:  # quem consultou de fato (antes ficava sempre "analista_metricas")
            tarefas.registrar_evento(tarefa_id, "consulta_painel", agente_id,
                                     detalhe=f"{nome}({', '.join(f'{k}={v}' for k, v in argumentos.items())})")
        return resposta[:MAX_SAIDA] + ("\n[… resposta cortada: peça um período menor ou uma campanha específica]"
                                       if len(resposta) > MAX_SAIDA else "")

    classe = type(f"Ferramenta_{nome}", (BaseTool,), {"__module__": __name__,
                                                      "__annotations__": {"name": str, "description": str,
                                                                           "args_schema": type[BaseModel]},
                                                      "name": nome, "description": f"Painel analítico: {descricao}",
                                                      "args_schema": esquema, "_run": _run})
    return classe()


def instrucoes() -> str:
    """Regras de leitura dos dados do painel (do INSTRUCOES_AGENTE.md dele): o que não somar, o que comparar, limites."""
    arquivo = SISTEMA / "INSTRUCOES_AGENTE.md"
    if not arquivo.exists():
        return ""
    texto = arquivo.read_text(encoding="utf-8")
    partes = [m.group(0) for m in re.finditer(r"## (?:Regras de Atuação|Limitações dos Dados)\n.*?(?=\n## |\Z)", texto, re.S)]
    return ("DADOS DO PAINEL ANALÍTICO: use as ferramentas do painel (analisar_*, comparar_redes, obter_metricas_hoje) "
            "para qualquer número; nunca invente nem estime sem dizer. Informe o período e a data dos dados. Marcas: "
            "Casa Veraneio (hospedagem), Casa Corp (= Casa Veraneio Corporativo) e Casa Vero; analise a empresa do "
            "trabalho e só compare com as outras se o usuário pedir. TRABALHO DO GRUPO (as três empresas): abra com "
            "\"Respondi pelas três empresas, cada uma no seu bloco\" e responda em três blocos, sempre nesta ordem: "
            "Casa Veraneio, Casa Veraneio Corporativo, Casa Vero; cada bloco com a sua métrica principal e a sua ação. "
            "As contas têm tamanhos muito diferentes: compare cada uma com a própria média (variação, taxa de valor, "
            "alcance por post), nunca número absoluto de uma contra a outra.\n\n" + "\n\n".join(partes))


# Vendas, receita, investimento em mídia, custo por resultado, ROAS/ROI: só a Diretoria (Thomas, 29/10/2026). As
# métricas de redes sociais e de e-mail valem para todos.
FINANCEIRAS = {"analisar_impulsionamentos", "analisar_trafego_pago", "analisar_google_ads", "analisar_crm"}
# Gestor de Tráfego (levantamento de 31/10/2026, gestor_trafego-01): os números de anúncio do painel, com a mesma trava
# financeira. Abrir uma versão sem reais para a equipe depende da decisão 11 do Thomas (gestor_trafego-02).
DO_AGENTE = {"analista_metricas": set(ANALISES), "gestor_trafego": FINANCEIRAS}


def para(agente_id: str, tarefa_id: int = 0, financeiro: bool = False) -> list[BaseTool]:
    """Ferramentas do painel do agente (só com o painel montado); as financeiras só para a Diretoria (`financeiro`)."""
    if agente_id not in DO_AGENTE or not disponivel():
        return []
    return [_ferramenta(nome, descricao, parametros, chamada, tarefa_id, agente_id)
            for nome, (descricao, parametros, chamada) in ANALISES.items()
            if nome in DO_AGENTE[agente_id] and (financeiro or nome not in FINANCEIRAS)]
