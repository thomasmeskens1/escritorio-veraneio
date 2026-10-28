"""Cérebro: base de conhecimento (SQLite), busca híbrida, versões, aprendizado e consolidação.

Busca: cosseno (embedding local) + BM25 normalizado, multiplicados pelo peso da fonte, pela recência
e pela pontuação aprendida; MMR para não repetir trechos parecidos.
"""

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import numpy as np

import cerebro_embed as embed
import config
import tarefas
from empresas import COMUM, PADRAO
from cerebro_texto import BM25, dividir, mesmo_assunto, termos

log = logging.getLogger(__name__)

PESOS_FONTE = {"ensinado": 1.3, "oficial": 1.2, "site": 1.1, "drive": 1.0, "dados": 1.0, "rede": 0.85, "tarefa": 0.6}  # rede: YouTube/Instagram (fala e legenda valem menos que a ficha)
LIMIAR_VERSAO = 0.90       # novo trecho parecido com um antigo do mesmo assunto: o novo vence
LIMIAR_DUPLICADO = 0.97    # consolidação: quase idênticos
COS_MINIMO = 0.40          # sem termo em comum, só entra se o significado for bem próximo
PESO_COSSENO, PESO_BM25 = 0.65, 0.35
LAMBDA_MMR = 0.7
PONTUACAO_LIMITE = 2.0
PASSO_SUCESSO, PASSO_FALHA = 0.10, 0.15
FATOR_PONTUACAO = 0.15     # multiplicador = 1 + 0.15 * pontuação  (0.7 a 1.3)
# Documentos com identidade própria (cada página do site, cada lodge da planilha/acervo, cada documento
# oficial): só o substituir_ref troca a versão. Lodges seguem o mesmo modelo de texto e não podem se
# substituir, e o catálogo de um documento oficial não apaga a página atualizada do site.
FONTES_COM_REF = {"site", "drive", "oficial"}
LOTE_EMBEDDINGS = 8

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS conhecimento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_tipo TEXT NOT NULL,          -- oficial | ensinado | site | drive | tarefa
    fonte_ref TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    conteudo TEXT NOT NULL,
    embedding BLOB,
    modelo_embedding TEXT,
    peso_fonte REAL NOT NULL,
    pontuacao REAL NOT NULL DEFAULT 0, -- aprendida com o resultado das tarefas
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    substituido_por INTEGER
);
CREATE INDEX IF NOT EXISTS idx_conhecimento_ativo ON conhecimento(ativo);
CREATE INDEX IF NOT EXISTS idx_conhecimento_ref ON conhecimento(fonte_tipo, fonte_ref);
CREATE TABLE IF NOT EXISTS consultas_cerebro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarefa_id INTEGER,
    agente TEXT,
    pergunta TEXT NOT NULL,
    ids_conhecimento TEXT NOT NULL DEFAULT '[]',
    em TEXT NOT NULL,
    resultado TEXT                     -- null | sucesso | falha
);
CREATE INDEX IF NOT EXISTS idx_consultas_tarefa ON consultas_cerebro(tarefa_id);
"""

_trava = threading.RLock()  # a conexão SQLite é compartilhada entre o loop e as threads dos agentes
_versao = 0                 # muda a cada escrita no conteúdo: o índice em memória é refeito
_indice = None
ORLANDO = "orlando"
REFAZER_INDICE_S = 15  # idade máxima do índice usado nas consultas (ver indice_atual)
_pronto = False


def agora(depois: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + depois).strftime("%Y-%m-%dT%H:%M:%SZ")


def db():
    global _pronto
    conexao = tarefas._db()
    if not _pronto:
        with _trava:
            conexao.executescript(_ESQUEMA)
            _migrar_empresa(conexao)
            _pronto = True
    return conexao


# Manuais oficiais por empresa (prefixo do arquivo); os demais (01-07) são da Casa Veraneio.
OFICIAIS_COMUNS = ("00", "08", "09", "10", "13", "15")
OFICIAIS_DA_EMPRESA = {"11": "cv_corporativo", "12": "casa_vero", "14": "cv_corporativo"}


def empresa_do_oficial(arquivo: str) -> str:
    prefixo = arquivo[:2]
    return COMUM if prefixo in OFICIAIS_COMUNS else OFICIAIS_DA_EMPRESA.get(prefixo, PADRAO)


def _migrar_empresa(conexao) -> None:
    """Coluna empresa (separação das 3 empresas). Na 1ª vez, os dados antigos são da Casa Veraneio, exceto os
    manuais comuns e as regras de ouro ensinadas, que valem para todas."""
    colunas = {c["name"] for c in conexao.execute("PRAGMA table_info(conhecimento)")}
    if "empresa" in colunas:
        return
    with conexao:
        conexao.execute(f"ALTER TABLE conhecimento ADD COLUMN empresa TEXT NOT NULL DEFAULT '{PADRAO}'")
        conexao.execute("CREATE INDEX IF NOT EXISTS idx_conhecimento_empresa ON conhecimento(empresa)")
        for prefixo in OFICIAIS_COMUNS:
            conexao.execute("UPDATE conhecimento SET empresa = ? WHERE fonte_tipo = 'oficial' AND fonte_ref LIKE ?",
                            (COMUM, f"{prefixo}%"))
        conexao.execute("UPDATE conhecimento SET empresa = ? WHERE fonte_tipo = 'ensinado' AND "
                        "(conteudo LIKE 'Regras de ouro%' OR conteudo LIKE 'Regra aprovada pelo Thomas para todos%')",
                        (COMUM,))


def _mudou() -> None:
    global _versao
    _versao += 1


# --- Escrita ---------------------------------------------------------------------------------

def _inserir(fonte_tipo: str, fonte_ref: str, titulo: str, conteudo: str, empresa: str = PADRAO) -> int:
    momento = agora()
    with _trava, db() as conexao:
        cursor = conexao.execute(
            "INSERT INTO conhecimento (fonte_tipo, fonte_ref, titulo, conteudo, peso_fonte, criado_em, atualizado_em, "
            "empresa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fonte_tipo, fonte_ref, titulo[:200], conteudo, PESOS_FONTE[fonte_tipo], momento, momento, empresa))
    _mudou()
    return cursor.lastrowid


def _desativar(ids: list[int], substituido_por: int | None) -> None:
    if not ids:
        return
    with _trava, db() as conexao:
        conexao.executemany("UPDATE conhecimento SET ativo = 0, substituido_por = ?, atualizado_em = ? WHERE id = ?",
                            [(substituido_por, agora(), i) for i in ids])
    _mudou()


def adicionar(fonte_tipo: str, fonte_ref: str, titulo: str, conteudo: str,
              empresa: str = PADRAO) -> tuple[list[int], int]:
    """Divide em trechos, grava, gera embeddings (se o Ollama responder) e aplica as versões.
    Devolve (ids novos, quantos trechos antigos foram substituídos)."""
    ids = [_inserir(fonte_tipo, fonte_ref, t, c, empresa) for t, c in dividir(titulo, conteudo)]
    return ids, gerar_embeddings(ids)


def substituir_ref(fonte_tipo: str, fonte_ref: str, titulo: str, conteudo: str, empresa: str = PADRAO) -> int:
    """Mesmo fonte_ref: os trechos novos substituem os anteriores daquele ref. Devolve o nº de trechos."""
    novos = dividir(titulo, conteudo)
    with _trava:
        antigos = db().execute("SELECT id, titulo, conteudo FROM conhecimento WHERE fonte_tipo = ? AND fonte_ref = ? "
                               "AND ativo = 1 ORDER BY id", (fonte_tipo, fonte_ref)).fetchall()
    if [(l["titulo"], l["conteudo"]) for l in antigos] == [(t[:200], c) for t, c in novos]:
        return len(antigos)  # nada mudou
    ids = [_inserir(fonte_tipo, fonte_ref, t, c, empresa) for t, c in novos]
    _desativar([l["id"] for l in antigos], ids[0] if ids else None)
    gerar_embeddings(ids)
    return len(ids)


def remover_ref(fonte_tipo: str, fonte_ref: str) -> int:
    """Desativa todos os trechos ativos de um documento que sumiu da fonte. Devolve quantos."""
    with _trava:
        ids = [l[0] for l in db().execute("SELECT id FROM conhecimento WHERE fonte_tipo = ? AND fonte_ref = ? AND ativo = 1",
                                          (fonte_tipo, fonte_ref))]
    _desativar(ids, None)
    return len(ids)


def pendentes(limite: int = 10_000) -> list[int]:
    with _trava:
        return [l[0] for l in db().execute(
            "SELECT id FROM conhecimento WHERE ativo = 1 AND (embedding IS NULL OR modelo_embedding IS NOT ?) "
            "ORDER BY id LIMIT ?", (config.MODELO_EMBEDDING, limite))]


def gerar_embeddings(ids: list[int]) -> int:
    """Gera os embeddings dos ids (em lotes) e aplica as versões. Devolve quantos antigos foram substituídos."""
    substituidos = 0
    for inicio in range(0, len(ids), LOTE_EMBEDDINGS):
        lote = ids[inicio:inicio + LOTE_EMBEDDINGS]
        marcadores = ",".join("?" * len(lote))
        with _trava:
            linhas = db().execute(f"SELECT id, titulo, conteudo FROM conhecimento WHERE id IN ({marcadores}) "
                                  "ORDER BY id", lote).fetchall()
        vetores = embed.gerar([f"{l['titulo']}\n{l['conteudo']}" for l in linhas])
        if vetores is None:
            return substituidos  # Ollama fora: ficam pendentes para a próxima rodada
        with _trava, db() as conexao:
            conexao.executemany("UPDATE conhecimento SET embedding = ?, modelo_embedding = ? WHERE id = ?",
                                [(embed.para_blob(v), config.MODELO_EMBEDDING, l["id"]) for l, v in zip(linhas, vetores)])
        _mudou()
        for linha, vetor in zip(linhas, vetores):
            substituidos += _versionar(linha["id"], vetor)
    return substituidos


def _documentos_distintos(fonte_a: str, ref_a: str, fonte_b: str, ref_b: str) -> bool:
    return fonte_a in FONTES_COM_REF and fonte_b in FONTES_COM_REF and ref_a != ref_b


def _pode_substituir(novo: str, antigo: str) -> bool:
    """O novo vence, exceto fonte de menor autoridade sobre maior (ex.: o site não apaga o que o dono ensinou)."""
    return novo == "ensinado" or PESOS_FONTE[novo] >= PESOS_FONTE[antigo]


def _versionar(novo_id: int, vetor: np.ndarray) -> int:
    """Trechos do mesmo documento (mesmo tipo e ref) não se substituem: isso é papel do substituir_ref."""
    indice = indice_atual(fresco=True)
    if not len(indice.ids):
        return 0
    with _trava:
        novo = db().execute("SELECT fonte_tipo, fonte_ref, conteudo, ativo, empresa FROM conhecimento WHERE id = ?",
                            (novo_id,)).fetchone()
    if not novo or not novo["ativo"]:
        return 0
    similares = indice.matriz @ vetor
    antigos = [indice.ids[i] for i in np.nonzero((similares > LIMIAR_VERSAO) & indice.tem_embedding)[0]
               if indice.ids[i] != novo_id
               and indice.empresas[i] == novo["empresa"]  # o dado de uma empresa nunca substitui o de outra
               and (indice.fontes[i], indice.refs[i]) != (novo["fonte_tipo"], novo["fonte_ref"])
               and _pode_substituir(novo["fonte_tipo"], indice.fontes[i])
               and not _documentos_distintos(novo["fonte_tipo"], novo["fonte_ref"], indice.fontes[i], indice.refs[i])
               and mesmo_assunto(novo["conteudo"], indice.conteudos[i])]
    _desativar(antigos, novo_id)
    return len(antigos)


# --- Índice em memória -------------------------------------------------------------------------

class Indice:
    def __init__(self, linhas: list):
        self.versao = _versao
        self.criado = time.monotonic()
        self.ids = [l["id"] for l in linhas]
        self.titulos = [l["titulo"] for l in linhas]
        self.conteudos = [l["conteudo"] for l in linhas]
        self.fontes = [l["fonte_tipo"] for l in linhas]
        self.refs = [l["fonte_ref"] for l in linhas]
        self.empresas = [l["empresa"] for l in linhas]
        # Lodges de Orlando: opção raríssima; só entram na busca quando a pergunta cita Orlando.
        self.orlando = np.array([ORLANDO in f"{l['fonte_ref']} {l['titulo']}".lower() for l in linhas], dtype=bool)
        self.datas = [l["atualizado_em"] for l in linhas]
        self.pesos = np.array([l["peso_fonte"] for l in linhas], dtype=np.float32)
        self._bm25 = None
        vetores = [embed.de_blob(l["embedding"]) if l["modelo_embedding"] == config.MODELO_EMBEDDING else None
                   for l in linhas]
        dimensao = next((len(v) for v in vetores if v is not None), 1)
        self.tem_embedding = np.array([v is not None and len(v) == dimensao for v in vetores], dtype=bool)
        self.matriz = np.zeros((len(linhas), dimensao), dtype=np.float32)
        for i, v in enumerate(vetores):
            if self.tem_embedding[i]:
                self.matriz[i] = v

    def _lexico(self) -> None:
        # Tokenização só na primeira busca (as versões, durante a ingestão, usam apenas os vetores).
        if self._bm25 is None:
            lista = [termos(f"{t} {c}") for t, c in zip(self.titulos, self.conteudos)]
            self.conjuntos = [set(t) for t in lista]
            self._bm25 = BM25(lista)

    @property
    def bm25(self) -> BM25:
        self._lexico()
        return self._bm25


def indice_atual(fresco: bool = False) -> Indice:
    """Índice da busca. Na consulta dos agentes, um índice com até REFAZER_INDICE_S de idade serve: antes, cada
    tarefa concluída mandava refazer tudo, segurando a trava e travando as consultas. `fresco` (versionamento e
    consolidação) sempre reflete a última escrita. A leitura fica na trava (conexão compartilhada); a montagem
    do índice (BM25, matriz), fora dela."""
    global _indice
    with _trava:
        atual, versao = _indice, _versao
        if atual is not None and (atual.versao == versao or
                                  (not fresco and time.monotonic() - atual.criado < REFAZER_INDICE_S)):
            return atual
        linhas = db().execute("SELECT id, fonte_tipo, fonte_ref, titulo, conteudo, embedding, modelo_embedding, "
                              "peso_fonte, atualizado_em, empresa FROM conhecimento WHERE ativo = 1 ORDER BY id"
                              ).fetchall()
    novo = Indice(linhas)
    novo.versao, novo.criado = versao, time.monotonic()
    with _trava:
        if _indice is None or _indice.versao < versao:
            _indice = novo
    return novo


# --- Busca ---------------------------------------------------------------------------------------

def _recencia(data: str) -> float:
    """Decaimento suave: 1.0 hoje, ~0.87 em 1 ano, nunca abaixo de 0.8."""
    try:
        dias = (datetime.now(timezone.utc) - datetime.strptime(data, "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=timezone.utc)).days
    except ValueError:
        dias = 0
    return 0.8 + 0.2 * math.exp(-max(dias, 0) / 365)


def _pontuacoes(ids: list[int]) -> dict[int, float]:
    if not ids:
        return {}
    with _trava:
        linhas = db().execute(f"SELECT id, pontuacao FROM conhecimento WHERE id IN ({','.join('?' * len(ids))})",
                              ids).fetchall()
    return {l["id"]: l["pontuacao"] for l in linhas}


def buscar(pergunta: str, k: int = 5, empresa: str = PADRAO) -> list[dict]:
    """Os k trechos mais relevantes (já diversificados pelo MMR), SÓ da empresa pedida e do que é comum às três.
    Lodges de Orlando ficam de fora, a menos que a pergunta cite Orlando."""
    indice = indice_atual()
    if not indice.ids:
        return []
    permitido = np.array([e in (empresa, COMUM) for e in indice.empresas], dtype=bool)
    if ORLANDO not in pergunta.lower():
        permitido &= ~indice.orlando
    termos_pergunta = termos(pergunta)
    bm25 = np.array(indice.bm25.pontuar(termos_pergunta), dtype=np.float32)
    cosseno = np.zeros(len(indice.ids), dtype=np.float32)
    if indice.tem_embedding.any():
        consulta = embed.gerar([pergunta], consulta=True)
        if consulta is not None and consulta.shape[1] == indice.matriz.shape[1]:
            cosseno = np.where(indice.tem_embedding, indice.matriz @ consulta[0], 0).astype(np.float32)
    if cosseno.any():
        cobertura = np.clip(bm25 / (indice.bm25.cobertura_maxima(termos_pergunta) or 1), 0, 1)
        relevancia = PESO_COSSENO * np.clip(cosseno, 0, None) + PESO_BM25 * cobertura
    else:  # só lexical (Ollama fora)
        relevancia = bm25 / bm25.max() if bm25.max() > 0 else bm25
    relevancia = np.where(permitido, relevancia, 0)
    candidatos = [i for i in np.argsort(-relevancia)[:40]
                  if permitido[i] and (bm25[i] > 0 or cosseno[i] >= COS_MINIMO)]
    if not candidatos:
        return []

    pontos = _pontuacoes([indice.ids[i] for i in candidatos])
    notas = {}
    for i in candidatos:
        aprendida = max(-PONTUACAO_LIMITE, min(PONTUACAO_LIMITE, pontos.get(indice.ids[i], 0.0)))
        notas[i] = float(relevancia[i] * indice.pesos[i] * _recencia(indice.datas[i]) * (1 + FATOR_PONTUACAO * aprendida))
    maior = max(notas.values()) or 1.0

    def parecido(a: int, b: int) -> float:
        if indice.tem_embedding[a] and indice.tem_embedding[b]:
            return float(indice.matriz[a] @ indice.matriz[b])
        uniao = indice.conjuntos[a] | indice.conjuntos[b]
        return len(indice.conjuntos[a] & indice.conjuntos[b]) / len(uniao) if uniao else 0.0

    escolhidos: list[int] = []
    restantes = sorted(notas, key=notas.get, reverse=True)
    while restantes and len(escolhidos) < k:
        melhor = max(restantes, key=lambda i: LAMBDA_MMR * notas[i] / maior
                     - (1 - LAMBDA_MMR) * max((parecido(i, j) for j in escolhidos), default=0.0))
        escolhidos.append(melhor)
        restantes.remove(melhor)
    return [{"id": indice.ids[i], "titulo": indice.titulos[i], "conteudo": indice.conteudos[i],
             "fonte_tipo": indice.fontes[i], "fonte_ref": indice.refs[i], "data": indice.datas[i][:10],
             "nota": round(notas[i], 4)} for i in escolhidos]


# --- Aprendizado ----------------------------------------------------------------------------------

def registrar_consulta(tarefa_id: int | None, agente: str, pergunta: str, ids: list[int]) -> None:
    with _trava, db() as conexao:
        conexao.execute("INSERT INTO consultas_cerebro (tarefa_id, agente, pergunta, ids_conhecimento, em) "
                        "VALUES (?, ?, ?, ?, ?)", (tarefa_id or None, agente, pergunta[:1000], json.dumps(ids), agora()))


def registrar_resultado(tarefa_id: int, sucesso: bool) -> int:
    """Ajusta a pontuação dos trechos usados na tarefa (+ sucesso, − falha). Devolve quantos trechos mudaram."""
    with _trava:
        linhas = db().execute("SELECT id, ids_conhecimento FROM consultas_cerebro WHERE tarefa_id = ? "
                              "AND resultado IS NULL", (tarefa_id,)).fetchall()
        if not linhas:
            return 0
        usados = {i for l in linhas for i in json.loads(l["ids_conhecimento"] or "[]")}
        passo = PASSO_SUCESSO if sucesso else -PASSO_FALHA
        with db() as conexao:
            conexao.executemany("UPDATE conhecimento SET pontuacao = MAX(?, MIN(?, pontuacao + ?)) WHERE id = ?",
                                [(-PONTUACAO_LIMITE, PONTUACAO_LIMITE, passo, i) for i in usados])
            conexao.executemany("UPDATE consultas_cerebro SET resultado = ? WHERE id = ?",
                                [("sucesso" if sucesso else "falha", l["id"]) for l in linhas])
    return len(usados)


# --- Consolidação ---------------------------------------------------------------------------------

def restaurar_documentos_distintos() -> int:
    """Reativa trechos de site/drive/oficial que outro documento desativou por engano (regra antiga de versões).
    Só a versão mais recente de cada ref volta; as trocadas pelo próprio substituir_ref continuam fora."""
    marcadores = ",".join("?" * len(FONTES_COM_REF))
    with _trava, db() as conexao:
        reativados = conexao.execute(f"""
            UPDATE conhecimento SET ativo = 1, substituido_por = NULL WHERE id IN (
              SELECT a.id FROM conhecimento a JOIN conhecimento b ON b.id = a.substituido_por
              WHERE a.ativo = 0 AND a.fonte_tipo IN ({marcadores}) AND b.fonte_tipo IN ({marcadores})
                AND a.fonte_ref != b.fonte_ref
                AND a.id >= COALESCE((SELECT MAX(c.substituido_por) FROM conhecimento c
                                      JOIN conhecimento d ON d.id = c.substituido_por
                                      WHERE c.fonte_tipo = a.fonte_tipo AND c.fonte_ref = a.fonte_ref
                                        AND d.fonte_ref = a.fonte_ref), 0))""",
            [*FONTES_COM_REF, *FONTES_COM_REF]).rowcount
    if reativados:
        _mudou()
        log.info("Cérebro: %s trecho(s) de site/drive reativados.", reativados)
    return reativados


def consolidar() -> dict:
    """Rotina diária: embeddings que faltam, duplicados quase idênticos e decaimento dos trechos de tarefa."""
    gerar_embeddings(pendentes())
    indice = indice_atual(fresco=True)
    com_vetor = np.nonzero(indice.tem_embedding)[0]
    removidos: dict[int, int] = {}
    for inicio in range(0, len(com_vetor), 256):
        bloco = com_vetor[inicio:inicio + 256]
        similares = indice.matriz[bloco] @ indice.matriz[com_vetor].T
        for linha, a in enumerate(bloco):
            for coluna in np.nonzero(similares[linha] > LIMIAR_DUPLICADO)[0]:
                b = com_vetor[coluna]
                if b <= a or indice.ids[a] in removidos or indice.ids[b] in removidos:
                    continue
                if not mesmo_assunto(indice.conteudos[a], indice.conteudos[b]) or _documentos_distintos(
                        indice.fontes[a], indice.refs[a], indice.fontes[b], indice.refs[b]):
                    continue
                # Fica o de maior autoridade; empate: o mais novo.
                fica, sai = sorted((a, b), key=lambda i: (indice.pesos[i], indice.ids[i]), reverse=True)
                removidos[indice.ids[sai]] = indice.ids[fica]
    for sai, fica in removidos.items():
        _desativar([sai], fica)
    with _trava, db() as conexao:
        decaidos = conexao.execute(
            "UPDATE conhecimento SET pontuacao = pontuacao * 0.9 WHERE fonte_tipo = 'tarefa' AND ativo = 1 "
            "AND pontuacao != 0 AND criado_em < ?", (agora(-timedelta(days=30)),)).rowcount
        # Versões antigas (inativas há 30+ dias) guardam o texto como histórico, mas não o vetor: era mais da
        # metade do banco. Se um trecho for reativado, o vetor é recalculado (pendentes() pega ativo sem vetor).
        liberados = conexao.execute(
            "UPDATE conhecimento SET embedding = NULL WHERE ativo = 0 AND embedding IS NOT NULL "
            "AND atualizado_em < ?", (agora(-timedelta(days=30)),)).rowcount
    if liberados >= 100:
        with _trava:
            db().execute("VACUUM")  # devolve o espaço ao disco (fora de transação)
    resultado = {"duplicados": len(removidos), "decaidos": decaidos, "vetores_liberados": liberados,
                 "pendentes": len(pendentes())}
    log.info("Cérebro: consolidação %s", resultado)
    return resultado


def estatisticas(inicio_hoje_utc: str) -> dict:
    with _trava:
        conexao = db()
        por_fonte = {l["fonte_tipo"]: l["n"] for l in conexao.execute(
            "SELECT fonte_tipo, COUNT(*) n FROM conhecimento WHERE ativo = 1 GROUP BY fonte_tipo")}
        por_empresa: dict[str, dict] = {}
        for l in conexao.execute("SELECT empresa, fonte_tipo, COUNT(*) n FROM conhecimento WHERE ativo = 1 "
                                 "GROUP BY empresa, fonte_tipo"):
            item = por_empresa.setdefault(l["empresa"], {"total": 0, "por_fonte": {}})
            item["total"] += l["n"]
            item["por_fonte"][l["fonte_tipo"]] = l["n"]
        ultima = conexao.execute("SELECT MAX(atualizado_em) FROM conhecimento").fetchone()[0]
        hoje = conexao.execute("SELECT COUNT(*) FROM consultas_cerebro WHERE em >= ?", (inicio_hoje_utc,)).fetchone()[0]
        total = conexao.execute("SELECT COUNT(*) FROM consultas_cerebro").fetchone()[0]
    return {"total": sum(por_fonte.values()), "por_fonte": {f: por_fonte.get(f, 0) for f in PESOS_FONTE},
            "por_empresa": por_empresa,  # ficha do Cérebro: uma linha por empresa (e o comum às três)
            "ultima_atualizacao": ultima, "consultas_hoje": hoje, "consultas_total": total}
