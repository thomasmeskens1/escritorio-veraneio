"""Catálogo das fotos da Casa Vero e do Corporativo (Drive, SOMENTE LEITURA), para a produção no Max.

Casa Vero (pastas indicadas pelo Thomas em 26/10/2026): MARKETING/CASA VERO/FOTOS VEROS e CONTEÚDOS LUCAS. Só uma
pasta "VERO N" é do Vero N; pasta "LODGE N ..." ou sem número fica listada à parte (ex.: "LODGE 2 FAZENDA ATIBAIA"
não é o Vero 2, que fica no Guarujá).
Corporativo: CORPORATIVO/FOTOS EVENTOS (uma pasta por evento, "Cliente - Lodge N", na numeração do Corporativo) e o
acervo dos Lodges da Casa Veraneio SÓ quando o espaço N do Corporativo fica na mesma cidade do Lodge N da Casa
Veraneio (a numeração das duas empresas só coincide em parte: o Lodge 31 do Corporativo é em Atibaia; o da Casa
Veraneio, em Itatiba). As cidades vêm da cópia do banco (backend/dados/escritorio.copia.db), só leitura.
Grava CÉREBRO/catalogo_fotos_casa_vero.md e CÉREBRO/catalogo_fotos_corporativo.md. Nunca grava nada nas fotos.

Uso avulso: python scripts/max/catalogo_fotos_empresas.py
"""

import re
import sqlite3
from pathlib import Path

import comum
from catalogo_lodges import FOTOS, IGNORAR, VIDEOS
from comum import log

MARKETING = comum.DRIVE.parent / "MARKETING"
PASTAS_VERO = [MARKETING / "CASA VERO" / "FOTOS VEROS", MARKETING / "CASA VERO" / "CONTEÚDOS LUCAS"]
FOTOS_EVENTOS = comum.DRIVE.parent / "CORPORATIVO" / "FOTOS EVENTOS"
INDICE_VERO = comum.CEREBRO / "catalogo_fotos_casa_vero.md"
INDICE_CORP = comum.CEREBRO / "catalogo_fotos_corporativo.md"
BANCO_COPIA = comum.DADOS / "escritorio.copia.db"
VERO_NA_PASTA = re.compile(r"^\s*vero\s*0*(\d{1,4})\b", re.IGNORECASE)
LODGE_NA_PASTA = re.compile(r"lodges?\s*0*(\d{1,3})((?:\s*[+e&,]\s*0*\d{1,3})*)", re.IGNORECASE)
CIDADE = re.compile(r"Lodge 0*(\d+)\s+—\s+([^\n(›]+?)\s*(?:\(|›|$)", re.MULTILINE)


def _contar(pasta: Path) -> tuple[int, int]:
    fotos = videos = 0
    for arquivo in pasta.rglob("*"):
        if arquivo.is_file() and arquivo.name.lower() not in IGNORAR:
            extensao = arquivo.suffix.lower()
            fotos += extensao in FOTOS
            videos += extensao in VIDEOS
    return fotos, videos


def _linha(pasta: Path, base: Path) -> str:
    fotos, videos = _contar(pasta)
    return f"- `{pasta.relative_to(base.parent)}` — {fotos} foto(s), {videos} vídeo(s)"


def catalogo_vero() -> str:
    por_numero: dict[int, list[str]] = {}
    outras = []
    for base in PASTAS_VERO:
        if not base.exists():
            continue
        for pasta in sorted(p for p in base.iterdir() if p.is_dir()):
            if (achado := VERO_NA_PASTA.match(pasta.name)):
                por_numero.setdefault(int(achado.group(1)), []).append(_linha(pasta, base))
            else:
                outras.append(_linha(pasta, base))
    partes = ["# Fotos e vídeos da Casa Vero Imóveis (somente leitura)", "",
              f"Pastas: {', '.join(str(p) for p in PASTAS_VERO)}.",
              "Use só a pasta do Vero citado na peça. Copie o arquivo para a pasta de trabalho antes de usar; nunca "
              "grave, mova, renomeie ou apague nada nestas pastas.", "", "## Por imóvel"]
    for numero in sorted(por_numero):
        partes += [f"### Vero {numero}", *por_numero[numero]]
    partes += ["", "## Pastas sem número de Vero (NÃO são o Vero de mesmo número; só use se o pedido citar a pasta)",
               *outras]
    return "\n".join(partes) + "\n"


def _cidades(prefixo: str) -> dict[int, str]:
    """Número -> cidade, dos documentos do site no Cérebro (cópia do banco, só leitura)."""
    if not BANCO_COPIA.exists():
        return {}
    banco = sqlite3.connect(f"file:{BANCO_COPIA}?mode=ro", uri=True)
    try:
        linhas = banco.execute("SELECT fonte_ref, titulo, conteudo FROM conhecimento WHERE ativo = 1 AND fonte_ref "
                               "LIKE ?", (f"{prefixo}%",)).fetchall()
    finally:
        banco.close()
    cidades = {}
    for ref, titulo, conteudo in linhas:
        if (achado := CIDADE.search(f"{titulo}\n{conteudo}")):
            cidades.setdefault(int(ref.rsplit("-", 1)[-1]), achado.group(2).strip())
    return cidades


def _chave(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def catalogo_corporativo() -> str:
    eventos: dict[int, list[str]] = {}
    sem_espaco = []
    if FOTOS_EVENTOS.exists():
        for grupo in sorted(p for p in FOTOS_EVENTOS.iterdir() if p.is_dir()):
            pastas = [grupo] if not re.fullmatch(r"\d{4}", grupo.name) else sorted(p for p in grupo.iterdir() if p.is_dir())
            for pasta in pastas:
                linha = _linha(pasta, FOTOS_EVENTOS)
                if (achado := LODGE_NA_PASTA.search(pasta.name)):
                    for numero in [achado.group(1), *re.findall(r"\d+", achado.group(2) or "")]:
                        eventos.setdefault(int(numero), []).append(linha)
                else:
                    sem_espaco.append(linha)
    corp, casa = _cidades("corporativo/espacos/lodge-"), _cidades("site/lodges/lodge-")
    mesma_casa = {n for n, cidade in corp.items() if casa.get(n) and _chave(casa[n]) == _chave(cidade)}
    partes = ["# Fotos do Casa Veraneio Corporativo (somente leitura)", "",
              f"1) Fotos de eventos: {FOTOS_EVENTOS} — uma pasta por evento, \"Cliente - Lodge N\" na numeração do "
              "Corporativo.",
              f"2) Acervo dos Lodges da Casa Veraneio ({comum.ACERVO}) SÓ para os espaços abaixo marcados como mesma "
              "casa (mesma cidade nas duas empresas). Nos outros, o Lodge de mesmo número da Casa Veraneio é OUTRA "
              "casa: não use o acervo.",
              "Copie o arquivo para a pasta de trabalho antes de usar; nunca grave, mova, renomeie ou apague nada.", "",
              "## Por espaço do Corporativo"]
    for numero in sorted(set(corp) | set(eventos)):
        cidade = corp.get(numero, "cidade não encontrada no site do Corporativo")
        acervo = ("acervo da Casa Veraneio: PODE (mesma casa)" if numero in mesma_casa
                  else f"acervo da Casa Veraneio: NÃO (lá o Lodge {numero} é em {casa.get(numero, '—')})")
        partes += [f"### Lodge {numero} — {cidade} · {acervo}", *eventos.get(numero, ["- (sem pasta de evento)"])]
    partes += ["", "## Pastas sem número de espaço (eventos gerais; use como referência de clima e produção)",
               *sem_espaco]
    return "\n".join(partes) + "\n"


def rodar() -> None:
    for nome, gerar, destino in (("Casa Vero", catalogo_vero, INDICE_VERO),
                                 ("Corporativo", catalogo_corporativo, INDICE_CORP)):
        try:
            texto = gerar()
            destino.parent.mkdir(parents=True, exist_ok=True)
            if not destino.exists() or destino.read_text(encoding="utf-8") != texto:
                destino.write_text(texto, encoding="utf-8")
                log(f"Catálogo de fotos ({nome}) atualizado: {destino.name}")
        except Exception as erro:  # o catálogo nunca derruba o ciclo do trabalhador
            log(f"Catálogo de fotos ({nome}) falhou: {erro}")


if __name__ == "__main__":
    rodar()
