"""Agentes criados pelo Construtor: validação, persistência (SQLite) e registro no escritório.

Ficha de contratação (levantamento de 31/10/2026, construtor-02 e decisão 16): o Construtor grava uma PROPOSTA, fora
do prédio e de `PERFIS`. Só quando a pessoa da Diretoria que pediu lê a persona e aprova ("Aprovar o agente proposto
<id>") ele ganha mesa: nasce "construindo", vira "disponivel" em segundos e volta nos reinícios (`carregar()`).
"""

import asyncio
import concurrent.futures
import json
import logging
import re
import unicodedata

from fastapi import APIRouter, Header, HTTPException
from pydantic import ValidationError

import acesso
import agentes_persona
import atividade
import config
import tarefas
from agents.perfis import PERFIS
from auth import carregar_usuarios, validar_token
from conexoes import gerenciador
from estado import ANDARES, Agente, Aparencia, Status, andar_do_agente

log = logging.getLogger(__name__)

# Andar -> setor -> mesas que cabem na área do setor (mesmos ids de frontend/js/cenario/setores.js).
# O frontend sempre mostra uma mesa vaga e acrescenta outra quando o setor lota (mesasComVaga), até
# este limite; passou disso, o layout do andar precisa de ajuste.
# Térreo e Cobertura (Cérebro e estagiários) não recebem agentes novos.
SETORES = {
    "porao": {"oficina": 4, "operacoes": 4},
    "marketing": {"gestao": 4, "criacao": 6, "conteudo": 6, "video": 6, "performance": 6},
    "comercial": {"hospedagem": 4, "corporativo": 4},
}
NOMES_ANDARES = {"porao": "Porão", "marketing": "Marketing", "comercial": "Comercial", "cobertura": "Cobertura"}
NOMES_SETORES = {"oficina": "Oficina", "operacoes": "Operações", "gestao": "Gestão", "criacao": "Criação",
                 "conteudo": "Conteúdo", "video": "Vídeo", "performance": "Performance", "hospedagem": "Hospedagem", "corporativo": "Corporativo",
                 "diretoria": "Diretoria"}

TONS_PELE = ["#ffdbac", "#f1c27d", "#e0ac69", "#c68642", "#a0522d", "#8d5524", "#6b4226", "#3b2219"]
ESTILOS_CABELO = ["curto", "longo", "coque", "careca", "cacheado", "moicano"]
ESTILOS_ROUPA = ["camiseta", "camisa", "blazer", "moletom", "macacao", "avental"]
ACESSORIOS = ["nenhum", "oculos", "fone", "bone", "capacete", "cracha", "gravata", "camera", "lapis"]

# Campo -> (mínimo, máximo) de caracteres. Persona com menos de 400 caracteres não cabe missão, regras, fluxo,
# entregáveis e com quem fala (construtor-04: o Vendedor de Pacotes nasceu com 141).
LIMITES = {"nome": (2, 40), "funcao": (3, 80), "descricao": (0, 300), "exemplo": (0, 200),
           "role": (2, 80), "goal": (10, 600), "backstory": (400, 2500)}
SEGUNDOS_CONSTRUINDO = 5
LIMITE_POR_DIA = 3     # construtor-27: um abuso (sessão roubada, instrução escondida) fica pequeno e visível
PROPOSTA, APROVADO, DESCARTADO = "proposta", "aprovado", "descartado"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS agentes_criados (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL, andar TEXT NOT NULL, setor TEXT NOT NULL, funcao TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '', exemplo TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL, goal TEXT NOT NULL, backstory TEXT NOT NULL,
    aparencia TEXT NOT NULL, criado_por TEXT NOT NULL, criado_em TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
"""
# Os já existentes estavam em serviço: entram como aprovados.
_COLUNAS_NOVAS = {"situacao": "TEXT NOT NULL DEFAULT 'aprovado'", "tarefa_id": "INTEGER",
                  "aprovado_por": "TEXT", "aprovado_em": "TEXT"}
_tabela_pronta = False
_pendentes: set[asyncio.Task] = set()  # referências às tarefas "construindo -> disponivel"
CRIADOS: set[str] = set()  # ids no prédio que vieram do Construtor (persona escrita por modelo: fora do Max)


class ErroValidacao(ValueError):
    """Especificação inválida (o Construtor pode corrigir e tentar de novo)."""


class SemPermissao(PermissionError):
    """Só a diretoria cria agentes."""


class LimiteAtingido(PermissionError):
    """Limite diário de criações (o Construtor não deve tentar de novo)."""


def _db():
    global _tabela_pronta
    db = tarefas._db()
    if not _tabela_pronta:
        db.executescript(_ESQUEMA)
        existentes = {c[1] for c in db.execute("PRAGMA table_info(agentes_criados)")}
        for coluna, tipo in _COLUNAS_NOVAS.items():
            if coluna not in existentes:
                db.execute(f"ALTER TABLE agentes_criados ADD COLUMN {coluna} {tipo}")
        _tabela_pronta = True
    return db


# --- Validação ----------------------------------------------------------------------------

def _snake(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento).strip("_")[:40].strip("_")


def _texto(spec: dict, campo: str, padrao: str = "") -> str:
    valor = spec.get(campo)
    valor = padrao if valor is None else str(valor)
    valor = " ".join(valor.split())
    minimo, maximo = LIMITES[campo]
    if len(valor) < minimo:
        raise ErroValidacao(f"'{campo}' precisa ter ao menos {minimo} caracteres.")
    return valor[:maximo]


def _hex(valor, campo: str) -> str:
    cor = str(valor or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", cor):
        cor = "#" + "".join(c * 2 for c in cor[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", cor):
        raise ErroValidacao(f"'{campo}' deve ser uma cor hex no formato #rrggbb (recebido: {valor!r}).")
    return cor


def _rgb(cor: str) -> tuple[int, int, int]:
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def tom_de_pele(cor: str) -> str:
    """Tom humano mais próximo da paleta (evita peles como laranja ou verde)."""
    r, g, b = _rgb(cor)
    return min(TONS_PELE, key=lambda t: sum((a - c) ** 2 for a, c in zip(_rgb(t), (r, g, b))))


def _opcao(valor, opcoes: list[str], campo: str) -> str:
    escolha = _snake(str(valor or ""))
    if escolha not in opcoes:
        raise ErroValidacao(f"'{campo}' deve ser um de: {', '.join(opcoes)} (recebido: {valor!r}).")
    return escolha


def _aparencia(bruta) -> Aparencia:
    if isinstance(bruta, str):
        try:
            bruta = json.loads(bruta)
        except ValueError:
            raise ErroValidacao("'aparencia' deve ser um objeto JSON.") from None
    if not isinstance(bruta, dict):
        raise ErroValidacao("'aparencia' deve ser um objeto com pele, cabelo, roupa, calca e acessorio.")
    cabelo, roupa = bruta.get("cabelo") or {}, bruta.get("roupa") or {}
    if not isinstance(cabelo, dict) or not isinstance(roupa, dict):
        raise ErroValidacao("'cabelo' e 'roupa' devem ser objetos com 'estilo' e 'cor'.")
    try:
        return Aparencia(
            pele=tom_de_pele(_hex(bruta.get("pele"), "pele")),
            cabelo={"estilo": _opcao(cabelo.get("estilo"), ESTILOS_CABELO, "cabelo.estilo"),
                    "cor": _hex(cabelo.get("cor"), "cabelo.cor")},
            roupa={"estilo": _opcao(roupa.get("estilo"), ESTILOS_ROUPA, "roupa.estilo"),
                   "cor": _hex(roupa.get("cor"), "roupa.cor")},
            calca=_hex(bruta.get("calca"), "calca"),
            acessorio=_opcao(bruta.get("acessorio") or "nenhum", ACESSORIOS, "acessorio"),
        )
    except ValidationError as erro:
        raise ErroValidacao(f"aparência inválida: {erro.errors()[0]['msg']}") from None


def _todos_agentes() -> list[Agente]:
    return [a for agentes in ANDARES.values() for a in agentes.values()]


def _exclusiva(aparencia: Aparencia) -> Aparencia:
    """Se for idêntica à de alguém, varia o cabelo e depois a roupa até ficar única."""
    existentes = [a.aparencia.model_dump() for a in _todos_agentes()]
    if aparencia.model_dump() not in existentes:
        return aparencia
    for cabelo in ESTILOS_CABELO:
        for roupa in ESTILOS_ROUPA:
            candidata = aparencia.model_copy(deep=True)
            candidata.cabelo.estilo, candidata.roupa.estilo = cabelo, roupa
            if candidata.model_dump() not in existentes:
                return candidata
    return aparencia


def _id_livre(agente_id: str, ajuste_de: str = "") -> bool:
    """Livre: ninguém no prédio com o id e nenhum cadastro ativo. A proposta da própria pessoa (`ajuste_de`) não
    ocupa o id: refazer a especificação dela é o "Pedir ajuste"."""
    if andar_do_agente(agente_id) or agente_id in PERFIS:
        return False
    linha = _db().execute("SELECT ativo, situacao, criado_por FROM agentes_criados WHERE id = ?", (agente_id,)).fetchone()
    if linha is None or not linha["ativo"]:  # id de agente desativado ou descartado pode ser reaproveitado
        return True
    return linha["situacao"] == PROPOSTA and bool(ajuste_de) and linha["criado_por"] == ajuste_de


def vagas(andar: str, setor: str) -> int:
    ocupadas = sum(1 for a in ANDARES.get(andar, {}).values() if a.setor == setor)
    return SETORES.get(andar, {}).get(setor, 0) - ocupadas


def setores_com_vagas() -> str:
    """Texto para o Construtor: setores válidos por andar e vagas livres."""
    return "; ".join(f"{andar}: " + ", ".join(f"{s} ({vagas(andar, s)} vaga(s))" for s in setores)
                     for andar, setores in SETORES.items())


def validar(spec: dict, ajuste_de: str = "") -> dict:
    """Normaliza a especificação; levanta ErroValidacao com a explicação do problema."""
    if not isinstance(spec, dict):
        raise ErroValidacao("a especificação deve ser um objeto.")
    nome = _texto(spec, "nome")
    andar = _snake(str(spec.get("andar") or ""))
    if andar not in SETORES:
        raise ErroValidacao(f"andar inválido {spec.get('andar')!r}; use um de: {', '.join(SETORES)} "
                            "(o térreo e a cobertura não recebem agentes novos).")
    setor = _snake(str(spec.get("setor") or ""))
    if setor not in SETORES[andar]:
        raise ErroValidacao(f"setor inválido {spec.get('setor')!r} para o andar {andar}; "
                            f"use um de: {', '.join(SETORES[andar])}.")
    if vagas(andar, setor) <= 0:
        raise ErroValidacao(f"o setor {setor} ({andar}) está lotado (o layout do andar precisa ser ampliado "
                            f"pelo dono). Setores: {setores_com_vagas()}.")
    agente_id = _snake(str(spec.get("id") or "")) or _snake(nome)
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", agente_id):
        raise ErroValidacao(f"id inválido {agente_id!r}: use snake_case começando por letra (2 a 40 caracteres).")
    if not _id_livre(agente_id, ajuste_de):
        raise ErroValidacao(f"já existe um agente com id {agente_id!r}; se é o mesmo agente, não crie de novo: "
                            "apenas confirme ao usuário. Se é outro agente, escolha outro nome/id.")
    textos = {"nome": nome, "funcao": _texto(spec, "funcao"), "descricao": _texto(spec, "descricao"),
              "exemplo": _texto(spec, "exemplo"), "role": _texto(spec, "role", nome),
              "goal": _texto(spec, "goal"), "backstory": _texto(spec, "backstory")}
    if (falha := agentes_persona.problema(textos)):
        raise ErroValidacao(falha)
    return {"id": agente_id, "andar": andar, "setor": setor, **textos,
            "aparencia": _exclusiva(_aparencia(spec.get("aparencia"))).model_dump()}


# --- Registro no escritório ----------------------------------------------------------------

def _registrar(registro: dict, status: Status) -> Agente:
    agente = Agente(id=registro["id"], nome=registro["nome"], funcao=registro["funcao"],
                    setor=registro["setor"], descricao=registro["descricao"], exemplo=registro["exemplo"],
                    aparencia=Aparencia.model_validate(registro["aparencia"]), status=status)
    ANDARES[registro["andar"]][agente.id] = agente
    PERFIS[agente.id] = {k: registro[k] for k in ("role", "goal", "backstory")}
    CRIADOS.add(agente.id)
    return agente


def do_construtor(agente_id: str) -> bool:
    """Agente criado pelo Construtor (persona escrita por modelo): fica fora do Max (construtor-06)."""
    return agente_id in CRIADOS


def _da_linha(linha) -> dict:
    registro = dict(linha)
    registro["aparencia"] = json.loads(registro["aparencia"])
    registro["ativo"] = bool(registro["ativo"])
    return registro


def _role_de(login: str) -> str | None:
    return (carregar_usuarios().get((login or "").strip().lower()) or {}).get("role")


async def _concluir_construcao(agente_id: str) -> None:
    await asyncio.sleep(SEGUNDOS_CONSTRUINDO)
    andar = andar_do_agente(agente_id)
    agente = ANDARES[andar][agente_id] if andar else None
    if agente and agente.status == Status.construindo:
        agente.status = Status.disponivel
        await atividade.transmitir_estado()


_agora = tarefas._agora


# construtor-18 e -27: um agente por tarefa. A troca de modelo no meio da tarefa recebe o que já foi registrado, em vez
# de criar "vendedor_2". O mesmo nome pela mesma pessoa em outra tarefa atualiza a proposta dela ("Pedir ajuste").
def _ja_proposto(tarefa_id: int | None):
    return tarefa_id and _db().execute("SELECT * FROM agentes_criados WHERE tarefa_id = ? AND ativo = 1",
                                       (tarefa_id,)).fetchone()


CHAT_CONSTRUTOR = {"andar": "porao", "agente": "construtor"}


async def criar(spec: dict, criado_por: str, tarefa_id: int | None = None) -> dict:
    """Valida e grava a PROPOSTA (fora do prédio). Devolve o registro, com "repetido" quando já existia."""
    if _role_de(criado_por) != "diretoria":
        raise SemPermissao("Somente a diretoria pode criar agentes.")
    agente_id = _snake(str((spec or {}).get("id") or "")) or _snake(str((spec or {}).get("nome") or ""))
    if (anterior := _ja_proposto(tarefa_id)):
        return {**_da_linha(anterior), "repetido": True}
    ajuste = _db().execute("SELECT 1 FROM agentes_criados WHERE id = ? AND criado_por = ? AND ativo = 1 AND "
                           "situacao = ?", (agente_id, criado_por, PROPOSTA)).fetchone()
    hoje = _db().execute("SELECT COUNT(*) FROM agentes_criados WHERE criado_em >= ?", (_agora()[:10],)).fetchone()[0]
    if not ajuste and hoje >= LIMITE_POR_DIA:
        raise LimiteAtingido(f"o limite é de {LIMITE_POR_DIA} agentes novos por dia, e ele já foi atingido hoje.")
    registro = validar(spec, ajuste_de=criado_por)
    registro.update(criado_por=criado_por, criado_em=_agora(), ativo=True, situacao=PROPOSTA, tarefa_id=tarefa_id)
    with _db() as db:
        db.execute(
            "INSERT OR REPLACE INTO agentes_criados (id, nome, andar, setor, funcao, descricao, exemplo, role, goal, "
            "backstory, aparencia, criado_por, criado_em, ativo, situacao, tarefa_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (*(registro[k] for k in ("id", "nome", "andar", "setor", "funcao", "descricao", "exemplo", "role",
                                     "goal", "backstory")),
             json.dumps(registro["aparencia"]), criado_por, registro["criado_em"], PROPOSTA, tarefa_id))
    andar, setor = NOMES_ANDARES[registro["andar"]], NOMES_SETORES[registro["setor"]]
    if tarefa_id:
        tarefas.registrar_evento(tarefa_id, "agente_proposto", registro["id"],
                                 detalhe=f"{registro['nome']} proposto para o setor {setor} ({andar}).")
    await gerenciador.enviar_para_usuario(criado_por, {
        "tipo": "aviso", **CHAT_CONSTRUTOR, "titulo": "Agente proposto",
        "texto": f"{registro['nome']} ({setor}, {andar}) está como PROPOSTA: leia a persona na resposta do Construtor "
                 "e decida. Ele só entra no escritório quando você aprovar.",
        "opcoes": [{"rotulo": "Aprovar", "texto": f"Aprovar o agente proposto {registro['id']}"},
                   {"rotulo": "Pedir ajuste", "texto": f"Ajuste o agente proposto {registro['id']}: ", "preencher": True},
                   {"rotulo": "Descartar", "texto": f"Descartar o agente proposto {registro['id']}"}],
    })
    if criado_por != config.DONO_MAX:  # construtor-27: toda criação chega ao Thomas, com quem pediu
        await gerenciador.enviar_para_usuario(config.DONO_MAX, {
            "tipo": "aviso", **CHAT_CONSTRUTOR, "titulo": "Agente proposto",
            "texto": f"{criado_por} pediu ao Construtor o agente {registro['nome']} ({setor}, {andar}); aguarda a "
                     "aprovação de quem pediu."})
    log.warning("Agente proposto: %s (%s/%s) por %s, tarefa %s", registro["id"], registro["andar"], registro["setor"],
                criado_por, tarefa_id)
    return registro


def criar_em_thread(spec: dict, criado_por: str, tarefa_id: int | None = None) -> str:
    """Para a ferramenta do CrewAI (thread): grava a proposta no loop principal e devolve texto para o LLM."""
    loop = atividade._loop
    if not loop:
        return "Erro: o servidor não está pronto para criar agentes agora. Avise o usuário."
    try:
        registro = asyncio.run_coroutine_threadsafe(criar(spec, criado_por, tarefa_id), loop).result(timeout=30)
    except ErroValidacao as erro:
        return f"Erro de validação: {erro} Corrija a especificação e chame criar_agente de novo."
    except (SemPermissao, LimiteAtingido) as erro:
        return f"Não autorizado: {erro} Explique isso ao usuário; não tente de novo."
    except (TimeoutError, concurrent.futures.TimeoutError):
        return "Erro: a criação demorou demais. Avise o usuário para tentar novamente."
    if registro.get("repetido"):
        return (f"Este agente já foi registrado nesta tarefa ({registro['nome']}, id {registro['id']}); não chame "
                "criar_agente de novo. Apenas confirme ao usuário que a proposta está pronta para ele revisar.")
    return (f"Proposta registrada: {registro['nome']} (id {registro['id']}), setor "
            f"{NOMES_SETORES[registro['setor']]} do andar {NOMES_ANDARES[registro['andar']]}. Ele AINDA NÃO está no "
            "escritório: só entra quando quem pediu ler a persona e aprovar. Não diga que o agente foi criado; diga que "
            "a proposta está pronta para revisão.")


# --- Decisão de quem pediu (decisão 16) --------------------------------------------------------

COMANDO = re.compile(r"^\s*(aprov\w*|descart\w*)\s+(?:o\s+)?agente\s+proposto\s+([a-z][a-z0-9_]{1,39})\b", re.I)


def comando(texto: str) -> tuple[str, str] | None:
    """"Aprovar o agente proposto vendedor" -> ("aprovar", "vendedor"); None se não for decisão."""
    achado = COMANDO.match(texto or "")
    if not achado:
        return None
    return ("aprovar" if achado.group(1).lower().startswith("aprov") else "descartar"), achado.group(2).lower()


async def decidir(agente_id: str, login: str, acao: str, tarefa_id: int | None = None) -> str:
    """Só a pessoa da Diretoria que pediu decide. Aprovado: ganha mesa (construindo -> disponivel)."""
    linha = _db().execute("SELECT * FROM agentes_criados WHERE id = ? AND ativo = 1 AND situacao = ?",
                          (agente_id, PROPOSTA)).fetchone()
    if not linha:
        no_predio = andar_do_agente(agente_id)
        return (f"O agente {agente_id} já foi aprovado e está no escritório." if no_predio
                else f"Não achei nenhuma proposta pendente com o id {agente_id}.")
    if _role_de(login) != "diretoria" or linha["criado_por"] != (login or "").strip().lower():
        return "Só a pessoa da Diretoria que pediu este agente pode aprová-lo ou descartá-lo."
    registro = _da_linha(linha)
    if acao == "descartar":
        with _db() as db:
            db.execute("UPDATE agentes_criados SET ativo = 0, situacao = ?, aprovado_por = ?, aprovado_em = ? "
                       "WHERE id = ?", (DESCARTADO, login, _agora(), agente_id))
        return f"Proposta do {registro['nome']} descartada. Nada entrou no escritório."
    if andar_do_agente(agente_id) or agente_id in PERFIS:
        return f"Já existe um agente com o id {agente_id} no escritório; peça ao Construtor outro nome."
    if vagas(registro["andar"], registro["setor"]) <= 0:
        return (f"O setor {NOMES_SETORES[registro['setor']]} lotou desde a proposta. Peça um ajuste com outro setor "
                f"({setores_com_vagas()}).")
    with _db() as db:
        db.execute("UPDATE agentes_criados SET situacao = ?, aprovado_por = ?, aprovado_em = ? WHERE id = ?",
                   (APROVADO, login, _agora(), agente_id))
    _registrar(registro, Status.construindo)
    await atividade.transmitir_estado()
    andar, setor = NOMES_ANDARES[registro["andar"]], NOMES_SETORES[registro["setor"]]
    for tarefa in {t for t in (registro.get("tarefa_id"), tarefa_id) if t}:
        tarefas.registrar_evento(tarefa, "agente_criado", agente_id,
                                 detalhe=f"{registro['nome']} aprovado por {login} no setor {setor} ({andar}).")
    await gerenciador.enviar_para_usuario(login, {
        "tipo": "aviso", "andar": registro["andar"], "agente": agente_id, "titulo": "Novo agente",
        "texto": f"{registro['nome']} chegou ao setor {setor} ({andar})."})
    pendente = asyncio.create_task(_concluir_construcao(agente_id))
    _pendentes.add(pendente)
    pendente.add_done_callback(_pendentes.discard)
    return (f"Aprovado: {registro['nome']} entrou no setor {setor} ({andar}). Ele aparece como \"construindo\" e fica "
            "disponível em alguns segundos.")


def decidir_em_thread(texto: str, login: str, tarefa_id: int | None = None) -> str | None:
    """Mensagem ao Construtor que é uma decisão: resolve sem modelo (None quando não é decisão)."""
    if not (pedido := comando(texto)):
        return None
    loop = atividade._loop
    if not loop:
        return "O servidor não está pronto agora. Tente de novo em instantes."
    return asyncio.run_coroutine_threadsafe(decidir(pedido[1], login, pedido[0], tarefa_id), loop).result(timeout=30)


# construtor-07: o chat só diz "criado" quando o registro existe. Sem registro e o modelo dizendo que criou, a
# resposta é descartada e o próximo modelo tenta (como no raciocínio vazado).
DISSE_QUE_CRIOU = re.compile(r"\b(?<!n[aã]o )(?<!n[aã]o foi )(?:foi |est[aá] |j[aá] )?(?:criad[oa]|registrad[oa]|"
                             r"cadastrad[oa])\b(?! ainda)|chegou ao setor|j[aá] est[aá] no (?:escrit[oó]rio|setor|andar)",
                             re.I)


def conferir_resposta(tarefa_id: int, texto: str) -> str:
    linha = _db().execute("SELECT * FROM agentes_criados WHERE tarefa_id = ? AND situacao IN (?, ?)",
                          (tarefa_id, PROPOSTA, APROVADO)).fetchone() if tarefa_id else None
    if not linha:
        # "O Designer já existe no setor Criação" fala de quem já está no prédio: não é falso sucesso.
        ja_no_predio = any(a.nome.lower() in (texto or "").lower() for a in _todos_agentes() if len(a.nome) > 3)
        if DISSE_QUE_CRIOU.search(texto or "") and "<<FORMULARIO>>" not in (texto or "") and not ja_no_predio:
            raise RuntimeError("o Construtor disse que criou o agente sem registrar a proposta")
        return texto
    r = _da_linha(linha)
    situacao = ("aprovado e já no escritório" if r["situacao"] == APROVADO else
                f"PROPOSTA, ainda fora do escritório. Para decidir, use os botões do aviso ou escreva \"Aprovar o "
                f"agente proposto {r['id']}\" / \"Descartar o agente proposto {r['id']}\" (ou peça um ajuste)")
    return (f"{texto}\n\nRegistro do sistema: {r['nome']} (id {r['id']}), {NOMES_SETORES[r['setor']]} · "
            f"{NOMES_ANDARES[r['andar']]}: {situacao}.\nFunção: {r['funcao']}\nObjetivo: {r['goal']}\n"
            f"Persona (instrução permanente dele):\n{r['backstory']}")


def carregar() -> None:
    """Na subida: devolve ao escritório e às personas os agentes criados ativos e aprovados (propostas não)."""
    for linha in _db().execute("SELECT * FROM agentes_criados WHERE ativo = 1 AND situacao = ? ORDER BY criado_em",
                               (APROVADO,)):
        registro = _da_linha(linha)
        if registro["andar"] not in ANDARES or andar_do_agente(registro["id"]):
            log.warning("Agente criado ignorado (andar inválido ou id repetido): %s", registro["id"])
            continue
        _registrar(registro, Status.disponivel)


async def desativar(agente_id: str) -> bool:
    with _db() as db:
        alterou = db.execute("UPDATE agentes_criados SET ativo = 0 WHERE id = ? AND ativo = 1",
                             (agente_id,)).rowcount
    if not alterou:
        return False
    andar = andar_do_agente(agente_id)
    if andar:
        ANDARES[andar].pop(agente_id, None)
    PERFIS.pop(agente_id, None)
    CRIADOS.discard(agente_id)
    await atividade.transmitir_estado()
    return True


def propostas_pendentes() -> int:
    return _db().execute("SELECT COUNT(*) FROM agentes_criados WHERE ativo = 1 AND situacao = ?", (PROPOSTA,)).fetchone()[0]


# --- Rotas ---------------------------------------------------------------------------------

rotas = APIRouter(prefix="/api/agentes-criados")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


@rotas.get("")
def listar(authorization: str = Header("")):
    usuario = _usuario(authorization)
    linhas = _db().execute("SELECT * FROM agentes_criados WHERE ativo = 1 AND situacao = ? ORDER BY criado_em",
                           (APROVADO,)).fetchall()
    return {"agentes": [_da_linha(l) for l in linhas if acesso.pode_ver_andar(usuario, l["andar"])]}


@rotas.delete("/{agente_id}")
async def remover(agente_id: str, authorization: str = Header("")):
    if _usuario(authorization)["role"] != "diretoria":
        raise HTTPException(status_code=403, detail="Apenas a diretoria pode remover agentes.")
    if not await desativar(agente_id):
        raise HTTPException(status_code=404, detail="Agente criado não encontrado.")
    return {"ok": True, "id": agente_id}
