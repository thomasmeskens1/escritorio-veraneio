"""Prévia da prospecção e criação dos leads aprovados (saiu de comercial.py, que passava de 600 linhas).

Prévia antes do Monday (Thomas, 28/10/2026: "ver o resultado antes de colocar em prática"): toda prospecção pesquisa e
mostra a lista sem criar nada; os leads só vão ao Monday quando a pessoa aprova a prévia.
N2-prospectador-02 (fase 1, ajuste do crítico): um trabalho do Max por lote de 5 empresas, uma linha <<LEAD>> por
empresa lida com tolerância (prospeccao_leitura) e prévia parcial quando um lote falha. A resposta bruta continua no
trabalho do Max (o id fica na prévia). Tudo aqui chama comercial.<nome> na hora (os testes trocam essas peças).
"""

import json
import logging
import re
from datetime import datetime, timezone

import comercial as c
import prospeccao_leitura
import segredos
import tarefas

log = logging.getLogger(__name__)


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pesquisar_lotes(tarefa_id: int, pedido: str) -> dict:
    """Um lote que falha (tempo, erro) não leva os outros: a prévia sai parcial com o que chegou."""
    divisao = c.lotes(c._quantidade(pedido))
    achados = {"aceitos": [], "recusados": [], "defeitos": 0, "falhas": [], "textos": [], "trabalhos": []}
    for n, quantidade in enumerate(divisao, 1):
        rotulo = f"lote {n} de {len(divisao)}" if len(divisao) > 1 else "pesquisa"

        def na_fila(trabalho_id: int, rotulo: str = rotulo) -> None:  # posição na fila, no registro da tarefa
            achados["trabalhos"].append(trabalho_id)
            c._evento(tarefa_id, "adiada", f"{rotulo} na fila do Max, {c.na_frente(trabalho_id)} trabalho(s) na frente")

        evitar = [a["empresa"] for a in achados["aceitos"]]
        prompt = c.prompt_prospeccao(pedido, quantidade, evitar) if evitar else c.prompt_prospeccao(pedido, quantidade)
        try:
            resposta = c.pedir_ao_max(prompt, c.LIMITE_LOTE_S, origem="prospeccao", ao_enfileirar=na_fila)
        except Exception as erro:
            log.warning("Prospecção da tarefa %s: %s falhou (%s).", tarefa_id, rotulo, erro)
            achados["falhas"].append(f"{rotulo}: {erro}")
            continue
        if not prospeccao_leitura.tem_leads(resposta):  # respondeu em texto (ex.: pedido ambíguo)
            achados["textos"].append(resposta)
            continue
        leads, defeitos = prospeccao_leitura.ler(resposta)
        achados["defeitos"] += defeitos
        ja_na_previa = {c._chave(a["empresa"]) for a in achados["aceitos"]}
        leads = [l for l in leads if c._chave(str(l.get("empresa") or "")) not in ja_na_previa]
        nomes, dominios = c.ja_conhecidos()  # de novo: a equipe pode ter cadastrado alguém durante a pesquisa
        aceitos, recusados = c.validar(leads, nomes, dominios)
        achados["aceitos"] += aceitos[:c.MAX_LEADS - len(achados["aceitos"])]
        achados["recusados"] += recusados
    return achados


def prospectar(tarefa_id: int, pedido: str) -> str:
    """Pesquisa e devolve a PRÉVIA (nada é criado no Monday)."""
    import carteira

    c._evento(tarefa_id, "consulta_cerebro", "Clientes e Prospecção Ativa no Monday (para não repetir empresas)")
    achados = pesquisar_lotes(tarefa_id, pedido)
    aceitos, recusados = achados["aceitos"], achados["recusados"]
    if not aceitos:
        if achados["falhas"] and not achados["textos"] and not recusados:
            raise RuntimeError(achados["falhas"][0])
        if achados["textos"] and not recusados:
            return segredos.limpar(achados["textos"][0].strip()) or "Não consegui montar a lista de empresas desta vez."
        return "Não encontrei empresas novas com canal de contato da empresa publicado." + (
            "\n\nFicaram de fora: " + "; ".join(recusados[:12]) + "." if recusados else "")
    c.PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
    tarefa = tarefas.obter(tarefa_id)
    usuario = tarefa["usuario"] if tarefa else ""
    parcial = bool(achados["falhas"] or achados["defeitos"])
    c._previa(tarefa_id).write_text(json.dumps({
        "usuario": usuario, "pedido": pedido, "leads": aceitos, "criados": [], "itens_monday": {},
        "parcial": parcial, "trabalhos_max": achados["trabalhos"], "criada_em": _agora()}, ensure_ascii=False),
        encoding="utf-8")
    texto = (f"Prévia #{tarefa_id}: {len(aceitos)} empresa(s) nova(s), ainda NÃO criadas no Monday.\n\n" +
             "\n\n".join(c._linha_lead(n, l) for n, l in enumerate(aceitos, 1)))
    if parcial:
        motivos = achados["falhas"] + ([f"{achados['defeitos']} linha(s) da resposta vieram com defeito e foram "
                                        "puladas"] if achados["defeitos"] else [])
        texto += "\n\nPrévia parcial: " + "; ".join(motivos) + ". Peça de novo para completar."
    if recusados:
        texto += "\n\nFicaram de fora: " + "; ".join(recusados[:12]) + "."
    return texto + (f"\n\nPara colocar em prática, diga \"Crie os leads da prévia #{tarefa_id}\" (todos) ou "
                    f"\"Crie os leads 1, 3 e 5 da prévia #{tarefa_id}\". Eles vão para o grupo [Corp] Prospecção Ativa."
                    f"\n\n{carteira.rodape(usuario)}")


def _qual_previa(texto: str, usuario: str) -> int | None:
    # Só prévias do próprio usuário (revisão de 30/10/2026: dava para criar os leads da prévia de outra pessoa).
    if (citada := re.search(r"#\s*(\d+)", texto)) and c._previa(int(citada.group(1))).exists():
        dono = json.loads(c._previa(int(citada.group(1))).read_text(encoding="utf-8"))["usuario"]
        return int(citada.group(1)) if dono == usuario else None
    pasta = c.PASTA_PREVIAS
    previas = sorted((int(a.stem) for a in pasta.glob("*.json") if a.stem.isdigit()), reverse=True) \
        if pasta.exists() else []
    return next((n for n in previas if json.loads(c._previa(n).read_text(encoding="utf-8"))["usuario"] == usuario), None)


def criar_da_previa(tarefa_id: int, texto: str) -> str:
    """Cria no Monday os leads aprovados de uma prévia (todos ou os números citados), sem nova pesquisa."""
    tarefa = tarefas.obter(tarefa_id)
    numero = _qual_previa(texto, tarefa["usuario"] if tarefa else "")
    if numero is None:
        return "Não achei nenhuma prévia de prospecção sua. Peça uma prospecção primeiro; eu mostro a lista antes."
    previa = json.loads(c._previa(numero).read_text(encoding="utf-8"))
    sem_numero_da_previa = re.sub(r"#\s*\d+", "", texto)
    if (primeiros := re.search(r"\b(\d{1,2})\s+primeir[oa]s\b", sem_numero_da_previa, re.IGNORECASE)):
        escolhidos = set(range(1, int(primeiros.group(1)) + 1))  # "os 3 primeiros" = 1, 2 e 3 (não o lead 3)
    else:
        escolhidos = {int(n) for n in re.findall(r"\b(\d{1,2})\b", sem_numero_da_previa)}
    leads = [(n, l) for n, l in enumerate(previa["leads"], 1) if not escolhidos or n in escolhidos]
    nomes, dominios = c.ja_conhecidos()  # alguém pode ter cadastrado a empresa depois da prévia
    criados, fora = [], []
    for n, lead in leads:
        if n in previa["criados"]:
            fora.append(f"{lead['empresa']}: já criado desta prévia")
            continue
        conferidos, motivos = c.validar([dict(lead)], nomes, dominios)  # regra atual vale até para prévia antiga
        if not conferidos:
            fora.append(motivos[0] if motivos else f"{lead['empresa']}: sem canal da empresa publicado")
            continue
        try:
            item_id = c.criar_lead(conferidos[0])
        except Exception as erro:
            log.warning("Prospectador: não criou %s (%s).", lead.get("empresa"), erro)
            fora.append(f"{lead['empresa']}: erro no Monday")
            continue
        previa["criados"].append(n)
        # Lacuna do crítico (R5): o item do Monday e a data de criação ligam a prévia ao lead real (fila de contatos,
        # placar e "de onde veio este contato?").
        previa.setdefault("itens_monday", {})[str(n)] = {"item_id": item_id, "criado_em": _agora(),
                                                         "criado_por": tarefa["usuario"] if tarefa else ""}
        criados.append(lead["empresa"].strip().upper())
        c._evento(tarefa_id, "item_monday", criados[-1])
    c._previa(numero).write_text(json.dumps(previa, ensure_ascii=False), encoding="utf-8")
    texto = (f"Criei {len(criados)} lead(s) da prévia #{numero} no grupo [Corp] Prospecção Ativa, com Origem "
             f"\"Prospecção Ativa\", Tipo \"Corporativo\" e as fontes no Histórico: {', '.join(criados)}."
             if criados else f"Nenhum lead da prévia #{numero} foi criado.")
    return texto + ("\n\nFicaram de fora: " + "; ".join(fora) + "." if fora else "")
