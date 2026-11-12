"""Pasta de REFERÊNCIAS do Drive citada num pedido (Thomas, 12/11/2026; tarefas 290 a 294 do João).

A pasta ESCRITÓRIO VERANEIO > REFERENCIAS > <EMPRESA> é usada de vez em quando, só quando o pedido a cita (link do
Drive ou caminho). O padrão é SÓ ESTUDO: a produção vê folhas de quadros com a marca "REFERÊNCIA – SÓ ESTUDO" e não
recebe os originais. Quem pede escolhe no popup do chat (frontend/js/pasta_referencias.js) se os arquivos podem entrar
na peça; a escolha vai num marcador no fim do texto. Nos dois casos o estudo acontece, e o que a produção aprendeu
vira uma observação "estudo" para a Diretoria aprovar antes de entrar no Cérebro (correcoes.py). O trabalhador do Max
(scripts/max/pasta_referencias.py) acha a pasta no Drive do PC e prepara o estudo.
"""

import logging
import re

import tarefas

log = logging.getLogger(__name__)

LINK_PASTA = re.compile(r"https://drive\.google\.com/drive/(?:u/\d+/)?folders/[\w-]{10,80}", re.I)
CAMINHO = re.compile(r"\brefer[eê]ncias\s*(?:->|>|/|\\)", re.I)
MARCADOR = re.compile(r"\[Pasta de refer[eê]ncias:\s*([^\]]*)\]", re.I)
USAR, ESTUDO = "usar", "estudo"
MAX_ESTUDO = 500  # cabe na regra do popup do Cérebro (correcoes.Decisao, até 500)

NOTA_AGENTE = ("PASTA DE REFERÊNCIAS DO DRIVE CITADA NO PEDIDO: daqui você não abre arquivos do Drive, e não precisa. "
               "Quando houver peça final, a produção (Claude Code no PC do escritório) acha a pasta sozinha em "
               "ESCRITÓRIO VERANEIO > REFERENCIAS > <empresa> e estuda os arquivos. {uso} Nunca peça para baixar os "
               "arquivos em outra pasta e nunca cite caminhos internos do sistema (AppData, max_texto, rascunhos). Se a "
               "pasta for de outra empresa ou ficar fora de REFERENCIAS, a produção avisa na entrega.")
USO_TEXTO = {
    ESTUDO: "Quem pediu marcou SÓ PARA ESTUDO: os arquivos servem de inspiração (ritmo, enquadramento, o que mostrar) "
            "e não entram na peça; o material vem do acervo oficial.",
    USAR: "Quem pediu liberou o USO dos arquivos na peça (além do estudo).",
}


def cita(texto: str) -> bool:
    return bool(LINK_PASTA.search(texto or "") or CAMINHO.search(texto or ""))


def uso(texto: str) -> str:
    """'usar' só com o marcador do popup liberando; qualquer outro caso (Monday, Telegram, sem resposta) = estudo."""
    marcador = MARCADOR.search(texto or "")
    return USAR if marcador and re.search(r"\bpode usar\b", marcador.group(1), re.I) else ESTUDO


def nota_para_agente(texto: str) -> str:
    return NOTA_AGENTE.format(uso=USO_TEXTO[uso(texto)]) if cita(texto) else ""


def linha_para_producao(linha) -> str:
    """Citação da pasta no projeto do Gestor que precisa chegar à produção: o link pode estar numa mensagem anterior
    da conversa, fora do "Pedido original" (tarefa 291 do João). Volta "" quando nada cita a pasta."""
    textos = [linha["texto"] or ""] + [h["texto"] or "" for h in tarefas.historico(
        linha["usuario"], linha["andar"], linha["agente"], linha["id"], limite=6, empresa=linha["empresa"])]
    citacoes = [t for t in textos if cita(t)]
    if not citacoes:
        return ""
    links = list(dict.fromkeys(m.group(0) for t in citacoes for m in LINK_PASTA.finditer(t)))
    caminhos = [t.strip()[:400] for t in citacoes if CAMINHO.search(t) and not LINK_PASTA.search(t)]
    escolhido = next((m.group(0) for t in reversed(textos) if (m := MARCADOR.search(t))), "")
    return "\n".join(filter(None, ["PASTA DE REFERÊNCIAS CITADA NA CONVERSA:", *links, *caminhos,
                                   escolhido or "[Pasta de referências: só para estudo]"]))


def registrar_estudo(tarefa_id: int, estudo: str, pasta: str) -> bool:
    """O que a produção aprendeu com a pasta vira observação 'estudo' (nunca regra direta): a Diretoria aprova,
    edita ou descarta no popup do Cérebro, e só o aprovado é ensinado ao Cérebro."""
    estudo = (estudo or "").strip()
    linha = tarefas.obter(tarefa_id)
    if not estudo or not linha:
        return False
    import correcoes  # import tardio: correcoes importa o estado dos agentes

    with correcoes._db() as db:
        db.execute("INSERT INTO observacoes (em, usuario, andar, agente, tarefa_anterior, correcao, resposta_anterior, "
                   "tipo) VALUES (?, ?, ?, ?, ?, ?, ?, 'estudo')",
                   (tarefas._agora(), linha["usuario"], linha["andar"], linha["agente"], tarefa_id,
                    estudo[:MAX_ESTUDO], f"Estudo da pasta de referências {pasta or '(sem nome)'} na peça #{tarefa_id} "
                                         f"({'arquivos liberados para uso' if uso(linha['texto']) == USAR else 'só estudo'})."))
    import atividade

    atividade._no_loop(correcoes.avisar_diretoria("estudo"))
    return True
