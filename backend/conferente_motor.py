"""Motor único das regras do conferente (Onda 2 de novembro, 11/11/2026; copywriter-03, moviemaker-21, sonoplasta-04,
designer-06, email_marketing-03). Código puro, sem IA, sem banco e sem importar o resto do backend: o conferente do
backend (chat, legenda do Monday, e-mail) e a conferência da entrega no PC (scripts/max/conferencia_saida.py) usam
estas mesmas funções. Tudo SÓ AVISA; a única correção é a mecânica, e só no clique ("Corrigir o mecânico").

As regras de texto por empresa ficam em conferente_regras.py; as de marca (cores, logos, ritmo, som), em
marcas_regras.json. Valor "pendente_decisao_1" não é conferido.
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from conferente_regras import COMUNS, ERROS_DE_GRAFIA, REGRAS

ARQUIVO_MARCAS = Path(__file__).with_name("marcas_regras.json")
PENDENTE = "pendente_decisao_1"

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⭐⭕]")
HASHTAG = re.compile(r"#[\wÀ-ÿ]+")
TRAVESSAO = re.compile(r"[—–]")
_UF = "|".join(COMUNS["ufs"])
# Fim do nome da cidade (minúscula ou parêntese) + separador + UF: o certo é exatamente " / ". Espaço sozinho
# ("litoral de SP") e lista de UFs ("SP, RJ") não contam.
LOCAL = re.compile(rf"([a-zà-ÿ)])(\s*[,\-–—(]\s*|/\s*|\s+/(?=\S))({_UF})\b(?![a-zà-ÿ])")


@lru_cache(maxsize=1)
def marcas() -> dict:
    return json.loads(ARQUIVO_MARCAS.read_text(encoding="utf-8"))


def da_marca(empresa: str, *caminho: str):
    """Valor de marcas_regras.json da empresa (ex.: "video", "velocidade"); None se faltar ou se for pendente."""
    valor = marcas()["marcas"].get(empresa) or {}
    for chave in caminho:
        valor = valor.get(chave) if isinstance(valor, dict) else None
    return None if valor == PENDENTE else valor


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")


def _unicos(lista: list[str]) -> str:
    vistos = []
    for item in lista:
        if item.lower() not in (v.lower() for v in vistos):
            vistos.append(item)
    return ", ".join(f'"{v.strip()}"' for v in vistos[:3])


# ---------------------------------------------------------------- legenda: formato e grafia

def formato_legenda(texto: str, empresa: str, tipo: str = "") -> list[str]:
    """Regras de formato da legenda (manual 07 §3 e manuais de cada empresa)."""
    if tipo == "STORIES":
        return ["STORIES não têm legenda: a legenda escrita foi descartada"]
    regras = REGRAS.get(empresa)
    avisos = []
    if (n := len(TRAVESSAO.findall(texto))):
        avisos.append(f"{n} travessão(ões): legenda sem travessão (troque por vírgula ou ponto)")
    if ";" in texto:
        avisos.append("ponto e vírgula na legenda")
    if (n := len(EMOJI.findall(texto))) > COMUNS["max_emojis"]:
        avisos.append(f"{n} emojis (no máximo {COMUNS['max_emojis']})")
    tags = HASHTAG.findall(texto)
    if len(tags) > COMUNS["max_hashtags"]:
        avisos.append(f"{len(tags)} hashtags (até {COMUNS['max_hashtags']})")
    if (acentuadas := [t for t in tags if not t.isascii()]):
        avisos.append(f"hashtag com acento ({_unicos(acentuadas)}): escreva sem acento")
    if not regras:
        return avisos
    obrigatoria = regras["hashtag_obrigatoria"]
    if tags and obrigatoria and obrigatoria not in (t.lower() for t in tags):
        avisos.append(f"falta a hashtag {obrigatoria}")
    if (vetadas := [t for t in tags for p in regras["hashtags_vetadas"] if re.fullmatch(p, t, re.I)]):
        avisos.append(f"hashtag de outra empresa ({_unicos(vetadas)})")
    minusculo = texto.lower()
    if not any(a.lower().rstrip("!.") in minusculo for a in regras["assinatura"]):
        avisos.append(f"falta a assinatura (\"{regras['assinatura'][0]}\")")
    if not any(re.search(c, texto, re.I) for c in regras["ctas"]):
        avisos.append("CTA fora da lista aprovada da empresa")
    return avisos


def grafia(texto: str) -> list[str]:
    """Erros de digitação conhecidos (email_marketing-03: "féria de janiero" foi parar no assunto). Só avisa: a
    palavra exigida no pedido entra com a grafia correta, mas quem decide é a pessoa."""
    achados = []
    for errado, certo in ERROS_DE_GRAFIA.items():
        if (m := re.search(errado, texto or "", re.I)):
            achados.append(f"\"{m.group(0)}\" (o certo é \"{certo}\")")
    return [f"grafia a conferir: {', '.join(achados[:4])}"] if achados else []


def empresa_pela_assinatura(texto: str) -> str:
    minusculo = (texto or "").lower()
    return next((e for e, r in REGRAS.items() if any(a.lower().rstrip("!.") in minusculo for a in r["assinatura"])),
                "")


# ---------------------------------------------------------------- legenda dentro da resposta do chat

RODAPE_DO_SISTEMA = re.compile(r"\n+(?:Conferência automática|Conferência dos itens gravados|Conferência de dados)",
                               re.I)
TITULO_DA_LEGENDA = re.compile(r"^\W*legenda\b[^\n]{0,60}:\W*$", re.I | re.M)
FICHA = re.compile(rf"\b(?:lodge|vero)\s*\d{{1,4}}\s*[·|•-]\s*[^\n]+?\s/\s(?:{_UF})\b", re.I)
FIM_DO_BLOCO = re.compile(r"^\s*(?:-{3,}|\*{3,}|#{1,6}\s|\*\*[^*\n]{2,60}:?\*\*\s*$|<<)", re.M)
MAX_PARAGRAFOS = 8


def _marca_de_legenda(paragrafo: str) -> bool:
    return bool(HASHTAG.search(paragrafo) or FICHA.search(paragrafo) or empresa_pela_assinatura(paragrafo))


def legenda_do_texto(texto: str) -> str:
    """O bloco de legenda dentro da resposta do agente ("" se não houver): depois de um título "Legenda:" ou, sem
    ele, os parágrafos que terminam na última linha de hashtags, assinatura ou ficha "Lodge N · Cidade / UF"."""
    texto = RODAPE_DO_SISTEMA.split(texto or "", maxsplit=1)[0]
    if (titulo := TITULO_DA_LEGENDA.search(texto)):
        resto = texto[titulo.end():].lstrip("\n")
        fim = FIM_DO_BLOCO.search(resto)
        bloco = (resto[:fim.start()] if fim else resto).strip()
        return bloco if _marca_de_legenda(bloco) or len(bloco) > 40 else ""
    paragrafos = [p for p in re.split(r"\n\s*\n", texto)]
    ultimo = max((i for i, p in enumerate(paragrafos) if _marca_de_legenda(p)), default=None)
    if ultimo is None:
        return ""
    inicio = ultimo
    while inicio > 0 and ultimo - inicio < MAX_PARAGRAFOS - 1:
        anterior = paragrafos[inicio - 1].strip()
        if not anterior or anterior.endswith(":") or FIM_DO_BLOCO.search(anterior) or len(anterior) > 700:
            break
        inicio -= 1
    return "\n\n".join(p.strip() for p in paragrafos[inicio:ultimo + 1]).strip()


# ---------------------------------------------------------------- "Corrigir o mecânico" (só no clique)

def _sem_travessao(texto: str, trocas: list[str]) -> str:
    novo = re.sub(r"(\d)[ \t]*[—–][ \t]*(\d)", r"\1 a \2", texto)  # intervalo: "10–12 pessoas" -> "10 a 12"
    novo = re.sub(r"^[ \t]*[—–][ \t]*", "", novo, flags=re.M)  # travessão de lista no começo da linha
    novo = re.sub(r"[ \t]*[—–][ \t]*(?=\S)", lambda m: ". " if novo[m.end():m.end() + 1].isupper() else ", ", novo)
    novo = re.sub(r"[ \t]*[—–][ \t]*$", ".", novo, flags=re.M)
    if (n := len(TRAVESSAO.findall(texto))):
        trocas.append(f"{n} travessão(ões) trocado(s) por vírgula ou ponto")
    return novo


def _local_no_padrao(texto: str, trocas: list[str]) -> str:
    partes, pos, feitos = [], 0, []
    for m in LOCAL.finditer(texto):
        fim = m.end()
        if "(" in m.group(2) and texto[fim:fim + 1] == ")":
            fim += 1  # "Maresias (SP)" -> "Maresias / SP"
        partes += [texto[pos:m.start()], f"{m.group(1)} / {m.group(3)}"]
        feitos.append(m.group(0).strip())
        pos = fim
    if not feitos:
        return texto
    trocas.append(f"localização no padrão \"Cidade / UF\" ({_unicos(feitos)})")
    return "".join(partes) + texto[pos:]


def _hashtags(texto: str, empresa: str, trocas: list[str]) -> str:
    regras = REGRAS.get(empresa) or {}
    acentuadas = [t for t in HASHTAG.findall(texto) if not t.isascii()]
    novo = HASHTAG.sub(lambda m: sem_acento(m.group(0)), texto)
    if acentuadas:
        trocas.append(f"acento tirado da(s) hashtag(s) {_unicos(acentuadas)}")
    vetadas = [t for t in HASHTAG.findall(novo) for p in regras.get("hashtags_vetadas", ()) if re.fullmatch(p, t, re.I)]
    for tag in dict.fromkeys(vetadas):
        novo = re.sub(rf"[ \t]*{re.escape(tag)}\b", "", novo)
    if vetadas:
        trocas.append(f"hashtag de outra empresa tirada ({_unicos(vetadas)})")
    tags = HASHTAG.findall(novo)
    obrigatoria = regras.get("hashtag_obrigatoria")
    if tags and obrigatoria and obrigatoria not in (t.lower() for t in tags):
        linhas = novo.split("\n")
        ultima = max(i for i, l in enumerate(linhas) if HASHTAG.search(l))
        linhas[ultima] = f"{obrigatoria} {linhas[ultima].lstrip()}"
        novo = "\n".join(linhas)
        trocas.append(f"hashtag obrigatória {obrigatoria} incluída")
    return novo


def corrigir_mecanico(texto: str, empresa: str = "") -> tuple[str, list[str]]:
    """(legenda corrigida, o que mudou). Só trocas que não mudam o sentido: travessão, hashtag (acento, de outra
    empresa, obrigatória que faltou) e "Cidade / UF". Fatos, CTA e palavras vetadas continuam só como aviso."""
    trocas: list[str] = []
    novo = _sem_travessao(texto or "", trocas)
    novo = _local_no_padrao(novo, trocas)
    novo = _hashtags(novo, empresa, trocas)
    novo = re.sub(r"[ \t]+([,.])", r"\1", novo)
    novo = re.sub(r"([,.]) {2,}", r"\1 ", novo)
    return novo, trocas


# ---------------------------------------------------------------- vídeo (motion.json) e cores

PEDE_1X = re.compile(r"\b1\s*x\b|velocidade (?:normal|natural|real)|sem c[aâ]mera lenta|tempo real", re.I)


def _palavras(elementos: list) -> int:
    total = 0
    for el in elementos or []:
        if not isinstance(el, dict) or el.get("tipo") not in ("texto", "caixa", "contagem"):
            continue
        linhas = [l.get("texto", "") if isinstance(l, dict) else l for l in el.get("linhas") or []]
        total += len(re.findall(r"[\wÀ-ÿ]+", " ".join(map(str, [el.get("texto") or "", *linhas]))))
    return total


def _cor_fora(valor) -> bool:
    nome = str(valor or "").strip().lower()
    paleta = {k: v.lower() for k, v in marcas()["paleta"].items() if not k.startswith("_")}
    return bool(nome) and nome not in paleta and nome not in paleta.values() and nome not in ("preto", "#000000")


def cores_do_video(spec: dict) -> list[str]:
    """Trava de paleta (editor_video-19), só como aviso: cor fora das 4 da marca, degradê de leitura preto, véu acima
    do limite e caixa preta."""
    veu = marcas()["veu"]["opacidade_max"]
    avisos = []
    for c, cena in enumerate(spec.get("cenas") or [], 1):
        if not isinstance(cena, dict):
            continue
        if _cor_fora(cena.get("fundo")) and not str(cena.get("fundo", "")).startswith(("acervo", "trabalho")):
            avisos.append(f"cena {c}: fundo \"{cena['fundo']}\" fora da paleta")
        for el in cena.get("elementos") or []:
            if not isinstance(el, dict):
                continue
            cor_el = str(el.get("cor") or "").strip().lower()
            if el.get("tipo") == "degrade" and cor_el in ("preto", "#000000"):
                opacidade = el.get("opacidade")
                if not isinstance(opacidade, (int, float)):
                    avisos.append(f"cena {c}: degradê de leitura preto (o degradê é sempre Verde)")
                elif opacidade > veu:
                    avisos.append(f"cena {c}: véu preto em {opacidade:.0%} (até {veu:.0%})")
            elif el.get("tipo") == "caixa" and cor_el in ("preto", "#000000", "cinza"):
                avisos.append(f"cena {c}: caixa {cor_el} (caixa só Verde ou Caramelo)")
            elif _cor_fora(cor_el):
                avisos.append(f"cena {c}: cor \"{el.get('cor')}\" fora da paleta")
    return avisos


def ritmo_do_video(spec: dict, empresa: str, pedido: str = "") -> list[str]:
    """Conferência premium do motion.json (moviemaker-21): takes curtos, velocidade fora do padrão da marca, takes
    demais, durações iguais em sequência e texto que não dá tempo de ler. "ritmo_livre": true desliga o ritmo."""
    regras = marcas()["video"]
    cenas = [c for c in spec.get("cenas") or [] if isinstance(c, dict)]
    avisos = []
    padrao = da_marca(empresa, "video", "velocidade")
    livre = bool(spec.get("ritmo_livre"))
    takes = [(n, c) for n, c in enumerate(cenas, 1) if c.get("video")]
    for n, cena in takes:
        duracao = float(cena.get("duracao") or 0)
        if duracao and duracao < regras["take_min_s"] and not livre:
            avisos.append(f"cena {n}: take de {duracao:.1f} s (o padrão é de {regras['take_min_s']:.1f} a "
                          f"{regras['take_max_s']:.0f} s)".replace(".", ","))
        velocidade = float(cena.get("velocidade", padrao if isinstance(padrao, (int, float)) else 1.0))
        if isinstance(padrao, (int, float)) and abs(velocidade - padrao) > 0.01 and not PEDE_1X.search(pedido or ""):
            avisos.append(f"cena {n}: velocidade {velocidade:g}x sem pedido (o padrão da marca é {padrao:g}x)"
                          .replace(".", ","))
    total = sum(float(c.get("duracao") or 0) for c in cenas)
    if not livre and total and total <= 30 and len(takes) > regras["max_takes_ate_30s"]:
        avisos.append(f"{len(takes)} takes em {total:.0f} s (no máximo {regras['max_takes_ate_30s']} até 30 s)")
    duracoes = [round(float(c.get("duracao") or 0), 1) for _, c in takes]
    limite = regras["duracoes_iguais_seguidas_max"]
    if not livre and any(len(set(duracoes[i:i + limite + 1])) == 1 for i in range(len(duracoes) - limite)):
        avisos.append(f"{limite + 1} ou mais takes seguidos com a mesma duração (varie o ritmo)")
    for n, cena in enumerate(cenas, 1):
        duracao = float(cena.get("duracao") or 0)
        palavras = _palavras(cena.get("elementos"))
        teto = max(regras["palavras_por_cena_max"], regras["palavras_por_segundo"] * duracao)
        if duracao and palavras > teto:
            avisos.append(f"cena {n}: {palavras} palavras em {duracao:.1f} s (não dá tempo de ler; até "
                          f"{teto:.0f})".replace(".", ","))
    return avisos + cores_do_video(spec)


# ---------------------------------------------------------------- áudio (versão _com_som)

def audio(medidas: dict) -> list[str]:
    """Medidas do ffmpeg (scripts/max/conferencia_audio.py) contra a ficha sonora comum: volume, pico, buraco de
    silêncio antes da vinheta (sonoplasta-04)."""
    som = marcas()["som_comum"]
    avisos = []
    if (lufs := medidas.get("lufs")) is not None and abs(lufs - som["lufs"]) > som["lufs_tolerancia"]:
        avisos.append(f"volume em {lufs:.1f} LUFS (o padrão é {som['lufs']})".replace(".", ","))
    if (pico := medidas.get("true_peak")) is not None and pico > som["true_peak_max_db"]:
        avisos.append(f"pico em {pico:.1f} dB (até {som['true_peak_max_db']:.0f} dB)".replace(".", ","))
    vinheta = medidas.get("vinheta_em")
    for inicio, fim in medidas.get("silencios") or []:
        if vinheta is not None and inicio >= vinheta - 1.0:
            continue  # a música sai de propósito quando a vinheta entra
        if fim - inicio > som["silencio_max_s"] and inicio > 0.5 and fim < (medidas.get("duracao") or 1e9) - 0.5:
            avisos.append(f"silêncio de {fim - inicio:.1f} s no segundo {inicio:.0f}".replace(".", ","))
    return avisos


# ---------------------------------------------------------------- fotos (Corp: pessoas e logo de cliente)

ANO = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")
EVENTO_COM_GENTE = re.compile(r"confraterniza|festa|evento|convidad|formatura|casamento|aniversario|palestra|"
                              r"premia|show", re.I)


def fotos(nomes: list[str], empresa: str, ano_atual: int) -> list[str]:
    """Avisos sobre as fotos usadas, pelo nome do arquivo/pasta (designer-06; sem reconhecer imagem). Só no Corp:
    foto de evento (pode ter rosto sem autorização e logo de cliente) e foto antiga (sinais de época)."""
    vetos = da_marca(empresa, "vetos_foto")
    if not vetos:
        return []
    antigas, de_evento = [], []
    for nome in dict.fromkeys(str(n).replace("\\", "/") for n in nomes or []):
        anos = [int(a) for a in ANO.findall(nome)]
        if anos and min(anos) <= ano_atual - vetos["foto_antiga_anos"]:
            antigas.append(f"{Path(nome).name} ({min(anos)})")
        if EVENTO_COM_GENTE.search(sem_acento(nome)):
            de_evento.append(Path(nome).name)
    avisos = []
    if antigas:
        avisos.append(f"foto antiga {_unicos(antigas)}: confira sinais de época (máscara, decoração de outra data)")
    if de_evento:
        avisos.append(f"foto de evento {_unicos(de_evento)}: rosto reconhecível só com autorização de imagem e "
                      "nenhuma logo ou crachá de cliente; sem foto liberada, prefira ambiente montado, mesa posta ou "
                      "pessoas de costas")
    return avisos
