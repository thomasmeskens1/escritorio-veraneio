"""Edição rápida sem o Max (Onda 3 de novembro; criador_imagens-03, designer-02 e sonoplasta-02).

Trabalho "edicao_rapida" do trabalhador do PC, em código e sem o Claude Code (backend/edicao_rapida.py enfileira):
- acao "ler": os textos editáveis de cada slide do molde.json da peça (rascunho local, versão vigente);
- acao "textos": troca só os campos pedidos (título, CTA, contagem...), confere se o texto de partida ainda é o
  vigente, re-renderiza SÓ os slides alterados pelo molde.py e grava como nova versão na mesma pasta da peça
  (<slide>_v<N>.png; a pasta FINAL/ fica na raiz da peça, como no pasta_da_peca.raiz_da_peca);
- acao "musica": refaz a versão _com_som dos vídeos com outra faixa APROVADA da marca (sonoplasta.py), em
  <vídeo>_com_som_v<N>; o vídeo sem som e as versões anteriores ficam como estavam.
Nada é apagado: o molde.json anterior fica em molde_anteriores/ e a receita nova vai como EDITÁVEL/receita_v<N>.json.
Peça sem molde (ou com o rascunho já limpo) devolve SEM_MOLDE; vídeo sem receita devolve SEM_RECEITA.
"""

import copy
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import comum
import desdobrar_formatos
import kit_postar
import molde
import pasta_da_peca
import pasta_final
import receita
import sonoplasta

SEM_MOLDE = "SEM_MOLDE:"      # mesmos marcadores de backend/edicao_rapida.py
SEM_RECEITA = "SEM_RECEITA:"
RASCUNHOS = comum.TRABALHO / "producoes"  # mesma pasta de trabalhador_max.RASCUNHOS
ANTERIORES = "molde_anteriores"
TEMPORARIO = "_edicao_rapida.json"
# Campos que cada molde mostra (os $campos dos HTMLs de scripts/max/moldes/casa_veraneio).
EDITAVEIS = {"capa": ("kicker", "titulo", "subtitulo", "local", "contagem"),
             "ficha": ("titulo", "subtitulo", "local", "cta"),
             "fechamento": ("kicker", "titulo", "subtitulo", "linhas", "cta"), "foto": ()}
ROTULOS = {"kicker": "chamada", "titulo": "título", "subtitulo": "subtítulo", "local": "local", "cta": "CTA",
           "linhas": "linhas", "contagem": "contagem"}


# ---------------------------------------------------------------- textos

def _rascunho(payload: dict) -> Path:
    return RASCUNHOS / str(int(payload["raiz"]))


def _valor(slide: dict, campo: str):
    """Valor normalizado do campo (o mesmo formato que o formulário do chat devolve)."""
    if campo == "linhas":
        return [str(l).strip() for l in slide.get("linhas") or [] if str(l).strip()]
    if campo == "contagem":
        contagem = slide.get("contagem") or {}
        return {"numero": str(contagem.get("numero") or "").strip(), "texto": str(contagem.get("texto") or "").strip()}
    return str(slide.get(campo) or "").strip()


def campos(slide: dict) -> dict:
    return {campo: _valor(slide, campo) for campo in EDITAVEIS.get(slide.get("molde"), ())}


def _carregar(rascunho: Path) -> dict:
    if not (rascunho / desdobrar_formatos.ARQUIVO).is_file():
        raise LookupError("a peça não foi montada com os moldes (ou o rascunho do PC já foi limpo)")
    try:
        return molde.carregar(rascunho / desdobrar_formatos.ARQUIVO)
    except (ValueError, KeyError) as erro:
        raise LookupError(str(erro)) from erro


def ler(payload: dict) -> str:
    try:
        dados = _carregar(_rascunho(payload))
    except LookupError as erro:
        return f"{SEM_MOLDE} {erro}"
    return json.dumps({"empresa": dados.get("empresa") or "casa_veraneio", "formato": dados.get("formato"),
                       "slides": [{"n": n, "molde": s.get("molde"), "campos": campos(s)}
                                  for n, s in enumerate(dados["slides"], 1)]}, ensure_ascii=False)


def _gravar(slide: dict, campo: str, valor) -> None:
    if campo == "linhas":
        slide["linhas"] = [str(l).strip() for l in valor or [] if str(l).strip()]
    elif campo == "contagem":
        numero = str((valor or {}).get("numero") or "").strip()
        slide["contagem"] = {"numero": numero, "texto": str((valor or {}).get("texto") or "").strip()} if numero else None
    elif campo == "local":
        slide["local"] = molde.local_padrao(valor)
    else:
        slide[campo] = str(valor or "").strip()


def _mostrar(valor) -> str:
    if isinstance(valor, list):
        return " / ".join(valor) or "(vazio)"
    if isinstance(valor, dict):
        return " ".join(v for v in (valor.get("numero"), valor.get("texto")) if v) or "(sem contagem)"
    return valor or "(vazio)"


def aplicar(dados: dict, mudancas: list[dict]) -> tuple[dict, list[int], list[str]]:
    """(molde novo, slides alterados, linhas do resumo). Recusa campo fora do molde e texto de partida que já mudou
    (outra versão saiu depois que o formulário abriu)."""
    novo = copy.deepcopy(dados)
    alterados, linhas = [], []
    for mudanca in mudancas:
        n, campo = int(mudanca.get("n") or 0), mudanca.get("campo")
        if not 1 <= n <= len(novo["slides"]):
            raise ValueError(f"slide {n} não existe nesta peça")
        slide = novo["slides"][n - 1]
        if campo not in EDITAVEIS.get(slide.get("molde"), ()):
            raise ValueError(f"o slide {n} ({slide.get('molde')}) não tem o campo {campo!r}")
        antes = _valor(slide, campo)
        if _valor({campo: mudanca.get("antes")}, campo) != antes:
            raise ValueError(f"o {ROTULOS[campo]} do slide {n} mudou desde que o formulário abriu (saiu outra "
                             "versão): abra \"Editar textos\" de novo")
        _gravar(slide, campo, mudanca.get("depois"))
        if (depois := _valor(slide, campo)) == antes:
            continue
        molde.conferir(slide)  # R$ ou diária sem "com_valor": recusa (decisão 3)
        alterados.append(n)
        linhas.append(f"slide {n} ({slide.get('molde')}), {ROTULOS[campo]}: “{_mostrar(antes)}” → “{_mostrar(depois)}”")
    return novo, sorted(set(alterados)), linhas


def proxima_versao(entrega: Path, rascunho: Path | None) -> int:
    """Uma versão acima da maior da pasta da peça (artes, editáveis e receitas) e do .versao do rascunho."""
    numeros = [pasta_final.chave_e_versao(a.relative_to(entrega).as_posix())[1] for a in pasta_final._candidatos(entrega)]
    numeros += [pasta_final.chave_e_versao(a.name)[1] for a in (entrega / "EDITÁVEL").glob("receita*.json")]
    try:
        numeros.append(int((rascunho / ".versao").read_text().strip()) if rascunho else 1)
    except (OSError, ValueError):
        pass
    return max([1, *numeros]) + 1


def _saida(slide: dict, n: int, versao: int) -> str:
    saida = Path(slide.get("saida") or f"entrega/{n:02d}_{slide['molde']}.png")
    base = Path(pasta_final.chave_e_versao(saida.name)[0])
    return (saida.parent / f"{base.stem}_v{versao}{base.suffix}").as_posix()


def _no_drive(origem: Path, raiz_local: Path, entrega: Path) -> Path:
    relativo = origem.relative_to(raiz_local) if origem.is_relative_to(raiz_local) else Path(origem.name)
    destino = desdobrar_formatos._livre(entrega / relativo)  # nunca troca um arquivo que já está no Drive
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)
    return destino


def _receita_nova(entrega: Path, receita_nova: dict, versao: int, origem: str) -> str:
    receita_nova["conferencia"] = {"em": datetime.now().isoformat(timespec="seconds"), "origem": origem,
                                   "medido": {}, "avisos": []}
    destino = desdobrar_formatos._livre(entrega / "EDITÁVEL" / f"receita_v{versao}.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(receita_nova, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino.relative_to(entrega).as_posix()


def organizar(entrega: Path, tarefa_id: int | None, novas: list[str]) -> str:
    """FINAL/ (na raiz da peça), folha de aprovação e kit POSTAR com a versão nova. O que a produção deixou fora da
    FINAL (ex.: legenda que diverge do texto aprovado) continua fora. Nunca derruba a edição: os arquivos já estão
    no Drive."""
    raiz = pasta_da_peca.raiz_da_peca(entrega)
    final = raiz / pasta_final.PASTA
    try:
        novas_chaves = {pasta_final.chave_e_versao(n)[0] for n in novas}
        fora = []
        if final.is_dir():
            presentes = {a.relative_to(final).as_posix() for a in final.rglob("*") if a.is_file()}
            fora = [c for c in pasta_final.vigentes(entrega) if c not in presentes and c not in novas_chaves]
        vigentes = pasta_final.atualizar(entrega, fora, final)
    except Exception as erro:  # noqa: BLE001
        comum.log(f"   pasta FINAL não atualizada ({erro})")
        return ""
    linhas = [f"Pasta {pasta_final.PASTA}/: {len(vigentes)} arquivo(s) na versão vigente."]
    try:
        if (folha := pasta_final.folha(final, vigentes, raiz.name)) and tarefa_id:
            comum.enviar_arquivo(f"/api/producao/{int(tarefa_id)}/folha", folha)
    except Exception as erro:  # noqa: BLE001 - a folha fica no Drive mesmo assim
        comum.log(f"   folha de aprovação não refeita/enviada ({erro})")
    try:
        linhas.append(kit_postar.linha_do_resumo(*kit_postar.montar(final, vigentes, raiz.name)))
    except Exception as erro:  # noqa: BLE001
        comum.log(f"   kit POSTAR não montado ({erro})")
    return " ".join(linhas)


def executar_textos(payload: dict, renderizador=None) -> str:
    rascunho = _rascunho(payload)
    try:
        dados = _carregar(rascunho)
    except LookupError as erro:
        return f"{SEM_MOLDE} {erro}"
    if (dados.get("empresa") or "casa_veraneio") not in molde.EMPRESAS:
        return f"{SEM_MOLDE} os moldes ainda são só da Casa Veraneio"
    novo, alterados, linhas = aplicar(dados, payload.get("mudancas") or [])
    if not alterados:
        return "Nada mudou nos textos: a peça ficou como estava."
    entrega = desdobrar_formatos.pasta_da_entrega(payload.get("pasta") or "")
    versao = proxima_versao(entrega, rascunho)
    for n in alterados:
        novo["slides"][n - 1]["saida"] = _saida(novo["slides"][n - 1], n, versao)
    temporario = rascunho / TEMPORARIO  # só os slides alterados, com os mesmos caminhos relativos do molde.json
    temporario.write_text(json.dumps({**novo, "slides": [novo["slides"][n - 1] for n in alterados]},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        extras = {"renderizador": renderizador} if renderizador else {}
        pngs = molde.renderizar(temporario, **extras)
    finally:
        temporario.unlink(missing_ok=True)
    gerados = [_no_drive(Path(png).resolve(), (rascunho / "entrega").resolve(), entrega).relative_to(entrega).as_posix()
               for png in pngs]
    anteriores = rascunho / ANTERIORES  # o molde anterior nunca se perde
    anteriores.mkdir(exist_ok=True)
    shutil.copy2(rascunho / desdobrar_formatos.ARQUIVO,
                 desdobrar_formatos._livre(anteriores / f"molde_v{versao - 1}.json"))
    (rascunho / desdobrar_formatos.ARQUIVO).write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
    (rascunho / ".versao").write_text(str(versao))  # o próximo ajuste no Max continua a numeração
    gerados.append(_receita_nova(entrega, receita.de_molde(novo, entrega.name), versao, "edição rápida (sem Max)"))
    comum.log(f"   textos editados sem o Max: {', '.join(gerados)}")
    return "\n".join([
        f"Textos trocados sem o Max (versão {versao}): " + "; ".join(linhas) + ".",
        f"Arquivos novos em ESCRITÓRIO VERANEIO/{entrega.relative_to(comum.DRIVE.resolve()).as_posix()}:",
        *(f"- {g}" for g in gerados),
        "Os outros slides e as versões anteriores ficaram como estavam. ⚠ O editável (PPTX) ainda tem os textos "
        "anteriores: troque à mão se for usá-lo.",
        organizar(entrega, payload.get("tarefa_id"), gerados)]).strip()


# ---------------------------------------------------------------- outra música

def _receita_vigente(entrega: Path) -> dict | None:
    achadas = sorted((pasta_final.chave_e_versao(a.name)[1], a.stat().st_mtime, a)
                     for a in (entrega / "EDITÁVEL").glob("receita*.json"))
    for *_, arquivo in reversed(achadas):
        try:
            if isinstance(dados := json.loads(arquivo.read_text(encoding="utf-8")), dict):
                return dados
        except (OSError, ValueError):
            continue
    return None


def videos_da_peca(entrega: Path) -> dict[str, Path]:
    """Vídeos vigentes sem som (nome base -> arquivo); a própria vinheta e as cenas do editável ficam fora."""
    return {chave: arquivo for chave, arquivo in pasta_final.vigentes(entrega).items()
            if Path(chave).suffix.lower() in sonoplasta.VIDEOS and not Path(chave).stem.endswith(sonoplasta.SUFIXO)
            and "vinheta" not in Path(chave).stem.lower()
            and not any(p.upper() == sonoplasta.EDITAVEL for p in Path(chave).parts[:-1])}


def executar_musica(payload: dict, mixar=None) -> str:
    entrega = desdobrar_formatos.pasta_da_entrega(payload.get("pasta") or "")
    empresa = payload.get("empresa") or "casa_veraneio"
    if empresa not in sonoplasta.MARCAS:
        raise RuntimeError(f"empresa desconhecida: {empresa}")
    if (atual := _receita_vigente(entrega)) is None:
        return f"{SEM_RECEITA} a peça não tem receita (EDITÁVEL/receita.json)"
    if not (videos := videos_da_peca(entrega)):
        return f"{SEM_RECEITA} a peça não tem vídeo para trocar a música"
    rascunho = _rascunho(payload) if _rascunho(payload).is_dir() else None
    usadas = sonoplasta._trilhas_da_peca(rascunho) if rascunho else {}
    na_receita = [(atual.get("faixa") or {}).get("arquivo")] if (atual.get("faixa") or {}).get("arquivo") else []
    versao = proxima_versao(entrega, rascunho)
    mixar = mixar or sonoplasta.mixar
    gerados, linhas, faixa_nova = [], [], None
    for grupo in sonoplasta.conjuntos(sorted(videos)):
        ja = list(dict.fromkeys(na_receita + [f for nome in grupo for f in usadas.get(videos[nome].name, [])]))
        if not (faixa := sonoplasta.outra_aprovada(empresa, ja, payload.get("pedido") or "")) \
                or not (arquivo_faixa := sonoplasta.arquivo_da_faixa(faixa)):
            raise RuntimeError("não há outra faixa APROVADA desta marca na biblioteca (aprove mais faixas no "
                               "catálogo do Sonoplasta)")
        desde = 0.0
        for nome in grupo:
            video, base = videos[nome], Path(nome)
            destino = desdobrar_formatos._livre(
                entrega / base.with_name(f"{base.stem}{sonoplasta.SUFIXO}_v{versao}{base.suffix}"))
            with tempfile.TemporaryDirectory() as tmp:
                saida = Path(tmp) / destino.name
                mixar(video, arquivo_faixa, saida, empresa, sonoplasta.vinheta_em(rascunho, video.name), desde)
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saida, destino)
            if len(grupo) > 1:
                desde += sonoplasta.duracao(video)  # carrossel em MP4: a faixa segue de um slide para o outro
            usadas[video.name] = [*usadas.get(video.name, []), faixa["arquivo"]]
            gerados.append(destino.relative_to(entrega).as_posix())
        sonoplasta._registrar_uso(faixa["arquivo"])
        faixa_nova = faixa
        extra = f", {faixa['bpm']} BPM" if faixa.get("bpm") else ""
        linhas.append(f"{Path(gerados[-1]).name}: {faixa.get('estilo', '').replace('_', ' ')}{extra} (faixa aprovada)")
    if rascunho:
        (rascunho / sonoplasta.TRILHAS_DA_PECA).write_text(json.dumps(usadas, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
        (rascunho / ".versao").write_text(str(versao))
    nova = {**atual, "faixa": {"arquivo": faixa_nova["arquivo"], "estilo": faixa_nova.get("estilo", "")}}
    gerados.append(_receita_nova(entrega, nova, versao, "outra música (sem Max)"))
    comum.log(f"   outra música sem o Max: {', '.join(gerados)}")
    return "\n".join([
        f"Outra música sem o Max (versão {versao}): " + "; ".join(linhas) + ".",
        f"Arquivos novos em ESCRITÓRIO VERANEIO/{entrega.relative_to(comum.DRIVE.resolve()).as_posix()}:",
        *(f"- {g}" for g in gerados),
        "O vídeo sem som e as versões com som anteriores ficaram como estavam.",
        organizar(entrega, payload.get("tarefa_id"), gerados)]).strip()


def executar(payload: dict, renderizador=None) -> str:
    acao = payload.get("acao")
    if acao == "ler":
        return ler(payload)
    if acao == "textos":
        return executar_textos(payload, renderizador)
    if acao == "musica":
        return executar_musica(payload)
    raise RuntimeError(f"Edição rápida desconhecida: {acao!r}")
