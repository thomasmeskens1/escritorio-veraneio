"""Drive do PC incompleto (brainstorm de 11/11/2026, despachante-10): aviso para quem pediu, no painel e no Telegram.

Antes, "Drive incompleto" existia só no log do trabalhador do Max: as peças esperavam horas (tarefa 272, "sem
nenhuma casa", esperou quase 4 h e rodou em 1 min 40 s) e ninguém sabia por quê. Agora:
- o trabalhador diz ao backend, a cada pedido da fila, o que falta do Drive;
- a peça que não usa o acervo dos Lodges (só marcas e fontes, já copiadas para a pasta da peça) roda mesmo sem ele;
- quem pediu a peça que espera recebe, uma vez, "sua peça espera o Drive do PC voltar";
- depois de 20 min, o aviso entra nos avisos de operação (painel da Diretoria e alarme do Telegram).
Estado só na memória: depois de um reinício, o próximo pedido da fila refaz o quadro.
"""

import logging
import re
import time

import encaminhamento
import tarefas
from conexoes import gerenciador

log = logging.getLogger(__name__)

AVISO_APOS_S = 20 * 60
SEM_NOTICIA_S = 15 * 60  # trabalhador calado: o aviso do Drive sai (o de "trabalhador parado" já cobre)
ACERVO = "acervo dos Lodges"

_estado = {"faltando": "", "desde": 0.0, "visto": 0.0}

# A peça usa o acervo? Na dúvida, sim (espera como antes). Marca ("Casa Veraneio", "Casa Vero") não conta, nem a
# negação ("sem nenhuma casa", "sem fotos"). Vídeo usa as filmagens do acervo: sempre espera.
_MARCAS = re.compile(r"\bcasa\s+ver(?:aneio|o)\w*(?:\s+corporativo)?\b", re.I)
_NEGADO = re.compile(r"\b(?:sem|nenhum|nenhuma|n[aã]o (?:use|usar|mostre|mostrar))\s+(?:\w+\s+){0,2}?"
                     r"(?:lodges?|casas?|im[oó]ve(?:l|is)|fotos?|imagens? reais|acervo)\b", re.I)
USA_ACERVO = re.compile(r"\b(?:lodges?|casas?|im[oó]ve(?:l|is)|su[ií]tes?|fotos?|fotografias?|acervo|piscinas?|"
                        r"quartos?|varandas?|ambientes?|filmage(?:m|ns)|takes?)\b", re.I)


def precisa_do_acervo(agente: str, texto: str) -> bool:
    if agente == "editor_video":
        return True
    return bool(USA_ACERVO.search(_NEGADO.sub(" ", _MARCAS.sub(" ", texto or ""))))


def registrar(faltando: str, incompleto: bool, agora: float | None = None) -> None:
    """Chamado pelo /proxima. `faltando`: nomes das pastas (o trabalhador antigo não manda; vale "Drive")."""
    agora = time.time() if agora is None else agora
    faltando = (faltando or "").strip()[:200] or ("Drive" if incompleto else "")
    if not faltando:
        if _estado["faltando"]:
            log.info("Drive do PC voltou depois de %d min.", (agora - _estado["desde"]) // 60)
        _estado.update(faltando="", desde=0.0, visto=agora)
        return
    if not _estado["faltando"]:
        _estado["desde"] = agora
    _estado.update(faltando=faltando, visto=agora)


def faltando() -> str:
    """O que falta do Drive agora ("" = tudo acessível ou sem notícia do trabalhador). Usado pelo inventario.py."""
    return _estado["faltando"]


def so_acervo() -> bool:
    """Falta só o acervo dos Lodges: as peças que não o usam podem rodar."""
    return _estado["faltando"] == ACERVO


def proxima_sem_acervo():
    """A primeira peça da fila que não usa o acervo (None se todas usam)."""
    for linha in tarefas._db().execute("SELECT * FROM tarefas WHERE status = 'producao' ORDER BY id"):
        if not precisa_do_acervo(linha["agente"], linha["texto"]):
            return linha
    return None


def aviso(agora: float | None = None) -> str | None:
    """Para saude.avisos_da_operacao (painel da Diretoria e Telegram)."""
    agora = time.time() if agora is None else agora
    if not _estado["faltando"] or agora - _estado["visto"] > SEM_NOTICIA_S or agora - _estado["desde"] < AVISO_APOS_S:
        return None
    fila = tarefas._db().execute("SELECT COUNT(*) FROM tarefas WHERE status = 'producao'").fetchone()[0]
    return (f"Drive do PC incompleto há {int((agora - _estado['desde']) // 60)} min (falta: {_estado['faltando']})"
            + (f", com {fila} peça(s) esperando" if fila else "") + ". Confira o Google Drive para computador e deixe "
            "as pastas MARCAS e FONTES como \"Disponível offline\".")


async def avisar_quem_espera() -> int:
    """Uma vez por peça: "sua peça espera o Drive do PC voltar", no chat onde foi pedida. Devolve quantos avisou."""
    if not _estado["faltando"]:
        return 0
    linhas = tarefas._db().execute(
        "SELECT * FROM tarefas t WHERE status = 'producao' AND NOT EXISTS (SELECT 1 FROM eventos e "
        "WHERE e.tarefa_id = t.id AND e.tipo = 'espera_drive') ORDER BY id").fetchall()
    avisados = 0
    for linha in linhas:
        if so_acervo() and not precisa_do_acervo(linha["agente"], linha["texto"]):
            continue  # esta roda sem o acervo
        tarefas.registrar_evento(linha["id"], "espera_drive", linha["agente"],
                                 detalhe=f"Drive do PC incompleto (falta: {_estado['faltando']})")
        andar, agente = encaminhamento.origem(linha["id"]) or (linha["andar"], linha["agente"])
        try:
            await gerenciador.enviar_para_usuario(linha["usuario"], {
                "tipo": "aviso", "andar": andar, "agente": agente, "tarefa_id": linha["id"],
                "titulo": "Peça esperando o Drive",
                "texto": f"Sua peça #{linha['id']} espera o Drive do PC voltar (falta: {_estado['faltando']}). Ela "
                         "começa sozinha assim que o Drive voltar, sem precisar reenviar. Se não precisar mais dela, "
                         "use o botão Parar."})
        except Exception:  # aviso nunca segura a fila
            log.exception("Drive do PC: não consegui avisar a espera da peça %s.", linha["id"])
        avisados += 1
    return avisados
