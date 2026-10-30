"""Triagem: porta de entrada única (Thomas, 30/10/2026). Barra de espaço duas vezes dentro de um andar abre a caixa;
o usuário escreve o pedido e a triagem indica o agente certo, na hora e sem gastar IA.

Não muda nada do que já existe: o pedido é enviado ao chat do agente escolhido, como se o usuário tivesse escrito
lá (o Gestor continua recebendo as peças completas pelo encaminhamento de sempre).

Como decide:
1. Regras de especialidade (as mesmas do encaminhamento ao Gestor, mais as dos outros andares).
2. Um classificador que aprende com o uso (TF-IDF + regressão logística, no PC, custo zero): os pedidos já feitos
   a cada agente e, com peso maior, as escolhas feitas na própria triagem (quando o usuário troca o agente sugerido,
   a triagem aprende). Entra quando há exemplos suficientes.
3. Peça completa (post, carrossel, reels...) que nenhum especialista resolve sozinho vai ao Gestor.
"""

import logging
import re
import threading
import time
import unicodedata

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import acesso
import encaminhamento
import tarefas
from auth import validar_token
from estado import ANDARES

log = logging.getLogger(__name__)
rotas = APIRouter(prefix="/api/triagem")

# Especialidades fora do Marketing e reforços das do Marketing (as do Marketing vêm de encaminhamento.ESCOPO).
EXTRA = {
    "gestor": r"projetos?|campanha completa|coorden\w+|v[aá]rias pe[cç]as|equipe toda",
    "designer": r"paleta|tipografia|identidade visual|dire[cç][aã]o de arte|conceito visual",
    "criador_imagens": r"arte final|png|capas?|thumbnails?|banners?|montar? (a |uma )?(arte|imagem)",
    "moviemaker": r"roteiros?|storyboard|capta[cç][aã]o|plano de grava[cç][aã]o",
    "editor_video": r"v[ií]deo final|mont\w+ (o |um )?v[ií]deo|mp4",
    "copywriter": r"escrev\w+|reda[cç][aã]o|tom de voz",
    "social_media": r"grade|agend\w+ (o |os )?posts?|frequ[eê]ncia de posts?",
    "gestor_trafego": r"meta ads|google ads|or[cç]amento de m[ií]dia|impulsion\w+|tr[aá]fego pago",
    "analista_metricas": r"desempenho|alcance|engajamento|insights|n[uú]meros do (instagram|perfil)",
    "prospectador": r"prospec\w+|leads?|empresas? para (prospectar|contatar)|clientes? corporativ\w+|crm|cliente ideal",
    "estrategista": r"estrat[eé]gi\w+|posicionamento|bcg|mckinsey|swot|for[cç]as de porter|5 for[cç]as|ansoff|"
                    r"concorr[eê]n\w+|precifica\w+|portf[oó]lio",
    "professor": r"briefings?|briefing (melhor|claro|bom)|como (eu )?(pe[cç]o|pedir|escrevo)|melhor\w* (o |meu )?pedido|"
                 r"me ensin\w+|me ajud\w+ a (escrever|montar|fazer) (um |o |meu )?(briefing|pedido)",
    "recepcionista": r"como (funciona|usa|usar) o escrit[oó]rio|onboarding|tour|qual agente|onde (fica|encontro)",
    "construtor": r"(cri\w+|novo|nova) agentes?",
}
SEM_TRIAGEM = {"cerebro", "despachante"}  # o Cérebro não tem chat; o Despachante é painel
MINIMO_EXEMPLOS = 30
RETREINO_S = 600

_ESQUEMA = ("CREATE TABLE IF NOT EXISTS triagens (id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, "
            "usuario TEXT NOT NULL, texto TEXT NOT NULL, sugerido TEXT NOT NULL, motivo TEXT, escolhido TEXT)")
_pronto = False
_modelo = None          # (vetorizador, classificador)
_treinado_em = 0.0
_amostras = 0
_trava = threading.Lock()


def _db():
    global _pronto
    db = tarefas._db()
    if not _pronto:
        db.execute(_ESQUEMA)
        _pronto = True
    return db


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")


def _candidatos(usuario: dict) -> dict[str, tuple[str, object]]:
    """agente_id -> (andar, agente) que este usuário pode usar pelo chat."""
    return {a.id: (andar, a) for andar, agentes in ANDARES.items() for a in agentes.values()
            if a.tipo == "ia" and a.id not in SEM_TRIAGEM and acesso.pode_usar(usuario, andar, a.id)}


def _limpar_pedido(texto: str) -> str:
    texto = encaminhamento.pedido_original(texto)
    texto = re.sub(r"^\[[^\]]{0,80}\]\s*", "", texto)          # "[Pedido feito ao Copywriter] ..."
    texto = re.sub(r"^\s*(planejamento|pe[cç]a final)\s*:\s*", "", texto, flags=re.IGNORECASE)
    return texto.strip()[:1500]


def _exemplos() -> tuple[list[str], list[str], list[float]]:
    """Pedidos já feitos (o agente que atendeu) e as escolhas da triagem (peso 3: correção direta)."""
    textos, rotulos, pesos = [], [], []
    for l in tarefas._db().execute(
            "SELECT texto, agente FROM tarefas WHERE status = 'concluida' AND texto NOT LIKE 'Produza a peça%' "
            "AND texto NOT LIKE 'Respostas%' AND texto NOT LIKE '[Copiado%' AND agente NOT IN ('cerebro')"):
        if (t := _limpar_pedido(l["texto"])):
            textos.append(t), rotulos.append(l["agente"]), pesos.append(1.0)
    for l in _db().execute("SELECT texto, escolhido FROM triagens WHERE escolhido IS NOT NULL"):
        textos.append(l["texto"]), rotulos.append(l["escolhido"]), pesos.append(3.0)
    return textos, rotulos, pesos


def _treinar_se_preciso() -> None:
    global _modelo, _treinado_em, _amostras
    if time.time() - _treinado_em < RETREINO_S or not _trava.acquire(blocking=False):
        return
    try:
        _treinado_em = time.time()
        textos, rotulos, pesos = _exemplos()
        if len(textos) < MINIMO_EXEMPLOS or len(set(rotulos)) < 2:
            _modelo, _amostras = None, len(textos)
            return
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        vetorizador = TfidfVectorizer(preprocessor=_normal, ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        matriz = vetorizador.fit_transform(textos)
        classificador = LogisticRegression(max_iter=2000, class_weight="balanced")
        classificador.fit(matriz, rotulos, sample_weight=pesos)
        _modelo, _amostras = (vetorizador, classificador), len(textos)
    except Exception:
        log.exception("Triagem: falha ao treinar o classificador; seguindo só com as regras.")
    finally:
        _trava.release()


def _pontos_regras(texto: str, candidatos) -> dict[str, list[str]]:
    """agente -> termos do pedido que batem com a especialidade dele."""
    achados: dict[str, list[str]] = {}
    for agente_id in candidatos:
        padroes = [p for p in (encaminhamento.ESCOPO.get(agente_id), EXTRA.get(agente_id)) if p]
        termos = {m.group(0).lower() for p in padroes for m in re.finditer(rf"\b({p})\b", texto, re.IGNORECASE)}
        if termos:
            achados[agente_id] = sorted(termos)
    return achados


def sugerir(usuario: dict, texto: str) -> dict:
    candidatos = _candidatos(usuario)
    if not candidatos:
        raise PermissionError("Você ainda não tem agentes liberados.")
    _treinar_se_preciso()
    regras = _pontos_regras(texto, candidatos)
    notas = {a: 0.6 * min(len(t), 3) / 3 for a, t in regras.items()}
    aprendido = {}
    if _modelo:
        vetorizador, classificador = _modelo
        for agente_id, prob in zip(classificador.classes_, classificador.predict_proba(vetorizador.transform([texto]))[0]):
            if agente_id in candidatos:
                aprendido[agente_id] = float(prob)
                notas[agente_id] = notas.get(agente_id, 0) + 0.4 * float(prob)
    ordem = sorted(notas, key=notas.get, reverse=True)
    escolhido = ordem[0] if ordem and notas[ordem[0]] > 0.15 else None

    def motivo_de(agente_id: str) -> str:
        partes = []
        if regras.get(agente_id):
            partes.append("o pedido fala em " + ", ".join(f"“{t}”" for t in regras[agente_id][:3]))
        if aprendido.get(agente_id, 0) >= 0.3:
            partes.append(f"pedidos parecidos costumam ir para ele ({aprendido[agente_id]:.0%})")
        return " e ".join(partes)

    gestor_ok = encaminhamento.GESTOR in candidatos
    peca = encaminhamento.PECAS.search(texto)
    if gestor_ok and peca and not encaminhamento.e_pergunta(texto) and (
            escolhido is None or (candidatos[escolhido][0] == encaminhamento.ANDAR
                                  and encaminhamento.para_o_gestor(encaminhamento.ANDAR, escolhido, texto))):
        motivo = (f"é uma peça completa (“{peca.group(0)}”): precisa de texto, arte e imagem, então o Gestor "
                  "monta o plano e aciona a equipe")
        escolhido, ordem = encaminhamento.GESTOR, [encaminhamento.GESTOR, *[a for a in ordem if a != encaminhamento.GESTOR]]
    elif escolhido:
        motivo = motivo_de(escolhido)
    else:  # nada reconhecido: o Professor ajuda a transformar o pedido em briefing
        escolhido = "professor" if "professor" in candidatos else next(iter(candidatos))
        motivo = "não reconheci a especialidade; ele ajuda a transformar o pedido num briefing claro"
        ordem = [escolhido, *[a for a in ordem if a != escolhido]]

    def item(agente_id: str) -> dict:
        andar, agente = candidatos[agente_id]
        return {"andar": andar, "agente": agente_id, "nome": agente.nome, "funcao": agente.funcao}

    with _db() as db:
        triagem_id = db.execute("INSERT INTO triagens (em, usuario, texto, sugerido, motivo) VALUES (?, ?, ?, ?, ?)",
                                (tarefas._agora(), usuario["sub"], texto[:1500], escolhido, motivo)).lastrowid
    return {"id": triagem_id, "sugestao": {**item(escolhido), "motivo": motivo},
            "alternativas": [{**item(a), "motivo": motivo_de(a)} for a in ordem[1:4] if a != escolhido],
            "todos": sorted((item(a) for a in candidatos), key=lambda x: (x["andar"], x["nome"])),
            "aprendizado": {"ativo": _modelo is not None, "exemplos": _amostras, "minimo": MINIMO_EXEMPLOS}}


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


class Pedido(BaseModel):
    texto: str = Field(min_length=3, max_length=30000)


class Decisao(BaseModel):
    agente: str = Field(min_length=2, max_length=60)


@rotas.post("")
def triar(pedido: Pedido, authorization: str = Header("")):
    try:
        return sugerir(_usuario(authorization), pedido.texto.strip())
    except PermissionError as erro:
        raise HTTPException(status_code=403, detail=str(erro)) from erro


@rotas.post("/{triagem_id}/decisao")
def decidir(triagem_id: int, decisao: Decisao, authorization: str = Header("")):
    """Para onde o pedido foi de fato (a sugestão ou outro agente): vira exemplo de treino da triagem."""
    usuario = _usuario(authorization)
    if decisao.agente not in _candidatos(usuario):
        raise HTTPException(status_code=403, detail="Agente não liberado para você.")
    with _db() as db:
        mudou = db.execute("UPDATE triagens SET escolhido = ? WHERE id = ? AND usuario = ?",
                           (decisao.agente, triagem_id, usuario["sub"])).rowcount
    if not mudou:
        raise HTTPException(status_code=404, detail="Triagem não encontrada.")
    return {"ok": True}
