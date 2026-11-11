"""Persona do Corporativo (manual 14) protegida (N2-prospectador-01; padrão mais seguro adotado em 11/11/2026).

Antes, qualquer frase com "persona" ("Me explique a persona", "Prospecte 5 empresas da persona") refazia o manual 14
inteiro por cima, sem cópia, e mandava a lista nominal da carteira ao Max. Agora:
  - só um pedido explícito refaz a persona ("Refaça a persona", "Atualize a persona", "Monte a persona");
  - a versão nova sai como RASCUNHO em dados/persona (fora de dados/conhecimento: não entra no Cérebro) e o manual 14
    continua valendo;
  - o manual só é trocado quando o Thomas escreve "Aprovo a persona nova", e a versão anterior fica guardada com a
    data. Nada é apagado: o rascunho aprovado também fica, renomeado.
A comparação seção por seção e o bloco protegido "Regras do Thomas" ficam para um segundo passo (ajuste do crítico).
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config

PASTA = config.DADOS_DIR / "persona"
PREFIXO_RASCUNHO = "14_persona_rascunho_"
FUSO = ZoneInfo("America/Sao_Paulo")
FRASE_APROVAR = "Aprovo a persona nova"


def _agora() -> datetime:
    return datetime.now(FUSO)


def _rascunhos() -> list[tuple[int, Path]]:
    """(tarefa, arquivo) dos rascunhos ainda não aprovados, do mais novo ao mais antigo."""
    if not PASTA.exists():
        return []
    achados = []
    for arquivo in PASTA.glob(f"{PREFIXO_RASCUNHO}*.md"):
        if (numero := re.fullmatch(rf"{PREFIXO_RASCUNHO}(\d+)", arquivo.stem)):
            achados.append((int(numero.group(1)), arquivo))
    return sorted(achados, reverse=True)


def _resumo_clientes(limite: int = 120) -> str:
    """Lista NOMINAL da carteira: só no pedido da persona, que roda no Max SEM pesquisa na web."""
    import comercial

    base = comercial.clientes()
    contas = [f"- {c['nome']} | {c['industry'] or 'setor ?'} | {c['text_mkxj2284'] or ''} "
              f"{c['dropdown_mkxj16y9'].split('–')[-1].strip()} | último evento {c['data_mknc1nvw'] or '?'}"
              for c in base["contas"][:limite]]
    unicos = list({comercial._chave(g["nome"]): g for g in base["ganhos"]}.values())  # a negociação se repete
    ganhos = [f"- {comercial._sem_codigo(g['nome'])} | {g['color_mm4pd1wc'] or 'evento'} | "
              f"{g['n_meros_mkmgpvds'] or '?'} pax | {g['local_mkmgy5nb'] or ''} | {g['date_mkp5eds'] or ''}"
              for g in unicos[:limite]]
    return (f"CONTAS CORPORATIVAS ATIVAS ({len(base['contas'])}):\n" + "\n".join(contas) +
            f"\n\nEVENTOS GANHOS ({len(unicos)} empresas):\n" + "\n".join(ganhos))


def prompt() -> str:
    """Pedido ao Max da persona nova (sem web: a lista nominal da carteira não sai do PC)."""
    return "\n\n".join([
        # Sem pesquisa na web (web=False no pedir_ao_max): a lista nominal da carteira não sai do PC (decisão 12).
        "Você é o Prospectador da Casa Veraneio Corporativo. Crie a PERSONA do cliente corporativo ideal a partir dos "
        "clientes reais abaixo (quem já fez evento conosco). Use só estes dados e o que você já sabe sobre os "
        "segmentos; não há pesquisa na web neste pedido.",
        _resumo_clientes(250),
        "Escreva em português, em Markdown, começando por \"# Persona · Cliente corporativo da Casa Veraneio "
        "Corporativo\", com as seções: 1. Resumo da persona (quem decide e quem influencia: RH, eventos, marketing, "
        "diretoria); 2. Empresas-alvo (segmentos, porte, regiões, padrões que aparecem nos clientes); 3. Tipos de "
        "evento e tamanho (pax) mais comuns; 4. Dores e motivações; 5. Gatilhos e épocas de compra; 6. Sinais de bom "
        "lead na prospecção; 7. Quem NÃO é o nosso cliente. Baseie cada ponto nos dados (cite contagens) e marque "
        "como HIPÓTESE o que não vier deles. Não cite nomes de pessoas, contatos nem os nomes das empresas clientes "
        "(a carteira é sigilosa: descreva por segmento, porte e região, ex.: \"gestora de investimentos de médio "
        "porte na capital\"). Entregue só o Markdown entre "
        "<<PERSONA>> e <<FIM>>.",
    ])


def refazer(tarefa_id: int) -> str:
    """Monta a persona nova no Max (sem web) e grava como rascunho; o manual 14 não muda."""
    import carteira
    import comercial
    import tarefas

    comercial._evento(tarefa_id, "consulta_cerebro", "Clientes corporativos no Monday (contas ativas e eventos ganhos)")
    resposta = comercial.pedir_ao_max(comercial.prompt_persona(), web=False, origem="persona")
    persona = comercial._bloco(resposta, "PERSONA")
    PASTA.mkdir(parents=True, exist_ok=True)
    rascunho = PASTA / f"{PREFIXO_RASCUNHO}{tarefa_id}.md"
    rascunho.write_text(persona + "\n", encoding="utf-8")
    tarefa = tarefas.obter(tarefa_id) if tarefa_id else None
    login = tarefa["usuario"] if tarefa else ""
    rascunho.with_suffix(".json").write_text(json.dumps({"tarefa_id": tarefa_id, "pedido_por": login,
                                                         "criado_em": _agora().isoformat(timespec="seconds")}),
                                             encoding="utf-8")
    base = comercial.clientes()
    return (f"Montei uma NOVA VERSÃO da persona a partir de {len(base['contas'])} contas ativas e "
            f"{len(base['ganhos'])} eventos ganhos no Monday. Ela é um RASCUNHO (#{tarefa_id}): o manual 14 continua "
            f"valendo e nada mudou no Cérebro. Para trocar o manual, o Thomas escreve \"{FRASE_APROVAR}\" (ou "
            f"\"{FRASE_APROVAR} #{tarefa_id}\"); a versão atual fica guardada com a data.\n\n{persona}\n\n"
            + carteira.rodape(login))


def aprovar(texto: str, login: str) -> str:
    """Troca o manual 14 pelo rascunho (o citado com #n ou o mais novo). Só o Thomas (decisão 12 ainda aberta)."""
    import comercial

    if (login or "").strip().lower() != config.DONO_MAX:
        return ("Só o Thomas aprova a persona nova (o manual 14 é a base de toda prospecção). O rascunho continua "
                "guardado para ele revisar.")
    rascunhos = _rascunhos()
    if (citado := re.search(r"#\s*(\d+)", texto or "")):
        rascunhos = [r for r in rascunhos if r[0] == int(citado.group(1))]
    if not rascunhos:
        return "Não achei nenhum rascunho de persona para aprovar. Peça antes \"Refaça a persona\"."
    numero, rascunho = rascunhos[0]
    carimbo = _agora().strftime("%Y-%m-%d_%H%M%S")
    manual = comercial.PASTA_PERSONA
    guardada = ""
    if manual.exists():  # a versão que valia até agora fica guardada com a data
        destino = PASTA / f"{manual.stem}_ate_{carimbo}.md"
        shutil.copy2(manual, destino)
        guardada = f" A versão anterior ficou guardada em dados/persona/{destino.name}."
    manual.write_text(rascunho.read_text(encoding="utf-8"), encoding="utf-8")
    rascunho.rename(PASTA / f"14_persona_aprovada_{numero}_{carimbo}.md")  # não apaga: só deixa de ser rascunho
    import cerebro

    cerebro.indexar_oficiais()  # a persona aprovada passa a valer para o Prospectador e o Cérebro do Corporativo
    return f"Persona nova aprovada (rascunho #{numero}): o manual 14 foi trocado e já vale no Cérebro.{guardada}"
