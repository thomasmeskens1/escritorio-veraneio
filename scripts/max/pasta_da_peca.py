"""Uma pasta por peça no Drive e o tipo da pasta conferido (brainstorm de 11/11/2026, Onda 2: social_media-01 e
gestor-07).

- Peça de item do Monday: a pasta é "SIGLA ｜ TIPO - DESCRIÇÃO #<item>", com o TIPO e a descrição do item (o backend
  manda em producao["item_monday"], backend/pasta_peca.py). Nova produção do mesmo item usa a MESMA pasta: a 1ª fica
  na raiz (como sempre) e as seguintes em v2/, v3/... A FINAL/ e a POSTAR/ ficam na raiz da peça, sempre com a
  versão mais recente. O "#<item>" acha a pasta mesmo se o item for renomeado.
- Sem item e sem tipo no pedido, o tipo saía do agente ("VÍDEO" para um carrossel de PNG, tarefa 271): agora sai dos
  arquivos entregues (só imagens: 1 = POST, várias = CARROSSEL; vídeo vertical = REELS, outro = VÍDEO).
- Aviso quando já existe pasta parecida da mesma empresa (duas pastas para a mesma peça). Nada é renomeado nem
  movido: pastas antigas ficam como estão.
"""

import difflib
import re
from pathlib import Path

SIGLA_EMPRESA = {"casa_veraneio": "VERANEIO", "cv_corporativo": "CORP", "casa_vero": "VERO"}
_PROIBIDOS = re.compile(r'[<>:"/\\|?*\n\r\t｜#]')
_EMPRESAS_NO_NOME = re.compile(r"\s*[-–—]?\s*\b(?:CASA VERANEIO CORPORATIVO|CASA VERANEIO CORP|CASA VERANEIO|"
                               r"CASA VERO IMÓVEIS|CASA VERO|CV CORP)\b\s*")
VERSAO = re.compile(r"^v(\d{1,3})$", re.IGNORECASE)
NOME_DA_PASTA = re.compile(r"^(VERANEIO|CORP|VERO) ｜ ([A-ZÀ-Ü-]+) - (.*?)(?: #(\d+))?(?: \(\d+\))?$")
IMAGENS, VIDEOS = {".png", ".jpg", ".jpeg"}, {".mp4", ".mov"}
LIMITE_NOME = 90
PARECIDA = 0.82  # semelhança mínima entre descrições para avisar


def nome_do_item(producao: dict) -> str | None:
    """"VERANEIO ｜ REELS - RÉVEILLON LODGE 239 #1234" (None se a peça não veio de um item do Monday)."""
    item = producao.get("item_monday") or {}
    if not item.get("id"):
        return None
    sigla = SIGLA_EMPRESA.get(producao.get("empresa") or "casa_veraneio", "VERANEIO")
    tipo = item.get("tipo") or "PEÇA"
    descricao = _PROIBIDOS.sub(" ", item.get("descricao") or producao.get("titulo") or "").upper()
    descricao = re.sub(r"\s+", " ", _EMPRESAS_NO_NOME.sub(" ", descricao)).strip(" .-") or "PEÇA"
    sufixo = f" #{item['id']}"
    inicio = f"{sigla} ｜ {tipo} - "
    return inicio + descricao[:max(LIMITE_NOME - len(inicio) - len(sufixo), 10)].rstrip(" .-") + sufixo


def pasta_do_item(raiz: Path, item_id: int) -> Path | None:
    """Pasta já criada para o item (termina em "#<item>"), na pasta do andar."""
    if not raiz.is_dir():
        return None
    return next((p for p in sorted(raiz.iterdir()) if p.is_dir() and p.name.endswith(f"#{item_id}")), None)


def versoes(pasta: Path) -> list[int]:
    return sorted(int(m.group(1)) for p in pasta.iterdir() if p.is_dir() and (m := VERSAO.match(p.name)))


def pasta_da_versao(raiz: Path, producao: dict) -> Path | None:
    """Nova produção de um item que já tem pasta: <pasta do item>/v<N> (a raiz é a v1). None = pasta nova."""
    item = producao.get("item_monday") or {}
    if not item.get("id") or not (existente := pasta_do_item(raiz, item["id"])):
        return None
    if not any(existente.iterdir()):
        return existente  # criada e vazia: a 1ª produção usa a raiz
    return existente / f"v{max([1, *versoes(existente)]) + 1}"


def raiz_da_peca(entrega: Path) -> Path:
    """A pasta da peça (onde ficam FINAL/ e POSTAR/): a de cima, se a entrega é uma subpasta de versão."""
    return entrega.parent if VERSAO.match(entrega.name) and entrega.parent.name else entrega


def tipo_declarado(producao: dict, padroes: list[tuple[str, str]]) -> str | None:
    """TIPO do item do Monday; senão o tipo citado no título ou no pedido (`padroes` do trabalhador)."""
    if (tipo := (producao.get("item_monday") or {}).get("tipo")):
        return tipo
    texto = f"{producao.get('titulo') or ''} {(producao.get('texto') or '')[:600]}"
    return next((t for t, padrao in padroes if re.search(padrao, texto, re.IGNORECASE)), None)


def tipo_pelos_arquivos(novos: list[str], medir=None) -> str | None:
    """Tipo pelo que foi entregue (só a raiz da entrega; editável e cenas não contam). `medir(nome)` -> (l, a, d)."""
    artes = [n for n in novos if "/" not in n]
    videos = [n for n in artes if Path(n).suffix.lower() in VIDEOS]
    imagens = [n for n in artes if Path(n).suffix.lower() in IMAGENS]
    if videos:
        medida = medir(videos[0]) if medir else None
        return "REELS" if medida and medida[1] > medida[0] else "VÍDEO"
    if imagens:
        return "POST" if len(imagens) == 1 else "CARROSSEL"
    return None


def conferir_tipo(producao: dict, entrega: Path, novos: list[str], padroes: list[tuple[str, str]],
                  medir=None) -> tuple[Path, str]:
    """(pasta de entrega, aviso). Sem tipo declarado, a pasta nova ganha o tipo dos arquivos ("ARTE"/"VÍDEO" do
    agente era só reserva). Ajuste, pasta já existente ou subpasta de versão: fica como está."""
    if producao.get("base") or entrega.exists() or VERSAO.match(entrega.name) or tipo_declarado(producao, padroes):
        return entrega, ""
    if not (pelo_arquivo := tipo_pelos_arquivos(novos, medir)) or not (m := NOME_DA_PASTA.match(entrega.name)):
        return entrega, ""
    if m.group(2) == pelo_arquivo:
        return entrega, ""
    resto = re.sub(r" \(\d+\)$", "", entrega.name[len(f"{m.group(1)} ｜ {m.group(2)} - "):])  # descrição e #item
    nova, n = entrega.with_name(f"{m.group(1)} ｜ {pelo_arquivo} - {resto}"), 2
    while nova.exists():
        nova, n = entrega.with_name(f"{m.group(1)} ｜ {pelo_arquivo} - {resto} ({n})"), n + 1
    return nova, f"Tipo da pasta pelos arquivos entregues: {pelo_arquivo} (o pedido não dizia o formato)."


def parecidas(raiz: Path, nome: str) -> list[str]:
    """Outras pastas da mesma empresa com descrição quase igual (só aviso)."""
    if not (m := NOME_DA_PASTA.match(nome)) or not raiz.is_dir():
        return []
    achadas = []
    for pasta in sorted(raiz.iterdir()):
        if not pasta.is_dir() or pasta.name == nome or not (outra := NOME_DA_PASTA.match(pasta.name)):
            continue
        if outra.group(1) != m.group(1) or (m.group(4) and outra.group(4) == m.group(4)):
            continue
        if difflib.SequenceMatcher(None, m.group(3), outra.group(3)).ratio() >= PARECIDA:
            achadas.append(pasta.name)
    return achadas[:3]


def aviso_de_parecidas(entrega: Path) -> str:
    """Linha do resumo quando a pasta da peça é nova e já existe outra parecida."""
    if raiz_da_peca(entrega) != entrega or entrega.exists() or not (achadas := parecidas(entrega.parent, entrega.name)):
        return ""
    return ("⚠ Já existe pasta parecida da mesma empresa no Drive: " + "; ".join(f"\"{a}\"" for a in achadas)
            + ". Confira se não é a mesma peça (nada foi renomeado nem movido).")


def antes_de_copiar(producao: dict, entrega: Path, novos: list[str], padroes: list[tuple[str, str]],
                    medir=None) -> tuple[Path, list[str]]:
    """Chamado pelo trabalhador antes de copiar os finais ao Drive: (pasta de entrega conferida, linhas do resumo)."""
    entrega, aviso_tipo = conferir_tipo(producao, entrega, novos, padroes, medir)
    return entrega, [linha for linha in (aviso_tipo, aviso_de_parecidas(entrega)) if linha]
