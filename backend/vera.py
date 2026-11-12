"""Vera, a assistente de voz do escritório (Thomas, 12/11/2026; inspirada no "Alfred, abre o escritório" do Reel
de @tonyareda). O reconhecimento e a fala ficam no navegador (frontend/js/voz.js, Web Speech API, sem custo de IA).

"Olá Vera, abre o escritório" pede este resumo do dia, montado só com contas no banco (sem modelo):
- pedidos de quem fala que estão em andamento, respostas novas e falhas nas últimas 24 h;
- o que espera a decisão dessa pessoa na aba "Para aprovar";
- para a Diretoria, as observações à espera no Cérebro e os avisos de operação (os mesmos do painel).
Os outros pedidos à Vera vão para a triagem (triagem.py), que já indica o agente certo.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

import tarefas
from auth import validar_token

rotas = APIRouter(prefix="/api/vera")

EM_ANDAMENTO = ("executando", "producao", "produzindo", "adiada", "pendente", "na_fila")
MAX_AVISOS = 3


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def resumo(login: str, nome: str, diretoria: bool) -> str:
    db = tarefas._db()
    marcas = ",".join("?" * len(EM_ANDAMENTO))
    andando = db.execute(f"SELECT COUNT(*) FROM tarefas WHERE usuario = ? AND status IN ({marcas})",
                         (login, *EM_ANDAMENTO)).fetchone()[0]
    novas = db.execute("SELECT COUNT(*) FROM tarefas WHERE usuario = ? AND entregue = 0 AND status = 'concluida'",
                       (login,)).fetchone()[0]
    desde = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    falhas = db.execute("SELECT COUNT(*) FROM tarefas WHERE usuario = ? AND status = 'falhou' AND criada_em >= ?",
                        (login, desde)).fetchone()[0]
    import aprovacoes  # import tardio: a fila de aprovações importa vários módulos

    aprovar = len(aprovacoes.itens(login))
    partes = [f"Olá, {nome}." if nome else "Olá."]
    pedidos = []
    if andando:
        pedidos.append(f"{_plural(andando, 'pedido seu está', 'pedidos seus estão')} em andamento")
    if novas:
        pedidos.append(f"{_plural(novas, 'resposta nova espera', 'respostas novas esperam')} por você")
    if falhas:
        pedidos.append(f"{_plural(falhas, 'pedido falhou', 'pedidos falharam')} nas últimas 24 horas")
    partes.append(("Hoje, " + ", ".join(pedidos) + ".") if pedidos else "Você não tem pedidos em andamento agora.")
    if aprovar:
        partes.append(f"{_plural(aprovar, 'item espera', 'itens esperam')} a sua aprovação na Caixa de entrada.")
    if diretoria:
        import correcoes
        import saude

        if (pendentes := correcoes.pendentes()):
            partes.append(f"No Cérebro, {_plural(pendentes, 'observação espera', 'observações esperam')} aprovação.")
        avisos = saude.avisos_da_operacao()
        if avisos:
            partes.append(f"Atenção na operação: {_plural(len(avisos), 'aviso', 'avisos')}. "
                          + " ".join(avisos[:MAX_AVISOS]))
        else:
            partes.append("A operação está em ordem.")
    partes.append("Do que você precisa?")
    return " ".join(partes)


@rotas.get("/resumo")
def ver_resumo(authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    from auth import carregar_usuarios

    nome = (carregar_usuarios().get(usuario["sub"]) or {}).get("nome", "")
    return {"texto": resumo(usuario["sub"], nome.split()[0] if nome else "", usuario.get("role") == "diretoria")}
