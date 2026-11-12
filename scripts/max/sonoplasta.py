"""Sonoplasta (Thomas, 05/11/2026): todo vídeo sai em DUAS versões, a entregue sem som (de qualquer agente,
desde 11/11/2026; antes só a do Editor de Vídeo) e a `_com_som`, com a trilha
da biblioteca da marca ("caso a equipe não se sinta satisfeita com o áudio produzido").

Roda no trabalhador, depois que o Max entrega o vídeo: sem IA e sem custo. Escolhe a faixa da biblioteca da empresa
(as aprovadas primeiro; enquanto nenhuma foi aprovada, as "para aprovação", avisando no resumo) pelo clima do pedido
e em rodízio, ajusta ao tamanho do vídeo (emenda com crossfade se o vídeo for maior que a faixa), entra e sai em
fade e fica em -14 LUFS (padrão das redes). Se o vídeo tem a vinheta do logo, a música sai quando ela começa e a
trilha da vinheta (efeitos e assinatura sonora aprovados) assume, sem sobreposição. Se o vídeo já tem som de
verdade (fala, som ambiente), a música fica por baixo e abaixa quando ele aparece.

Uso: python sonoplasta.py <video.mp4> <empresa> [pedido]   (gera <video>_com_som.mp4 ao lado)
"""

import json
import math
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import comum

MARCAS = {"casa_veraneio": "CASA VERANEIO", "cv_corporativo": "CASA VERANEIO CORP", "casa_vero": "CASA VERO"}
BIBLIOTECA = comum.DRIVE / "MARKETING" / "MOTION GRAPHICS - para aprovação" / "BIBLIOTECA DE MÚSICAS - para aprovação"
ESPELHO = comum.DADOS / "biblioteca_musicas.json"  # cópia para o chat do Sonoplasta (o container não vê o Drive)
USO = comum.TRABALHO / "sonoplasta_uso.json"       # quando cada faixa entrou num vídeo (rodízio entre os vídeos)
TRILHAS_DA_PECA = ".trilhas.json"                  # no rascunho: a faixa de cada vídeo (para "troque a música")
MARCACOES = "sonoplasta.json"                      # no rascunho, escrito pelo Editor: onde a vinheta começa
SUFIXO = "_com_som"
VIDEOS = {".mp4", ".mov"}
EDITAVEL = "EDITÁVEL"
APROVADA, REPROVADA = "aprovada", "reprovada"
EMENDA_S = 2.0       # crossfade quando a faixa precisa repetir
FADE_ENTRADA_S = 0.4
SAI_ANTES_DA_VINHETA_S = 0.9   # a música termina de sair logo depois que a vinheta começa
LUFS = -14
VOZ_DB = -45.0       # pico acima disso = o vídeo tem som de verdade (o AAC silencioso do motion.py fica em -91 dB)
MUSICA_SOB_VOZ = 0.35

# Clima pedido -> direção do andamento (-1 mais lenta, +1 mais rápida). Palavras sem acento.
CALMA = re.compile(r"calm|tranquil|relax|suave|aconcheg|acolhed|intimis|por do sol|golden|fim de tarde|brisa|"
                   r"descans|sereno|contempla", re.I)
ANIMADA = re.compile(r"animad|energi|festa|celebr|danc|vibrant|alegr|virada|reveillon|carnaval|contagem|lancament|"
                     r"agito|balada", re.I)
TROCAR_MUSICA = re.compile(r"(troc|troq|mud|outr|substitu|diferent)\w*\s+(\w+\s+){0,3}(musica|trilha|som|audio)|"
                           r"(musica|trilha|som|audio)\s+(\w+\s+){0,3}(outr|diferent|nov)\w*", re.I)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def _ffmpeg(programa: str = "ffmpeg") -> str:
    from motion_video import achar_ffmpeg

    return achar_ffmpeg(programa) or programa


def _rodar(args: list, **extra) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=comum.SEM_JANELA, **extra)


def duracao(arquivo: Path) -> float:
    saida = _rodar([_ffmpeg("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                    str(arquivo)], timeout=60).stdout.strip()
    return float(saida)


# ---------------------------------------------------------------- biblioteca

def catalogo() -> list[dict]:
    """O catálogo do Drive (onde fica o status de aprovação), espelhado em backend/dados para o chat do Sonoplasta.
    Drive fora do ar: vale o último espelho."""
    try:
        itens = json.loads((BIBLIOTECA / "catalogo.json").read_text(encoding="utf-8"))
        try:
            ESPELHO.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return itens
    except (OSError, ValueError):
        try:
            return json.loads(ESPELHO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []


def faixas_da_marca(empresa: str, itens: list[dict] | None = None) -> tuple[list[dict], bool]:
    """(faixas que podem entrar, se são todas aprovadas). Reprovada nunca entra; com alguma aprovada, só as aprovadas."""
    marca = MARCAS.get(empresa, MARCAS["casa_veraneio"])
    da_marca = [f for f in (catalogo() if itens is None else itens)
                if f.get("marca") == marca and f.get("status") != REPROVADA]
    aprovadas = [f for f in da_marca if f.get("status") == APROVADA]
    return (aprovadas, True) if aprovadas else (da_marca, False)


def arquivo_da_faixa(faixa: dict) -> Path | None:
    """O original em alta qualidade (WAV no PC) ou, sem ele, o MP3 da biblioteca no Drive."""
    for candidato in (Path(faixa.get("original") or ""), BIBLIOTECA / faixa.get("arquivo", "")):
        if candidato.suffix and candidato.is_file():
            return candidato
    return None


def _ler_uso() -> dict:
    """{"ultimo": {arquivo: quando}, "historico": [{arquivo, empresa, peca, em, origem}]}. O formato antigo
    ({arquivo: quando}) vira o "ultimo". Nada é apagado do histórico (decisão 17)."""
    try:
        dados = json.loads(USO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    if not isinstance(dados, dict):
        dados = {}
    if "historico" not in dados:
        dados = {"ultimo": {k: v for k, v in dados.items() if isinstance(v, (int, float))}, "historico": []}
    return dados


def _usos() -> dict:
    return _ler_uso().get("ultimo") or {}


def _registrar_uso(arquivo: str, empresa: str = "", peca: str = "", origem: str = "sonoplasta") -> None:
    dados = _ler_uso()
    dados["ultimo"][arquivo] = agora = time.time()
    dados["historico"].append({"arquivo": arquivo, "empresa": empresa, "peca": peca, "em": agora, "origem": origem})
    try:
        USO.parent.mkdir(parents=True, exist_ok=True)
        USO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def registrar_uso(arquivo: str, empresa: str, peca: str = "", origem: str = "fora") -> None:
    """Mixagem feita fora do Sonoplasta (Reels tipográfico, mixagem à mão) também entra no rodízio (sonoplasta-17)."""
    if arquivo:
        _registrar_uso(arquivo, empresa, peca, origem)


RODIZIO_PECAS = 3       # sonoplasta-17 (ajuste do crítico): faixas das últimas 3 produções da marca perdem pontos
PENALIDADE_RODIZIO = 3.0  # menos que o estilo citado pelo nome (5): o pedido explícito ainda ganha


def recentes(empresa: str, pecas: int = RODIZIO_PECAS) -> set[str]:
    """Faixas usadas nas últimas `pecas` produções da empresa (vários vídeos da mesma peça contam uma vez)."""
    vistas, faixas = [], set()
    for uso in reversed(_ler_uso()["historico"]):
        if uso.get("empresa") != empresa:
            continue
        chave = uso.get("peca") or f"_{uso.get('em')}"
        if chave not in vistas:
            if len(vistas) >= pecas:
                break
            vistas.append(chave)
        faixas.add(uso.get("arquivo"))
    return faixas


def pontuar(faixa: dict, pedido: str) -> float:
    """Quanto a faixa combina com o pedido: estilo citado pelo nome vale muito; palavras do clima e da descrição
    contam um ponto cada; "calma"/"animada" puxam pelo andamento (BPM)."""
    texto = _sem_acento(pedido)
    estilo = faixa.get("estilo", "").replace("_", " ")
    pontos = 5.0 if estilo and estilo in texto else 0.0
    palavras = set(re.findall(r"[a-z]{4,}", _sem_acento(f"{estilo} {faixa.get('clima', '')} {faixa.get('legenda', '')}")))
    pontos += sum(1 for p in palavras if re.search(rf"\b{p}", texto))
    direcao = (1 if ANIMADA.search(texto) else 0) - (1 if CALMA.search(texto) else 0)
    return pontos + direcao * (float(faixa.get("bpm") or 100) - 105) / 10


def escolher(empresa: str, pedido: str = "", evitar: set[str] = frozenset(),
             itens: list[dict] | None = None) -> tuple[dict | None, bool]:
    """A faixa que mais combina com o pedido; empate vai para a usada há mais tempo (rodízio). `evitar`: as que esta
    peça já usou (pedido de troca da música)."""
    faixas, aprovadas = faixas_da_marca(empresa, itens)
    faixas = [f for f in faixas if f.get("arquivo") not in evitar] or faixas
    if not faixas:
        return None, False
    usos, vizinhas = _usos(), recentes(empresa)
    return max(faixas, key=lambda f: (round(pontuar(f, pedido) - (PENALIDADE_RODIZIO if f.get("arquivo") in vizinhas
                                                                  else 0.0), 3),
                                      -usos.get(f["arquivo"], 0.0))), aprovadas


def outra_aprovada(empresa: str, ja_usadas: list[str], pedido: str = "",
                   itens: list[dict] | None = None) -> dict | None:
    """Botão "Outra música" (Onda 3, sonoplasta-02): só faixa APROVADA da marca, nunca a que está no vídeo agora
    (a última de `ja_usadas`) e, enquanto houver, nenhuma que a peça já usou. None = não há outra aprovada."""
    marca = MARCAS.get(empresa)
    aprovadas = [f for f in (catalogo() if itens is None else itens)
                 if marca and f.get("marca") == marca and f.get("status") == APROVADA and f.get("arquivo")]
    atual = ja_usadas[-1] if ja_usadas else None
    candidatas = ([f for f in aprovadas if f["arquivo"] not in ja_usadas]
                  or [f for f in aprovadas if f["arquivo"] != atual])
    return escolher(empresa, pedido, itens=candidatas)[0] if candidatas else None


# ---------------------------------------------------------------- mixagem

def tem_som(video: Path) -> bool:
    """O vídeo tem áudio de verdade (não só o AAC silencioso que o motion.py põe nas cenas)?"""
    saida = _rodar([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a:0?", "-af", "volumedetect",
                    "-f", "null", "-"], timeout=300).stderr
    achado = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", saida)
    return bool(achado) and achado.group(1) != "-inf" and float(achado.group(1)) > VOZ_DB


def vinheta_em(rascunho: Path | None, nome: str) -> float | None:
    """Segundo em que a vinheta do logo começa no vídeo final (o Editor anota em sonoplasta.json na raiz)."""
    if not rascunho:
        return None
    try:
        marcas = json.loads((rascunho / MARCACOES).read_text(encoding="utf-8"))
        valor = (marcas.get(nome) or marcas.get(Path(nome).name) or {}).get("vinheta_em")
        return float(valor) if valor is not None else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


QUEDA_DO_FIM_DB = 5.0
JANELA_S = 0.5


def fim_util(faixa: Path) -> float:
    """Até onde a faixa tem corpo: as do ACE-Step terminam em silêncio ou numa saída 8 a 10 dB mais baixa entre 31 e
    38 s (medido em 05/11/2026), e a emenda ou o meio de um vídeo longo caíam nesse buraco. É o fim da última janela
    de 0,5 s que ainda fica a menos de 5 dB do nível típico (mediana, suavizado em 2 s) da faixa."""
    total = duracao(faixa)
    amostras = int(48000 * JANELA_S)
    saida = _rodar([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(faixa), "-af",
                    f"aresample=48000,asetnsamples={amostras},astats=metadata=1:reset=1,"
                    "ametadata=print:key=lavfi.astats.Overall.RMS_level", "-f", "null", "-"], timeout=300).stderr
    niveis = [float(v) if v not in ("-inf", "inf", "nan") else -120.0
              for v in re.findall(r"RMS_level=(\S+)", saida)]
    if len(niveis) < 8:
        return total
    # nível suavizado em 2 s (uma batida mais fraca não conta como fim)
    suave = [sum(niveis[max(0, i - 3):i + 1]) / len(niveis[max(0, i - 3):i + 1]) for i in range(len(niveis))]
    tipico = sorted(suave)[len(suave) // 2]
    ultima = max(i for i, v in enumerate(suave) if v >= tipico - QUEDA_DO_FIM_DB)
    return min(total, max(total / 2, (ultima + 1) * JANELA_S))


def filtro(dur: float, dur_faixa: float, copias: int, vinheta: float | None, com_som: bool,
           inicio: float = 0.0) -> str:
    """Grafo do ffmpeg. Entradas: 0 = vídeo, 1..copias = a faixa (já sem o silêncio do fim: `dur_faixa`), depois a
    trilha da vinheta (se houver). `inicio`: de onde a faixa começa (slides de um carrossel em sequência)."""
    fim = min(dur, vinheta + SAI_ANTES_DA_VINHETA_S * 0.3) if vinheta is not None else dur
    saida = min(SAI_ANTES_DA_VINHETA_S, fim / 3) if vinheta is not None else min(2.0, max(0.5, fim * 0.12))
    partes = [f"[{n}:a]atrim={f'{inicio:.3f}' if n == 1 and inicio else 0}:{dur_faixa:.3f},asetpts=PTS-STARTPTS[c{n}]"
              for n in range(1, copias + 1)]
    atual = "[c1]"
    for n in range(2, copias + 1):
        partes.append(f"{atual}[c{n}]acrossfade=d={EMENDA_S}:c1=qsin:c2=qsin[e{n}]")
        atual = f"[e{n}]"
    partes.append(f"{atual}atrim=0:{fim:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={FADE_ENTRADA_S},"
                  f"afade=t=out:st={max(0.0, fim - saida):.3f}:d={saida:.3f}[m]")
    mix = "[m]"
    if com_som:  # a música por baixo e abaixando quando o som do vídeo aparece
        partes.append(f"[m]volume={MUSICA_SOB_VOZ}[mb];[0:a]asplit=2[s1][s2];"
                      "[mb][s1]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=500[md];"
                      "[md][s2]amix=inputs=2:normalize=0:duration=longest[mv]")
        mix = "[mv]"
    if vinheta is not None:
        atraso = int(vinheta * 1000)
        partes.append(f"[{copias + 1}:a]adelay={atraso}:all=1[vh];{mix}[vh]amix=inputs=2:normalize=0:duration=longest[mx]")
        mix = "[mx]"
    partes.append(f"{mix}loudnorm=I={LUFS}:TP=-1.5:LRA=11,aresample=48000,apad,atrim=0:{dur:.3f}[a]")
    return ";".join(partes)


def _trilha_da_vinheta(empresa: str, pasta: Path) -> Path | None:
    try:
        from audio_sintese import salvar
        from audio_vinhetas import TRILHAS, trilha

        if empresa not in TRILHAS:
            return None
        sinal, reverb = trilha(empresa)
        return salvar(sinal, pasta / "vinheta", reverb=reverb, cauda=0.0, manter_wav=False)
    except Exception:  # noqa: BLE001 - sem a trilha da vinheta, a música só sai em fade
        return None


def ponto_de_inicio(desde: float, dur_faixa: float) -> float:
    """Onde o próximo slide pega a faixa: segue de onde o anterior parou e volta ao começo quando faltam menos de
    8 s de corpo (num 5 s isso evita cair no fim da música)."""
    inicio = desde % max(1.0, dur_faixa)
    return 0.0 if dur_faixa - inicio < 8.0 else inicio


def mixar(video: Path, faixa: Path, saida: Path, empresa: str, vinheta: float | None = None,
          desde: float = 0.0) -> Path:
    """`desde`: segundos da faixa já tocados nos slides anteriores do mesmo carrossel (0 = do começo)."""
    dur, dur_faixa = duracao(video), fim_util(faixa)
    inicio = ponto_de_inicio(desde, dur_faixa) if desde else 0.0
    fim = min(dur, vinheta + 1.0) if vinheta is not None else dur
    restante = dur_faixa - inicio
    copias = 1 if restante >= fim else 1 + math.ceil((fim - restante) / max(1.0, dur_faixa - EMENDA_S))
    with tempfile.TemporaryDirectory() as tmp:
        trilha_vinheta = _trilha_da_vinheta(empresa, Path(tmp)) if vinheta is not None else None
        if trilha_vinheta is None:
            vinheta = None
        entradas = ["-i", str(video)] + ["-i", str(faixa)] * copias + (["-i", str(trilha_vinheta)] if vinheta is not None else [])
        audio = ["-c:a", "pcm_s24le"] if saida.suffix.lower() == ".mov" else ["-c:a", "aac", "-b:a", "256k"]
        resultado = _rodar([_ffmpeg(), "-y", "-loglevel", "error", *entradas,
                            "-filter_complex", filtro(dur, dur_faixa, copias, vinheta, tem_som(video), inicio),
                            "-map", "0:v", "-map", "[a]", "-c:v", "copy", *audio, "-ar", "48000",
                            "-movflags", "+faststart", "-t", f"{dur:.3f}", str(saida)], timeout=900)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg: {resultado.stderr.strip()[-400:]}")
    return saida


def nome_da_faixa(faixa: dict) -> str:
    return Path(faixa.get("arquivo", "")).stem


def versao_com_som(video: Path, empresa: str, pedido: str = "", rascunho: Path | None = None,
                   evitar: set[str] = frozenset(), escolhida: tuple[dict, bool] | None = None,
                   desde: float = 0.0) -> tuple[Path, dict, bool]:
    """Gera <video>_com_som ao lado do vídeo. Devolve (arquivo, faixa usada, se a faixa já é aprovada).
    `escolhida`: (faixa, aprovada) já escolhida para o conjunto (carrossel); `desde`: onde ela continua."""
    saida = video.with_name(f"{video.stem}{SUFIXO}{video.suffix}")
    if "vinheta" in video.stem.lower() and empresa in MARCAS:  # a própria vinheta: só a trilha dela, sem música
        from audio_vinhetas import montar

        return montar(empresa, video, saida), {"arquivo": "", "estilo": "trilha da vinheta"}, True
    faixa, aprovada = escolhida or escolher(empresa, pedido, evitar)
    if not faixa or not (arquivo := arquivo_da_faixa(faixa)):
        raise RuntimeError("nenhuma faixa da biblioteca desta empresa está disponível")
    mixar(video, arquivo, saida, empresa, vinheta_em(rascunho, video.name), desde)
    _registrar_uso(faixa["arquivo"], empresa, rascunho.name if rascunho else video.parent.name)
    return saida, faixa, aprovada


_NUMERO_FINAL = re.compile(r"[\s_-]*\d{1,3}$")


def conjuntos(videos: list[str]) -> list[list[str]]:
    """Vídeos da mesma peça em partes (slide_1, slide_2...; carrossel em MP4) ficam juntos, na ordem do feed; os
    demais saem sozinhos. Só o nome decide: mesmo tronco e um número no fim (sonoplasta-06, 11/11/2026)."""
    grupos: dict[tuple, list[str]] = {}
    for nome in videos:
        caminho = Path(nome)
        tronco = _NUMERO_FINAL.sub("", caminho.stem)
        numerado = tronco != caminho.stem and bool(tronco)
        chave = (caminho.parent.as_posix(), tronco.lower(), caminho.suffix.lower()) if numerado else (nome,)
        grupos.setdefault(chave, []).append(nome)

    def numero(nome: str) -> int:
        achado = re.search(r"(\d{1,3})$", Path(nome).stem)
        return int(achado.group(1)) if achado else 0
    return [sorted(g, key=numero) for g in grupos.values()]


# ---------------------------------------------------------------- na produção (trabalhador_max)

def _trilhas_da_peca(rascunho: Path) -> dict:
    try:
        return json.loads((rascunho / TRILHAS_DA_PECA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def e_troca_de_musica(pedido: str) -> bool:
    return bool(TROCAR_MUSICA.search(_sem_acento(pedido)))


def na_producao(rascunho: Path, final: Path, novos: list[str], empresa: str, pedido: str,
                ajuste: bool = False) -> tuple[list[str], str]:
    """Versão com som de cada vídeo novo da entrega (nomes relativos a `final`). Num ajuste que só pede outra música,
    sem vídeo novo, refaz a versão com som dos vídeos que já existem com outra faixa. Devolve (nomes gerados, linha
    para o resumo). Nunca derruba a entrega: o que falhar vira aviso."""
    def e_video(nome: str) -> bool:  # cenas brutas do editável (EDITÁVEL/CENAS) não ganham música
        caminho = Path(nome)
        return (caminho.suffix.lower() in VIDEOS and not caminho.stem.endswith(SUFIXO)
                and not any(p.upper() == EDITAVEL for p in caminho.parts[:-1]))
    videos = [n for n in novos if e_video(n)]
    troca = ajuste and e_troca_de_musica(pedido)
    if not videos and troca:
        videos = sorted(r for a in final.rglob("*") if e_video(r := a.relative_to(final).as_posix()))
    if not videos:
        return [], ""
    usadas = _trilhas_da_peca(rascunho)
    gerados, linhas, falhas = [], [], []
    for grupo in conjuntos(videos):
        # Carrossel em MP4: uma faixa só para todos os slides, em sequência, para soarem como um conjunto.
        escolhida, desde, linha_do_grupo = None, 0.0, False
        if len(grupo) > 1:
            evitar = {f for n in grupo for f in usadas.get(n, [])} if troca else set()
            escolhida = escolher(empresa, pedido, evitar)
            if not escolhida[0]:
                escolhida = None
        for nome in grupo:
            evitar = set(usadas.get(nome, [])) if troca else set()
            try:
                extra = {"escolhida": escolhida, "desde": desde} if escolhida else {}
                saida, faixa, aprovada = versao_com_som(final / nome, empresa, pedido, rascunho, evitar, **extra)
                if escolhida:
                    desde += duracao(final / nome)
            except Exception as erro:  # noqa: BLE001
                falhas.append(f"{nome} ({erro})")
                continue
            gerados.append(saida.relative_to(final).as_posix())
            if faixa.get("arquivo"):
                usadas[nome] = [*usadas.get(nome, []), faixa["arquivo"]]
            rotulo = faixa.get("estilo", "").replace("_", " ")
            extra = f", {faixa['bpm']} BPM" if faixa.get("bpm") else ""
            em_aprovacao = "" if aprovada else " (faixa ainda em aprovação)"
            if escolhida and linha_do_grupo:
                continue  # o conjunto aparece numa linha só (a mesma faixa)
            primeiro = Path(gerados[-1]).name
            nomes = f"{primeiro} e os outros slides, em sequência" if escolhida else primeiro
            linhas.append(f"{nomes}: {rotulo}{extra}{em_aprovacao}")
            linha_do_grupo = True
    try:
        (rascunho / TRILHAS_DA_PECA).write_text(json.dumps(usadas, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    texto = ""
    if linhas:
        texto = ("Sonoplasta: cada vídeo saiu em duas versões, sem som e com som. Trilha: " + "; ".join(linhas) + ". "
                 "Para outra música, peça um ajuste (ex.: \"troque a música por uma mais animada\").")
    if falhas:
        texto += f"\n⚠ Sonoplasta: versão com som não gerada para {'; '.join(falhas)}. O vídeo sem som segue normal."
    return gerados, texto.strip()


if __name__ == "__main__":
    arquivo, faixa_usada, _ = versao_com_som(Path(sys.argv[1]), sys.argv[2], " ".join(sys.argv[3:]))
    print(arquivo, "<-", faixa_usada.get("arquivo"))
