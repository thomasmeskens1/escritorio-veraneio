"""Relatório visual do Analista de Métricas (Thomas, 28/10/2026, em teste): uma página HTML com gráficos para cada
resposta, ao lado do texto do agente. Os NÚMEROS dos gráficos saem direto do banco do painel analítico (consultas
só leitura); o modelo escreve só a análise. Assim nenhum número da página é digitado por modelo.

A página fica em dados/relatorios/<tarefa>-<token>.html e abre pelo botão "Ver relatório" no chat. O token no nome
faz o papel de senha do link (a página não pede login porque abre numa aba nova).
"""

import html
import json
import logging
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import config
import empresas

log = logging.getLogger(__name__)

AGENTE = "analista_metricas"
PASTA = config.DADOS_DIR / "relatorios"
BANCO = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", "/painel")) / "analytics.db"
CONTAS_INSTAGRAM = {"casa_veraneio": "casaveraneio", "cv_corporativo": "casaveraneiocorp",
                    "casa_vero": "casaveroimoveis"}
YOUTUBE = "casa_vero"  # o canal do YouTube coletado é o da Casa Vero
MESES = 6
NOME_ARQUIVO = re.compile(r"^(\d+)-[\w-]{20,}\.html$")
# Caramelo da marca (manual 01) e o verde-água do escritório: legíveis no tema claro e no escuro (o Verde #00361b
# some no fundo escuro).
CORES = ["#2a9d8f", "#d9a15b", "#7fc29b", "#8c6d46"]

rotas = APIRouter()


def _conexao() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)


def _instagram_mensal(db, conta: str, meses: int) -> list[dict]:
    linhas = db.execute(
        "SELECT substr(data, 1, 7) mes, SUM(alcance), SUM(visualizacoes), SUM(interacoes), SUM(salvamentos), "
        "SUM(compartilhamentos), SUM(seguiram), SUM(deixaram_de_seguir) FROM instagram_diario WHERE nome_conta = ? "
        "GROUP BY mes ORDER BY mes DESC LIMIT ?", (conta, meses)).fetchall()
    chaves = ("mes", "alcance", "views", "interacoes", "salvamentos", "compartilhamentos", "seguiram", "deixaram")
    return [dict(zip(chaves, linha)) for linha in reversed(linhas)]


def _seguidores(db, conta: str, dias: int = 90) -> list[tuple[str, int]]:
    desde = (date.today() - timedelta(days=dias)).isoformat()
    return db.execute("SELECT data, seguidores FROM estatisticas WHERE rede = 'Instagram' AND nome_conta = ? "
                      "AND data >= ? AND seguidores IS NOT NULL ORDER BY data", (conta, desde)).fetchall()


def _melhores(db, conta: str, dias: int = 30, limite: int = 5) -> list[dict]:
    desde = (date.today() - timedelta(days=dias)).isoformat()
    linhas = db.execute(
        "SELECT publicado_em, tipo, legenda, link, alcance, visualizacoes, salvamentos, compartilhamentos "
        "FROM instagram_posts WHERE nome_conta = ? AND publicado_em >= ? "
        "ORDER BY COALESCE(salvamentos, 0) + COALESCE(compartilhamentos, 0) DESC LIMIT ?",
        (conta, desde, limite)).fetchall()
    chaves = ("data", "tipo", "legenda", "link", "alcance", "views", "salvamentos", "compartilhamentos")
    return [dict(zip(chaves, linha)) for linha in linhas]


def _youtube_mensal(db, meses: int) -> list[dict]:
    linhas = db.execute(
        "SELECT substr(data, 1, 7) mes, SUM(visualizacoes), SUM(minutos_assistidos), "
        "SUM(inscritos_ganhos) - SUM(inscritos_perdidos) FROM youtube_diario GROUP BY mes ORDER BY mes DESC LIMIT ?",
        (meses,)).fetchall()
    return [dict(zip(("mes", "views", "minutos", "saldo"), linha)) for linha in reversed(linhas)]


def dados(empresa: str) -> dict:
    """Números da(s) empresa(s) do trabalho; "*" = as três, cada uma no seu bloco."""
    alvo = list(CONTAS_INSTAGRAM) if empresa == empresas.COMUM else [empresa]
    with _conexao() as db:
        blocos = []
        for e in alvo:
            if e not in CONTAS_INSTAGRAM:
                continue
            conta = CONTAS_INSTAGRAM[e]
            blocos.append({"empresa": empresas.nome(e), "conta": conta,
                           "mensal": _instagram_mensal(db, conta, MESES), "seguidores": _seguidores(db, conta),
                           "melhores": _melhores(db, conta),
                           "youtube": _youtube_mensal(db, MESES) if e == YOUTUBE else []})
        coleta = db.execute("SELECT MAX(data) FROM instagram_diario").fetchone()[0]
    return {"blocos": blocos, "coleta": coleta}


def _num(valor) -> str:
    return "—" if valor is None else f"{valor:,.0f}".replace(",", ".")


def _grafico(id_: str, titulo: str, tipo: str, rotulos: list, series: list[tuple[str, list]]) -> str:
    conjuntos = [{"label": nome, "data": valores, "backgroundColor": CORES[i % len(CORES)],
                  "borderColor": CORES[i % len(CORES)], "tension": 0.25, "pointRadius": 0 if tipo == "line" else 3}
                 for i, (nome, valores) in enumerate(series)]
    config_grafico = {"type": tipo, "data": {"labels": rotulos, "datasets": conjuntos},
                      "options": {"responsive": True, "maintainAspectRatio": False,
                                  "plugins": {"legend": {"position": "bottom"},
                                              "title": {"display": True, "text": titulo, "align": "start"}}}}
    return (f'<div class="grafico"><canvas id="{id_}"></canvas></div>'
            f'<script>graficos.push(["{id_}", {json.dumps(config_grafico, ensure_ascii=False)}]);</script>')


def _analise_html(texto: str) -> str:
    """Markdown simples da resposta do agente (títulos, listas, negrito) para HTML seguro."""
    partes = []
    for bloco in re.split(r"\n{2,}", texto.strip()):
        linhas = [html.escape(l) for l in bloco.splitlines() if l.strip()]
        linhas = [re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", l) for l in linhas]
        if not linhas or all(re.fullmatch(r"\|?[\s:|-]+\|?", l) for l in linhas):
            continue
        if linhas[0].startswith("#"):
            partes.append(f"<h3>{linhas[0].lstrip('# ')}</h3>")
            linhas = linhas[1:]
        if linhas and all(re.match(r"\s*[-*] ", l) for l in linhas):
            itens = (re.sub(r"^\s*[-*] ", "", l) for l in linhas)
            partes.append("<ul>" + "".join(f"<li>{item}</li>" for item in itens) + "</ul>")
        elif linhas and linhas[0].startswith("|"):  # tabela markdown: mantém como texto pré-formatado
            partes.append("<pre>" + "\n".join(linhas) + "</pre>")
        elif linhas:
            partes.append("<p>" + "<br>".join(linhas) + "</p>")
    return "\n".join(partes)


def html_do_relatorio(tarefa_id: int, pedido: str, analise: str, empresa: str, numeros: dict) -> str:
    corpo = []
    for i, b in enumerate(numeros["blocos"]):
        mensal = b["mensal"]
        meses = [m["mes"] for m in mensal]
        ultimo = mensal[-1] if mensal else {}
        cartoes = [("Seguidores", b["seguidores"][-1][1] if b["seguidores"] else None),
                   (f"Alcance ({ultimo.get('mes', '—')})", ultimo.get("alcance")),
                   (f"Salvamentos ({ultimo.get('mes', '—')})", ultimo.get("salvamentos")),
                   (f"Compartilhamentos ({ultimo.get('mes', '—')})", ultimo.get("compartilhamentos"))]
        corpo.append(f'<section><h2>{html.escape(b["empresa"])} <span class="conta">@{b["conta"]}</span></h2>'
                     '<div class="cartoes">' + "".join(f'<div class="cartao"><span>{html.escape(r)}</span>'
                                                      f'<strong>{_num(v)}</strong></div>' for r, v in cartoes)
                     + "</div>")
        if mensal:
            corpo.append(_grafico(f"alcance{i}", "Alcance e views por mês (mês atual parcial)", "bar", meses,
                                  [("Alcance", [m["alcance"] for m in mensal]),
                                                                 ("Views", [m["views"] for m in mensal])]))
            corpo.append(_grafico(f"salvos{i}", "Salvamentos e compartilhamentos por mês", "line", meses,
                                  [("Salvamentos", [m["salvamentos"] for m in mensal]),
                                   ("Compartilhamentos", [m["compartilhamentos"] for m in mensal])]))
        if b["seguidores"]:
            corpo.append(_grafico(f"seg{i}", "Seguidores nos últimos 90 dias", "line", [d for d, _ in b["seguidores"]],
                                  [("Seguidores", [s for _, s in b["seguidores"]])]))
        if b["youtube"]:
            yt = b["youtube"]
            corpo.append("<h3>YouTube</h3>" + _grafico(f"yt{i}", "YouTube por mês: views e saldo de inscritos", "bar",
                                                         [m["mes"] for m in yt],
                                                         [("Views", [m["views"] for m in yt]),
                                                          ("Saldo de inscritos", [m["saldo"] for m in yt])]))
        if b["melhores"]:
            corpo.append("<h3>Melhores publicações dos últimos 30 dias (salvamentos + compartilhamentos)</h3>"
                         "<table><tr><th>Data</th><th>Tipo</th><th>Publicação</th><th>Alcance</th>"
                         "<th>Salvos</th><th>Compart.</th></tr>" + "".join(
                             f'<tr><td>{(p["data"] or "")[:10]}</td><td>{html.escape(p["tipo"] or "")}</td>'
                             f'<td><a href="{html.escape(p["link"] or "#")}" target="_blank" rel="noopener">'
                             f'{html.escape((p["legenda"] or "")[:70])}…</a></td><td>{_num(p["alcance"])}</td>'
                             f'<td>{_num(p["salvamentos"])}</td><td>{_num(p["compartilhamentos"])}</td></tr>'
                             for p in b["melhores"]) + "</table>")
        corpo.append("</section>")
    titulo = f"Relatório #{tarefa_id} · {empresas.nome(empresa)}"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {{ --fundo: #f7f2ea; --papel: #ffffff; --texto: #1d1d1b; --suave: #6b6457; --linha: #e4dccd; --verde: #00361b; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fundo: #14140f; --papel: #1f1f19; --texto: #f0ebe1;
  --suave: #b3ab9b; --linha: #34322a; --verde: #7fc29b; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--fundo); color: var(--texto); font: 15px/1.55 system-ui, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }}
h1 {{ color: var(--verde); margin: 0 0 4px; font-size: 1.6rem; }}
h2 {{ margin: 32px 0 12px; color: var(--verde); }} h3 {{ margin: 24px 0 8px; }}
.conta, .meta {{ color: var(--suave); font-size: .9rem; font-weight: 400; }}
.cartoes {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
.cartao {{ background: var(--papel); border: 1px solid var(--linha); border-radius: 10px; padding: 12px 14px; }}
.cartao span {{ display: block; color: var(--suave); font-size: .8rem; }} .cartao strong {{ font-size: 1.4rem; }}
.grafico {{ position: relative; height: 280px; background: var(--papel); border: 1px solid var(--linha);
  border-radius: 10px; padding: 12px; margin-top: 12px; }}
table {{ width: 100%; border-collapse: collapse; background: var(--papel); font-size: .88rem; display: block;
  overflow-x: auto; }}
th, td {{ padding: 8px; border-bottom: 1px solid var(--linha); text-align: left; }} a {{ color: var(--verde); }}
.analise {{ background: var(--papel); border: 1px solid var(--linha); border-radius: 10px; padding: 4px 20px;
  margin-top: 16px; }}
pre {{ white-space: pre-wrap; font-size: .82rem; }}
</style></head><body><main>
<h1>{html.escape(titulo)}</h1>
<p class="meta">Pedido: {html.escape(pedido[:300])}<br>Dados do painel analítico até {numeros["coleta"] or "—"}.
Os números e gráficos vêm direto do banco do painel; o texto é a análise do Analista de Métricas.</p>
<script>const graficos = [];</script>
{"".join(corpo)}
<h2>Análise do Analista de Métricas</h2>
<div class="analise">{_analise_html(analise)}</div>
</main>
<script>
if (window.Chart) {{
  Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue('--suave');
  graficos.forEach(([id, cfg]) => new Chart(document.getElementById(id), cfg));
}}
</script></body></html>"""


def gerar(linha) -> str | None:
    """Gera a página da resposta do Analista de Métricas (None se o painel não estiver montado ou falhar)."""
    if not BANCO.exists():
        return None
    try:
        numeros = dados(linha["empresa"] or empresas.PADRAO)
        if not numeros["blocos"]:
            return None
        PASTA.mkdir(parents=True, exist_ok=True)
        arquivo = PASTA / f"{linha['id']}-{secrets.token_urlsafe(18)}.html"
        arquivo.write_text(html_do_relatorio(linha["id"], linha["texto"], linha["resposta"] or "",
                                             linha["empresa"] or empresas.PADRAO, numeros), encoding="utf-8")
        return link_de(linha["id"])
    except Exception:
        log.exception("Relatório da tarefa %s não foi gerado.", linha["id"])
        return None


def link_de(tarefa_id: int) -> str | None:
    """Endereço da página da tarefa (botão "Ver relatório"); None se não houver."""
    achados = sorted(PASTA.glob(f"{tarefa_id}-*.html")) if PASTA.exists() else []
    return f"/relatorios/{achados[-1].name}" if achados else None


@rotas.get("/relatorios/{nome}")
def abrir(nome: str):
    if not NOME_ARQUIVO.match(nome) or not (arquivo := PASTA / nome).is_file():
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return FileResponse(arquivo, media_type="text/html; charset=utf-8")
