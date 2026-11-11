"""Pergunta do Gestor com opções e "Escolha por mim" que decide de fato (Onda 2 de novembro: gestor-02,
moviemaker-33, professor-13 e despachante-19). Fica fora de projeto.py para ele não passar de 500 linhas.

Caso real (tarefas 268 a 270, 06/11/2026): "Quais Lodges ficam no Nordeste?" saiu três vezes em texto livre, mesmo
depois de "acho que você pode escolher". Agora:
- a dúvida do plano sai como o formulário que o chat já tem (<<FORMULARIO>>), com 2 a 4 opções concretas e, quando a
  escolha é editorial, "Escolha por mim";
- a resposta (ou a delegação) fica gravada no projeto seguinte, em decisoes.json, e entra no pedido do plano;
- trava em código: se a pergunta nova for parecida com uma já respondida no mesmo projeto, ela não volta. Delegada,
  o Gestor decide (e, se ainda insistir, o sistema fica com a primeira opção que ele mesmo ofereceu).
Fato que só a equipe sabe (preço, condição especial, valores na arte, data do evento, responsável) não é delegável:
fica PENDENTE no texto, nunca inventado (manual 10 §5; a lista é configurável em NAO_DELEGAVEIS).
"""

import json
import re
from datetime import timedelta
from pathlib import Path

ESCOLHA_POR_MIM = "Escolha por mim"
TITULO = "Pergunta do Gestor"
CAMPO, OUTRA = "escolha_gestor", "outra_resposta"
MAX_OPCOES = 4
JANELA = timedelta(hours=6)   # resposta que chega depois disso já é outra conversa
PARECIDA = 0.6                # termos em comum (Jaccard), o mesmo corte das lacunas do Cérebro

# "pode escolher", "você escolhe", "tanto faz", "decide você", "pode preencher" (tarefa 88), "Escolha por mim".
DELEGACAO = re.compile(
    r"\bescolh\w*\s+(por\s+mim|voc[eê]|a\s+seu\s+crit[eé]rio)|\b(voc[eê]|pode)\s+(mesmo\s+)?(escolher|escolhe|decidir|"
    r"decide|preencher)\b|\bdecid[ae]\s+(voc[eê]|por\s+mim)\b|\btanto\s+faz\b|\ba\s+seu\s+crit[eé]rio\b|"
    r"\bcomo\s+(voc[eê]\s+)?achar\s+melhor\b|\bfica\s+a\s+seu\s+cargo\b", re.IGNORECASE)
NEGACAO = re.compile(r"\bn[aã]o\s+(\w+\s+){0,2}(pode|escolh|decid|preench)", re.IGNORECASE)
# Manual 10 §5: o que o agente nunca escolhe sozinho (a regra está na proposta da Onda 1, ainda sem aprovação).
NAO_DELEGAVEIS = re.compile(r"condi[cç][aã]o\s+especial|valor(es)?\s+na\s+arte|\bpre[cç]os?\b|\bdescontos?\b|"
                            r"\bdi[aá]rias?\b|data\s+do\s+evento|\brespons[aá]vel\b", re.IGNORECASE)
PEDIDO_FEITO = re.compile(r"^\[Pedido feito a[o]? [^\]]+\]\s*")
LINHA_FORM = re.compile(r"^\s*-\s*[^:\n]+:\s*(.+)$", re.M)

INSTRUCAO = (
    "Se preencher \"duvida\", preencha também \"opcoes\" (de 2 a 4 respostas curtas e concretas que você já pode "
    "oferecer, ex.: os Lodges que passam no filtro) e \"pode_decidir\" (true se é uma escolha editorial que você "
    "poderia fazer sozinho; false se é um fato que só a equipe sabe, como preço, condição especial, valores na arte, "
    "data do evento ou responsável). Nunca repita uma pergunta das DECISÕES JÁ TOMADAS. ")


def e_delegacao(texto: str) -> bool:
    """A pessoa deixou a escolha com o agente ("pode escolher", "Escolha por mim", "tanto faz")."""
    texto = texto or ""
    return ESCOLHA_POR_MIM.lower() in texto.lower() or (bool(DELEGACAO.search(texto)) and not NEGACAO.search(texto))


def _termos(texto: str) -> set[str]:
    from cerebro_texto import termos  # import tardio: o Cérebro não carrega no import do projeto

    return {t for t in termos(texto or "") if not t.isdigit() or len(t) > 2}


def parecidas(a: str, b: str) -> bool:
    ta, tb = _termos(a), _termos(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= PARECIDA


def _campo(texto: str, nome: str) -> str:
    achado = re.search(rf'"{nome}"\s*:\s*"((?:[^"\\]|\\.)*)"', texto or "")
    if not achado:
        return ""
    try:
        return json.loads(f'"{achado.group(1)}"').strip()
    except ValueError:
        return achado.group(1).strip()


def duvida_de(resposta: str) -> str:
    duvida = _campo(resposta, "duvida")
    return "" if duvida.lower().strip(" .") in ("", "nenhuma", "nenhum", "não", "nao", "-", "n/a") else duvida


def _opcoes(resposta: str) -> list[str]:
    achado = re.search(r'"opcoes"\s*:\s*(\[.*?\])', resposta or "", re.S)
    try:
        lista = json.loads(achado.group(1)) if achado else []
    except ValueError:
        return []
    limpas = [str(o).strip()[:120] for o in lista if isinstance(o, (str, int)) and str(o).strip()]
    return [o for o in dict.fromkeys(limpas) if o.lower() != ESCOLHA_POR_MIM.lower()][:MAX_OPCOES]


def guardar(pasta: Path, resposta: str, duvida: str) -> dict:
    """pergunta.json do projeto: a pergunta, as opções e se o agente pode decidir (a resposta chega no próximo)."""
    pode = not re.search(r'"pode_decidir"\s*:\s*false', resposta or "", re.I) and not NAO_DELEGAVEIS.search(duvida)
    dados = {"pergunta": duvida, "opcoes": _opcoes(resposta), "pode_decidir": pode}
    (pasta / "pergunta.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return dados


def formulario(dados: dict) -> str:
    """Bloco <<FORMULARIO>> que o chat já transforma em pop-up: opções + "Escolha por mim" + resposta livre."""
    opcoes = list(dados.get("opcoes") or []) + ([ESCOLHA_POR_MIM] if dados.get("pode_decidir") else [])
    rotulo = dados["pergunta"] + ("" if dados.get("pode_decidir") else
                                  " (só a equipe sabe isso: o Gestor não escolhe sozinho)")
    campos = ([{"nome": CAMPO, "rotulo": rotulo, "tipo": "opcoes", "opcoes": opcoes}] if opcoes else []) + [
        {"nome": OUTRA, "rotulo": "Outra resposta (opcional)" if opcoes else rotulo,
         "tipo": "texto_longo" if not opcoes else "texto", "obrigatorio": not opcoes}]
    corpo = {"titulo": TITULO, "botao": "Responder ao Gestor", "campos": campos}
    return f"<<FORMULARIO>>{json.dumps(corpo, ensure_ascii=False)}<<FIM DO FORMULARIO>>"


def texto_da_pergunta(pasta: Path, entendimento: str, duvida: str) -> str:
    """final.md da dúvida: entendimento, formulário e a linha PERGUNTA no fim (a espera do Max lê essa linha)."""
    arquivo = pasta / "pergunta.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None
    nota = "" if not dados or dados.get("pode_decidir") else (
        "Isso só a equipe sabe: veja no site ou pergunte ao Thomas. Sem a resposta, o dado fica PENDENTE.\n\n")
    return ((f"{entendimento}\n\n" if entendimento else "") + nota + (f"{formulario(dados)}\n\n" if dados else "")
            + f"PERGUNTA: {duvida}")


def resposta_limpa(pedido: str) -> str:
    """O que a pessoa respondeu: os valores do formulário ("- rótulo: valor") ou o texto, sem o prefixo do sistema."""
    texto = PEDIDO_FEITO.sub("", pedido or "").split("\n\n---\n")[0].strip()
    if texto.startswith("Respostas"):
        texto = "; ".join(v.strip() for v in LINHA_FORM.findall(texto)) or texto
    return texto[:400]


def _e_resposta(pedido: str) -> bool:
    import espera  # import tardio: a espera abre o banco das tarefas

    texto = PEDIDO_FEITO.sub("", pedido or "").strip()
    return (texto.startswith("Respostas") or e_delegacao(texto)
            or (len(texto) <= 300 and not espera.PEDIDO_NOVO.search(texto)))


def _anterior(tarefa_id: int):
    """A tarefa anterior do mesmo chat (pessoa, agente e empresa), se for recente; None se não houver."""
    import tarefas

    linha = tarefas.obter(tarefa_id)
    if not linha:
        return None
    return tarefas._db().execute(
        "SELECT id FROM tarefas WHERE usuario = ? AND agente = ? AND empresa IS ? AND id < ? AND criada_em >= ? "
        "ORDER BY id DESC LIMIT 1",
        (linha["usuario"], linha["agente"], linha["empresa"], tarefa_id, tarefas._agora(-JANELA))).fetchone()


def _ler(arquivo: Path):
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None
    except ValueError:
        return None


def decisoes(pasta: Path, pedido: str) -> list[dict]:
    """Decisões do projeto (decisoes.json): as da conversa anterior + a resposta à pergunta que ela deixou. Cada uma
    tem pergunta, opções, resposta, se foi delegada e, depois, a escolha feita."""
    arquivo = pasta / "decisoes.json"
    if (gravadas := _ler(arquivo)) is not None:
        return gravadas
    lista = []
    if pasta.name.isdigit() and (anterior := _anterior(int(pasta.name))):
        antes = pasta.parent / str(anterior["id"])
        pergunta = _ler(antes / "pergunta.json")
        if pergunta and _e_resposta(pedido):
            lista = list(_ler(antes / "decisoes.json") or [])
            delegada = e_delegacao(pedido)
            lista.append({**pergunta, "resposta": resposta_limpa(pedido),
                          "delegada": bool(delegada and pergunta.get("pode_decidir")),
                          "delegou_fato": bool(delegada and not pergunta.get("pode_decidir"))})
    if lista:
        arquivo.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    return lista


def _como_seguir(d: dict) -> str:
    if d.get("escolha"):
        return f"DECIDIDO: {d['escolha']} (o usuário delegou e esta é a escolha final)"
    if d.get("delegada"):
        opcoes = f" (as opções que você ofereceu: {', '.join(d['opcoes'])})" if d.get("opcoes") else ""
        return ("o usuário DELEGOU a escolha: decida você por um critério escrito, diga no entendimento \"Escolhi ... "
                f"porque ...\" e siga com as etapas{opcoes}")
    if d.get("delegou_fato"):
        return ("o usuário pediu para você escolher, mas é um fato que só a equipe sabe: siga com as etapas e deixe "
                "esse dado marcado como PENDENTE no texto (nunca invente)")
    return f"resposta do usuário: {d.get('resposta') or '-'} (use esta resposta)"


def bloco(lista: list[dict]) -> str:
    """Trecho do pedido do plano com as decisões já tomadas no projeto ("" se não houver)."""
    if not lista:
        return ""
    return ("DECISÕES JÁ TOMADAS NESTE PROJETO (não pergunte de novo nada disto):\n"
            + "\n".join(f"- Pergunta: {d['pergunta']} | {_como_seguir(d)}" for d in lista) + "\n\n")


def no_plano(pasta: Path) -> str:
    """Decisões para o fim do plano.md (a escolha gravada no plano, como pede a gestor-02); "" se não houver."""
    lista = _ler(pasta / "decisoes.json") or []
    return "".join(f"\n\n- Decisão: {d['pergunta']} -> {d.get('escolha') or _como_seguir(d)}" for d in lista)


def pedir_plano(pasta: Path, executar, descricao: str) -> str:
    """Pede o plano ao Gestor (`executar` do projeto) já com a trava contra pergunta repetida."""
    esperado = "JSON com o entendimento, o título e as etapas."
    resposta = executar("gestor", descricao, esperado, "gestor")
    return sem_repeticao(pasta, resposta, lambda extra: executar("gestor", f"{descricao}\n\n{extra}", esperado,
                                                                 "gestor"))


def _sem_duvida(resposta: str) -> str:
    return re.sub(r'("duvida"\s*:\s*)"(?:[^"\\]|\\.)*"', r'\1""', resposta, count=1)


def sem_repeticao(pasta: Path, resposta: str, refazer) -> str:
    """Trava contra pergunta repetida no mesmo projeto. `refazer(extra)` pede o plano de novo com uma instrução a
    mais. Pergunta nova (sem parecida já respondida) passa como está e vira formulário."""
    duvida = duvida_de(resposta)
    lista = _ler(pasta / "decisoes.json") or []
    repetida = next((d for d in lista if parecidas(duvida, d["pergunta"])), None) if duvida else None
    if not repetida:
        return resposta
    import tarefas

    if pasta.name.isdigit():  # o painel mostra quais modelos caem em laço (despachante-19)
        tarefas.registrar_evento(int(pasta.name), "laco_pergunta", "gestor", detalhe=duvida[:200])
    nova = refazer(f"ATENÇÃO: você ia perguntar de novo \"{duvida}\", que já foi tratada neste projeto: "
                   f"{_como_seguir(repetida)}. NÃO pergunte isso: deixe \"duvida\" vazio e preencha as etapas.")
    if not (ainda := duvida_de(nova)) or not parecidas(ainda, repetida["pergunta"]):
        return nova
    if not (repetida.get("delegada") or repetida.get("delegou_fato")):
        return nova  # respondeu algo que o modelo não entendeu: a pergunta volta em formulário, com opções
    if repetida.get("delegada"):  # o sistema decide: a primeira opção que o próprio Gestor ofereceu
        repetida["escolha"] = (repetida.get("opcoes") or ["a opção que melhor serve ao pedido, explicada"])[0]
        (pasta / "decisoes.json").write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
        nova = refazer(f"DECISÃO FINAL (já tomada, não pergunte): {repetida['pergunta']} -> {repetida['escolha']}. "
                       "Diga no entendimento \"Escolhi ... porque ...\" e preencha as etapas.")
    return _sem_duvida(nova)
