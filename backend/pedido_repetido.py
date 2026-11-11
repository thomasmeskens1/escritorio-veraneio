"""Pedido repetido ao Gestor: continuar em vez de refazer (Onda 2 de novembro: copywriter-06, editor_video-06 e 07).

Casos reais: o Reels do Lodge 32 e o do Lodge 239 foram produzidos duas vezes, inteiros, em pastas diferentes; as
tarefas 265 e 266 (mesmo texto, 25 minutos depois) rodaram duas vezes no Max. Antes de acionar a equipe, sem IA:
- pedido idêntico da mesma pessoa, na mesma empresa e no mesmo chat nas últimas 2 horas: aviso leve, com
  "Quero outra versão" (a resposta anterior continua no chat);
- peça parecida (mesma empresa, mesmo formato e o mesmo Lodge, produzida nos últimos 45 dias): três botões,
  "Ajuste da v1" (vai à mesma pasta como nova versão, pelo "Ajuste na peça #N" que já existe), "Variante B" (peça
  nova que muda uma variável só, anotada para comparar A e B) e "Peça nova". A pessoa sempre escolhe; o sistema
  nunca junta pastas sozinho.
"""

import re
import unicodedata
from datetime import datetime, timedelta, timezone

import tarefas

JANELA_IDENTICO = timedelta(hours=2)
JANELA_PECA = timedelta(days=45)   # o crítico pediu de 30 a 60 dias
ANDAR, GESTOR = "marketing", "gestor"
DE_PROPOSITO = "pedido de propósito"  # marca dos botões: o pedido reenviado não é checado de novo
PREFIXO = re.compile(r"^\s*(\[Pedido feito a[o]? [^\]]+\]\s*)?((planejamento|pe[cç]a\s+final)\s*:\s*)?", re.I)
ORIGINAL = re.compile(r"Pedido original:\s*(.*?)(?:\n\nResultado consolidado|\Z)", re.S)
LODGE = re.compile(r"\blodges?\s*#?0*(\d{1,4})\b", re.I)
SUFIXOS = re.compile(r"\n\n(FORMATO DA PEÇA \(obrigatório\):|---\n).*\Z", re.S)


def _normal(texto: str) -> str:
    """Só o que a pessoa escreveu (sem o prefixo do encaminhamento, a linha de formato e as instruções do sistema)."""
    texto = SUFIXOS.sub("", PREFIXO.sub("", texto or ""))
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())


def _minutos(criada_em: str) -> int:
    quando = datetime.strptime(criada_em, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(1, int((datetime.now(timezone.utc) - quando).total_seconds() // 60))


def identico(login: str, agentes: tuple[str, ...], texto: str, empresa: str):
    """Tarefa recente (2 h) da mesma pessoa e empresa, num destes agentes, com o mesmo pedido; ou None."""
    alvo = _normal(texto)
    if len(alvo) < 12:
        return None
    marcas = ",".join("?" * len(agentes))
    linhas = tarefas._db().execute(
        f"SELECT id, texto, status, criada_em FROM tarefas WHERE usuario = ? AND empresa IS ? AND agente IN ({marcas}) "
        "AND criada_em >= ? AND status != 'falhou' ORDER BY id DESC LIMIT 30",
        (login, empresa, *agentes, tarefas._agora(-JANELA_IDENTICO))).fetchall()
    return next((l for l in linhas if _normal(l["texto"]) == alvo), None)


def _pedido_da_producao(texto: str) -> str:
    achado = ORIGINAL.search(texto or "")
    return achado.group(1) if achado else (texto or "")[:1500]


def peca_parecida(login: str, texto: str, empresa: str):
    """(produção, formato, Lodges em comum) da peça parecida mais recente, ou None. A chave é a do crítico:
    empresa + formato + Lodge, nos últimos 45 dias."""
    import monday
    import producao  # import tardio: a produção depende do orquestrador

    tipo, lodges = monday.tipo_no_texto(PREFIXO.sub("", texto)), set(LODGE.findall(texto or ""))
    if not tipo or not lodges:
        return None
    linhas = producao._db().execute(
        "SELECT t.id, t.texto, t.criada_em FROM tarefas t JOIN producao_info p ON p.tarefa_id = t.id "
        "WHERE t.usuario = ? AND t.empresa IS ? AND t.status = 'concluida' AND p.pasta IS NOT NULL "
        "AND t.criada_em >= ? ORDER BY t.id DESC LIMIT 60",
        (login, empresa, tarefas._agora(-JANELA_PECA))).fetchall()
    for linha in linhas:
        original = _pedido_da_producao(linha["texto"])
        comuns = lodges & set(LODGE.findall(original))
        if comuns and monday.tipo_no_texto(original) == tipo:
            return linha, tipo, sorted(comuns, key=int)
    return None


def aviso(login: str, andar: str, agente_id: str, texto: str, empresa: str, para_o_gestor: bool = False) -> dict | None:
    """Aviso com botões para o chat (titulo, texto, opcoes), ou None se o pedido segue normal. Vale para o Gestor e
    para a peça pedida a um especialista que vai ao Gestor (`para_o_gestor`)."""
    if andar != ANDAR or not (agente_id == GESTOR or para_o_gestor) or DE_PROPOSITO in (texto or ""):
        return None
    pedido = texto.strip()
    if pedido.startswith("Respostas") or re.match(r"\s*ajuste\s+na\s+pe[cç]a\s+#\d+", pedido, re.I):
        return None  # resposta de formulário e ajuste citado seguem o caminho deles
    so_plano = bool(re.match(r"\s*(\[[^\]]+\]\s*)?planejamento\s*:", pedido, re.I))  # ideias não são peça
    if not so_plano and (parecida := peca_parecida(login, pedido, empresa)):
        linha, tipo, lodges = parecida
        quando = f"{linha['criada_em'][8:10]}/{linha['criada_em'][5:7]}"
        lodge_txt = ", ".join(f"Lodge {n}" for n in lodges)
        return {
            "titulo": "Peça parecida",
            "texto": f"Você já tem uma peça parecida: #{linha['id']} ({tipo}, {lodge_txt}), produzida em {quando}. "
                     "Quer ajustar essa versão, fazer uma variante B para comparar ou uma peça nova do zero? Nada é "
                     "juntado sem a sua escolha.",
            "opcoes": [
                {"rotulo": "Ajuste da v1", "texto": f"Ajuste na peça #{linha['id']}: {PREFIXO.sub('', pedido).strip()}"},
                {"rotulo": "Variante B", "texto": f"{pedido}\n\n(Variante B da peça #{linha['id']}, {DE_PROPOSITO}: "
                                                   "mesma base e mesmo Lodge; mude UMA variável só, como o gancho, a "
                                                   "capa ou a abertura, e diga no plano qual foi, para comparar A e B.)"},
                {"rotulo": "Peça nova", "texto": f"{pedido}\n\n(Peça nova, {DE_PROPOSITO}: não é ajuste da "
                                                  f"#{linha['id']}.)"}]}
    if (anterior := identico(login, (GESTOR, agente_id), pedido, empresa)):
        estado = ("a resposta está aqui no chat" if anterior["status"] == "concluida"
                  else "ela ainda está a caminho e chega aqui")
        return {
            "titulo": "Pedido repetido",
            "texto": f"Você pediu isso há {_minutos(anterior['criada_em'])} minuto(s) (tarefa #{anterior['id']}): "
                     f"{estado}. Quer outra versão?",
            "opcoes": [{"rotulo": "Quero outra versão",
                        "texto": f"{pedido}\n\n(Outra versão, {DE_PROPOSITO}: não repita a abertura da tarefa "
                                 f"#{anterior['id']}.)"}]}
    return None
