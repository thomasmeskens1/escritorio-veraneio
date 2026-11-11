"""Piloto da prospecção com o Comercial (Onda 2, N2-prospectador-09): só o mecanismo.

O piloto: 3 prévias de 5 empresas, e cada vendedor dá uma nota de 1 a 5 (com comentário) para cada lead ("ligaria?").
Quando as 3 prévias tiverem nota em todos os leads, sai o resumo do piloto (média, distribuição, por vendedor, os
leads mais bem avaliados e os comentários). Mede a qualidade real do Prospectador antes de pedir mais prospecção.

Regras:
- nada aqui dispara prospecção nem o Max: as prévias já existem (prospeccao_previa.py) e o master escolhe quais
  formam o piloto;
- a nota fica na própria prévia (`notas` no JSON) e não leva dado de contato: o comentário passa por
  insatisfacoes.texto_seguro (sem e-mail, telefone, CPF/CNPJ nem segredo) e a tela do piloto mostra o lead sem e-mail,
  telefone nem site;
- nada se apaga: nota trocada vai para `notas_historico`, e a troca das prévias do piloto guarda a lista anterior.
"""

import json
import re
import threading

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import comercial as c
import tarefas
from auth import carregar_usuarios, validar_token

rotas = APIRouter(prefix="/api/prospeccao")

PREVIAS_DO_PILOTO = 3
LEADS_POR_PREVIA = 5     # referência do piloto; a prévia pode ter menos (lote parcial)
NOTA_MIN, NOTA_MAX = 1, 5
LIGARIA = 4              # média a partir da qual o lead conta como "ligaria"
COMENTARIO_MAX = 500
_trava = threading.Lock()  # nota e criação de leads gravam o mesmo JSON

# "Nota 4 para o lead 2 da prévia #123: porte bom" ou "Prévia #123: lead 1 = 5; lead 2: nota 3, fora do perfil".
PEDE_NOTA = re.compile(r"\bnotas?\b.{0,80}\blead|\blead\s*\d{1,2}\s*(?:[:=\-–]|com|recebe|leva)?\s*(?:nota\s*)?[1-5]\b",
                       re.IGNORECASE)
_PREVIA = re.compile(r"\bpr[ée]via\s*#?\s*(\d+)", re.IGNORECASE)
_NOTA_LEAD = re.compile(r"\bnota\s*([1-5])\b\D{0,25}?\blead\s*(\d{1,2})\b", re.IGNORECASE)
_LEAD_NOTA = re.compile(r"\blead\s*(\d{1,2})\b\s*(?:[:=\-–]|com|recebe|leva)?\s*(?:nota\s*)?([1-5])\b", re.IGNORECASE)


def _arquivo_piloto():
    return c.PASTA_PREVIAS / "piloto.json"  # não é número: a busca de prévias (stem.isdigit) não o pega


def _ler_piloto() -> dict:
    arquivo = _arquivo_piloto()
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {"previas": [], "historico": []}


def _gravar_piloto(piloto: dict) -> None:
    c.PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
    _arquivo_piloto().write_text(json.dumps(piloto, ensure_ascii=False), encoding="utf-8")


def _ler_previa(previa_id: int) -> dict | None:
    arquivo = c._previa(previa_id)
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None


def _seguro(texto: str) -> str:
    import insatisfacoes  # import tardio: carrega o Cérebro (filtro de contatos)

    return insatisfacoes.texto_seguro(texto or "").strip()[:COMENTARIO_MAX]


def no_piloto(previa_id: int) -> bool:
    return previa_id in _ler_piloto()["previas"]


def pode_dar_nota(usuario: dict, previa_id: int, previa: dict) -> bool:
    """Dono da prévia, master ou, nas prévias do piloto, qualquer vendedor que usa o Prospectador."""
    return previa.get("usuario") == usuario.get("sub") or bool(usuario.get("master")) or no_piloto(previa_id)


def dar_nota(previa_id: int, lead: int, usuario: str, nota: int, comentario: str = "") -> dict:
    """Grava a nota (1 a 5) de `usuario` para o lead `lead` (1, 2, ...) da prévia. A nota anterior vai ao histórico."""
    if not NOTA_MIN <= int(nota) <= NOTA_MAX:
        raise ValueError(f"A nota vai de {NOTA_MIN} a {NOTA_MAX}.")
    comentario = _seguro(comentario)
    with _trava:
        previa = _ler_previa(previa_id)
        if previa is None:
            raise LookupError(f"A prévia #{previa_id} não existe.")
        if not 1 <= lead <= len(previa.get("leads", [])):
            raise LookupError(f"A prévia #{previa_id} tem {len(previa.get('leads', []))} lead(s); não há o lead {lead}.")
        notas = previa.setdefault("notas", {}).setdefault(str(lead), {})
        if usuario in notas:
            previa.setdefault("notas_historico", []).append({"lead": lead, "usuario": usuario, **notas[usuario]})
        notas[usuario] = {"nota": int(nota), "comentario": comentario, "em": tarefas._agora()}
        c._previa(previa_id).write_text(json.dumps(previa, ensure_ascii=False), encoding="utf-8")
    _talvez_fechar_resumo()
    return notas[usuario]


def _lead_sem_contato(n: int, lead: dict) -> dict:
    """O que o vendedor precisa para dizer "ligaria?": sem e-mail, telefone nem site."""
    return {"n": n, "empresa": str(lead.get("empresa") or "").strip().upper(),
            "local": f"{lead.get('cidade', '')} / {lead.get('uf', '')}".strip(" /"),
            "segmento": lead.get("segmento") or "", "porte": lead.get("porte") or "",
            "funcionarios": lead.get("funcionarios") or None, "motivo": _seguro(lead.get("motivo") or "")}


def _media(valores: list[int]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def estado(login: str = "") -> dict:
    """Prévias do piloto com os leads (sem contato), as notas de cada vendedor (`minha`: de `login`) e se fechou."""
    piloto = _ler_piloto()
    nomes = {login: d.get("nome", login) for login, d in carregar_usuarios().items()}
    previas = []
    for previa_id in piloto["previas"]:
        previa = _ler_previa(previa_id)
        if previa is None:
            previas.append({"id": previa_id, "existe": False, "leads": [], "completa": False})
            continue
        notas = previa.get("notas", {})
        leads = []
        for n, lead in enumerate(previa.get("leads", []), 1):
            dadas = notas.get(str(n), {})
            leads.append({**_lead_sem_contato(n, lead), "media": _media([d["nota"] for d in dadas.values()]),
                          "notas": [{"usuario": u, "nome": nomes.get(u, u), "minha": u == login, **d}
                                    for u, d in dadas.items()]})
        previas.append({"id": previa_id, "existe": True, "pedido": _seguro(previa.get("pedido", ""))[:200],
                        "criada_em": previa.get("criada_em"), "leads": leads,
                        "completa": bool(leads) and all(l["notas"] for l in leads)})
    completo = len(previas) == PREVIAS_DO_PILOTO and all(p["completa"] for p in previas)
    return {"previas": previas, "completo": completo, "faltam_previas": max(0, PREVIAS_DO_PILOTO - len(previas)),
            "nota_min": NOTA_MIN, "nota_max": NOTA_MAX, "resumo": resumo(previas, nomes) if completo else None,
            "resumo_fechado_em": piloto.get("resumo_fechado_em")}


def resumo(previas: list[dict], nomes: dict | None = None) -> dict:
    """Resumo do piloto: média geral, distribuição 1 a 5, "ligaria" (média >= LIGARIA), por prévia e por vendedor."""
    leads = [l for p in previas for l in p["leads"]]
    todas = [n for l in leads for n in l["notas"]]
    distribuicao = {str(v): sum(n["nota"] == v for n in todas) for v in range(NOTA_MIN, NOTA_MAX + 1)}
    vendedores: dict[str, list[int]] = {}
    for n in todas:
        vendedores.setdefault(n["nome"], []).append(n["nota"])
    ligaria = [l for l in leads if (l["media"] or 0) >= LIGARIA]
    return {
        "leads": len(leads), "notas": len(todas), "media_geral": _media([n["nota"] for n in todas]),
        "distribuicao": distribuicao, "ligaria": len(ligaria),
        "ligaria_pct": round(100 * len(ligaria) / len(leads)) if leads else 0,
        "por_previa": [{"id": p["id"], "media": _media([n["nota"] for l in p["leads"] for n in l["notas"]]),
                        "ligaria": sum((l["media"] or 0) >= LIGARIA for l in p["leads"])} for p in previas],
        "por_vendedor": [{"nome": nome, "notas": len(v), "media": _media(v)} for nome, v in sorted(vendedores.items())],
        "melhores": [{"empresa": l["empresa"], "media": l["media"]}
                     for l in sorted(leads, key=lambda l: -(l["media"] or 0))[:5]],
        "comentarios": [{"empresa": l["empresa"], "nota": n["nota"], "nome": n["nome"], "comentario": n["comentario"]}
                        for l in leads for n in l["notas"] if n.get("comentario")][:30],
    }


def _talvez_fechar_resumo() -> None:
    """Na primeira vez que as 3 prévias ficam com nota, grava o resumo no piloto (o retrato do dia; nada se apaga)."""
    piloto = _ler_piloto()
    if piloto.get("resumo_fechado_em") or len(piloto["previas"]) != PREVIAS_DO_PILOTO:
        return
    atual = estado()
    if atual["completo"]:
        piloto.update({"resumo_fechado_em": tarefas._agora(), "resumo": atual["resumo"]})
        _gravar_piloto(piloto)


def marcar(previas: list[int], quem: str) -> dict:
    """Escolhe as prévias do piloto (até PREVIAS_DO_PILOTO). A lista anterior fica no histórico."""
    unicas = list(dict.fromkeys(int(p) for p in previas))
    if not 1 <= len(unicas) <= PREVIAS_DO_PILOTO:
        raise ValueError(f"O piloto tem de 1 a {PREVIAS_DO_PILOTO} prévias.")
    faltando = [p for p in unicas if _ler_previa(p) is None]
    if faltando:
        raise LookupError("Prévia(s) inexistente(s): " + ", ".join(f"#{p}" for p in faltando))
    piloto = _ler_piloto()
    if piloto["previas"]:
        piloto.setdefault("historico", []).append({k: piloto.get(k) for k in
                                                   ("previas", "marcado_em", "marcado_por", "resumo_fechado_em")})
    piloto.update({"previas": unicas, "marcado_em": tarefas._agora(), "marcado_por": quem})
    piloto.pop("resumo_fechado_em", None)
    if piloto.get("resumo"):
        piloto.setdefault("resumos_anteriores", []).append(piloto.pop("resumo"))
    _gravar_piloto(piloto)
    _talvez_fechar_resumo()
    return estado()


# --- Pelo chat do Prospectador (comercial.executar chama antes de "criar leads da prévia") ----------------------

def e_nota(texto: str) -> bool:
    return bool(_PREVIA.search(texto or "") and PEDE_NOTA.search(texto or ""))


def ler_notas(texto: str) -> list[tuple[int, int, str]]:
    """[(lead, nota, comentário)] de "nota 4 para o lead 2: ..." ou "lead 1 = 5; lead 2: nota 3, ..." (um por trecho)."""
    sem_previa = _PREVIA.sub(" ", texto or "")
    achadas = []
    for trecho in re.split(r"[;\n]+", sem_previa):
        if not (m := _NOTA_LEAD.search(trecho)) and not (m := _LEAD_NOTA.search(trecho)):
            continue
        nota, lead = (m.group(1), m.group(2)) if m.re is _NOTA_LEAD else (m.group(2), m.group(1))
        resto = trecho[m.end():]
        if (separador := re.search(r"[:,(\-–]", resto)):  # "... da prévia: porte bom" -> "porte bom"
            resto = resto[separador.end():]
        elif re.fullmatch(r"\s*(da|do|na|no|para)?\s*", resto, re.IGNORECASE):
            resto = ""
        achadas.append((int(lead), int(nota), resto.strip(" :-–,.()")))
    return achadas


def nota_pelo_chat(tarefa_id: int, texto: str) -> str:
    tarefa = tarefas.obter(tarefa_id)
    login = tarefa["usuario"] if tarefa else ""
    previa_id = int(_PREVIA.search(texto).group(1))
    previa = _ler_previa(previa_id)
    if previa is None:
        return f"Não achei a prévia #{previa_id}."
    from auth import e_master

    if not pode_dar_nota({"sub": login, "master": e_master(login)}, previa_id, previa):
        return f"A prévia #{previa_id} não é sua nem faz parte do piloto: só o dono dela dá nota."
    notas = ler_notas(texto)
    if not notas:
        return (f"Não entendi a nota. Escreva, por exemplo: \"Nota 4 para o lead 2 da prévia #{previa_id}: porte bom\" "
                f"ou \"Prévia #{previa_id}: lead 1 = 5; lead 2 = 3, fora do perfil\". A nota vai de {NOTA_MIN} a "
                f"{NOTA_MAX}.")
    feitas, erros = [], []
    for lead, nota, comentario in notas:
        try:
            dar_nota(previa_id, lead, login, nota, comentario)
            feitas.append(f"lead {lead} = {nota}")
        except (LookupError, ValueError) as erro:
            erros.append(str(erro))
    texto_final = (f"Nota registrada na prévia #{previa_id}: {', '.join(feitas)}. Nenhum lead foi criado no Monday."
                   if feitas else f"Nenhuma nota registrada na prévia #{previa_id}.")
    if erros:
        texto_final += "\n\nFicou de fora: " + "; ".join(erros)
    atual = estado()
    if no_piloto(previa_id):
        texto_final += ("\n\nO piloto fechou: as 3 prévias têm nota. O resumo está no painel do piloto."
                        if atual["completo"] else "")
    return texto_final


# --- Rotas ----------------------------------------------------------------------------------------------------

def _usuario(authorization: str) -> dict:
    import acesso

    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    if not acesso.pode_usar(usuario, c.ANDAR, c.AGENTE):
        raise HTTPException(status_code=403, detail="O piloto é de quem usa o Prospectador.")
    return usuario


@rotas.get("/piloto")
def ver_piloto(authorization: str = Header("")):
    return estado(_usuario(authorization)["sub"])


class Marcacao(BaseModel):
    previas: list[int] = Field(min_length=1, max_length=PREVIAS_DO_PILOTO)


@rotas.post("/piloto")
def marcar_piloto(dados: Marcacao, authorization: str = Header("")):
    usuario = _usuario(authorization)
    if not usuario.get("master"):
        raise HTTPException(status_code=403, detail="Só o master escolhe as prévias do piloto.")
    try:
        return marcar(dados.previas, usuario["sub"])
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))


class Nota(BaseModel):
    lead: int = Field(ge=1, le=c.MAX_LEADS)
    nota: int = Field(ge=NOTA_MIN, le=NOTA_MAX)
    comentario: str = Field("", max_length=1000)


@rotas.post("/previas/{previa_id}/notas")
def nota_rota(previa_id: int, dados: Nota, authorization: str = Header("")):
    usuario = _usuario(authorization)
    previa = _ler_previa(previa_id)
    if previa is None or not pode_dar_nota(usuario, previa_id, previa):
        raise HTTPException(status_code=404, detail="Prévia não encontrada.")
    try:
        nota = dar_nota(previa_id, dados.lead, usuario["sub"], dados.nota, dados.comentario)
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    return {"ok": True, "nota": nota, "completo": estado()["completo"]}
