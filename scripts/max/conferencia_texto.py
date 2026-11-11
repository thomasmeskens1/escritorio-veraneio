"""Texto aprovado = texto da peça (Onda 1 de novembro, 11/11/2026; copywriter-02, fase 1).

O backend manda ao Max a legenda/texto que o Copywriter escreveu e a equipe aprovou na conversa (backend/
texto_aprovado.py). Aqui ficam o bloco do prompt ("copie, não reescreva") e a conferência em código, sem IA, antes
da pasta FINAL: os números da legenda entregue (datas, contagens, capacidade) precisam estar no texto aprovado, e as
frases que o Copywriter mandou tirar não podem voltar. Evidência: tarefas 258 e 265/266 ("4 suítes" virou "Quatro
quartos"; "2 meses" virou "dois meses" e "ainda dá tempo" voltou). Na Casa Vero, a legenda não pode citar "Lodge".
"""

import re
import unicodedata
import zipfile
from pathlib import Path

LIMITE_TEXTO = 8000
NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
           "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30,
           "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100}
# Unidade (sem acento, singular) -> nome no aviso. Só número ligado a uma destas conta (evita alarme falso).
UNIDADES = {"suite": "suítes", "quarto": "quartos", "banheiro": "banheiros", "pessoa": "pessoas",
            "hospede": "hóspedes", "convidado": "convidados", "noite": "noites", "diaria": "diárias", "dia": "dias",
            "semana": "semanas", "mes": "meses", "meses": "meses", "hora": "horas", "minuto": "minutos",
            "vaga": "vagas", "cama": "camas", "andar": "andares", "andares": "andares", "lugar": "lugares",
            "lugares": "lugares", "m2": "m²", "km": "km", "piscina": "piscinas", "lodge": "Lodges"}
MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
_NUMERO = r"\d{1,4}|" + "|".join(sorted(NUMEROS, key=len, reverse=True))
FATO = re.compile(rf"\b({_NUMERO})\s+(?:(?:de|ate|a|e|mais|novas?|novos?|grandes?|amplas?|amplos?)\s+)?"
                  r"(suites?|quartos?|banheiros?|pessoas?|hospedes?|convidados?|noites?|diarias?|dias?|semanas?|"
                  r"mes|meses|horas?|minutos?|vagas?|camas?|andar|andares|lugar|lugares|m2|m²|km|piscinas?|lodges?)\b")
DATA = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?\b")
DATA_EXTENSO = re.compile(rf"\b(\d{{1,2}})\s+de\s+({'|'.join(MESES)})\b")
ANO = re.compile(r"\b(20[2-4]\d)\b")
TIRAR = re.compile(r"\b(?:tire|tirar|tira|remova|remover|corte|cortar|retire|retirar|evite|evitar|sem a frase|"
                   r"troque|trocar|substitua|substituir|"
                   r"n[aã]o use|n[aã]o usar|exclua|excluir)\b[^\"“'\n]{0,40}[\"“']([^\"”'\n]{3,80})[\"”']",
                   re.IGNORECASE)
LODGE = re.compile(r"\blodges?\b", re.IGNORECASE)


def _plano(texto: str) -> str:
    """Minúsculas, sem acento e com espaços simples (a comparação ignora isso)."""
    sem = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem.lower().replace("m²", "m2"))


def _valor(numero: str) -> int:
    return int(numero) if numero.isdigit() else NUMEROS[numero]


def _unidade(palavra: str) -> str:
    palavra = palavra.replace("m²", "m2")
    if palavra in UNIDADES:
        return UNIDADES[palavra]
    singular = re.sub(r"(?<=[a-z])s$", "", palavra)
    return UNIDADES.get(singular, palavra)


def fatos(texto: str) -> set[tuple]:
    """Números do texto: ("4", "suítes"), ("data", "31/12"), ("ano", "2027"). Por extenso vale como algarismo."""
    plano = _plano(texto)
    achados = {(str(_valor(n)), _unidade(u)) for n, u in FATO.findall(plano)}
    achados |= {("data", f"{int(d)}/{int(m)}") for d, m, _ in DATA.findall(plano) if 1 <= int(m) <= 12}
    achados |= {("data", f"{int(d)}/{MESES.index(m) + 1}") for d, m in DATA_EXTENSO.findall(plano)}
    achados |= {("ano", a) for a in ANO.findall(plano)}
    return achados


def frases_a_tirar(aprovado: str) -> list[str]:
    """Frases que o Copywriter mandou tirar (entre aspas, depois de "tire", "remova", "evite"...)."""
    return list(dict.fromkeys(f.strip() for f in TIRAR.findall(aprovado or "") if f.strip()))


def _rotulo(fato: tuple) -> str:
    return fato[1] if fato[0] in ("data", "ano") else f"{fato[0]} {fato[1]}"


def _presente(frase: str, entregue: str) -> bool:
    """A frase está no texto (sem acento/caixa); frase curta com número também vale por extenso ("2 meses")."""
    if _plano(frase) in _plano(entregue):
        return True
    dela = fatos(frase)
    return bool(dela) and len(frase.split()) <= 4 and dela <= fatos(entregue)


def divergencias(aprovado: str, entregue: str, empresa: str = "") -> list[str]:
    """O que o texto entregue tem de diferente do aprovado ([] = bate). Faltar um número não é erro (a legenda pode
    ser mais curta); número que o aprovado não tem, sim."""
    if not (aprovado or "").strip() or not (entregue or "").strip():
        return []
    do_aprovado = fatos(aprovado)
    problemas = [f"\"{_rotulo(f)}\" não está no texto aprovado" for f in sorted(fatos(entregue) - do_aprovado)]
    problemas += [f"voltou \"{frase}\", que o Copywriter mandou tirar ou trocar"
                  for frase in frases_a_tirar(aprovado) if _presente(frase, entregue)]
    if empresa == "casa_vero" and LODGE.search(entregue):
        problemas.append("cita \"Lodge\" numa peça da Casa Vero (manual 12 §5)")
    return problemas


def texto_do_docx(arquivo: Path) -> str:
    """Texto de um .docx sem python-docx (o XML do Word: um parágrafo por <w:p>)."""
    try:
        with zipfile.ZipFile(arquivo) as pacote:
            xml = pacote.read("word/document.xml").decode("utf-8", errors="ignore")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    paragrafos = re.findall(r"<w:p[ >].*?</w:p>", xml, re.DOTALL)
    return "\n".join("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p)) for p in paragrafos)


def _e_legenda(nome: str) -> bool:
    return Path(nome).suffix.lower() == ".docx" and "legenda" in Path(nome).stem.lower()


def instrucao(aprovado: dict | None) -> str:
    """Bloco do prompt: o texto aprovado como TEXTO FIXO."""
    if not aprovado or not (aprovado.get("texto") or "").strip():
        return ""
    texto = aprovado["texto"].strip()[:LIMITE_TEXTO]
    return ("TEXTO APROVADO (TEXTO FIXO: COPIE, NÃO REESCREVA). O texto abaixo foi escrito pelo Copywriter e "
            f"aprovado na conversa ({aprovado.get('origem') or 'conversa'}). A legenda e os textos de tela desta peça "
            "saem DELE, palavra por palavra: mesmos números (datas, contagens, capacidade), escritos do mesmo jeito "
            "(\"2 meses\" continua \"2 meses\"), mesma pontuação e emojis. Não resuma, não melhore, não troque "
            "palavras nem acrescente frases ou dados. O \"Legenda - <peça>.docx\" leva a legenda COPIADA daqui. "
            "Observações do Copywriter para a equipe (fora da legenda e dos textos de tela) não entram na peça. Se "
            "algo não couber na arte ou parecer errado, mantenha o texto e explique no resumo: não corrija sozinho. "
            "O sistema confere os números da legenda contra este texto antes da pasta FINAL.\n"
            f"<<<TEXTO APROVADO\n{texto}\nFIM DO TEXTO APROVADO>>>")


def _textos_do_motion(rascunho: Path) -> str:
    """Textos de tela do motion.json (vídeo), para a mesma conferência."""
    import json

    try:
        spec = json.loads((Path(rascunho) / "motion.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    partes = []
    for cena in spec.get("cenas") or []:
        for el in cena.get("elementos") or [] if isinstance(cena, dict) else []:
            if isinstance(el, dict):
                linhas = el.get("linhas") or []
                partes += [str(el.get("texto") or "")] + [str(l.get("texto", "") if isinstance(l, dict) else l)
                                                           for l in linhas]
    return "\n".join(p for p in partes if p.strip())


def conferir(entrega: Path, novos: list[str], aprovado: dict | None, empresa: str = "",
             rascunho: Path | None = None) -> tuple[list[str], str]:
    """(legendas que ficam FORA da pasta FINAL por divergir, linha para o resumo). Sem texto aprovado, só confere
    "Lodge" na legenda da Casa Vero. Nunca derruba a entrega."""
    texto_aprovado = (aprovado or {}).get("texto") or ""
    barradas, linhas = [], []
    for nome in novos:
        if not _e_legenda(nome):
            continue
        entregue = texto_do_docx(Path(entrega) / nome)
        if texto_aprovado:
            problemas = divergencias(texto_aprovado, entregue, empresa)
        else:
            problemas = (["cita \"Lodge\" numa peça da Casa Vero (manual 12 §5)"]
                         if empresa == "casa_vero" and LODGE.search(entregue) else [])
        if problemas:
            barradas.append(nome)
            linhas.append(f"{Path(nome).name}: {'; '.join(problemas[:5])}")
    if texto_aprovado and rascunho is not None and (tela := _textos_do_motion(rascunho)):
        if (problemas := divergencias(texto_aprovado, tela, empresa)):
            linhas.append(f"textos do vídeo (motion.json): {'; '.join(problemas[:5])}")
    if not linhas:
        return [], ("Texto aprovado: a legenda confere com o texto do Copywriter." if texto_aprovado and
                    any(_e_legenda(n) for n in novos) else "")
    fora = (f" A(s) legenda(s) com divergência ficaram FORA da pasta FINAL (continuam na pasta da peça) até a "
            "correção." if barradas else "")
    return barradas, ("⚠ Texto aprovado: o que saiu diverge do texto aprovado na conversa. " + " | ".join(linhas)
                      + "." + fora + " Peça um ajuste (\"copie a legenda aprovada\") ou confirme a mudança.")
