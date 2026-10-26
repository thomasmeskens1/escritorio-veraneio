"""Painel analítico (C:\\dev\\social-analytics, "Sistema Casa Veraneio") para o Cérebro: o que já publicamos, o que
performa, o que a mídia paga entrega e o que o CRM fecha. Liberado pelo Thomas em 26/10/2026.

Lê o banco do painel (%LOCALAPPDATA%\\SocialAnalytics\\analytics.db) SOMENTE LEITURA, sem tokens: o painel coleta
pelas APIs oficiais (Instagram e Meta Ads com o token da Meta, YouTube, Google Ads, Monday/CRM, Brevo).
- Cada publicação do Instagram vira um documento (legenda + métricas), na empresa da conta. Fonte "rede".
- Resumos por empresa (fonte "dados"): desempenho do Instagram e do YouTube, tráfego pago (Meta e Google Ads, com
  os textos de anúncio e as buscas que convertem), CRM (leads e vendas por mês, só números) e e-mail marketing.
Nada pessoal entra no Cérebro: sem nomes, e-mails ou telefones de leads e clientes (só contagens e somas).
Marcas (regras do painel, INSTRUCOES_AGENTE.md): Corporativo = conta "Casa Corp", campanhas com "Corp" no nome,
leads do tipo "Corporativo" e o Funil Corp; impulsionamento = conta do Instagram do post.

Uso: python scripts/max/painel_analitico.py (também roda no ciclo de 6 h do trabalhador).
"""

import os
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import comum
from comum import log
from sites_empresas import TELEFONE

BANCO = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", Path(os.environ.get("LOCALAPPDATA", "")) / "SocialAnalytics")) / "analytics.db"
CONTA_INSTAGRAM = {"casaveraneio": "casa_veraneio", "casaveraneiocorp": "cv_corporativo", "casaveroimoveis": "casa_vero"}
CONTAS_ANUNCIO = {"act_1868351480015873": "casa_veraneio", "act_1227886486162881": "cv_corporativo"}
NOME_EMPRESA = {"casa_veraneio": "Casa Veraneio", "cv_corporativo": "Casa Veraneio Corporativo", "casa_vero": "Casa Vero Imóveis"}
CORP = re.compile(r"corp|corporativ|eventos corporativos", re.I)
# E-mail: a regra do painel (coleta/brevo.py) olha só o nome da campanha; o assunto também denuncia o Corporativo.
EMAIL_CORP = re.compile(r"\bcorp\b|corporativ|\boff-?site\b|\bempresa\b|confraterniza|\bseu time\b|\beventos?\b|"
                        r"escrit[óo]rio", re.I)
MESES_RESUMO = 12
LOTE = 20
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _banco() -> sqlite3.Connection:
    banco = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    banco.row_factory = sqlite3.Row
    return banco


def _inicio(meses: int = MESES_RESUMO) -> str:
    return (date.today() - timedelta(days=30 * meses)).isoformat()


def _n(valor) -> str:
    return f"{round(valor or 0):,}".replace(",", ".")


def _r(valor) -> str:
    return "R$ " + f"{valor or 0:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _doc(empresa: str, ref: str, titulo: str, conteudo: str, tipo: str = "dados") -> dict:
    # A empresa entra na referência: o Cérebro identifica o documento só por (tipo, ref), e o mesmo resumo existe
    # para as três empresas (sem isso, o envio de uma sobrescrevia o da outra).
    return {"fonte_tipo": tipo, "empresa": empresa, "fonte_ref": ref.replace("analytics/", f"analytics/{empresa}/", 1), "titulo": f"{titulo} — {NOME_EMPRESA[empresa]}",
            "conteudo": f"Fonte: painel analítico interno (Sistema Casa Veraneio), dados de {date.today():%d/%m/%Y}\n"
                        "USO INTERNO: referência para decidir conteúdo e mídia; nunca publicar estes números (vendas, "
                        "investimento, resultados).\n" + conteudo}


# --- Instagram ---------------------------------------------------------------------------------------------------

def _legenda(texto: str | None, limite: int) -> str:
    return TELEFONE.sub("", re.sub(r"\s+", " ", texto or "")).strip()[:limite]


def instagram(banco: sqlite3.Connection) -> list[dict]:
    documentos = []
    for post in banco.execute("SELECT * FROM instagram_posts ORDER BY publicado_em"):
        empresa = CONTA_INSTAGRAM.get(post["nome_conta"])
        if not empresa or not (post["legenda"] or "").strip():
            continue
        quando = post["publicado_em"][:10]
        metricas = (f"alcance {_n(post['alcance'])} · visualizações {_n(post['visualizacoes'])} · interações "
                    f"{_n(post['interacoes'])} · salvamentos {_n(post['salvamentos'])} · compartilhamentos "
                    f"{_n(post['compartilhamentos'])} · curtidas {_n(post['curtidas'])} · comentários {_n(post['comentarios'])}")
        documentos.append({"fonte_tipo": "rede", "empresa": empresa,
                           "fonte_ref": f"instagram/{post['nome_conta']}/{post['post_id']}",
                           "titulo": f"Instagram @{post['nome_conta']}: {post['tipo']} de {quando[8:10]}/{quando[5:7]}/{quando[:4]}",
                           "conteudo": f"Fonte: {post['link']} (Instagram @{post['nome_conta']}, publicado em {quando})\n"
                                       f"Formato: {post['tipo']}\nDesempenho acumulado: {metricas}\n"
                                       f"Legenda publicada: {_legenda(post['legenda'], 4000)}"})
    for conta, empresa in CONTA_INSTAGRAM.items():
        posts = banco.execute("SELECT * FROM instagram_posts WHERE nome_conta = ? AND publicado_em >= ?",
                              (conta, _inicio())).fetchall()
        if posts:
            documentos.append(_doc(empresa, f"analytics/instagram/{conta}", f"Desempenho no Instagram @{conta}",
                                   _resumo_instagram(banco, conta, posts)))
    return documentos


def _top(posts: list, metrica: str, rotulo: str, n: int = 8) -> str:
    melhores = sorted(posts, key=lambda p: p[metrica] or 0, reverse=True)[:n]
    return f"Top {n} por {rotulo}:\n" + "\n".join(
        f"- {p['publicado_em'][:10]} {p['tipo']}: {_n(p[metrica])} — \"{_legenda(p['legenda'], 110)}\" ({p['link']})"
        for p in melhores)


def _resumo_instagram(banco: sqlite3.Connection, conta: str, posts: list) -> str:
    partes = [f"Últimos {MESES_RESUMO} meses: {len(posts)} publicações (métricas acumuladas desde a publicação; posts "
              "recentes ainda estão crescendo)."]
    por_tipo = defaultdict(list)
    for p in posts:
        por_tipo[p["tipo"]].append(p)
    partes.append("Média por formato: " + "; ".join(
        f"{tipo} ({len(lista)}): alcance {_n(sum(p['alcance'] or 0 for p in lista) / len(lista))}, salvamentos "
        f"{_n(sum(p['salvamentos'] or 0 for p in lista) / len(lista))}, compartilhamentos "
        f"{_n(sum(p['compartilhamentos'] or 0 for p in lista) / len(lista))}" for tipo, lista in por_tipo.items()))
    por_dia = defaultdict(list)
    for p in posts:
        por_dia[datetime.fromisoformat(p["publicado_em"]).weekday()].append(p["alcance"] or 0)
    ranking = sorted(((sum(v) / len(v), d, len(v)) for d, v in por_dia.items() if len(v) >= 3), reverse=True)
    if ranking:
        partes.append("Alcance médio por dia da semana (com 3+ posts): " + ", ".join(
            f"{DIAS_SEMANA[d]} {_n(media)} ({qtd})" for media, d, qtd in ranking))
    partes += [_top(posts, "alcance", "alcance"), _top(posts, "salvamentos", "salvamentos"),
               _top(posts, "compartilhamentos", "compartilhamentos")]
    meses = banco.execute("SELECT substr(data, 1, 7) AS mes, SUM(seguiram) AS s, SUM(deixaram_de_seguir) AS d, "
                          "SUM(visualizacoes) AS v, SUM(interacoes) AS i FROM instagram_diario WHERE nome_conta = ? "
                          "AND data >= ? GROUP BY mes ORDER BY mes", (conta, _inicio(6))).fetchall()
    if meses:
        partes.append("Últimos meses (visualizações · interações · seguidores ganhos − perdidos): " + "; ".join(
            f"{m['mes']}: {_n(m['v'])} · {_n(m['i'])} · +{_n(m['s'])}/−{_n(m['d'])}" for m in meses))
    seguidores = banco.execute("SELECT seguidores, data FROM estatisticas WHERE nome_conta = ? ORDER BY data DESC LIMIT 1",
                               (conta,)).fetchone()
    if seguidores:
        partes.append(f"Seguidores em {seguidores['data']}: {_n(seguidores['seguidores'])}.")
    return "\n".join(partes)


# --- YouTube (Casa Vero) -----------------------------------------------------------------------------------------

def youtube(banco: sqlite3.Connection) -> list[dict]:
    videos = banco.execute("SELECT * FROM youtube_publicacoes").fetchall()
    if not videos:
        return []
    partes = []
    for formato, rotulo in (("video", "Vídeos longos"), ("short", "Shorts")):
        lista = [v for v in videos if v["formato"] == formato]
        if not lista:
            continue
        partes.append(f"{rotulo}: {len(lista)}, {_n(sum(v['visualizacoes'] or 0 for v in lista))} visualizações, "
                      f"{_n(sum(v['minutos_assistidos'] or 0 for v in lista) / 60)} horas assistidas, "
                      f"{_n(sum(v['inscritos_ganhos'] or 0 for v in lista))} inscritos ganhos.")
        for metrica, nome in (("visualizacoes", "visualizações"), ("minutos_assistidos", "minutos assistidos")):
            melhores = sorted(lista, key=lambda v: v[metrica] or 0, reverse=True)[:8]
            partes.append(f"Top 8 {rotulo.lower()} por {nome}:\n" + "\n".join(
                f"- {v['publicado_em'][:10]}: {_n(v[metrica])} — {v['titulo']} (assistido em média "
                f"{_n((v['duracao_media_s'] or 0) / 60)} de {_n((v['duracao_s'] or 0) / 60)} min)" for v in melhores))
    meses = banco.execute("SELECT substr(data, 1, 7) AS mes, SUM(visualizacoes) AS v, SUM(minutos_assistidos) AS m, "
                          "SUM(inscritos_ganhos) - SUM(inscritos_perdidos) AS i FROM youtube_diario WHERE data >= ? "
                          "GROUP BY mes ORDER BY mes", (_inicio(6),)).fetchall()
    if meses:
        partes.append("Por mês (visualizações · horas · saldo de inscritos): " + "; ".join(
            f"{m['mes']}: {_n(m['v'])} · {_n((m['m'] or 0) / 60)} · {_n(m['i'])}" for m in meses))
    return [_doc("casa_vero", "analytics/youtube", "Desempenho do YouTube (@CasaVeroImóveis)", "\n".join(partes))]


# --- Tráfego pago ------------------------------------------------------------------------------------------------

def _empresa_do_anuncio(banco: sqlite3.Connection, anuncio: sqlite3.Row) -> str | None:
    if anuncio["tipo"] == "impulsionamento" and anuncio["post_origem_id"]:
        conta = banco.execute("SELECT nome_conta FROM instagram_posts WHERE post_id = ?",
                              (anuncio["post_origem_id"],)).fetchone()
        return CONTA_INSTAGRAM.get(conta["nome_conta"]) if conta else None
    if CORP.search(anuncio["campanha"] or ""):
        return "cv_corporativo"
    return CONTAS_ANUNCIO.get(anuncio["conta_anuncio"])


def meta_ads(banco: sqlite3.Connection) -> list[dict]:
    campanhas: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for anuncio in banco.execute("SELECT * FROM anuncios WHERE conta_anuncio LIKE 'act_%'"):
        empresa = _empresa_do_anuncio(banco, anuncio)
        if not empresa:
            continue
        soma = banco.execute("SELECT SUM(investimento) inv, SUM(impressoes) imp, SUM(cliques_link) cli, SUM(leads) lea, "
                             "SUM(mensagens) msg, SUM(engajamento) eng FROM anuncios_diario WHERE ad_id = ? AND data >= ?",
                             (anuncio["ad_id"], _inicio())).fetchone()
        if not soma["inv"]:
            continue
        chave = f"{'Impulsionamento' if anuncio['tipo'] == 'impulsionamento' else 'Gerenciador'} · {anuncio['campanha']} ({anuncio['objetivo'] or '—'})"
        for campo in ("inv", "imp", "cli", "lea", "msg", "eng"):
            campanhas[empresa][chave][campo] += soma[campo] or 0
    documentos = []
    for empresa, lista in campanhas.items():
        total = {c: sum(v[c] for v in lista.values()) for c in ("inv", "imp", "cli", "lea", "msg")}
        linhas = [f"Meta Ads, últimos {MESES_RESUMO} meses: investimento {_r(total['inv'])}, {_n(total['imp'])} impressões, "
                  f"{_n(total['cli'])} cliques no link, {_n(total['lea'])} leads, {_n(total['msg'])} conversas"
                  + (f", custo por lead {_r(total['inv'] / total['lea'])}" if total["lea"] else "") + ".",
                  "O resultado depende do objetivo de cada campanha: não some resultados de objetivos diferentes.",
                  "Campanhas com mais investimento:"]
        for nome, v in sorted(lista.items(), key=lambda par: -par[1]["inv"])[:20]:
            ctr = f", CTR {100 * v['cli'] / v['imp']:.2f}%" if v["imp"] else ""
            cpl = f", {_n(v['lea'])} leads (CPL {_r(v['inv'] / v['lea'])})" if v["lea"] else ""
            linhas.append(f"- {nome}: {_r(v['inv'])}, {_n(v['imp'])} impressões{ctr}{cpl}"
                          + (f", {_n(v['msg'])} conversas" if v["msg"] else ""))
        documentos.append(_doc(empresa, "analytics/meta-ads", "Tráfego pago na Meta (Facebook/Instagram)", "\n".join(linhas)))
    return documentos


def google_ads(banco: sqlite3.Connection) -> list[dict]:
    por_empresa = defaultdict(list)
    for campanha in banco.execute("SELECT * FROM gads_campanhas"):
        por_empresa["cv_corporativo" if CORP.search(campanha["nome"]) else "casa_veraneio"].append(campanha)
    documentos = []
    for empresa, campanhas in por_empresa.items():
        ids = [c["campanha_id"] for c in campanhas]
        marcas = ",".join("?" * len(ids))
        linhas = ["Google Ads, últimos 90 dias (o resultado é a conversão configurada na conta; não somar com leads "
                  "da Meta). Por campanha:"]
        for c in campanhas:
            s = banco.execute("SELECT SUM(investimento) inv, SUM(impressoes) imp, SUM(cliques) cli, SUM(conversoes) con "
                              "FROM gads_diario WHERE nivel = 'campanha' AND entidade_id = ?", (c["campanha_id"],)).fetchone()
            if s["inv"]:
                linhas.append(f"- {c['nome']} ({c['status']}, {c['tipo']}): {_r(s['inv'])}, {_n(s['cli'])} cliques, "
                              f"{s['con'] or 0:.1f} conversões" + (f", custo/conversão {_r(s['inv'] / s['con'])}" if s["con"] else ""))
        termos = banco.execute(f"SELECT termo, SUM(conversoes) con, SUM(cliques) cli, SUM(investimento) inv FROM gads_termos "
                               f"WHERE campanha_id IN ({marcas}) GROUP BY termo HAVING con > 0 ORDER BY con DESC LIMIT 30",
                               ids).fetchall()
        if termos:
            linhas.append("Buscas que mais converteram (termo · conversões · cliques · investimento): " + "; ".join(
                f"\"{t['termo']}\" {t['con']:.1f} · {_n(t['cli'])} · {_r(t['inv'])}" for t in termos))
        palavras = banco.execute(f"SELECT p.texto, p.correspondencia, p.qs, SUM(d.conversoes) con, SUM(d.cliques) cli "
                                 f"FROM gads_palavras p JOIN gads_diario d ON d.nivel = 'palavra' AND d.entidade_id = p.palavra_id "
                                 f"WHERE p.campanha_id IN ({marcas}) AND p.negativa = 0 GROUP BY p.palavra_id "
                                 f"ORDER BY con DESC, cli DESC LIMIT 25", ids).fetchall()
        if palavras:
            linhas.append("Palavras-chave com mais resultado (palavra [correspondência] · Índice de Qualidade · conversões · "
                          "cliques): " + "; ".join(f"{p['texto']} [{p['correspondencia']}] · QS {p['qs'] or '—'} · "
                                                   f"{p['con'] or 0:.1f} · {_n(p['cli'])}" for p in palavras))
        textos = banco.execute(f"SELECT DISTINCT r.campo, r.texto FROM gads_recursos r JOIN gads_anuncios a ON a.anuncio_id = "
                               f"r.anuncio_id WHERE a.campanha_id IN ({marcas}) AND r.campo IN ('HEADLINE', 'DESCRIPTION', "
                               f"'LONG_HEADLINE') AND a.status = 'ENABLED'", ids).fetchall()
        for campo, rotulo in (("HEADLINE", "Títulos de anúncio em uso"), ("DESCRIPTION", "Descrições de anúncio em uso")):
            lista = [t["texto"] for t in textos if t["campo"] == campo]
            if lista:
                linhas.append(f"{rotulo}: " + " | ".join(lista[:60]))
        cidades = banco.execute(f"SELECT COALESCE(n.nome_curto, g.geo_id) cidade, SUM(g.investimento) inv, SUM(g.conversoes) con "
                                f"FROM gads_geo_diario g LEFT JOIN gads_geo_nomes n ON n.geo_id = g.geo_id WHERE "
                                f"g.campanha_id IN ({marcas}) GROUP BY cidade ORDER BY con DESC, inv DESC LIMIT 12", ids).fetchall()
        if cidades:
            linhas.append("Cidades de onde vêm as conversões (onde a pessoa estava): " + "; ".join(
                f"{c['cidade']} {c['con'] or 0:.1f} conv. ({_r(c['inv'])})" for c in cidades))
        documentos.append(_doc(empresa, "analytics/google-ads", "Google Ads: campanhas, buscas e anúncios", "\n".join(linhas)))
    return documentos


# --- CRM e e-mail (só números) -----------------------------------------------------------------------------------

def crm(banco: sqlite3.Connection) -> list[dict]:
    documentos = []
    for empresa, tipo, negocio in (("casa_veraneio", "Hospedagem", "Hospedagem"), ("cv_corporativo", "Corporativo", "Corp")):
        leads = banco.execute("SELECT substr(data, 1, 7) mes, COUNT(*) n, SUM(status = 'Qualificado') q, "
                              "SUM(origem = 'Tráfego') t, SUM(origem = 'Orgânico') o FROM crm_leads WHERE tipo = ? "
                              "AND data >= ? GROUP BY mes ORDER BY mes", (tipo, _inicio())).fetchall()
        vendas = banco.execute("SELECT substr(data, 1, 7) mes, COUNT(*) n, SUM(valor) v FROM crm_vendas WHERE negocio = ? "
                               "AND data >= ? GROUP BY mes ORDER BY mes", (negocio, _inicio())).fetchall()
        campanhas = banco.execute("SELECT COALESCE(NULLIF(campanha, ''), utm_source, 'sem campanha') c, COUNT(*) n FROM crm_leads "
                                  "WHERE tipo = ? AND data >= ? AND origem = 'Tráfego' GROUP BY c ORDER BY n DESC LIMIT 12",
                                  (tipo, _inicio())).fetchall()
        if not leads and not vendas:
            continue
        linhas = [f"CRM (Monday), últimos {MESES_RESUMO} meses. Só totais; nenhum dado pessoal de cliente.",
                  "Leads por mês (total · qualificados · de tráfego pago · orgânicos): " + "; ".join(
                      f"{l['mes']}: {l['n']} · {l['q'] or 0} · {l['t'] or 0} · {l['o'] or 0}" for l in leads)]
        if vendas:
            total = sum(v["v"] or 0 for v in vendas)
            qtd = sum(v["n"] for v in vendas)
            linhas.append(f"Vendas ({negocio}): {qtd} no período, {_r(total)}"
                          + (f", ticket médio {_r(total / qtd)}" if qtd else "") + ". Por mês (quantidade · valor): "
                          + "; ".join(f"{v['mes']}: {v['n']} · {_r(v['v'])}" for v in vendas))
        if campanhas:
            linhas.append("Campanhas que mais trouxeram leads de tráfego: " + "; ".join(f"{c['c']} ({c['n']})" for c in campanhas))
        documentos.append(_doc(empresa, "analytics/crm", "Leads e vendas (CRM)", "\n".join(linhas)))
    return documentos


def email(banco: sqlite3.Connection) -> list[dict]:
    documentos = []
    todas = banco.execute("SELECT * FROM brevo_campanhas WHERE COALESCE(teste, 0) = 0 ORDER BY enviada_em DESC").fetchall()
    corp = {c["campanha_id"] for c in todas if c["marca"] == "corp" or EMAIL_CORP.search(f"{c['nome']} {c['assunto']}")}
    for empresa, eh_corp in (("casa_veraneio", False), ("cv_corporativo", True)):
        campanhas = [c for c in todas if (c["campanha_id"] in corp) == eh_corp]
        if not campanhas:
            continue
        linhas = ["E-mail marketing (Brevo). Taxas sobre os entregues; a abertura inclui aberturas automáticas do Apple Mail "
                  "(compare campanhas pela taxa de cliques). Assunto · data · entregues · abertura · cliques:"]
        for c in campanhas:
            entregues = c["entregues"] or 0
            taxa = (lambda x: f"{100 * (x or 0) / entregues:.1f}%" if entregues else "—")
            linhas.append(f"- \"{c['assunto']}\" · {(c['enviada_em'] or '')[:10]} · {_n(entregues)} · {taxa(c['aberturas'])} · {taxa(c['cliques'])}")
        documentos.append(_doc(empresa, "analytics/email", "E-mail marketing", "\n".join(linhas)))
    return documentos


def documentos() -> list[dict]:
    banco = _banco()
    try:
        return [*instagram(banco), *youtube(banco), *meta_ads(banco), *google_ads(banco), *crm(banco), *email(banco)]
    finally:
        banco.close()


def rodar() -> None:
    if not BANCO.exists():
        log("Painel analítico: banco não encontrado (o app Sistema Casa Veraneio está instalado nesta máquina?).")
        return
    try:
        lista = documentos()
    except Exception as erro:
        log(f"Painel analítico: não foi possível ler o banco ({erro}).")
        return
    enviados = all([comum.enviar_ao_cerebro(lista[i:i + LOTE]) for i in range(0, len(lista), LOTE)])
    log(f"Painel analítico: {len(lista)} documento(s) para o Cérebro{'' if enviados else ' (envio adiado)'}.")


if __name__ == "__main__":
    rodar()
