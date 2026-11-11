"""Reels tipográfico do Corporativo (Onda 2 de novembro, 11/11/2026; gestor-27 e designer-13).

No Corp o Reels alcança cerca de 3 vezes mais que o carrossel (manual 15 §2), mas os temas comerciais saíam como
carrossel parado por falta de vídeo de evento sem marca de cliente. Aqui o texto é o protagonista: 4 a 6 frases
curtas, uma por cena, sobre fundo Verde (manual 11 §6: o Corp puxa para o Verde), em Playfair Extrabold entrando
palavra por palavra, a última linha em itálico e um filete Caramelo marcando o ritmo (F4 tipográfico animado). Fecha
com a chamada e o logo do Corp (logos_empresas.py; nunca o de outra marca). Sai SEM música: o Sonoplasta põe a trilha
aprovada do Corp na versão _com_som, como em todo vídeo.

Contagem regressiva ("45 dias para fechar..."): só entra com um prazo "fechar até" VÁLIDO (backend/
prazos_comerciais.py). O backend manda o prazo vigente da peça e o trabalhador grava em _referencias/
prazo_comercial.json; este gerador só lê de lá (nunca das frases). Sem prazo válido, nada de contagem.

Uso: python motion_tipografico.py tipografico.json [--previa] [--com-som]
tipografico.json (na pasta da peça):
{"empresa": "cv_corporativo", "peca": "Reels tipográfico - fim de ano", "formato": "1080x1920",
 "kicker": "CONFRATERNIZAÇÃO", "frases": ["O ano está acabando", "e o seu time merece celebrar", "...", "..."],
 "cta": "Realize agora mesmo o seu orçamento", "saida": "entrega/Reels_Tipografico.mp4"}
Gera motion.json e receita.json ao lado (receita.py) e renderiza pelo motion.py. Formatos: 1080x1920 (Reels) e
1080x1080 (LinkedIn). A vinheta do logo entra por padrão no fim do 9:16 ("vinheta": false tira; o logo sai do fechamento).
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

if __name__ == "__main__":  # rodado pelo Max na caixa de areia: não grava .pyc em scripts/max
    sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import logos_empresas  # noqa: E402
import receita as receita_mod  # noqa: E402

EMPRESAS = ("cv_corporativo",)  # Vero e Casa Veraneio: depois das decisões de cor (decisão 1)
FRASES = (4, 6)
MAX_PALAVRAS, MAX_CARACTERES = 10, 70
CTA_PADRAO = "Realize agora mesmo o seu orçamento"  # manual 11 §6.3: um CTA por peça
ARQUIVO_PRAZO = "_referencias/prazo_comercial.json"
DURACAO_ALVO = (8.0, 15.0)  # gestor-27: 8 a 15 s; designer-13: ~12 s
# Sem dado de cliente nem canal proibido nas frases: e-mail, telefone, WhatsApp (proibido em tudo) e valores.
PROIBIDO = re.compile(r"@|\bwhats\s*app\b|\bzap\b|R\$|\bdi[áa]ria|\d[\d\s().-]{7,}\d", re.IGNORECASE)
# Medidas por formato: corpo do texto, quebra de linha (caracteres), centro vertical do bloco e posições do fechamento.
# 9:16: texto entre ~300 e ~1250 px (zonas mortas do manual 08 §3).
LAYOUT = {
    "1080x1920": {"tamanho": 88, "entrelinha": 106, "caracteres": 15, "centro": 860, "kicker": 24, "filete": 120,
                  "contagem": 230, "contagem_y": 520, "cta_y": 700, "logo_y": 1010, "logo": 135, "largura": 760},
    "1080x1080": {"tamanho": 74, "entrelinha": 90, "caracteres": 19, "centro": 520, "kicker": 22, "filete": 110,
                  "contagem": 190, "contagem_y": 250, "cta_y": 330, "logo_y": 640, "logo": 110, "largura": 940},
}


# ---------------------------------------------------------------- prazo "fechar até"

def prazo_valido(prazo, hoje: date | None = None) -> dict | None:
    """O prazo (como o backend manda) só vale com "valido", fechamento a partir de hoje e confirmação em dia."""
    hoje = hoje or date.today()
    if not isinstance(prazo, dict) or prazo.get("valido") is not True or not prazo.get("momento"):
        return None
    try:
        fechar = date.fromisoformat(str(prazo.get("fechar_ate"))[:10])
        vale_ate = date.fromisoformat(str(prazo.get("vale_ate"))[:10]) if prazo.get("vale_ate") else fechar
    except ValueError:
        return None
    faltam = (fechar - hoje).days
    if faltam < 1 or vale_ate < hoje:
        return None
    return {"momento": str(prazo["momento"])[:80], "fechar_ate": fechar.isoformat(), "faltam": faltam}


def ler_prazo(base: Path, hoje: date | None = None) -> dict | None:
    try:
        bruto = json.loads((Path(base) / ARQUIVO_PRAZO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return prazo_valido(bruto, hoje)


def gravar_prazo(rascunho: Path, prazo) -> None:
    """Trabalhador: grava (ou apaga, sem prazo válido) o prazo vigente da peça em _referencias/."""
    arquivo = Path(rascunho) / ARQUIVO_PRAZO
    if isinstance(prazo, dict) and prazo.get("valido"):
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(prazo, ensure_ascii=False, indent=2), encoding="utf-8")
    elif arquivo.is_file():
        arquivo.unlink()  # sobra de uma versão anterior: o prazo pode ter vencido


# ---------------------------------------------------------------- roteiro

def quebrar(frase: str, caracteres: int, cabe=None) -> list[str]:
    """Linhas da frase: "|" ou quebra de linha mandam; cada trecho ainda quebra (guloso) pela largura medida
    (`cabe(linha)`, com a fonte da marca) ou, sem ela, pelo número de caracteres."""
    cabe = cabe or (lambda linha: len(linha) <= caracteres)
    linhas = []
    for trecho in (p.strip() for p in re.split(r"[|\n]", frase) if p.strip()):
        atual = ""
        for palavra in trecho.split():
            if atual and not cabe(f"{atual} {palavra}"):
                linhas.append(atual)
                atual = palavra
            else:
                atual = f"{atual} {palavra}".strip()
        linhas += [atual] if atual else []
    for n in range(len(linhas) - 1):  # palavra curta ("o", "e", "à") não fica pendurada no fim da linha
        partes = linhas[n].split()
        if len(partes) > 1 and len(partes[-1]) <= 2:
            linhas[n], linhas[n + 1] = " ".join(partes[:-1]), f"{partes[-1]} {linhas[n + 1]}"
    return linhas


def _tamanho(linhas: list[str], m: dict, fontes=None, italico_ultima: bool = True) -> tuple[int, int]:
    """(tamanho, entrelinha) do bloco: diminui se a linha mais larga, medida com a fonte da marca, passa da área
    segura (m["largura"]). Sem fontes (contêiner, testes), fica o tamanho da tabela."""
    tamanho, entrelinha = m["tamanho"], m["entrelinha"]
    if fontes is None:
        return tamanho, entrelinha
    from motion_camadas import largura_texto
    larguras = [largura_texto(fontes.fonte("playfair_italico" if italico_ultima and n and n == len(linhas) - 1
                                           else "playfair", tamanho), linha) for n, linha in enumerate(linhas)]
    if (maior := max(larguras or [0])) <= m["largura"]:
        return tamanho, entrelinha
    fator = m["largura"] / maior
    return int(tamanho * fator), int(entrelinha * fator)


def conferir_frases(frases) -> list[str]:
    if not isinstance(frases, list) or not FRASES[0] <= len(frases) <= FRASES[1]:
        raise ValueError(f"Reels tipográfico: de {FRASES[0]} a {FRASES[1]} frases (texto demais cansa).")
    limpas = []
    for n, frase in enumerate(frases, 1):
        frase = re.sub(r"[ \t]+", " ", str(frase or "")).strip()
        if not frase:
            raise ValueError(f"frase {n} vazia")
        sem_quebra = re.sub(r"[|\n]", " ", frase)
        if len(sem_quebra) > MAX_CARACTERES or len(sem_quebra.split()) > MAX_PALAVRAS:
            raise ValueError(f"frase {n} longa demais (até {MAX_PALAVRAS} palavras e {MAX_CARACTERES} caracteres)")
        if PROIBIDO.search(frase):
            raise ValueError(f"frase {n}: sem e-mail, telefone, WhatsApp ou valores no Reels")
        limpas.append(frase)
    return limpas


def _bloco(linhas: list[str], tamanho: int, entrelinha: int, centro: int) -> tuple[int, int]:
    """(y do topo, y logo abaixo) do bloco de linhas centralizado em `centro`."""
    altura = entrelinha * (len(linhas) - 1) + tamanho
    topo = round(centro - altura / 2)
    return topo, topo + altura


def _cena_frase(frase: str, m: dict, kicker: str = "", fontes=None) -> list[dict]:
    cabe = None
    if fontes is not None:  # mede com a Playfair Extrabold (a mais larga) na área segura
        from motion_camadas import largura_texto
        cabe = lambda linha: largura_texto(fontes.fonte("playfair", m["tamanho"]), linha) <= m["largura"]  # noqa: E731
    linhas = quebrar(frase, m["caracteres"], cabe)
    tamanho, entrelinha = _tamanho(linhas, m, fontes, len(linhas) > 1)
    topo, base = _bloco(linhas, tamanho, entrelinha, m["centro"])
    elementos = []
    if kicker:
        elementos.append({"tipo": "texto", "texto": kicker, "fonte": "muli", "peso": 700, "tamanho": m["kicker"],
                          "cor": "caramelo", "espacamento": 9, "maiusculas": True, "y": topo - 90, "entrada": "letras"})
    elementos.append({"tipo": "texto", "linhas": linhas, "italico_ultima": len(linhas) > 1, "fonte": "playfair",
                      "tamanho": tamanho, "entrelinha": entrelinha, "cor": "branco", "y": topo,
                      "entrada": "palavra"})
    elementos.append({"tipo": "filete", "cor": "caramelo", "largura": m["filete"], "espessura": 4, "y": base + 46,
                      "entrada": "desenha"})
    return elementos


def _cena_contagem(prazo: dict, m: dict) -> list[dict]:
    """Contagem regressiva até os dias que faltam (de +12 para baixo) e o momento em itálico."""
    faltam, y = prazo["faltam"], m["contagem_y"]
    return [
        {"tipo": "contagem", "valor": faltam, "de": faltam + 12, "fonte": "playfair", "tamanho": m["contagem"],
         "cor": "caramelo", "y": y, "entrada": {"efeito": "contagem", "duracao": 1.8}},
        {"tipo": "texto", "texto": "dia para fechar" if faltam == 1 else "dias para fechar", "fonte": "muli",
         "peso": 700, "tamanho": m["kicker"] + 8, "cor": "branco", "espacamento": 6, "maiusculas": True,
         "y": y + m["contagem"] + 60},
        {"tipo": "texto", "linhas": quebrar(prazo["momento"], m["caracteres"] + 6), "fonte": "playfair", "italico": True,
         "tamanho": round(m["tamanho"] * 0.62), "entrelinha": round(m["entrelinha"] * 0.62), "cor": "creme",
         "y": y + m["contagem"] + 130, "entrada": "palavra"}]


def _cena_fechamento(cta: str, m: dict, com_logo: bool) -> list[dict]:
    linhas = quebrar(cta, m["caracteres"] + 6)
    elementos = [{"tipo": "texto", "linhas": linhas, "fonte": "playfair", "italico": True, "tamanho": round(m["tamanho"] * 0.66),
                  "entrelinha": round(m["entrelinha"] * 0.66), "cor": "creme", "y": m["cta_y"], "entrada": "palavra"}]
    base = m["cta_y"] + round(m["entrelinha"] * 0.66) * len(linhas)
    elementos.append({"tipo": "filete", "cor": "caramelo", "largura": m["filete"], "espessura": 4, "y": base + 30,
                      "entrada": "desenha"})
    if com_logo:  # manual 11 §6.2: fechamento em Verde, logo Caramelo com texto branco, ~135 px no 9:16
        elementos.append({"tipo": "imagem", "logo": "caramelo", "altura": m["logo"], "y": m["logo_y"],
                          "entrada": "escala", "sai": False})
    return elementos


def _duracao(elementos: list[dict], minimo: float) -> float:
    """A menor duração (de 0,1 em 0,1 s, a partir do tempo de leitura) em que todas as entradas cabem antes da saída."""
    from motion import linha_do_tempo
    duracao = round(minimo, 1)
    while duracao < 8:
        try:
            linha_do_tempo(elementos, duracao)
            return duracao
        except ValueError:
            duracao = round(duracao + 0.1, 1)
    raise ValueError("cena do Reels tipográfico longa demais")


def _palavras(elementos: list[dict]) -> int:
    return sum(len(" ".join(e.get("linhas") or [str(e.get("texto", ""))]).split())
               for e in elementos if e["tipo"] == "texto")


def roteiro(dados: dict, prazo: dict | None = None, hoje: date | None = None,
            fontes=None) -> tuple[dict, dict, list[str]]:
    """(motion.json, receita, avisos) do Reels tipográfico. `prazo`: o do backend/_referencias (validado aqui);
    `fontes`: motion_camadas.Fontes para medir as linhas (sem ela, só a quebra por caracteres)."""
    empresa = logos_empresas.empresa_do_ambiente(dados.get("empresa") or "cv_corporativo")
    if empresa not in EMPRESAS:
        raise ValueError(f"Reels tipográfico só do Corporativo por enquanto (pedido: {empresa}).")
    formato = dados.get("formato") or "1080x1920"
    if formato not in LAYOUT:
        raise ValueError(f"Formato do Reels tipográfico: {', '.join(LAYOUT)}")
    vinheta = com_vinheta(dados)
    if vinheta and formato != "1080x1920":
        raise ValueError("A vinheta do logo só existe no 9:16 aqui; no 1:1 o fechamento leva o logo.")
    frases = conferir_frases(dados.get("frases"))
    cta = str(dados.get("cta") or CTA_PADRAO).strip()
    if PROIBIDO.search(cta):
        raise ValueError("a chamada não pode ter e-mail, telefone, WhatsApp ou valores")
    kicker = str(dados.get("kicker") or "").strip()[:40]
    saida = str(dados.get("saida") or "entrega/Reels_Tipografico.mp4")
    m, avisos = LAYOUT[formato], []
    blocos = [_cena_frase(f, m, kicker if n == 0 else "", fontes) for n, f in enumerate(frases)]
    valido = prazo_valido(prazo, hoje)
    if valido:
        blocos.append(_cena_contagem(valido, m))
    elif prazo:
        avisos.append("prazo \"fechar até\" vencido ou sem confirmação: o Reels saiu sem contagem regressiva")
    blocos.append(_cena_fechamento(cta, m, com_logo=not vinheta))
    cenas = []
    for n, elementos in enumerate(blocos, 1):
        leitura = 0.9 + 0.25 * _palavras(elementos)  # tempo de ler, além das entradas caberem
        duracao = _duracao(elementos, max(2.0, leitura))
        cenas.append({"fundo": "verde", "duracao": duracao, "saida": f"trabalho/tipografico_{n:02d}.mp4",
                      "elementos": elementos, **({"sai": False} if n == len(blocos) else {})})
    spec = {"formato": formato, "empresa": empresa, "cascata": 0.15, "inicio": 0.3, "sai": True, "cenas": cenas,
            **({} if vinheta else {"juntar": saida})}
    total = round(sum(c["duracao"] for c in cenas), 1)
    if not DURACAO_ALVO[0] <= total <= DURACAO_ALVO[1]:
        avisos.append(f"duração das frases {total} s, fora de {DURACAO_ALVO[0]:g} a {DURACAO_ALVO[1]:g} s: "
                      "encurte ou junte frases")
    ficha = receita_mod.de_motion(spec, str(dados.get("peca") or Path(saida).stem), "reels")
    ficha.update({"molde": "tipografico", "arquivos": [receita_mod._rel(saida)],
                  "contagem": {"momento": valido["momento"], "fechar_ate": valido["fechar_ate"]} if valido else None})
    if vinheta:
        ficha["vinheta_em"] = total
        ficha["duracao_s"] = None  # soma a vinheta depois do render
    return spec, ficha, avisos


# ---------------------------------------------------------------- render

def renderizar(arquivo: Path, com_previa: bool = False, hoje: date | None = None) -> dict:
    """Grava motion.json e receita.json ao lado do tipografico.json e renderiza o Reels (sem música)."""
    import motion
    arquivo = Path(arquivo).resolve()
    base = arquivo.parent
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    from motion_camadas import Fontes, pastas_de_recursos
    empresa = logos_empresas.empresa_do_ambiente(dados.get("empresa") or "cv_corporativo")
    spec, ficha, avisos = roteiro(dados, ler_prazo(base, hoje), hoje, Fontes(pastas_de_recursos(base, empresa)))
    (base / "motion.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    resultados = motion.renderizar(base / "motion.json", com_previa)
    saida = base / (dados.get("saida") or "entrega/Reels_Tipografico.mp4")
    if com_vinheta(dados):
        import motion_vinheta
        from motion_video import duracao_do_video, juntar_cenas
        vinheta = motion_vinheta.vinheta(spec["empresa"], spec["formato"], base / "trabalho" / "vinheta.mp4", base)
        juntar_cenas([r["saida"] for r in resultados] + [vinheta["saida"]], saida)
        marcas = {saida.name: {"vinheta_em": ficha["vinheta_em"]}}  # o Sonoplasta tira a música na vinheta
        (base / "sonoplasta.json").write_text(json.dumps(marcas, ensure_ascii=False), encoding="utf-8")
        ficha["duracao_s"] = round(duracao_do_video(saida), 2)
        ficha["cenas"].append({"n": len(ficha["cenas"]) + 1, "origem": "vinheta", "de": 0,
                               "duracao_s": round(vinheta["quadros"] / motion.FPS, 2), "velocidade": None,
                               "textos": [], "logo": "vinheta"})
    (base / receita_mod.ARQUIVO).write_text(json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")
    avisos += [a for r in resultados for a in r["avisos"]]
    return {"saida": saida, "receita": base / receita_mod.ARQUIVO, "avisos": avisos,
            "previas": [p for r in resultados for p in r.get("previas", [])]}


def com_som(video: Path, empresa: str, pedido: str = "reels tipografico corporativo animado") -> tuple[Path, dict]:
    """Versão _com_som com uma faixa APROVADA da marca, sem passar pelo trabalhador (exemplo local). Só lê o
    catálogo do Drive e não mexe no rodízio do Sonoplasta."""
    import sonoplasta
    itens = json.loads((sonoplasta.BIBLIOTECA / "catalogo.json").read_text(encoding="utf-8"))
    faixa, aprovada = sonoplasta.escolher(empresa, pedido, itens=itens)
    if not faixa or not aprovada or not (arquivo := sonoplasta.arquivo_da_faixa(faixa)):
        raise RuntimeError("nenhuma faixa APROVADA desta marca disponível")
    saida = video.with_name(f"{video.stem}{sonoplasta.SUFIXO}{video.suffix}")
    sonoplasta.mixar(video, arquivo, saida, empresa, sonoplasta.vinheta_em(video.parent.parent, video.name))
    return saida, faixa


def com_vinheta(dados: dict) -> bool:
    """A vinheta do logo entra por padrão no 9:16 (Thomas, 11/11/2026); no 1:1 o fechamento já leva o logo."""
    return bool(dados.get("vinheta", (dados.get("formato") or "1080x1920") == "1080x1920"))


def instrucao(agente: str, empresa: str, entrega: str = "") -> str:
    """Bloco do prompt do Editor de Vídeo do Corporativo."""
    if agente != "editor_video" or empresa not in EMPRESAS or entrega in ("texto", "documento"):
        return ""
    exemplo = json.dumps({"empresa": empresa, "peca": "<nome da peça>", "formato": "1080x1920", "kicker": "<TIPO DE EVENTO>",
                          "frases": ["<frase 1>", "<frase 2>", "<frase 3>", "<frase 4>"], "cta": CTA_PADRAO,
                          "saida": "entrega/<Peça>.mp4"}, ensure_ascii=False)
    return ("REELS TIPOGRÁFICO DO CORP (Onda 2): SÓ quando o pedido disser Reels tipográfico, \"só texto\" ou "
            "\"frases animadas\" (Thomas, 11/11/2026: nunca por iniciativa própria). Nesse caso, NÃO monte do zero: grave na raiz desta pasta um "
            f"tipografico.json ({exemplo}) e rode: python \"{Path(__file__).as_posix()}\" tipografico.json --previa\n"
            f"De {FRASES[0]} a {FRASES[1]} frases curtas (até {MAX_PALAVRAS} palavras; \"|\" quebra a linha), do "
            "texto aprovado quando houver, no tom do manual 11; sem nome de cliente, e-mail, telefone ou valores. O "
            "gerador faz fundo Verde, Playfair palavra a palavra com a última linha em itálico, filete Caramelo, "
            "chamada e o logo do Corp no fechamento, e grava motion.json e receita.json. A contagem regressiva entra "
            f"SOZINHA só se houver prazo \"fechar até\" válido ({ARQUIVO_PRAZO}, gravado pelo sistema): nunca "
            "escreva contagem, \"faltam N dias\" ou prazo nas frases. Versão 1:1 para o LinkedIn: \"formato\": "
            "\"1080x1080\" com outra saída. A vinheta do logo entra sozinha no fim do 9:16. Entregue sem música (o Sonoplasta põe a trilha aprovada do Corp).")


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("dados", help="tipografico.json")
    args.add_argument("--previa", action="store_true", help="PNG de cada cena (em previas/)")
    args.add_argument("--com-som", action="store_true", help="também a versão _com_som (exemplo fora do trabalhador)")
    opcoes = args.parse_args()
    r = renderizar(Path(opcoes.dados), opcoes.previa)
    print(f"Reels tipográfico: {r['saida']}\nReceita: {r['receita']}")
    for aviso in r["avisos"]:
        print(f"  AVISO: {aviso}")
    if opcoes.com_som:
        saida, faixa = com_som(r["saida"], json.loads(Path(opcoes.dados).read_text(encoding="utf-8")).get("empresa")
                               or "cv_corporativo")
        print(f"Com som: {saida} ({faixa.get('estilo')})")


if __name__ == "__main__":
    main()
