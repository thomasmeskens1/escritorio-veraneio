"""Kit POSTAR de cada peça (brainstorm de 11/11/2026, Onda 2: designer-35, social_media-02 fase 1 e gestor-07).

Para publicar, o Social Media baixava os PNGs um a um, abria o .docx só para copiar a legenda e conferia a ordem pelo
nome do arquivo (slide1.png, slide_1.png, Carrossel_Janeiro_01.png...). Agora, depois da FINAL/, o trabalhador monta
FINAL/POSTAR/ em código, sem Max:
- as artes na ordem do feed, com o prefixo da empresa e o tipo da peça: VERANEIO_CARROSSEL_01.png, 02...; do vídeo,
  a versão com som (a que vai ao ar); vídeo acima de VIDEO_ATE_MB não é duplicado: o POSTAR.txt aponta o da FINAL/;
- LEGENDA.txt com a legenda pronta para copiar (do "Legenda - ....docx" da entrega; sem ele, do texto aprovado);
- POSTAR.txt: ordem, capa, qual vídeo usar, hashtags e os avisos da conferência (tipo da peça contra os arquivos,
  mais de 5 hashtags, falta de legenda).
POSTAR/ é só cópia: refeito a cada entrega, com a versão vigente; os originais continuam na pasta da peça.
Pendente: texto alternativo por slide (precisa do Max olhar a foto) e o comentário fixo no item do Monday.
"""

import re
import shutil
from pathlib import Path

import pasta_da_peca

PASTA = "POSTAR"
LEGENDA = "LEGENDA.txt"
LEIA_ME = "POSTAR.txt"
IMAGENS, VIDEOS, DOCUMENTOS_POSTAVEIS = {".png", ".jpg", ".jpeg"}, {".mp4", ".mov"}, {".pdf"}
SUFIXO_COM_SOM = "_com_som"  # sonoplasta.SUFIXO
VIDEO_ATE_MB = 300           # acima disso o vídeo não é duplicado no Drive
MAX_HASHTAGS = 5             # manual 02 §10
HASHTAG = re.compile(r"(?<![\w&])#[^\s#.,;:!?]+")
SEM_LEGENDA = {"STORIES"}    # stories não têm legenda (manual 09)
PRECISA_VIDEO = {"REELS", "SHORTS", "TIKTOK", "YOUTUBE"}


def da_pasta(nome: str) -> tuple[str, str]:
    """("VERANEIO", "CARROSSEL") do nome "VERANEIO ｜ CARROSSEL - ..." da pasta da peça; ("PECA", "PECA") se não segue."""
    m = pasta_da_peca.NOME_DA_PASTA.match(nome or "")
    return (m.group(1), m.group(2)) if m else ("PECA", "PECA")


def artes_para_postar(vigentes: list[str]) -> list[str]:
    """Artes da raiz da FINAL/ na ordem do feed; de cada vídeo, só a versão com som quando ela existe."""
    raiz = [n for n in vigentes if "/" not in n and Path(n).suffix.lower() in IMAGENS | VIDEOS | DOCUMENTOS_POSTAVEIS
            and not n.upper().startswith("FOLHA DE APROVA")]
    com_som = {Path(n).stem[:-len(SUFIXO_COM_SOM)] for n in raiz if Path(n).stem.endswith(SUFIXO_COM_SOM)}
    return [n for n in raiz if not (Path(n).suffix.lower() in VIDEOS and Path(n).stem in com_som)]


def legenda_do_docx(arquivo: Path) -> str:
    from docx import Document

    paragrafos = [p.text.strip() for p in Document(str(arquivo)).paragraphs]
    texto = "\n".join(paragrafos).strip()
    return re.sub(r"\n{3,}", "\n\n", texto)


def achar_legenda(final: Path, vigentes: list[str], aprovada: str | None) -> tuple[str, str]:
    """(texto da legenda, de onde veio). Docx da entrega primeiro; senão o texto aprovado do Copywriter."""
    for nome in vigentes:
        if Path(nome).suffix.lower() == ".docx" and Path(nome).name.lower().startswith("legenda"):
            try:
                if (texto := legenda_do_docx(final / nome)):
                    return texto, nome
            except Exception:  # noqa: BLE001 - docx ilegível: tenta o texto aprovado
                continue
    if (aprovada or "").strip():
        return aprovada.strip(), "texto aprovado na conversa"
    return "", ""


def conferir_tipo(tipo: str, artes: list[str]) -> str:
    """O tipo da peça (pasta) contra os arquivos: "" se bate."""
    imagens = [n for n in artes if Path(n).suffix.lower() in IMAGENS]
    videos = [n for n in artes if Path(n).suffix.lower() in VIDEOS]
    if tipo == "CARROSSEL" and len(artes) < 2:
        return f"a peça é CARROSSEL, mas a FINAL tem {len(artes)} arte(s)"
    if tipo == "POST" and (len(imagens) != 1 or videos):
        return f"a peça é POST (uma imagem), mas a FINAL tem {len(imagens)} imagem(ns) e {len(videos)} vídeo(s)"
    if tipo in PRECISA_VIDEO and not videos:
        return f"a peça é {tipo}, mas a FINAL não tem vídeo"
    return ""


def montar(final: Path, vigentes: list[str], nome_da_peca: str, aprovada: str | None = None) -> tuple[list[str], list[str]]:
    """Refaz FINAL/POSTAR/; devolve (arquivos do kit, avisos)."""
    sigla, tipo = da_pasta(nome_da_peca)
    artes = artes_para_postar(vigentes)
    destino = final / PASTA
    destino.mkdir(parents=True, exist_ok=True)
    avisos = [a for a in (conferir_tipo(tipo, artes),) if a]
    copiar, ordem = {}, []
    for i, nome in enumerate(artes, 1):
        origem = final / nome
        novo = f"{sigla}_{tipo}_{i:02d}{origem.suffix.lower()}" if len(artes) > 1 else f"{sigla}_{tipo}{origem.suffix.lower()}"
        if origem.suffix.lower() in VIDEOS and origem.stat().st_size > VIDEO_ATE_MB * 1024 * 1024:
            ordem.append(f"{i}. {nome} (vídeo grande: poste direto da pasta FINAL)")
            continue
        copiar[novo] = origem
        ordem.append(f"{i}. {novo}  (de FINAL/{nome})")
    legenda, fonte = ("", "") if tipo in SEM_LEGENDA else achar_legenda(final, vigentes, aprovada)
    if tipo not in SEM_LEGENDA and not legenda:
        avisos.append("sem legenda pronta (nenhum \"Legenda - ....docx\" na entrega nem texto aprovado)")
    if len(hashtags := HASHTAG.findall(legenda)) > MAX_HASHTAGS:
        avisos.append(f"a legenda tem {len(hashtags)} hashtags (o manual pede até {MAX_HASHTAGS})")
    feitos = set(copiar) | ({LEGENDA} if legenda else set()) | {LEIA_ME}
    for antigo in [a for a in destino.iterdir() if a.is_file()]:  # cópia de uma versão anterior: sai do kit
        if antigo.name not in feitos:
            antigo.unlink()
    for novo, origem in copiar.items():
        alvo = destino / novo
        if not (alvo.exists() and alvo.stat().st_size == origem.stat().st_size
                and alvo.stat().st_mtime >= origem.stat().st_mtime):
            shutil.copy2(origem, alvo)
    if legenda:
        (destino / LEGENDA).write_text(legenda + "\n", encoding="utf-8")
    (destino / LEIA_ME).write_text(_leia_me(nome_da_peca, ordem, legenda, fonte, hashtags, avisos), encoding="utf-8")
    return sorted(feitos), avisos


def _leia_me(nome: str, ordem: list[str], legenda: str, fonte: str, hashtags: list[str], avisos: list[str]) -> str:
    linhas = [f"PRONTO PARA POSTAR — {nome}", "", "Ordem de publicação (o 1º é a capa):",
              *(ordem or ["(nenhuma arte)"]), ""]
    if legenda:
        linhas += [f"Legenda: em {LEGENDA} (copie e cole; fonte: {fonte}).",
                   f"Hashtags na legenda: {len(hashtags)}" + (f" ({' '.join(hashtags)})" if hashtags else ""), ""]
    if avisos:
        linhas += ["CONFIRA ANTES DE POSTAR:", *(f"- {a}" for a in avisos), ""]
    linhas.append("Arquivos copiados da pasta FINAL (versão vigente). Revisão e publicação são sempre humanas.")
    return "\n".join(linhas) + "\n"


def linha_do_resumo(arquivos: list[str], avisos: list[str]) -> str:
    texto = f"Kit {PASTA}/ na FINAL: {len(arquivos)} arquivo(s), com {LEGENDA} e {LEIA_ME} prontos para copiar."
    if LEGENDA not in arquivos:
        texto = f"Kit {PASTA}/ na FINAL: {len(arquivos)} arquivo(s), com {LEIA_ME}."
    return texto + (f" ⚠ Confira: {'; '.join(avisos)}." if avisos else "")
