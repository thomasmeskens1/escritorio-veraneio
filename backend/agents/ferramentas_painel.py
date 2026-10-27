"""Ferramentas do Analista de Métricas ligadas ao painel analítico (Sistema Casa Veraneio), pedido do Thomas
(26/10/2026): os números do momento, com as MESMAS análises que o painel e o agente analista dele usam.

O código do painel (C:\\dev\\social-analytics) e a pasta de dados dele (analytics.db, .env) estão montados SÓ
LEITURA no container (docker-compose.yml: SISTEMA_DIR e SOCIAL_ANALYTICS_DADOS). Cada ferramenta chama a função
de leitura do painel (db_manager.ler_*), sem duplicar cálculo nem tocar nas APIs.
Só na conta do Thomas: há vendas, receita e investimento (executor.py).
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
    "analisar_melhores_publicacoes": ("Ranking das publicações do Instagram (todas as contas) no período.",
                                      {"dias": _DIAS, "limite": _LIMITE,
                                       "metrica": (str, Field("visualizacoes", description="visualizacoes, alcance, "
                                                              "interacoes, salvamentos, compartilhamentos, comentarios ou curtidas"))},
                                      lambda db, dias, limite, metrica: db.ler_melhores_publicacoes(dias, metrica, limite)),
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


def _ferramenta(nome: str, descricao: str, parametros: dict, chamada, tarefa_id: int) -> BaseTool:
    esquema = create_model(f"_{nome}", **parametros) if parametros else create_model(f"_{nome}")

    def _run(self, **argumentos) -> str:
        try:
            resposta = str(chamada(_db(), **argumentos))
        except Exception as erro:
            return f"Não foi possível ler o painel agora: {erro}"
        if tarefa_id:
            tarefas.registrar_evento(tarefa_id, "consulta_painel", "analista_metricas",
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
            "trabalho e só compare com as outras se o usuário pedir.\n\n" + "\n\n".join(partes))


def para(agente_id: str, tarefa_id: int = 0) -> list[BaseTool]:
    """Ferramentas do painel (só o Analista de Métricas e só com o painel montado)."""
    if agente_id != "analista_metricas" or not disponivel():
        return []
    return [_ferramenta(nome, descricao, parametros, chamada, tarefa_id)
            for nome, (descricao, parametros, chamada) in ANALISES.items()]
