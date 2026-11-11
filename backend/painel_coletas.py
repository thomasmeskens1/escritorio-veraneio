"""Coletas do painel analítico e procedência dos números (brainstorm de 11/11/2026, analista_metricas-07, -27 e -34).

- Coleta parada: lê a tabela execucoes do painel (só leitura) e, quando uma fonte falha em rodadas seguidas (hoje:
  YouTube, YouTube Analytics e Google Ads) ou a coleta inteira para, o aviso entra em saude.avisos_da_operacao, que
  vai ao painel da Diretoria e ao alarme do Telegram. O texto do erro passa pelo filtro de segredos.
- Rodapé de procedência: no fim de toda resposta que consultou o painel, o PRÓPRIO SISTEMA escreve as consultas
  feitas (eventos consulta_painel) e a data da última coleta lida do banco. Antes a data era digitada pelo modelo
  (tarefa 87: "última coleta: 28/10/2026").
"""

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import segredos
import tarefas

log = logging.getLogger(__name__)

BANCO = Path(os.getenv("SOCIAL_ANALYTICS_DADOS", "/painel")) / "analytics.db"
RODADAS_LIDAS = 6
FALHAS_SEGUIDAS = 2           # erro na mesma fonte em 2 rodadas seguidas: coleta parada (1 vez pode ser passageira)
COLETA_PARADA_H = 12          # nenhuma coleta completa nesse tempo: o motor de coleta parou
MAX_LINHAS_RODAPE = 4
ORIGEM = re.compile(r"^\s*([^:]+?)(?:\s*\(\d{3}\))?\s*:")  # "YouTube (canal) (400): ..." -> "YouTube (canal)"


def _ler(sql: str, parametros: tuple = ()) -> list:
    if not BANCO.exists():
        return []
    with sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True) as db:
        return db.execute(sql, parametros).fetchall()


def _quando(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso).replace(tzinfo=None) if iso else None
    except ValueError:
        return None


def _fonte(erro: str) -> str:
    achado = ORIGEM.match(erro)
    return achado.group(1).strip() if achado else erro.strip()[:40]


def fontes_com_falha() -> list[dict]:
    """Fontes que falharam nas últimas rodadas completas seguidas: [{fonte, rodadas, desde, erro}]."""
    rodadas = _ler("SELECT finalizado_em, erros FROM execucoes WHERE escopo IS NULL ORDER BY id DESC LIMIT ?",
                   (RODADAS_LIDAS,))
    if not rodadas:
        return []
    por_rodada = [{_fonte(e): e for e in (erros or "").split("\n") if e.strip()} for _, erros in rodadas]
    falhas = []
    for fonte, erro in por_rodada[0].items():
        seguidas = next((n for n, erros in enumerate(por_rodada) if fonte not in erros), len(por_rodada))
        if seguidas >= FALHAS_SEGUIDAS:
            falhas.append({"fonte": fonte, "rodadas": seguidas, "desde": _quando(rodadas[seguidas - 1][0]),
                           "erro": segredos.limpar(erro)[:200]})
    return falhas


def ultima_coleta() -> datetime | None:
    """Fim da última coleta completa do painel (ou, sem o registro de execuções, o último dia do Instagram)."""
    linha = _ler("SELECT MAX(finalizado_em) FROM execucoes WHERE escopo IS NULL")
    if linha and linha[0][0]:
        return _quando(linha[0][0])
    linha = _ler("SELECT MAX(data) FROM instagram_diario")
    return _quando(linha[0][0]) if linha and linha[0][0] else None


def avisos(agora: datetime | None = None) -> list[str]:
    """Para saude.avisos_da_operacao: coleta inteira parada e cada fonte com falha repetida. Nunca derruba o painel."""
    agora = agora or datetime.now()
    try:
        if not BANCO.exists():
            return []
        lista = []
        if (ultima := ultima_coleta()) and agora - ultima > timedelta(hours=COLETA_PARADA_H):
            lista.append(f"Painel analítico sem coleta completa desde {ultima:%d/%m %H:%M}: os números dos agentes "
                         "estão parados. Confira se a coleta do painel está rodando no PC.")
        for falha in fontes_com_falha():
            desde = f" (desde {falha['desde']:%d/%m %H:%M})" if falha["desde"] else ""
            lista.append(f"Coleta do painel parada: {falha['fonte']} falhou nas últimas {falha['rodadas']} rodadas"
                         f"{desde}. Erro: {falha['erro']}")
        return lista
    except Exception:
        log.exception("Não foi possível ler as coletas do painel analítico.")
        return []


def _consultas(tarefa_id: int) -> list[str]:
    """Consultas ao painel desta tarefa, agrupadas pelo nome, na ordem em que aconteceram (até 4 linhas)."""
    grupos: dict[str, list[str]] = {}
    for (detalhe,) in tarefas._db().execute(
            "SELECT detalhe FROM eventos WHERE tarefa_id = ? AND tipo = 'consulta_painel' ORDER BY id", (tarefa_id,)):
        nome, _, argumentos = (detalhe or "").partition("(")
        argumentos = argumentos.rstrip(")")
        lista = grupos.setdefault(nome.strip(), [])
        if argumentos and argumentos not in lista:
            lista.append(argumentos)
    linhas = [f"{nome} ({'; '.join(args)})" if args else nome for nome, args in grupos.items() if nome]
    if len(linhas) > MAX_LINHAS_RODAPE:
        linhas = linhas[:MAX_LINHAS_RODAPE - 1] + [f"e mais {len(linhas) - MAX_LINHAS_RODAPE + 1} consulta(s)"]
    return linhas


def rodape(tarefa_id: int) -> str:
    """Rodapé de procedência montado pelo código ("" se a tarefa não consultou o painel)."""
    if not tarefa_id or not (consultas := _consultas(tarefa_id)):
        return ""
    try:
        ultima, falhas = ultima_coleta(), fontes_com_falha()
    except Exception:
        log.exception("Rodapé do painel: não consegui ler a data da coleta.")
        ultima, falhas = None, []
    linhas = ["---", "Origem dos números (escrita pelo sistema): painel analítico.",
              *[f"- {c}" for c in consultas],
              f"Última coleta do painel: {ultima:%d/%m/%Y às %H:%M}." if ultima else
              "Última coleta do painel: não encontrada."]
    if falhas:
        linhas.append("Coleta com falha agora: " + ", ".join(f["fonte"] for f in falhas)
                      + " (os números dessas fontes podem estar parados).")
    return "\n".join(linhas)


def com_rodape(tarefa_id: int, texto: str) -> str:
    try:
        extra = rodape(tarefa_id)
    except Exception:  # o rodapé nunca segura a entrega
        log.exception("Rodapé do painel da tarefa %s falhou.", tarefa_id)
        return texto
    return f"{(texto or '').rstrip()}\n\n{extra}" if extra else texto
