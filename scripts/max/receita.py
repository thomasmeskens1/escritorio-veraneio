"""Receita fixa da peça (Onda 2 de novembro, 11/11/2026; editor_video-04 e criador_imagens-08).

Cada peça sai com uma ficha técnica num formato só, em JSON simples: formato, tamanho, duração, cenas, fotos
usadas, logo, faixa (trilha do Sonoplasta), textos de tela e empresa. Antes, cada vídeo tinha um manifest.json
montado do zero pelo Max, com campos diferentes a cada vez ("cena" contra "ordem", velocidade "1x" contra 1.0), e
nenhum programa lia o arquivo. Agora o Max grava receita.json na raiz do rascunho (ou o sistema monta a receita do
motion.json/molde.json), o trabalhador confere com o que voltou (medidas, duração, número de cenas, logo, textos)
e grava a versão conferida em entrega/EDITÁVEL/receita.json, que vai para o Drive junto com a peça. Divergiu: aviso
no resumo, sem barrar a entrega. É a base da Onda 3 ("Editar textos sem o Max" e o PPTX por código).

Formato (versão 1). Caminhos relativos à pasta da peça; "arquivos" relativos a entrega/:
{"versao": 1, "empresa": "cv_corporativo", "peca": "Reels tipográfico - fim de ano", "tipo": "reels",
 "formato": "1080x1920", "duracao_s": 12.4, "molde": "tipografico",
 "cenas": [{"n": 1, "origem": "fundo:verde", "de": 0, "duracao_s": 2.6, "velocidade": null,
            "textos": ["Faltam poucas semanas", "para o fim do ano"], "logo": null},
           {"n": 2, "origem": "acervo/salao.mp4", "de": 4.0, "duracao_s": 4.5, "velocidade": 0.75,
            "textos": [], "logo": "clara"}],
 "fotos": ["acervo/salao.mp4"],
 "logo": {"apelido": "caramelo", "arquivo": "logo_corp_caramelo_texto_branco.png"},
 "faixa": null, "vinheta_em": null, "contagem": null,
 "textos": ["Faltam poucas semanas", "para o fim do ano"],
 "arquivos": ["Reels_Fim_de_Ano.mp4"]}
- "tipo": reels, stories, carrossel, post, video, shorts ou documento. "duracao_s": null em arte parada.
- "cenas": uma por cena do vídeo ou por slide/arte; "origem" é a foto/vídeo usado ou "fundo:<cor>".
- "faixa": o sistema preenche com a trilha que o Sonoplasta usou ({"arquivo", "estilo"}); o Max deixa null.
- "contagem": {"momento", "fechar_ate"} só quando a peça tem contagem regressiva de prazo "fechar até".
- Ao gravar no EDITÁVEL, o sistema acrescenta "conferencia": {"em", "origem", "medido", "avisos"}.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

ARQUIVO = "receita.json"            # na raiz do rascunho (o Max grava aqui, fora de entrega/)
DESTINO = "EDITÁVEL/receita.json"   # versão conferida, dentro de entrega/ (vai para o Drive)
VERSAO = 1
TIPOS = ("reels", "stories", "carrossel", "post", "video", "shorts", "documento")
OBRIGATORIOS = ("versao", "empresa", "peca", "tipo", "formato", "cenas", "logo", "textos", "arquivos")
EMPRESAS = ("casa_veraneio", "cv_corporativo", "casa_vero")
FORMATO = re.compile(r"^(\d{3,4})x(\d{3,4})$")
ARTES = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".pdf"}
VIDEOS = {".mp4", ".mov"}
TOLERANCIA_S = 0.6        # diferença aceita entre a duração da receita e a medida (ffprobe)
TAKE_MINIMO_S = 3.5       # manual 06 §2: take de vídeo com menos que isso é corte rápido demais
PEDIU_1X = re.compile(r"\b1\s*x\b|velocidade normal|velocidade natural|sem c[aâ]mera lenta", re.IGNORECASE)


def _plano(texto) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem.lower()).strip()


def _rel(nome: str) -> str:
    return str(nome or "").replace("\\", "/").removeprefix("entrega/")


# ---------------------------------------------------------------- formato

def validar(receita) -> list[str]:
    """Problemas de formato da receita ([] = no formato fixo)."""
    if not isinstance(receita, dict):
        return ["a receita não é um objeto JSON"]
    problemas = [f"falta \"{c}\"" for c in OBRIGATORIOS if c not in receita]
    if receita.get("versao") not in (None, VERSAO):
        problemas.append(f"versão {receita.get('versao')!r} desconhecida (use {VERSAO})")
    if receita.get("empresa") and receita["empresa"] not in EMPRESAS:
        problemas.append(f"empresa desconhecida: {receita['empresa']!r}")
    if receita.get("tipo") and receita["tipo"] not in TIPOS:
        problemas.append(f"tipo {receita['tipo']!r} fora da lista ({', '.join(TIPOS)})")
    if "formato" in receita and not FORMATO.match(str(receita["formato"])):
        problemas.append(f"formato {receita['formato']!r} não é LARGURAxALTURA")
    duracao = receita.get("duracao_s")
    if duracao is not None and not isinstance(duracao, (int, float)):
        problemas.append("\"duracao_s\" precisa ser número (segundos) ou null")
    cenas = receita.get("cenas")
    if "cenas" in receita and (not isinstance(cenas, list) or not cenas):
        problemas.append("\"cenas\" precisa ser uma lista com pelo menos uma cena")
    for n, cena in enumerate(cenas if isinstance(cenas, list) else [], 1):
        if not isinstance(cena, dict):
            problemas.append(f"cena {n} não é um objeto")
            continue
        if not isinstance(cena.get("textos", []), list):
            problemas.append(f"cena {n}: \"textos\" precisa ser lista")
        velocidade = cena.get("velocidade")
        if velocidade is not None and not isinstance(velocidade, (int, float)):
            problemas.append(f"cena {n}: velocidade precisa ser número (0.75), não {velocidade!r}")
    for campo in ("textos", "arquivos", "fotos"):
        if campo in receita and not isinstance(receita[campo], list):
            problemas.append(f"\"{campo}\" precisa ser lista")
    logo = receita.get("logo")
    if "logo" in receita and logo is not None and not isinstance(logo, dict):
        problemas.append("\"logo\" precisa ser {\"apelido\", \"arquivo\"} ou null")
    return problemas


def nova(empresa: str, peca: str, tipo: str, formato: str, cenas: list[dict], **extra) -> dict:
    """Receita no formato fixo, com os campos opcionais vazios (os geradores do sistema usam esta)."""
    textos = [t for c in cenas for t in c.get("textos") or []]
    fotos = list(dict.fromkeys(c["origem"] for c in cenas if c.get("origem") and not str(c["origem"]).startswith("fundo:")))
    receita = {"versao": VERSAO, "empresa": empresa, "peca": peca, "tipo": tipo, "formato": formato,
               "duracao_s": None, "molde": None, "cenas": cenas, "fotos": fotos, "logo": None, "faixa": None,
               "vinheta_em": None, "contagem": None, "textos": textos, "arquivos": []}
    receita.update(extra)
    return receita


def _textos_do_elemento(el: dict) -> list[str]:
    if el.get("linhas") is not None:
        return [str(l.get("texto", "") if isinstance(l, dict) else l) for l in el["linhas"]]
    if el.get("tipo") == "contagem":
        return [f"{el.get('prefixo', '')}{el.get('valor')}{el.get('sufixo', '')}".strip()]
    return [str(el.get("texto") or "")]


def textos_do_motion(spec: dict) -> list[str]:
    """Textos de tela do motion.json, na ordem."""
    textos = []
    for cena in spec.get("cenas") or []:
        for el in (cena.get("elementos") or []) if isinstance(cena, dict) else []:
            if isinstance(el, dict) and el.get("tipo") in ("texto", "caixa", "contagem"):
                textos += [t for t in _textos_do_elemento(el) if t.strip()]
    return textos


def de_motion(spec: dict, peca: str = "", tipo: str = "reels") -> dict:
    """Receita montada do motion.json (quando o Max não gravou a dele)."""
    cenas, logo = [], None
    for n, cena in enumerate(spec.get("cenas") or [], 1):
        elementos = [e for e in cena.get("elementos") or [] if isinstance(e, dict)]
        textos = [t for e in elementos if e.get("tipo") in ("texto", "caixa", "contagem")
                  for t in _textos_do_elemento(e) if t.strip()]
        logos = [e.get("logo") for e in elementos if e.get("tipo") == "imagem" and e.get("logo")]
        logo = logo or (logos[0] if logos else None)
        cenas.append({"n": n, "origem": cena.get("video") or f"fundo:{cena.get('fundo')}",
                      "de": float(cena.get("de", 0)), "duracao_s": cena.get("duracao"),
                      "velocidade": cena.get("velocidade", 0.75) if cena.get("video") else None,
                      "textos": textos, "logo": logos[0] if logos else None})
    duracoes = [c["duracao_s"] for c in cenas]
    receita = nova(spec.get("empresa") or "casa_veraneio", peca, tipo, spec.get("formato", "1080x1920"), cenas,
                   molde="motion", duracao_s=round(sum(duracoes), 2) if all(duracoes) else None)
    if logo:
        receita["logo"] = {"apelido": logo, "arquivo": _arquivo_do_logo(receita["empresa"], logo)}
    if spec.get("juntar"):
        receita["arquivos"] = [_rel(spec["juntar"])]
    return receita


def de_molde(dados: dict, peca: str = "") -> dict:
    """Receita montada do molde.json (artes da Casa Veraneio)."""
    cenas = []
    for n, slide in enumerate(dados.get("slides") or [], 1):
        textos = [str(slide[c]) for c in ("kicker", "titulo", "subtitulo", "local", "cta") if slide.get(c)]
        textos += [str(l) for l in slide.get("linhas") or []]
        cenas.append({"n": n, "origem": slide.get("foto") or "fundo:verde", "de": 0, "duracao_s": None,
                      "velocidade": None, "textos": textos, "logo": slide.get("logo"), "molde": slide.get("molde"),
                      "arquivo": _rel(slide.get("saida") or f"{n:02d}_{slide.get('molde')}.png")})
    tipo = "carrossel" if len(cenas) > 1 else "post"
    receita = nova(dados.get("empresa") or "casa_veraneio", peca, tipo, dados.get("formato") or "1080x1440", cenas,
                   molde="molde")
    receita["arquivos"] = [c["arquivo"] for c in cenas]
    return receita


def _arquivo_do_logo(empresa: str, apelido: str) -> str | None:
    try:
        import logos_empresas
        return logos_empresas.arquivo_do_apelido(empresa, apelido)[0]
    except (ImportError, ValueError):
        return None


def _ler_json(arquivo: Path):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def carregar(rascunho: Path, peca: str = "") -> tuple[dict | None, str]:
    """(receita, origem): a do Max (receita.json), senão a montada do motion.json ou do molde.json."""
    rascunho = Path(rascunho)
    if (rascunho / ARQUIVO).is_file():
        receita = _ler_json(rascunho / ARQUIVO)
        return (receita if isinstance(receita, dict) else {"_invalida": True}), "max"
    if isinstance(spec := _ler_json(rascunho / "motion.json"), dict) and spec.get("cenas"):
        return de_motion(spec, peca), "motion.json"
    if isinstance(dados := _ler_json(rascunho / "molde.json"), dict) and dados.get("slides"):
        return de_molde(dados, peca), "molde.json"
    return None, ""


# ---------------------------------------------------------------- conferência na volta do Max

def _faixa_usada(rascunho: Path, arquivos: list[str]) -> dict | None:
    """A trilha que o Sonoplasta pôs no vídeo (.trilhas.json do rascunho: nome -> faixas, a última vale)."""
    trilhas = _ler_json(Path(rascunho) / ".trilhas.json") or {}
    for nome in arquivos:
        if isinstance(trilhas, dict) and (usadas := trilhas.get(nome)):
            arquivo = usadas[-1]
            estilo = re.sub(r"^.*(?:Corp|Vero|Veraneio)_", "", Path(arquivo).stem)
            return {"arquivo": arquivo, "estilo": estilo}
    return None


def _ritmo(cenas: list[dict], pedido: str) -> list[str]:
    """Aviso de ritmo (manual 06 §2): take de vídeo curto ou em 1x sem pedido. Nunca barra (1x pode ser de propósito)."""
    avisos = []
    for cena in cenas:
        origem = str(cena.get("origem") or "") if isinstance(cena, dict) else ""
        if origem.startswith("fundo:") or Path(origem).suffix.lower() not in VIDEOS:
            continue
        duracao = cena.get("duracao_s")
        if isinstance(duracao, (int, float)) and duracao < TAKE_MINIMO_S:
            avisos.append(f"ritmo: cena {cena.get('n')} com {duracao} s (take de vídeo pede {TAKE_MINIMO_S} s ou mais)")
        if cena.get("velocidade") == 1 and not PEDIU_1X.search(pedido or ""):
            avisos.append(f"ritmo: cena {cena.get('n')} em 1x sem o pedido pedir (padrão 0,75x)")
    return avisos


def conferir(receita: dict, final: Path, novos: list[str], empresa: str, medir=None, rascunho: Path | None = None,
             pedido: str = "", prazo_valido: bool = False) -> tuple[dict, list[str]]:
    """(medidas, avisos) da receita contra o que voltou do Max. `medir(caminho)` -> (largura, altura, duração|None)."""
    avisos = validar(receita)
    final = Path(final)
    entregues = [_rel(n) for n in novos]
    artes = [n for n in entregues if Path(n).suffix.lower() in ARTES and not n.upper().startswith("EDITÁVEL/")
             and not Path(n).stem.endswith("_com_som")]
    if receita.get("empresa") and receita["empresa"] != empresa:
        avisos.append(f"a receita diz empresa {receita['empresa']}, mas a peça é de {empresa}")
    medido = {}
    for nome in artes:
        if medir and (m := medir(final / nome)):
            medido[nome] = {"formato": f"{m[0]}x{m[1]}", "duracao_s": m[2]}
    formato = str(receita.get("formato") or "")
    fora = [f"{n} ({v['formato']})" for n, v in medido.items() if formato and v["formato"] != formato]
    if fora:
        avisos.append(f"formato da receita {formato}, entregue {', '.join(fora[:4])}")
    videos = [v["duracao_s"] for n, v in medido.items() if Path(n).suffix.lower() in VIDEOS and v["duracao_s"]]
    if isinstance(receita.get("duracao_s"), (int, float)) and len(videos) == 1:
        if abs(videos[0] - receita["duracao_s"]) > TOLERANCIA_S:
            avisos.append(f"duração da receita {receita['duracao_s']} s, vídeo entregue com {videos[0]} s")
    imagens = [n for n in artes if Path(n).suffix.lower() in {".png", ".jpg", ".jpeg"} and "/" not in n]
    cenas = receita.get("cenas") if isinstance(receita.get("cenas"), list) else []
    if receita.get("tipo") in ("carrossel", "stories", "post") and imagens and cenas and len(cenas) != len(imagens):
        avisos.append(f"receita com {len(cenas)} slide(s), entregues {len(imagens)} imagem(ns)")
    faltam = [n for n in receita.get("arquivos") or [] if isinstance(n, str) and _rel(n) not in entregues
              and not (final / _rel(n)).is_file()]
    if faltam:
        avisos.append(f"arquivo(s) da receita que não voltaram: {', '.join(faltam[:4])}")
    logo = receita.get("logo") if isinstance(receita.get("logo"), dict) else {}
    if logo.get("arquivo"):
        try:
            import logos_empresas
            if (outra := logos_empresas.logo_de_outra(empresa, logo["arquivo"])):
                avisos.append(f"logo da receita ({logo['arquivo']}) é de {logos_empresas.LOGOS[outra]['nome']}")
        except ImportError:
            pass
    if rascunho is not None and isinstance(spec := _ler_json(Path(rascunho) / "motion.json"), dict):
        tela = _plano(" | ".join(textos_do_motion(spec)))
        sumidos = [t for t in receita.get("textos") or [] if isinstance(t, str) and t.strip() and _plano(t) not in tela]
        if tela and sumidos:
            avisos.append(f"texto(s) da receita fora do vídeo: {'; '.join(f'“{t}”' for t in sumidos[:3])}")
    if receita.get("contagem") and not prazo_valido:
        avisos.append("contagem regressiva sem prazo \"fechar até\" válido: tire a contagem ou confirme o prazo")
    avisos += _ritmo(cenas, pedido)
    return medido, avisos


def na_producao(rascunho: Path, final: Path, novos: list[str], empresa: str, peca: str = "", pedido: str = "",
                medir=None, prazo_valido: bool = False) -> tuple[str | None, str]:
    """Confere a receita e grava a versão conferida em entrega/EDITÁVEL/receita.json. Devolve (nome relativo a
    entrega/ ou None, linha para o resumo). Sem arte nova não faz nada. Nunca derruba a entrega."""
    entregues = [_rel(n) for n in novos]
    if not any(Path(n).suffix.lower() in ARTES for n in entregues):
        return None, ""
    try:
        receita, origem = carregar(rascunho, peca)
        if receita is None:
            return None, ("⚠ Receita da peça: sem receita.json (nem motion.json ou molde.json) para conferir. A "
                          "Onda 3 (editar textos sem o Max) depende dela: peça um ajuste se precisar.")
        if receita.get("_invalida"):
            return None, "⚠ Receita da peça: o receita.json não é um JSON válido; não foi conferido."
        if not receita.get("arquivos"):
            receita["arquivos"] = [n for n in entregues if not n.upper().startswith("EDITÁVEL/")
                                   and Path(n).suffix.lower() in ARTES and not Path(n).stem.endswith("_com_som")]
        if receita.get("faixa") is None and (faixa := _faixa_usada(rascunho, receita["arquivos"])):
            receita["faixa"] = faixa
        medido, avisos = conferir(receita, final, novos, empresa, medir, rascunho, pedido, prazo_valido)
        receita["conferencia"] = {"em": datetime.now().isoformat(timespec="seconds"), "origem": origem,
                                  "medido": medido, "avisos": avisos}
        destino = Path(final) / DESTINO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(receita, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as erro:  # noqa: BLE001 - a conferência nunca derruba a entrega
        return None, f"⚠ Receita da peça: não conferida ({erro})."
    gerada = "" if origem == "max" else f" (montada pelo sistema a partir do {origem})"
    if avisos:
        return DESTINO, (f"⚠ Receita da peça{gerada}: o resultado diverge da ficha técnica. " + "; ".join(avisos[:6])
                         + ". Confira antes de aprovar.")
    cenas = len(receita.get("cenas") or [])
    return DESTINO, f"Receita da peça{gerada}: confere ({cenas} cena(s), formato {receita.get('formato')}); em {DESTINO}."


def instrucao(agente: str, entrega: str = "") -> str:
    """Bloco do prompt: o Max grava a receita no formato fixo."""
    if agente not in ("criador_imagens", "editor_video") or entrega in ("texto", "documento"):
        return ""
    exemplo = json.dumps(nova("<empresa>", "<nome da peça>", "reels", "1080x1920", [
        {"n": 1, "origem": "acervo/<arquivo>.mp4", "de": 2.0, "duracao_s": 4.5, "velocidade": 0.75,
         "textos": ["<texto de tela>"], "logo": None}], logo={"apelido": "clara", "arquivo": "<logo>.png"},
        duracao_s=4.5, arquivos=["<peça>.mp4"]), ensure_ascii=False)
    return ("RECEITA DA PEÇA (formato fixo; Onda 2): ao terminar, grave na RAIZ desta pasta (fora de entrega/) um "
            f"{ARQUIVO} com a ficha técnica da peça, SEMPRE com estes campos e tipos: {exemplo}. Regras: \"tipo\" é "
            f"{', '.join(TIPOS)}; \"formato\" LARGURAxALTURA; \"duracao_s\" em segundos (null em arte parada); uma "
            "\"cena\" por cena do vídeo ou por slide, com \"origem\" = a foto/vídeo copiado (ou \"fundo:verde\"), "
            "\"velocidade\" número (0.75) e os textos de tela exatos; \"fotos\" = todas as fotos/vídeos usados; "
            "\"logo\" = o apelido e o arquivo usados; \"faixa\": null (o Sonoplasta preenche); \"contagem\": "
            "{\"momento\", \"fechar_ate\"} só se houver contagem de prazo \"fechar até\"; \"arquivos\" = os finais "
            "em entrega/. Em vídeo, este arquivo substitui o manifest.json do editável (o sistema grava a versão "
            f"conferida em entrega/{DESTINO}). Com motion.json ou molde.json, a receita repete os mesmos dados. O "
            "sistema confere a receita com o que você entregou e avisa a equipe se divergir.")
