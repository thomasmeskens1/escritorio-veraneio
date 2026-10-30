"""Projetos do Gestor em livro-razão (.md): plano, etapas e passagem salvos em disco.

Cada etapa roda separada e é gravada assim que termina. Se o modelo trocar no meio do caminho,
o próximo lê o plano e a passagem e continua da primeira etapa pendente: nada se perde nem é refeito.
"""

import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import config
import saude
from agents.perfis import ESTILO_CHAT
from estado import ANDARES

PASTA_PROJETOS = config.DADOS_DIR / "projetos"
MAX_ETAPAS = 8  # micro-tarefas: cada especialista com uma entrega focada
TRECHO_ETAPA = 1500   # caracteres de cada etapa anterior enviados à próxima
TRECHO_FINAL = 2500   # caracteres de cada etapa enviados à consolidação
PALAVRAS_ETAPA = 400  # limite pedido a cada etapa (tempo e tokens)
PALAVRAS_FINAL = 800
MAX_PARALELAS = 4      # etapas da mesma fase rodando ao mesmo tempo (limite dos modelos gratuitos)


# "Me dá 3 ideias de post", "sugestões de pauta": o usuário quer um plano em texto, não a peça pronta.
# Exige a FORMA de um pedido de ideias, não só a palavra: "Crie um post sobre as opções de café da manhã" é peça.
IDEACAO = re.compile(
    r"\b(me\s+d[aáê]|d[eê]-?me|quero|queria|preciso\s+de|traga|liste|sugira|sugerir|pense\s+em|levante|gere)\b"
    r"[^.?!\n]{0,40}?\b(ideias?|sugest[aã]o|sugest[oõ]es|conceitos?|op[cç][oõ]es|propostas?|pautas?)\b"
    r"|\bbrainstorm|\bplano\s+de\s+a[cç][aã]o\b|^\s*(ideias?|sugest[oõ]es)\b", re.IGNORECASE)


def e_ideacao(pedido: str, contexto: str = "") -> bool:
    """Pedido de ideias/plano (sem produção de arquivos). Item do Monday com formato definido é sempre peça.
    Só o texto do usuário (1º parágrafo, sem a descrição dos anexos que vem depois) decide."""
    if "FORMATO DA PEÇA" in f"{pedido}{contexto}":
        return False
    texto = re.sub(r"^\[Pedido feito a[o]? [^\]]+\]\s*", "", pedido).split("\n\n")[0]
    if (escolha := re.match(r"^\s*(planejamento|pe[cç]a\s+final)\s*:", texto, re.IGNORECASE)):
        return escolha.group(1).lower().startswith("plan")  # resposta aos botões "Só o planejamento" / "Peça final"
    return bool(IDEACAO.search(texto[:400]))


class Cancelado(Exception):
    """A tentativa estourou o tempo; o próximo modelo retoma do livro-razão."""


# Executa um agente: (agente_id, descrição da tarefa, saída esperada, papel "gestor"|"equipe") -> texto
Executar = Callable[[str, str, str, str], str]


def _gravar(arquivo: Path, texto: str) -> None:
    """Gravação atômica; se outra tentativa já gravou, mantém a primeira."""
    if arquivo.exists():
        return
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(texto, encoding="utf-8")
    temporario.replace(arquivo)


def _chave(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", sem_acento.lower())


def equipe() -> dict[str, str]:
    """Especialistas do andar do Gestor (id -> nome), incluindo os criados pelo Construtor."""
    return {i: a.nome for i, a in ANDARES["marketing"].items() if a.tipo == "ia" and i != "gestor"}


def _nome(agente_id: str) -> str:
    return equipe().get(agente_id, agente_id)


def _extrair_plano(texto: str) -> tuple[list[dict], str]:
    """(etapas, título curto do projeto). Etapas: agente, instrução e fase (mesma fase = rodam juntas)."""
    bloco = re.search(r"\[.*\]", texto, re.DOTALL)
    if not bloco:
        raise saude.FalhaDoModelo("O Gestor não devolveu um plano em JSON.")
    # Aceita o id ("gestor_trafego") ou o nome ("Gestor de Tráfego"), sem diferenciar maiúsculas/acentos.
    time = equipe()
    ids_por_chave = {**{_chave(i): i for i in time}, **{_chave(n): i for i, n in time.items()}}
    plano = []
    try:
        passos = json.loads(bloco.group(0))
    except ValueError as erro:  # JSON quebrado é resposta ruim do modelo: o próximo modelo tenta
        raise saude.FalhaDoModelo(f"O Gestor devolveu um plano com JSON inválido ({erro}).") from erro
    for passo in passos:
        agente = ids_por_chave.get(_chave(passo.get("agente", ""))) if isinstance(passo, dict) else None
        if agente:
            fase = passo.get("fase")
            plano.append({"agente": agente, "instrucao": str(passo.get("instrucao", "")),
                          "fase": int(fase) if str(fase).isdigit() and int(fase) > 0 else len(plano) + 1})
    if not plano:
        raise saude.FalhaDoModelo("Plano sem etapas válidas.")
    titulo = re.search(r'"titulo"\s*:\s*"([^"]{3,80})"', texto)
    return plano[:MAX_ETAPAS], (titulo.group(1).strip() if titulo else "")


# Pedido longo (o Gestor aceita até 30 mil caracteres): antes do plano, o Gestor transforma o pedido numa FICHA DE
# REQUISITOS fiel (R1, R2... verificáveis, com os dados copiados literalmente). A ficha guia as etapas no lugar do
# texto gigante (cada especialista não se perde nele), ancora o objetivo no fim de cada etapa e vira o checklist da
# consolidação. Pedido do Thomas (28/10/2026): o Gestor não pode se perder num pedido desse tamanho.
LIMITE_PEDIDO_CURTO = 6000
CHECAGEM = re.compile(r"<<CHECAGEM>>(.*?)<<FIM>>", re.S)


def _ficha(pasta: Path, pedido: str, contexto: str, executar: "Executar") -> str:
    """Ficha de requisitos do pedido longo ("" se o pedido é curto ou a ficha não saiu)."""
    if len(pedido) <= LIMITE_PEDIDO_CURTO:
        return ""
    arquivo = pasta / "requisitos.md"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8")
    descricao = (
        f"{contexto}\n\nPedido do usuário ({len(pedido)} caracteres):\n{pedido}\n\n"
        "O pedido acima é longo. Antes de planejar, transforme-o numa FICHA DE REQUISITOS fiel, que vai guiar toda a "
        "equipe no lugar do texto original. Não resuma dados: copie literalmente números, nomes, datas, cores, "
        "medidas, textos obrigatórios (entre aspas) e a estrutura pedida, na ordem. Não acrescente nada que não "
        "esteja no pedido. Responda SOMENTE neste formato:\n"
        "OBJETIVO: <uma frase>\n"
        "ENTREGÁVEIS: <formato, quantidade e medidas de cada entrega>\n"
        "REQUISITOS:\nR1. <um requisito verificável>\nR2. ...\n"
        "DADOS FORNECIDOS: <fatos que o pedido dá (local, datas, serviços...)>\n"
        "TOM E RESTRIÇÕES: <tom, o que evitar>\n"
        "A CONFIRMAR: <dados que o próprio pedido manda confirmar, conflitos com as regras de ouro, ou 'nada'>")
    for _ in range(2):  # uma nova tentativa se o modelo fugir do formato
        ficha = executar("gestor", descricao, "Ficha de requisitos no formato pedido.", "gestor").strip()
        if "OBJETIVO:" in ficha and re.search(r"^\s*R1[.)]", ficha, re.M):
            _gravar(arquivo, ficha)
            return ficha
    return ""


def _objetivo(ficha: str) -> str:
    return (m.group(1).strip() if (m := re.search(r"OBJETIVO:\s*(.+)", ficha)) else "")


def _entregaveis(ficha: str) -> str:
    return (m.group(1).strip() if (m := re.search(r"ENTREGÁVEIS:\s*(.+)", ficha)) else "")


def entregaveis_do_projeto(tarefa_id: int) -> str:
    """Entregáveis da ficha do pedido longo (decide o produtor sem varrer o texto gigante); "" se não houver."""
    arquivo = PASTA_PROJETOS / str(tarefa_id) / "requisitos.md"
    return _entregaveis(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else ""


def titulo_do_projeto(tarefa_id: int) -> str:
    """Título curto que o Gestor deu ao projeto (nome da pasta de entrega); "" se não houver."""
    arquivo = PASTA_PROJETOS / str(tarefa_id) / "titulo.txt"
    return arquivo.read_text(encoding="utf-8").strip() if arquivo.exists() else ""


# Interpretar a conversa antes de planejar (Thomas, 30/10/2026): "agora monte o carrossel... essa casa", logo depois
# de pedir 6 Lodges, virou um carrossel do Lodge 35, tirado de uma troca antiga (#232). Em vez de regra fixa, o Gestor
# escreve primeiro o ENTENDIMENTO (a que trabalho o pedido se refere e de qual troca isso vem); as etapas e a
# consolidação recebem esse entendimento. Se não der para saber, ele pergunta (DÚVIDA) em vez de escolher.
INTERPRETAR = (
    "ANTES de dividir o trabalho, interprete o pedido à luz da conversa, como uma pessoa da equipe faria: a que "
    "trabalho, peça, imóveis e dados ele se refere, e de qual troca da conversa isso vem. Pedido curto ou com "
    "referência sem nome (\"agora monte\", \"essa casa\", \"o carrossel\") continua a troca MAIS RECENTE; não puxe "
    "imóvel, data ou assunto de troca antiga que o usuário não retomou, nem de ficha que só aparece no contexto. "
    "Escreva isso no campo \"entendimento\" (2 a 4 frases, com os imóveis e dados concretos). Se a conversa não deixa "
    "claro a que o pedido se refere e um palpite errado estragaria a entrega, NÃO escolha: preencha \"duvida\" com "
    "uma pergunta objetiva e deixe \"etapas\" vazio. ")


def _campo(texto: str, nome: str) -> str:
    """Campo de texto do JSON do plano (lido à parte: o JSON às vezes vem com sobras em volta)."""
    achado = re.search(rf'"{nome}"\s*:\s*"((?:[^"\\]|\\.)*)"', texto)
    if not achado:
        return ""
    try:
        return json.loads(f'"{achado.group(1)}"').strip()
    except ValueError:
        return achado.group(1).strip()


def _lido(pasta: Path, nome: str) -> str:
    arquivo = pasta / nome
    return arquivo.read_text(encoding="utf-8").strip() if arquivo.exists() else ""


def _plano(pasta: Path, pedido: str, contexto: str, executar: Executar, ficha: str = "") -> list[dict]:
    from estado import AGENTES_PRODUCAO

    arquivo = pasta / "plano.json"
    if not arquivo.exists():
        ideacao = e_ideacao(pedido, contexto)
        if ideacao:
            _gravar(pasta / "ideacao.txt", "Pedido de ideias/plano: só texto, sem produção no Max.")
        time = {i: n for i, n in equipe().items() if not (ideacao and i in AGENTES_PRODUCAO)}
        equipe_txt = ", ".join(f"{i} ({nome})" for i, nome in time.items())
        modo = ("ATENÇÃO: o usuário pediu IDEIAS/PLANO, não a peça pronta. Acione só quem pensa e escreve "
                "(ex.: Social Media e Copywriter); ninguém produz arte, imagem ou vídeo. " if ideacao else "")
        guia = (f"FICHA DE REQUISITOS (feita por você a partir do pedido; é a referência da equipe):\n{ficha}\n\n"
                "Cada requisito R# precisa de uma etapa responsável: cite os R# na instrução de cada etapa e copie "
                "nela os dados e textos obrigatórios que o especialista vai precisar (ele recebe a ficha, não o "
                "pedido original). " if ficha else "")
        descricao = (
            f"{contexto}\n\nPedido do usuário: {pedido}\n\n{guia}"
            f"{INTERPRETAR}{modo}Depois, divida o trabalho em até {MAX_ETAPAS} etapas para a sua equipe: {equipe_txt}. "
            "Prefira micro-tarefas: cada etapa é uma entrega focada de um único especialista "
            "(ex.: post de Lodge = Copywriter escreve o texto da arte e a legenda com os dados do Cérebro, "
            "Criador de Imagens escolhe as fotos reais do acervo, Designer define o layout e o editável; "
            "reels = Moviemaker faz o roteiro, Copywriter os textos de tela, Editor de Vídeo a montagem; "
            "stories = só textos de tela e roteiro visual, SEM legenda: ninguém escreve legenda para stories). "
            "Acione só quem for necessário. "
            "Organize as etapas em FASES para ganhar tempo: etapas que não dependem umas das outras ficam na "
            "mesma fase e rodam ao mesmo tempo (ex.: Copywriter e Criador de Imagens juntos na fase 1); quem "
            "precisa do resultado de outra etapa vai para uma fase seguinte (ex.: Designer na fase 2). Cada etapa "
            "recebe só os resultados das fases anteriores. "
            "Dê também um título curto ao projeto (até 6 palavras, sem data, ex.: \"Post Réveillon Lodge 1\"). "
            "As instruções das etapas seguem o entendimento (citem os imóveis e dados dele). "
            'Responda SOMENTE com um JSON: {"entendimento": "<o que o usuário quer agora>", "duvida": "", '
            '"titulo": "<título>", "etapas": [{"agente": "<id>", "instrucao": "<o que entregar>", "fase": <número>}]}.'
        )
        resposta = executar("gestor", descricao, "JSON com o entendimento, o título e as etapas.", "gestor")
        if (entendimento := _campo(resposta, "entendimento")):
            _gravar(pasta / "entendimento.txt", entendimento)
        duvida = _campo(resposta, "duvida")
        if duvida and duvida.lower().strip(" .") not in ("nenhuma", "nenhum", "não", "nao", "-", "n/a"):
            _gravar(pasta / "duvida.txt", duvida)
            _gravar(arquivo, "[]")
            return []
        plano, titulo = _extrair_plano(resposta)
        if ideacao:  # rede de segurança: nada de produção num pedido de ideias
            plano = [p for p in plano if p["agente"] not in AGENTES_PRODUCAO] or [
                {"agente": "social_media", "instrucao": pedido, "fase": 1}]
        if titulo:
            _gravar(pasta / "titulo.txt", titulo)
        _gravar(arquivo, json.dumps(plano, ensure_ascii=False, indent=2))
        linhas = [f"{n}. **{_nome(p['agente'])}** (fase {p['fase']}): {p['instrucao']}" for n, p in enumerate(plano, 1)]
        _gravar(pasta / "plano.md", f"# Plano\n\nPedido: {pedido}\n\nEntendimento: {entendimento or '-'}\n\n"
                + "\n".join(linhas) + "\n")
    return json.loads(arquivo.read_text(encoding="utf-8"))


def agentes_de_producao(tarefa_id: int) -> list[str]:
    """Agentes do plano que entregam arquivo (PNG/MP4) e, por isso, seguem para a produção no Max."""
    from estado import AGENTES_PRODUCAO

    pasta = PASTA_PROJETOS / str(tarefa_id)
    arquivo = pasta / "plano.json"
    if not arquivo.exists() or (pasta / "ideacao.txt").exists():
        return []
    ids = [p["agente"] for p in json.loads(arquivo.read_text(encoding="utf-8"))]
    return [i for i in dict.fromkeys(ids) if i in AGENTES_PRODUCAO]


def _arquivo_etapa(pasta: Path, numero: int, agente: str) -> Path:
    return pasta / "etapas" / f"{numero:02d}-{agente}.md"


def _passagem(pasta: Path, plano: list[dict]) -> str:
    """Resumo curto do andamento: o que já foi feito e o que falta."""
    linhas = []
    for n, passo in enumerate(plano, 1):
        arquivo = _arquivo_etapa(pasta, n, passo["agente"])
        if arquivo.exists():
            inicio = arquivo.read_text(encoding="utf-8")[:300].replace("\n", " ")
            linhas.append(f"- [x] {n}. {_nome(passo['agente'])}: {inicio}...")
        else:
            linhas.append(f"- [ ] {n}. {_nome(passo['agente'])}: {passo['instrucao']}")
    texto = "# Passagem\n\n" + "\n".join(linhas) + "\n"
    (pasta / "passagem.md").write_text(texto, encoding="utf-8")
    return texto


def _sem_aviso(tipo: str, agente: str, detalhe: str) -> None:
    pass


# Revisão de 30/10/2026 (item 1.9): o plano do #232 (Lodge 35) foi feito por um gratuito fraco que caiu; o Max
# assumiu e reaproveitou plano e etapas salvos sem reinterpretar o pedido. Plano de modelo fraco não é herdado.
MODELOS_FORTES = ("claude-code/", "anthropic/", "claude-")
REFEITOS_QUANDO_FORTE_ASSUME = ("plano.json", "plano.md", "entendimento.txt", "duvida.txt", "titulo.txt",
                                "requisitos.md", "final.md", "passagem.md", "plano_modelo.txt")


def _forte(modelo: str) -> bool:
    return bool(modelo) and modelo.startswith(MODELOS_FORTES)


def _descartar_plano_fraco(pasta: Path, modelo: str) -> bool:
    """Modelo forte assumindo um projeto planejado por um fraco: apaga plano, entendimento e etapas (refaz do zero)."""
    if not _forte(modelo) or not (pasta / "plano.json").exists() or _forte(_lido(pasta, "plano_modelo.txt")):
        return False
    for nome in REFEITOS_QUANDO_FORTE_ASSUME:
        (pasta / nome).unlink(missing_ok=True)
    for etapa in (pasta / "etapas").glob("*"):
        etapa.unlink(missing_ok=True)
    return True


def executar_projeto(tarefa_id: int, pedido: str, contexto: str, executar: Executar,
                     cancelar: threading.Event, avisar: Callable[[str, str, str], None] = _sem_aviso,
                     modelo: str = "") -> str:
    """`avisar(tipo, agente, detalhe)` recebe etapa_iniciada/etapa_salva (registro e animação do setor). `modelo`: quem
    coordena agora (o plano feito por um modelo fraco é refeito quando um forte assume)."""
    pasta = PASTA_PROJETOS / str(tarefa_id)
    (pasta / "etapas").mkdir(parents=True, exist_ok=True)
    if _descartar_plano_fraco(pasta, modelo):
        avisar("etapa_iniciada", "gestor", f"Plano refeito: {modelo} assumiu o projeto de um modelo gratuito")
    ficha = _ficha(pasta, pedido, contexto, executar)
    novo = not (pasta / "plano.json").exists()
    plano = _plano(pasta, pedido, contexto, executar, ficha)
    if novo and modelo:
        _gravar(pasta / "plano_modelo.txt", modelo)
    entendimento = _lido(pasta, "entendimento.txt")
    if (duvida := _lido(pasta, "duvida.txt")):  # não deu para saber a que o pedido se refere: pergunta antes
        final = pasta / "final.md"
        if not final.exists():
            _gravar(final, (f"{entendimento}\n\n" if entendimento else "") + f"PERGUNTA: {duvida}")
        return final.read_text(encoding="utf-8")
    fase = lambda n, p: p.get("fase", n)  # plano antigo (sem fases): uma etapa por vez
    # Pedido longo: a etapa recebe a ficha (não o texto gigante) e termina com a âncora do objetivo.
    projeto_txt = (f"Projeto (ficha de requisitos de um pedido de {len(pedido)} caracteres; é a sua referência):\n"
                   f"{ficha}" if ficha else f"Projeto: {pedido}")
    if entendimento:
        projeto_txt += f"\n\nENTENDIMENTO DO GESTOR (o que o usuário quer agora, lido na conversa): {entendimento}"

    def rodar_etapa(n: int, passo: dict) -> None:
        if cancelar.is_set():
            raise Cancelado
        anteriores = "\n\n".join(
            f"## Etapa {i} ({_nome(p['agente'])})\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_ETAPA]}"
            for i, p in enumerate(plano, 1) if fase(i, p) < fase(n, passo)
        )
        ancora = (f"\n\nLEMBRETE: o objetivo do projeto é \"{_objetivo(ficha)}\". Faça só a sua etapa, cumpra os "
                  "requisitos R# citados nela com os dados literais da ficha e não mude o objetivo nem o formato."
                  if ficha else "")
        descricao = (
            f"{contexto}\n\n{projeto_txt}\n\n{_passagem(pasta, plano)}\n"
            f"Resultados das etapas anteriores:\n{anteriores or '(nenhuma)'}\n\n"
            f"Sua etapa ({n}): {passo['instrucao']}\n\n"
            f"Seja objetivo: até ~{PALAVRAS_ETAPA} palavras, só o essencial para as próximas etapas.{ancora}"
        )
        detalhe = f"Etapa {n}: {passo['instrucao'][:160]}"
        avisar("etapa_iniciada", passo["agente"], detalhe)
        try:
            _gravar(_arquivo_etapa(pasta, n, passo["agente"]),
                    executar(passo["agente"], descricao, "Entrega completa desta etapa.", "equipe"))
        finally:
            avisar("etapa_encerrada", passo["agente"], detalhe)
        avisar("etapa_salva", passo["agente"], detalhe)

    # Fase a fase; dentro da fase, as etapas rodam ao mesmo tempo (o que já foi feito numa tentativa anterior é pulado).
    for numero_fase in sorted({fase(n, p) for n, p in enumerate(plano, 1)}):
        pendentes = [(n, p) for n, p in enumerate(plano, 1)
                     if fase(n, p) == numero_fase and not _arquivo_etapa(pasta, n, p["agente"]).exists()]
        if pendentes:
            with ThreadPoolExecutor(min(len(pendentes), MAX_PARALELAS)) as pool:
                for futuro in [pool.submit(rodar_etapa, n, p) for n, p in pendentes]:
                    futuro.result()  # repassa erro ou Cancelado (as demais da fase terminam antes)
            _passagem(pasta, plano)

    final = pasta / "final.md"
    if not final.exists():
        if cancelar.is_set():
            raise Cancelado
        entregas = "\n\n".join(
            f"## {_nome(p['agente'])}\n{_arquivo_etapa(pasta, i, p['agente']).read_text(encoding='utf-8')[:TRECHO_FINAL]}"
            for i, p in enumerate(plano, 1)
        )
        lido = f"\n\nSeu entendimento do pedido (a entrega precisa bater com ele): {entendimento}" if entendimento else ""
        descricao = (f"{contexto}\n\nPedido do usuário: {pedido}{lido}\n\nEntregas da equipe:\n{entregas}\n\n"
                     f"Revise e consolide tudo numa entrega final coerente para o usuário (até ~{PALAVRAS_FINAL} palavras). "
                     "Entregue só o que ele pediu. NÃO inclua bastidores: observações internas, conferência de "
                     "dados, especificações técnicas (medidas, zonas mortas, fontes, cores), quem fez o quê nem "
                     "próximos passos de Drive, Monday ou produção. Se faltar uma decisão do usuário para "
                     "produzir, não assuma nada: termine com uma linha \"PERGUNTA: <pergunta objetiva>\" "
                     "(a produção espera a resposta). "
                     f"{ESTILO_CHAT}")
        if ficha:  # checklist: cada requisito do pedido longo conferido antes de entregar
            descricao += (f"\n\nFICHA DE REQUISITOS:\n{ficha}\n\nAntes de entregar, confira cada R# contra a "
                          "entrega. Depois do texto final, acrescente o bloco <<CHECAGEM>> com uma linha por "
                          "requisito (\"R1: ok\" ou \"R1: faltou - motivo\") e feche com <<FIM>>.")
        texto = executar("gestor", descricao, "Entrega final consolidada e revisada.", "gestor")
        if ficha:
            texto = _aplicar_checagem(pasta, texto)
        _gravar(final, texto)
    return final.read_text(encoding="utf-8")


def _aplicar_checagem(pasta: Path, texto: str) -> str:
    """Tira o bloco de checagem da resposta (fica em checagem.md) e mostra ao usuário só o que faltou."""
    achado = CHECAGEM.search(texto)
    if not achado:
        return texto
    _gravar(pasta / "checagem.md", achado.group(1).strip())
    texto = (texto[:achado.start()] + texto[achado.end():]).strip()
    faltou = [linha.strip() for linha in achado.group(1).splitlines() if re.search(r"falt", linha, re.I)]
    if faltou:
        texto += "\n\nO que ainda falta do seu pedido:\n" + "\n".join(f"- {linha}" for linha in faltou)
    return texto
