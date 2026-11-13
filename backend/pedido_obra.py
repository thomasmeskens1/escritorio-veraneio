"""Pedido de obra do Construtor (Onda 2, N2-construtor-01, versão enxuta do crítico).

O Construtor só cria agentes de conversa: persona escrita por modelo gratuito, sem ferramenta e fora do Max. Quando o
pedido envolve Max, Monday, Drive, Brevo ou arquivo, ele não grava proposta: o pedido vira um PEDIDO DE OBRA escrito
para o Thomas, com as peças tiradas do commit do Sonoplasta (1462535), o que o agente NÃO faz e 3 pedidos de exemplo
com a resposta esperada (viram teste). O texto aparece na resposta do chat e na fila "Para aprovar" do Thomas, que
cola no Claude Code. Na dúvida, vale "com ferramentas". Nada é apagado: aceitar ou recusar só muda a situação.
O andar Comercial continua bloqueado (N2-construtor-02).
"""

import logging
import re

import agentes_persona
import config
import encaminhamento
import tarefas
from conexoes import gerenciador

log = logging.getLogger(__name__)

PENDENTE, ACEITO, RECUSADO = "pendente", "aceito", "recusado"
LIMITE_POR_DIA = 3
EXEMPLOS = 3

# Pedido que precisa de mãos: Max (produção, arquivos), Monday, Drive, Brevo, e-mail, Telegram ou arquivo gerado.
FERRAMENTAS = re.compile(
    r"\bmax\b|\bmonday\b|\bdrive\b|\bbrevo\b|\btelegram\b|\bcanva\b|\barquivos?\b|\bplanilhas?\b|\b(?:png|jpe?g|mp4|"
    r"mp3|docx?|pdf|pptx?|xlsx?|csv)\b|dispar\w+\s+(?:e-?mails?|mensagens?)|\benvi\w+\s+e-?mails?|"
    r"\bpublic\w+\s+(?:no|na|nas|nos)\s+(?:instagram|redes|linkedin|tiktok|site)|\bgerar?\s+(?:imagens?|v[ií]deos?|"
    r"[aá]udios?)|\bpainel\b|\bapi\b|\bintegra\w+", re.I)

# Mesmos perigos da persona que importam num texto que o Thomas cola no Claude Code (ler arquivo e comando são o
# próprio assunto da obra; link, contato, senha e "ignore as instruções" não).
_PERIGOS = {"links", "e-mails", "telefones", "ordem para ignorar instruções", "senhas, tokens ou chaves"}

INSTRUCAO = (
    "PEDIDO DE OBRA: se o agente pedido precisa de ferramenta (Max, Monday, Drive, Brevo, e-mail, gerar arquivo, "
    "imagem, vídeo ou áudio), ele NÃO vira proposta: o sistema transforma a especificação num pedido de obra para o "
    "Thomas executar no Claude Code. Nesse caso, chame criar_agente com os campos de sempre e mais: ferramentas "
    "(lista do que ele precisa usar), nao_faz (o que ele NÃO faz) e exemplos (exatamente 3 objetos {\"pedido\": ..., "
    "\"resposta_esperada\": ...}, com um pedido real da equipe e o que o agente deve devolver). Na dúvida, trate como "
    "agente com ferramentas. Na resposta, diga que virou pedido de obra para o Thomas e que nada entrou no escritório.")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS pedidos_obra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL, andar TEXT NOT NULL, setor TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL, criado_por TEXT NOT NULL, criado_em TEXT NOT NULL, tarefa_id INTEGER,
    situacao TEXT NOT NULL DEFAULT 'pendente', decidido_por TEXT, decidido_em TEXT
);
"""
_pronto = False


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.executescript(_ESQUEMA)
        _pronto = True
    return db


def _pedido(tarefa_id: int | None) -> str:
    linha = tarefas.obter(tarefa_id) if tarefa_id else None
    return encaminhamento.pedido_original(linha["texto"]) if linha else ""


def com_ferramentas(spec: dict, tarefa_id: int | None = None) -> bool:
    """O pedido ou a especificação falam de ferramenta (a persona fica de fora: ela cita o Monday de passagem)."""
    if (spec or {}).get("ferramentas"):
        return True
    campos = [str((spec or {}).get(c) or "") for c in ("nome", "funcao", "descricao", "exemplo", "goal")]
    return bool(FERRAMENTAS.search(" ".join([_pedido(tarefa_id), *campos])))


def _lista(valor) -> list[str]:
    if isinstance(valor, str):
        valor = re.split(r"[;\n]|,\s+", valor)
    return [" ".join(str(v).split())[:200] for v in (valor or []) if str(v).strip()][:12]


def _exemplos(valor) -> list[dict]:
    exemplos = []
    for item in valor if isinstance(valor, list) else []:
        if isinstance(item, dict):
            pedido = " ".join(str(item.get("pedido") or "").split())[:300]
            resposta = " ".join(str(item.get("resposta_esperada") or item.get("resposta") or "").split())[:600]
            if len(pedido) >= 10 and len(resposta) >= 20:
                exemplos.append({"pedido": pedido, "resposta_esperada": resposta})
    return exemplos


def montar(spec: dict, pedido_por: str, pedido: str = "") -> dict:
    """Valida e escreve o pedido de obra em Markdown. Levanta ErroValidacao com o que falta."""
    from agentes_dinamicos import (ANDARES_BLOQUEADOS, NOMES_ANDARES, NOMES_SETORES, SETORES, ErroValidacao, _snake,
                                   _texto)

    nome, funcao = _texto(spec, "nome"), _texto(spec, "funcao")
    andar = _snake(str(spec.get("andar") or ""))
    if andar in ANDARES_BLOQUEADOS:
        raise ErroValidacao(f"o andar {NOMES_ANDARES[andar]} não recebe agentes novos, nem por pedido de obra: "
                            f"{ANDARES_BLOQUEADOS[andar]}. Explique isso ao usuário e ofereça os colegas de lá "
                            "(Prospectador e Estrategista) ou outro andar.")
    if andar not in SETORES:
        raise ErroValidacao(f"andar inválido {spec.get('andar')!r}; use um de: "
                            f"{', '.join(a for a in SETORES if a not in ANDARES_BLOQUEADOS)}.")
    setor = _snake(str(spec.get("setor") or ""))
    setor = setor if setor in SETORES[andar] else ""
    exemplos = _exemplos(spec.get("exemplos"))
    if len(exemplos) < EXEMPLOS:
        raise ErroValidacao(f"este agente precisa de ferramentas e vira PEDIDO DE OBRA para o Thomas. Inclua "
                            f"'exemplos' com {EXEMPLOS} objetos {{\"pedido\": ..., \"resposta_esperada\": ...}} (pedido "
                            "real da equipe e o que o agente deve devolver), 'ferramentas' e 'nao_faz', e chame de novo.")
    ferramentas = _lista(spec.get("ferramentas")) or ["(o Construtor não listou: o Thomas define)"]
    nao_faz = " ".join(str(spec.get("nao_faz") or "").split())[:600] or "(não informado: o Thomas define)"
    descricao, goal = _texto(spec, "descricao"), " ".join(str(spec.get("goal") or "").split())[:600]
    texto = "\n".join([
        f"# Pedido de obra: {nome}",
        "",
        f"Pedido por {pedido_por} ao Construtor. Texto escrito por modelo a partir do pedido: revise antes de colar no "
        "Claude Code. Nada entrou no escritório.",
        "",
        f"**Pedido original:** {' '.join(pedido.split())[:500] or '(sem texto)'}",
        f"**Mesa:** {NOMES_ANDARES[andar]}, setor {NOMES_SETORES.get(setor, 'a definir')}",
        f"**Função:** {funcao}",
        *([f"**O que faz:** {descricao}"] if descricao else []),
        *([f"**Objetivo:** {goal}"] if goal else []),
        f"**Ferramentas:** {'; '.join(ferramentas)}",
        f"**O que NÃO faz:** {nao_faz}",
        "",
        "## Peças a montar (molde do Sonoplasta, commit 1462535)",
        "- mesa e setor (backend/estado.py e frontend/js/escritorio3d/1_motor.js);",
        "- persona e método (backend/agents/perfis.py) e diretrizes (backend/agents/diretrizes.py);",
        "- manuais que ele lê e a ficha de pedido no manual 16;",
        "- gatilhos da triagem (backend/triagem.py) e formulário de pedido (frontend/js/modelos_pedido.js);",
        "- script do Max (scripts/max/) e passo no trabalhador_max.py, se gerar arquivo;",
        "- entrega no Drive (pasta do andar) e testes com os exemplos abaixo.",
        "",
        "## Exemplos (viram teste)",
        *[f"{n}. Pedido: \"{e['pedido']}\"\n   Resposta esperada: {e['resposta_esperada']}"
          for n, e in enumerate(exemplos[:EXEMPLOS], 1)],
    ])
    if (achados := _perigos(" ".join([nome, funcao, descricao, goal, nao_faz, *ferramentas,
                                      *(v for e in exemplos for v in e.values())]))):
        raise ErroValidacao(f"o pedido de obra traz o que não pode: {', '.join(achados)}. Tire isso (sem links, "
                            "contatos, senhas ou ordem para ignorar instruções; WhatsApp só como proibição) e chame "
                            "de novo.")
    return {"nome": nome, "andar": andar, "setor": setor, "texto": texto}


def _perigos(texto: str) -> list[str]:
    achados = [motivo for padrao, motivo in agentes_persona.PERIGOSOS
               if motivo in _PERIGOS and re.search(padrao, texto, re.I)]
    if any(not re.search(agentes_persona.NEGACAO + r"$", texto[max(0, a.start() - 50):a.start()], re.I)
           for a in re.finditer(r"whatsapp", texto, re.I)):
        achados.append("WhatsApp como CTA")
    return achados


def da_tarefa(tarefa_id: int | None):
    return tarefa_id and _db().execute("SELECT * FROM pedidos_obra WHERE tarefa_id = ?", (tarefa_id,)).fetchone()


async def registrar(spec: dict, criado_por: str, tarefa_id: int | None = None) -> dict:
    """Grava o pedido de obra (um por tarefa) e avisa o Thomas. Devolve o registro com "obra": True."""
    from agentes_dinamicos import LimiteAtingido

    if (anterior := da_tarefa(tarefa_id)):
        return {**dict(anterior), "obra": True, "repetido": True}
    hoje = _db().execute("SELECT COUNT(*) FROM pedidos_obra WHERE criado_em >= ?", (tarefas._agora()[:10],)).fetchone()[0]
    if hoje >= LIMITE_POR_DIA:
        raise LimiteAtingido(f"o limite é de {LIMITE_POR_DIA} pedidos de obra por dia, e ele já foi atingido hoje.")
    obra = montar(spec, criado_por, _pedido(tarefa_id))
    with _db() as db:
        cursor = db.execute("INSERT INTO pedidos_obra (nome, andar, setor, texto, criado_por, criado_em, tarefa_id) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)", (obra["nome"], obra["andar"], obra["setor"], obra["texto"],
                                                            criado_por, tarefas._agora(), tarefa_id))
    obra.update(id=cursor.lastrowid, criado_por=criado_por, situacao=PENDENTE, tarefa_id=tarefa_id, obra=True)
    if tarefa_id:
        tarefas.registrar_evento(tarefa_id, "pedido_obra", str(obra["id"]),
                                 detalhe=f"{obra['nome']}: pedido de obra #{obra['id']} para o Thomas.")
    aviso = {"tipo": "aviso", "andar": "porao", "agente": "construtor", "titulo": "Pedido de obra",
             "texto": f"{obra['nome']} precisa de ferramentas e virou o pedido de obra #{obra['id']} para o Thomas. "
                      "Está na Caixa de entrada, em \"Para aprovar\"."}
    entregue = await gerenciador.enviar_para_usuario(config.DONO_MAX, aviso)
    if criado_por != config.DONO_MAX:
        await gerenciador.enviar_para_usuario(criado_por, aviso)
    log.warning("Pedido de obra #%s (%s) por %s, tarefa %s%s", obra["id"], obra["nome"], criado_por, tarefa_id,
                "" if entregue else "; aviso ao Thomas não entregue (fica na Caixa de entrada)")
    return obra


def pendentes() -> list:
    return _db().execute("SELECT * FROM pedidos_obra WHERE situacao = ? ORDER BY criado_em",
                         (PENDENTE,)).fetchall()


def decidir(obra_id: int, login: str, acao: str) -> str:
    """Só o Thomas: "aceitar" (vai executar no Claude Code) ou "recusar". Nada é apagado."""
    if (login or "").strip().lower() != config.DONO_MAX:
        return "Só o Thomas decide os pedidos de obra (ele é quem monta o agente no Claude Code)."
    linha = _db().execute("SELECT * FROM pedidos_obra WHERE id = ? AND situacao = ?", (obra_id, PENDENTE)).fetchone()
    if not linha:
        return f"Não achei nenhum pedido de obra pendente com o número {obra_id}."
    situacao = ACEITO if acao == "aprovar" else RECUSADO
    with _db() as db:
        db.execute("UPDATE pedidos_obra SET situacao = ?, decidido_por = ?, decidido_em = ? WHERE id = ?",
                   (situacao, login, tarefas._agora(), obra_id))
    return (f"Pedido de obra #{obra_id} ({linha['nome']}) aceito: copie o texto para o Claude Code." if situacao == ACEITO
            else f"Pedido de obra #{obra_id} ({linha['nome']}) recusado. O texto continua guardado.")


def rodape(tarefa_id: int | None) -> str:
    """Texto do pedido de obra para ir junto da resposta do Construtor no chat ("" se a tarefa não gerou obra)."""
    linha = da_tarefa(tarefa_id)
    if not linha:
        return ""
    return (f"\n\nRegistro do sistema: virou o PEDIDO DE OBRA #{linha['id']} para o Thomas (agente com ferramentas "
            f"não entra pelo Construtor). Nada entrou no escritório.\n\n{linha['texto']}")
