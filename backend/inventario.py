"""Inventário do material do imóvel no briefing, antes do plano (brainstorm de 11/11/2026, Onda 2: moviemaker-01,
editor_video-01, despachante-11 e gestor-04).

O Gestor fechava o plano de vídeo sem saber o que havia na pasta do Lodge (tarefas 246, 247 e 256: "não sei os nomes
dos 2 vídeos, a duração nem se existe take de drone"). Agora, quando o pedido cita um Lodge e é de vídeo ou
carrossel, o Gestor, o Moviemaker e o Editor de Vídeo recebem a ficha do material: cada vídeo com duração,
resolução, orientação, fps, áudio, indício de drone e cópias repetidas, mais as fotos por subpasta.

Quem lê é o trabalhador do Max, no PC (o Drive está lá), sem IA: trabalho "inventario" da fila
(scripts/max/inventario_acervo.py), só da pasta do imóvel pedido. O resultado vale 7 dias e é lido do próprio registro do
trabalho (trabalhos_max): nada é apagado, a ficha antiga só deixa de valer. Sem ficha válida, o trabalho é pedido e,
com o trabalhador livre, a montagem do contexto espera até ESPERA_S; se ele estiver ocupado, o plano segue avisando
que o material não foi lido, e a ficha fica pronta para o próximo pedido.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

TIPO = "inventario"
AGENTES = {"gestor", "moviemaker", "editor_video"}
EMPRESAS = {"casa_veraneio", "cv_corporativo"}  # o acervo dos Lodges (o Corporativo usa os espaços "mesma casa")
VALIDADE = timedelta(days=7)
VALIDADE_SEM_PASTA = timedelta(days=1)  # pasta não achada: confere de novo no dia seguinte
ESPERA_S = 45
MAX_IMOVEIS = 3
MAX_VIDEOS_NO_BLOCO = 15
LODGE = re.compile(r"\blodges?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)  # o mesmo de fichas.LODGE_CITADO
PEDE_MATERIAL = re.compile(r"\b(reels?|v[ií]deos?|takes?|cenas?|shorts?|tik ?toks?|stories|story|carross[eé]is|"
                           r"carrossel|filmage(?:m|ns)|drone|youtube)\b", re.IGNORECASE)
VELOCIDADE_PADRAO = {"casa_veraneio": 0.75}  # manual 05 §5; nas outras marcas depende da decisão 1 (em aberto)


def imoveis_citados(texto: str) -> list[str]:
    """["Lodge 32", ...] na ordem em que aparecem, sem repetir."""
    vistos: list[str] = []
    for numero in LODGE.findall(texto or ""):
        if (imovel := f"Lodge {int(numero)}") not in vistos:
            vistos.append(imovel)
    return vistos[:MAX_IMOVEIS]


def precisa(agente_id: str, empresa: str | None, pedido: str) -> list[str]:
    """Imóveis cujo material entra no contexto deste agente ([] = nenhum)."""
    if agente_id not in AGENTES or empresa not in EMPRESAS or not PEDE_MATERIAL.search(pedido or ""):
        return []
    return imoveis_citados(pedido)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def guardada(imovel: str, agora: datetime | None = None) -> dict | None:
    """A ficha mais recente ainda válida (7 dias; pasta não achada, 1 dia), ou None."""
    import producao  # import tardio: a produção importa os agentes

    agora = agora or _agora()
    linha = producao._db().execute(
        "SELECT resultado, concluido_em FROM trabalhos_max WHERE tipo = ? AND status = 'concluido' "
        "AND json_extract(payload, '$.imovel') = ? AND concluido_em >= ? ORDER BY id DESC LIMIT 1",
        (TIPO, imovel, (agora - VALIDADE).strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchone()
    if not linha:
        return None
    try:
        ficha = json.loads(linha["resultado"] or "")
    except ValueError:
        return None
    concluida = datetime.strptime(linha["concluido_em"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if not ficha.get("encontrado") and agora - concluida > VALIDADE_SEM_PASTA:
        return None
    return ficha


def pedir(imovel: str) -> int:
    """Trabalho "inventario" na fila (um só por imóvel em aberto)."""
    import producao

    return producao.trabalho_em_aberto(TIPO, "imovel", imovel) or producao.criar_trabalho_agora(TIPO, {"imovel": imovel})


def obter(imovel: str, esperar_s: float = 0.0) -> tuple[dict | None, str]:
    """(ficha, motivo de não ter ficha). Pede a leitura se preciso e espera até `esperar_s` (só chamado em thread)."""
    import drive_pc
    import producao

    if (ficha := guardada(imovel)):
        return ficha, ""
    if (falta := drive_pc.faltando()) and ("acervo" in falta or falta == "Drive"):
        return None, f"o acervo dos Lodges não está acessível no PC agora (falta: {falta})"
    trabalho_id = pedir(imovel)
    limite = time.monotonic() + esperar_s
    while time.monotonic() < limite:
        trabalho = producao.obter_trabalho(trabalho_id)
        if trabalho and trabalho["status"] in ("concluido", "falhou", "cancelado"):
            if trabalho["status"] == "falhou":
                return None, f"a leitura falhou ({(trabalho['resultado'] or '')[:150]})"
            break
        time.sleep(1.0)
    if (ficha := guardada(imovel)):
        return ficha, ""
    return None, ("o PC do Max está ocupado ou desligado agora; a leitura ficou na fila e vale para os próximos "
                  "pedidos (7 dias)")


def _resolucao(largura: int | None, altura: int | None) -> str:
    if not largura or not altura:
        return "resolução desconhecida"
    maior = max(largura, altura)
    rotulo = " (4K)" if maior >= 3840 else " (Full HD)" if maior >= 1920 else ""
    return f"{largura}×{altura}{rotulo}"


def _video(i: int, video: dict, numeros: dict[str, int]) -> str:
    if "erro" in video:
        return f"  {i}. {video['nome']}: não abriu ({video['erro']})"
    if (original := video.get("copia_de")):
        return f"  {i}. {video['nome']}: CÓPIA do arquivo {numeros.get(original, '?')} (mesmo tamanho e duração; não conta)"
    partes = [f"{video['duracao_s']:g} s" if video.get("duracao_s") else "duração desconhecida",
              _resolucao(video.get("largura"), video.get("altura")), video.get("orientacao") or "",
              f"{video['fps']:g} fps" if video.get("fps") else "", "com áudio" if video.get("audio") else "sem áudio",
              "provável DRONE (nome ou metadado)" if video.get("drone") else ""]
    return f"  {i}. {video['nome']}: " + ", ".join(p for p in partes if p)


def texto(ficha: dict, empresa: str | None = None) -> str:
    """Bloco do contexto a partir da ficha do trabalhador."""
    imovel, lido = ficha.get("imovel", "imóvel"), (ficha.get("lido_em") or "")[:10]
    if not ficha.get("encontrado"):
        return (f"MATERIAL DO {imovel.upper()} NO ACERVO (leitura automática, sem IA, em {lido}): a pasta dele NÃO foi "
                "achada nas faixas \"Lodges N - M\" do acervo. Não prometa fotos nem takes dele: diga isso no plano e "
                "proponha outra saída (anexo da equipe ou outro Lodge parecido).")
    videos = ficha.get("videos") or []
    uteis = [v for v in videos if "erro" not in v and not v.get("copia_de")]
    numeros = {v["nome"]: i for i, v in enumerate(videos, 1)}
    linhas = [f"MATERIAL DO {imovel.upper()} NO ACERVO (leitura automática, sem IA, em {lido}; pasta "
              f"\"{ficha.get('pasta', '')}\"):"]
    if ficha.get("outras_pastas"):
        linhas.append(f"- Outras pastas com o mesmo número (não lidas): {', '.join(ficha['outras_pastas'])}")
    if videos:
        linhas.append(f"- Vídeos: {len(videos)} arquivo(s), {len(uteis)} útil(eis):")
        linhas += [_video(i, v, numeros) for i, v in enumerate(videos[:MAX_VIDEOS_NO_BLOCO], 1)]
        if len(videos) > MAX_VIDEOS_NO_BLOCO:
            linhas.append(f"  ... e mais {len(videos) - MAX_VIDEOS_NO_BLOCO} vídeo(s)")
    else:
        linhas.append("- Vídeos: NENHUM na pasta. Para vídeo, ofereça logo fotos com movimento lento ou outro Lodge "
                      "parecido que tenha vídeo.")
    if ficha.get("videos_nao_lidos"):
        linhas.append(f"- Vídeos só contados (leitura parou no limite): {len(ficha['videos_nao_lidos'])}")
    por_pasta = ", ".join(f"{p} {n}" for p, n in (ficha.get("fotos_por_pasta") or {}).items())
    linhas.append(f"- Fotos: {ficha.get('fotos', 0)}" + (f" ({por_pasta})" if por_pasta else ""))
    if uteis and not any(v.get("drone") for v in uteis):
        linhas.append("- Drone: nenhum indício no nome ou nos metadados (confira antes de prometer vista aérea).")
    bruto = sum(v.get("duracao_s") or 0 for v in uteis)
    if bruto and (velocidade := VELOCIDADE_PADRAO.get(empresa or "")):
        virgula = lambda n: f"{n:g}".replace(".", ",")  # noqa: E731
        linhas.append(f"- Conta de material: {virgula(bruto)} s de vídeo bruto útil; em {virgula(velocidade)}x um take "
                      f"de 4 s gasta {virgula(4 * velocidade)} s do bruto, e o bruto todo rende até "
                      f"{bruto / velocidade:.0f} s na tela.")
    linhas.append("Planeje só com este material: cite o arquivo e o trecho (ex.: \"arquivo 1, 0:12 a 0:16\"). Se o "
                  "pedido pede algo que não está aqui (drone, um espaço sem vídeo), avise logo no começo e proponha "
                  "outra saída.")
    return "\n".join(linhas)


def bloco(agente_id: str, empresa: str | None, pedido: str, esperar_s: float | None = None) -> str:
    """Bloco para agents/perfis.contexto ("" = não se aplica). Nunca derruba o contexto."""
    imoveis = precisa(agente_id, empresa, pedido)
    if not imoveis:
        return ""
    import max_texto

    if esperar_s is None:  # só espera com o trabalhador livre (ele pede a fila a cada ~10 s)
        esperar_s = ESPERA_S if max_texto.online() else 0.0
    partes, limite = [], time.monotonic() + esperar_s  # uma espera só para todos os imóveis do pedido
    if esperar_s and len(imoveis) > 1:  # todos entram na fila antes da espera
        for imovel in imoveis:
            try:
                guardada(imovel) or pedir(imovel)
            except Exception:  # noqa: BLE001
                log.exception("Inventário do %s: não entrou na fila.", imovel)
    for imovel in imoveis:
        try:
            ficha, motivo = obter(imovel, max(0.0, limite - time.monotonic()))
        except Exception:  # noqa: BLE001
            log.exception("Inventário do %s: falhou.", imovel)
            continue
        partes.append(texto(ficha, empresa) if ficha else
                      f"MATERIAL DO {imovel.upper()}: ainda não lido ({motivo}). Não prometa takes, drone nem "
                      "espaços que ninguém conferiu: liste no plano o que precisa ser conferido no material.")
    return "\n\n".join(partes)
