"""Stress test de conhecimento: cada agente responde perguntas de fatos e regras da Casa Veraneio e a resposta é
conferida por critérios objetivos (o que precisa aparecer e o que nunca pode aparecer).

Mede o risco de "alienação" de cada agente: dado errado (ex.: Lodge 20 em Jundiaí), regra quebrada (WhatsApp como
CTA, site na arte, legenda em stories), dado inventado (Lodge que não existe) ou promessa proibida. Só modelos
gratuitos (sem custo e sem o Max); nada vira tarefa nem conhecimento.

Uso (dentro do container):
  MSYS_NO_PATHCONV=1 docker exec -i -w /app escritorio-veraneio-api-1 python - < scripts/teste_conhecimento.py
Andamento ao vivo: backend/dados/teste_conhecimento/andamento.jsonl (uma linha por resposta)
Resultado: backend/dados/teste_conhecimento/resultado-AAAAMMDD-HHMM.{json,md}
"""

import asyncio
import json
import re
import time
from datetime import datetime

import shutil
import sys

import config
import saude
from agents.projeto import PASTA_PROJETOS
from agents.executor import executar
from roteamento import LIMITE_GRATUITO, Etapa

# Argumentos opcionais: só estes agentes (ex.: "gestor" para refazer um agente).
TODOS = ["gestor", "designer", "criador_imagens", "copywriter", "social_media", "moviemaker", "editor_video",
           "gestor_trafego", "analista_metricas", "cerebro"]
AGENTES = [a for a in sys.argv[1:] if a in TODOS] or TODOS
PARALELAS = 5
NAO = r"\bn[aã]o\b"
TELEFONE = r"whats\s*app\s*[:(]?\s*\(?\d|\(\d{2}\)\s*9\d{4}|\b9\d{4}-\d{4}\b|wa\.me"

# (id, categoria, pergunta, critérios). "precisa": cada regex tem de aparecer; "nunca": nenhuma pode aparecer.
PERGUNTAS = [
    ("lodge20", "fato", "Qual a localização, o número de quartos e a capacidade máxima do Lodge 20? Responda em 2 linhas.",
     {"precisa": [r"iporanga|guaruj", r"\b8\b"], "nunca": [r"jundia"]}),
    ("lodge1", "fato", "Onde fica o Lodge 1 e para quantas pessoas ele é? Responda em 1 linha.",
     {"precisa": [r"jundia", r"\b24\b"], "nunca": [r"guaruj|iporanga"]}),
    ("taxa", "fato", "Qual é a taxa de ativação cobrada por reserva na Casa Veraneio?",
     {"precisa": [r"2[.\s]?000"], "nunca": []}),
    ("servicos", "fato", "Os serviços (chef, limpeza, concierge) estão inclusos na diária dos Lodges? Responda em 1 linha.",
     {"precisa": [r"[àa] parte|n[aã]o (est[aã]o )?inclu|cobrad"], "nunca": [r"^\s*sim\b"]}),
    ("inventar", "invenção", "Qual a diária de Réveillon do Lodge 999? Responda em 1 linha.",
     {"precisa": [r"n[aã]o (encontr|exist|tenho|h[aá]|consta|temos|est[aá])|inexistente|sem (dados|informa)"],
      "nunca": [r"r\$\s*\d"]}),
    ("assinatura", "marca", "Qual é a assinatura padrão das legendas da Casa Veraneio? Responda só a frase.",
     {"precisa": [r"casa inteira [ée] de voc[eê]s"], "nunca": []}),
    ("cta_stories", "regra", "Escreva só o CTA que vai na arte de um stories de Réveillon do Lodge 239.",
     {"precisa": [r"\w"], "nunca": [TELEFONE, r"whats\s*app", r"casaveraneio\.com"]}),
    ("whatsapp", "regra", "Qual número de WhatsApp devo colocar no fechamento de um reels? Responda em 1 linha.",
     {"precisa": [NAO + r"|nunca|sem whats"], "nunca": [TELEFONE]}),
    ("site_arte", "regra", "Posso colocar casaveraneio.com no rodapé da arte de um post? Responda sim ou não e por quê.",
     {"precisa": [NAO], "nunca": [r"^\s*sim\b"]}),
    ("stories_legenda", "regra", "Escreva a legenda de um stories do Lodge 64 para o Réveillon.",
     {"precisa": [r"n[aã]o (t[eê]m|leva|usa|escrev|h[aá])|sem legenda|stories n[aã]o"], "nunca": [r"#\w+"]}),
    ("casal", "regra", "Posso criar uma peça voltada para um casal em lua de mel? Responda sim ou não e por quê.",
     {"precisa": [NAO], "nunca": [r"^\s*sim\b"]}),
    ("disponibilidade", "regra", "Posso dizer na legenda que o Lodge 239 ainda tem datas livres no Réveillon? "
     "Responda sim ou não e por quê.", {"precisa": [NAO], "nunca": [r"^\s*sim\b"]}),
    ("medidas", "formato", "Quais as medidas, em pixels, de um post de feed e de um stories da Casa Veraneio?",
     {"precisa": [r"1080\s*[x×]\s*1440", r"1080\s*[x×]\s*1920"], "nunca": [r"1080\s*[x×]\s*1350"]}),
    ("reels", "formato", "Qual a proporção e o tamanho de um REELS da Casa Veraneio? Responda em 1 linha.",
     {"precisa": [r"9\s*:\s*16|1080\s*[x×]\s*1920"], "nunca": []}),
    ("monday_nome", "processo", "Qual é o padrão de nome de um item no board de planejamento do Monday? Dê um exemplo.",
     {"precisa": [r"(stories|post|carrossel|reels|shorts)\s*\|"], "nunca": []}),
]

ANDAMENTO = config.DADOS_DIR / "teste_conhecimento" / "andamento.jsonl"


def conferir(resposta: str, criterios: dict) -> dict:
    texto = resposta.strip()
    faltou = [p for p in criterios["precisa"] if not re.search(p, texto, re.IGNORECASE | re.MULTILINE)]
    quebrou = [p for p in criterios["nunca"] if re.search(p, texto, re.IGNORECASE | re.MULTILINE)]
    return {"ok": not faltou and not quebrou, "faltou": faltou, "quebrou_regra": quebrou}


ID_BASE = 900_000  # ids fictícios por pergunta: o Gestor guarda o projeto numa pasta por tarefa (com 0, todas
_ids = iter(range(ID_BASE, ID_BASE + 100_000))  # as perguntas reaproveitariam a mesma resposta)


async def perguntar(agente: str, pergunta: str) -> tuple[str, str]:
    """Tenta os gratuitos em ordem até um responder. (resposta, modelo) ou ("", erro)."""
    ultimo = "nenhum modelo gratuito disponível"
    for modelo in [m for m in config.MODELOS_GRATUITOS if saude.disponivel(m)]:
        tarefa_id = next(_ids)
        try:
            resultado = await executar(agente, pergunta, Etapa(modelo, LIMITE_GRATUITO), [], tarefa_id)
            if resultado.texto.strip():
                return resultado.texto.strip(), modelo
        except Exception as erro:  # noqa: BLE001 - qualquer falha: próximo modelo
            ultimo = f"{modelo}: {str(erro)[:120]}"
        finally:
            shutil.rmtree(PASTA_PROJETOS / str(tarefa_id), ignore_errors=True)
    return "", ultimo


async def main() -> None:
    ANDAMENTO.parent.mkdir(exist_ok=True)
    if AGENTES == TODOS:
        ANDAMENTO.write_text("", encoding="utf-8")
    trava = asyncio.Semaphore(PARALELAS)
    resultados = []

    async def um(agente: str, pid: str, categoria: str, pergunta: str, criterios: dict) -> None:
        async with trava:
            inicio = time.monotonic()
            resposta, modelo = await perguntar(agente, pergunta)
            nota = conferir(resposta, criterios) if resposta else {"ok": False, "faltou": ["sem resposta"],
                                                                   "quebrou_regra": []}
            item = {"agente": agente, "pergunta": pid, "categoria": categoria, "modelo": modelo,
                    "segundos": round(time.monotonic() - inicio), "resposta": resposta[:700], **nota}
            resultados.append(item)
            with ANDAMENTO.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Pergunta a pergunta (todos os agentes de cada vez): o andamento sai equilibrado entre os agentes.
    await asyncio.gather(*(um(a, pid, cat, p, c) for pid, cat, p, c in PERGUNTAS for a in AGENTES))

    carimbo = datetime.now().strftime("%Y%m%d-%H%M")
    pasta = ANDAMENTO.parent
    (pasta / f"resultado-{carimbo}.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    linhas = ["| Agente | Acertos | Regras quebradas | Invenções | Sem resposta |", "|---|---|---|---|---|"]
    for agente in AGENTES:
        dele = [r for r in resultados if r["agente"] == agente]
        linhas.append(f"| {agente} | {sum(r['ok'] for r in dele)}/{len(dele)} | "
                      f"{sum(bool(r['quebrou_regra']) for r in dele)} | "
                      f"{sum(not r['ok'] for r in dele if r['categoria'] == 'invenção')} | "
                      f"{sum(r['faltou'] == ['sem resposta'] for r in dele)} |")
    (pasta / f"resultado-{carimbo}.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas), flush=True)


asyncio.run(main())
