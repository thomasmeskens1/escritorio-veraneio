"""Origem de cada foto, take e faixa da peça (Onda 3 de novembro; criador_imagens-06, editor_video-05, sonoplasta-17).

Roda no trabalhador depois da receita conferida (receita.py): lê entrega/EDITÁVEL/receita.json, descobre de onde veio
cada arquivo (acervo dos Lodges, Marketing > LODGES ou SABORES CV, pastas da Casa Vero ou do Corporativo) e pede ao
backend os avisos de capa/take repetido (só aviso). A lista vai junto do /concluir e o backend grava
(backend/uso_material.py; este arquivo tem outro nome para não colidir com ele). Sem IA e sem custo; nada aqui barra a entrega nem grava nas pastas de fotos.

O Max copia o arquivo para acervo/ da pasta da peça; a receita guarda a cópia. Por isso o Max anota em cada cena a
"fonte" (o caminho original). Sem ela, o original é procurado pelo nome e tamanho só nas pastas do Lodge da peça.
"""

import json
import os
import re
from pathlib import Path

import comum

IMOVEL = re.compile(r"\b(lodge|vero)s?\s*(?:n[ºo°.]*\s*)?#?0*(\d{1,3})\b", re.IGNORECASE)
VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".webm"}
LIMITE_BUSCA = 4000   # arquivos olhados por peça ao procurar um original sem "fonte" (o Drive é lento)


def raizes() -> list[tuple[str, Path]]:
    """(nome da fonte, pasta raiz), da mais específica para a mais geral."""
    import acervo_marketing
    import catalogo_fotos_empresas
    return [("marketing_lodges", acervo_marketing.LODGES), ("sabores", acervo_marketing.SABORES),
            *(("vero", p) for p in catalogo_fotos_empresas.PASTAS_VERO),
            ("corp", catalogo_fotos_empresas.FOTOS_EVENTOS), ("acervo", comum.ACERVO)]


def classificar(caminho: Path, lista: list[tuple[str, Path]] | None = None) -> tuple[str, str] | None:
    """(fonte, caminho relativo à raiz) se o arquivo está numa das pastas de fotos."""
    for nome, raiz in lista if lista is not None else raizes():
        try:
            return nome, Path(caminho).relative_to(raiz).as_posix()
        except ValueError:
            continue
    return None


def imovel_de(texto: str) -> str | None:
    # o último citado: num caminho, "Lodges 1 - 50/Lodge 12" é o Lodge 12 (a pasta mais funda)
    achados = [a for a in IMOVEL.finditer(texto or "") if not re.match(r"\s*-\s*\d", (texto or "")[a.end():])]
    return f"{achados[-1].group(1).lower()} {int(achados[-1].group(2))}" if achados else None


def pastas_do_imovel(imovel: str | None) -> list[Path]:
    """Onde procurar o original de uma cópia: só as pastas do Lodge da peça (acervo e Marketing)."""
    if not imovel or not imovel.startswith("lodge"):
        return []
    numero = int(imovel.split()[1])
    pastas = []
    try:
        import acervo_marketing
        import catalogo_lodges
        pastas += acervo_marketing.pastas_do_lodge(numero)
        for faixa, inicio, fim in catalogo_lodges.pastas_de_faixa(comum.ACERVO):
            if inicio <= numero <= fim:
                pastas += [p for p in faixa.iterdir() if p.is_dir() and imovel_de(p.name) == imovel]
    except OSError:
        pass
    return pastas


def procurar(copia: Path, pastas: list[Path], limite: int = LIMITE_BUSCA) -> Path | None:
    """O original da cópia (mesmo nome e tamanho: o Max copia com shutil.copy2)."""
    try:
        tamanho = copia.stat().st_size
    except OSError:
        tamanho = None
    vistos = 0
    for pasta in pastas:
        for raiz, _dirs, arquivos in os.walk(pasta, onerror=lambda _: None):
            vistos += len(arquivos)
            if copia.name in arquivos:
                achado = Path(raiz) / copia.name
                try:
                    if tamanho is None or achado.stat().st_size == tamanho:
                        return achado
                except OSError:
                    pass
            if vistos > limite:
                return None
    return None


def _ler(arquivo: Path):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def origens(rascunho: Path, final: Path, pedido: str = "", lista: list[tuple[str, Path]] | None = None,
            buscar: bool = True) -> list[dict]:
    """A lista para o backend: {tipo, papel, fonte, caminho, imovel, de, duracao_s} por foto, take e faixa."""
    import receita as receita_mod
    dados = _ler(Path(final) / receita_mod.DESTINO)
    if not isinstance(dados, dict):
        dados, _ = receita_mod.carregar(rascunho)
    if not isinstance(dados, dict) or dados.get("_invalida"):
        return []
    lista = raizes() if lista is None else lista
    imovel_pedido = imovel_de(pedido)
    saida, vistos, cache = [], set(), {}

    def resolver(origem: str, fonte: str = "") -> tuple[str, str, str | None]:
        for candidato in filter(None, (fonte, origem)):
            caminho = Path(candidato)
            if caminho.is_absolute() and (achado := classificar(caminho, lista)):
                return achado[0], achado[1], imovel_de(achado[1]) or imovel_pedido
        if origem.replace("\\", "/").startswith("anexos/"):
            return "anexo", Path(origem).name, imovel_pedido
        copia = Path(rascunho) / origem
        if buscar and imovel_pedido and copia.is_file():
            if imovel_pedido not in cache:
                cache[imovel_pedido] = pastas_do_imovel(imovel_pedido)
            if (original := procurar(copia, cache[imovel_pedido])) and (achado := classificar(original, lista)):
                return achado[0], achado[1], imovel_de(achado[1]) or imovel_pedido
        return "desconhecida", Path(origem).name, imovel_pedido

    cenas = [c for c in dados.get("cenas") or [] if isinstance(c, dict)]
    primeira = True
    for cena in cenas:
        origem = str(cena.get("origem") or "")
        if not origem or origem.startswith("fundo:") or origem == "vinheta":
            continue
        video = Path(origem).suffix.lower() in VIDEOS
        fonte, caminho, imovel = resolver(origem, str(cena.get("fonte") or ""))
        papel = "take" if video else ("capa" if primeira else "foto")
        primeira = False
        saida.append({"tipo": "video" if video else "foto", "papel": papel, "fonte": fonte, "caminho": caminho,
                      "imovel": imovel, "de": cena.get("de") if video else None,
                      "duracao_s": cena.get("duracao_s") if video else None})
        vistos.add(origem)
    for origem in dados.get("fotos") or []:  # fotos da receita fora das cenas
        if isinstance(origem, str) and origem not in vistos and not origem.startswith("fundo:"):
            video = Path(origem).suffix.lower() in VIDEOS
            fonte, caminho, imovel = resolver(origem)
            saida.append({"tipo": "video" if video else "foto", "papel": "take" if video else "foto",
                          "fonte": fonte, "caminho": caminho, "imovel": imovel, "de": None, "duracao_s": None})
    faixa = dados.get("faixa") if isinstance(dados.get("faixa"), dict) else {}
    if faixa.get("arquivo"):
        saida.append({"tipo": "faixa", "papel": "faixa", "fonte": "biblioteca", "caminho": faixa["arquivo"],
                      "imovel": imovel_pedido, "de": None, "duracao_s": None})
    return saida


def na_producao(producao: dict, rascunho: Path, final: Path, novos: list[str]) -> tuple[list[dict], str]:
    """(origens para o /concluir, linha de aviso para o resumo). Nunca derruba a entrega."""
    if not any(Path(n).suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"} for n in novos):
        return [], ""
    try:
        lista = origens(rascunho, final, producao.get("texto") or "")
    except Exception as erro:  # noqa: BLE001
        comum.log(f"   origens da peça não lidas ({erro})")
        return [], ""
    if not lista:
        return [], ""
    try:
        avisos = comum.chamar("POST", f"/api/uso-material/{producao['tarefa_id']}/conferir",
                              {"empresa": producao.get("empresa") or "casa_veraneio", "origens": lista}).get("avisos") or []
    except Exception as erro:  # noqa: BLE001 - backend antigo ou fora: sem aviso, o registro vai no /concluir
        comum.log(f"   avisos de material repetido não consultados ({erro})")
        avisos = []
    linha = ("⚠ Material repetido (só aviso): " + "; ".join(avisos[:6]) + ". Se foi de propósito, siga; se não, "
             "peça um ajuste com outra capa ou outro trecho.") if avisos else ""
    return lista, linha


def instrucao(producao: dict) -> str:
    """Bloco do prompt: anotar a fonte original e a lista do que já saiu do mesmo Lodge (para variar)."""
    if producao.get("agente") not in ("criador_imagens", "editor_video", "designer") or \
            producao.get("entrega") in ("texto", "documento"):
        return producao.get("ja_usados") or ""
    texto = ("ORIGEM DAS FOTOS (Onda 3): em cada cena da receita.json, acrescente \"fonte\" com o caminho ORIGINAL "
             "completo do arquivo no acervo, no material do Marketing ou na pasta da empresa (não o da cópia em "
             "acervo/); em vídeo, \"de\" e \"duracao_s\" são o trecho usado do arquivo original. O sistema registra "
             "o que cada peça usou e avisa quando uma capa ou um take se repete.")
    return "\n\n".join(filter(None, [texto, producao.get("ja_usados") or ""]))
