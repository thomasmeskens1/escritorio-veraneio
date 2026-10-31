"""Documentos como entrega (Onda 3, item 8: cerebro-21, estrategista-16, gestor_trafego-07): arquivos feitos em
código, sem IA e sem modelo externo.

- planilha(): .xlsx do catálogo de imóveis (cerebro_imoveis), com filtro em cada coluna, cabeçalho fixo, link de
  cada Lodge e a aba "Fonte e data". SEM PREÇO (a tabela não guarda valores).
- documento(): .docx de um texto em markdown (estudo do Estrategista, plano/relatório do Gestor de Tráfego), com capa
  simples da marca, selo "ESTUDO de <data>" e marca de confidencial. O .docx é montado à mão (zip + XML do Word):
  o python-docx não está na imagem da API e acrescentá-lo pediria rebuild; o formato gerado abre no Word, no
  LibreOffice e no Google Docs.

Logo da capa: lido na hora de dados/marcas/<PASTA>/<arquivo>.png (cópia dos PNGs de CÉREBRO/MARCAS do Drive, fora do
git) ou da pasta em DOCUMENTOS_MARCAS_DIR. Sem o arquivo, a capa sai só com o nome da empresa.
"""

import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import config
import empresas

FUSO = ZoneInfo("America/Sao_Paulo")
VERDE, CREME, CARAMELO = "00361B", "F0DBC3", "D9A15B"  # paleta da marca (manual 01)
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Empresa -> (pasta em CÉREBRO/MARCAS, logo para fundo Verde). Corp e Vero: identidade ainda em rascunho (decisão 1).
LOGOS = {"casa_veraneio": ("CASA_VERANEIO", "logo_branca.png")}
LARGURA_LOGO_CM = 5.0


def hoje() -> str:
    return datetime.now(FUSO).strftime("%d/%m/%Y")


# --- Planilha do catálogo --------------------------------------------------------------------------

COLUNAS = [("numero", "Lodge", 9), ("nome", "Nome", 22), ("cidade", "Cidade", 22), ("uf", "UF", 6),
           ("bairro", "Bairro", 20), ("quartos", "Quartos", 9), ("suites", "Suítes", 9), ("banheiros", "Banheiros", 10),
           ("pessoas", "Pessoas", 9), ("categorias", "Categorias", 20), ("comodidades", "Comodidades", 60),
           ("link", "Link", 45), ("fonte", "Fonte", 26)]


def planilha(resultado: dict, filtro: str = "") -> bytes:
    """`resultado`: o dicionário de cerebro_imoveis.filtrar(). Devolve os bytes do .xlsx."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    livro = Workbook()
    aba = livro.active
    aba.title = "Imóveis"
    aba.append([titulo for _, titulo, _ in COLUNAS])
    for celula in aba[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=VERDE)
        celula.alignment = Alignment(vertical="center")
    for linha in resultado["linhas"]:
        valores = []
        for chave, _, _ in COLUNAS:
            valor = linha.get(chave)
            if chave == "fonte":
                valor = "fora do site (planilha interna de 2023)" if valor == "planilha" else "site"
            valores.append(valor if valor not in (None, "") else None)
        aba.append(valores)
        if (link := linha.get("link")):
            celula = aba.cell(row=aba.max_row, column=[c for c, _, _ in COLUNAS].index("link") + 1)
            celula.hyperlink, celula.style = link, "Hyperlink"
    for n, (_, _, largura) in enumerate(COLUNAS, start=1):
        aba.column_dimensions[get_column_letter(n)].width = largura
    aba.freeze_panes = "A2"
    aba.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS))}{max(aba.max_row, 1)}"

    fonte = livro.create_sheet("Fonte e data")
    rotulo = "Lodges" if resultado["empresa"] != "casa_vero" else "imóveis"
    conferido = resultado.get("total_no_site")
    for par in [("Empresa", empresas.nome(resultado["empresa"])),
                ("Coleta do site", resultado.get("coletado_em") or "—"),
                ("Planilha gerada em", datetime.now(FUSO).strftime("%d/%m/%Y %H:%M")),
                ("Filtro", filtro or "nenhum (catálogo inteiro)"),
                (f"{rotulo} nesta planilha", resultado["total"]),
                (f"{rotulo} na tabela do Cérebro", resultado["total_base"]),
                ("Deles, no site", resultado["no_site"]),
                ("Total no resumo do site", conferido if conferido is not None else "—"),
                ("Fonte", "Site oficial (coleta automática); os marcados \"fora do site\" vêm da planilha interna "
                          "de 2023."),
                ("Atenção", "Sem preços (diárias e taxas ficam fora). Reconfira no site antes de publicar.")]:
        fonte.append(par)
        fonte.cell(row=fonte.max_row, column=1).font = Font(bold=True)
    fonte.column_dimensions["A"].width, fonte.column_dimensions["B"].width = 30, 90
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


# --- Documento .docx (montado à mão) ------------------------------------------------------------------

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_INVALIDOS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _t(texto: str) -> str:
    return escape(_INVALIDOS.sub("", texto))


def _runs(texto: str, tamanho: int | None = None, cor: str | None = None, negrito: bool = False) -> str:
    """Trechos de texto com **negrito** do markdown; links [texto](url) viram "texto (url)"."""
    texto = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", texto).replace("`", "")
    partes = []
    for i, pedaco in enumerate(re.split(r"\*\*(.+?)\*\*", texto)):
        if not pedaco:
            continue
        estilo = ("<w:b/>" if negrito or i % 2 else "") + (f'<w:color w:val="{cor}"/>' if cor else "") + \
            (f'<w:sz w:val="{tamanho}"/>' if tamanho else "")
        partes.append(f'<w:r>{f"<w:rPr>{estilo}</w:rPr>" if estilo else ""}'
                      f'<w:t xml:space="preserve">{_t(pedaco.replace("*", ""))}</w:t></w:r>')
    return "".join(partes)


def _p(conteudo: str = "", estilo: str = "", centro: bool = False, recuo: int = 0, depois: int | None = None) -> str:
    props = (f'<w:pStyle w:val="{estilo}"/>' if estilo else "") + \
        (f'<w:spacing w:after="{depois}"/>' if depois is not None else "") + \
        (f'<w:ind w:left="{recuo}" w:hanging="240"/>' if recuo else "") + ('<w:jc w:val="center"/>' if centro else "")
    return f'<w:p>{f"<w:pPr>{props}</w:pPr>" if props else ""}{conteudo}</w:p>'


def _tabela(linhas: list[list[str]]) -> str:
    borda = "".join(f'<w:{lado} w:val="single" w:sz="4" w:space="0" w:color="BFB5A3"/>'
                    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"))
    xml = [f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{borda}</w:tblBorders></w:tblPr>']
    fundo = f'<w:shd w:val="clear" w:color="auto" w:fill="{CREME}"/>'  # cabeçalho em Creme
    for n, linha in enumerate(linhas):
        celulas = "".join(f'<w:tc><w:tcPr>{fundo if n == 0 else ""}</w:tcPr>'
                          f'{_p(_runs(c.strip(), 18, negrito=n == 0), depois=0)}</w:tc>' for c in linha)
        xml.append(f"<w:tr>{celulas}</w:tr>")
    return "".join(xml) + "</w:tbl>" + _p()


def _corpo(texto: str) -> list[str]:
    """Markdown simples (o que os agentes escrevem) -> parágrafos do Word."""
    xml, tabela = [], []
    for linha in texto.splitlines() + [""]:
        bruta = linha.strip()
        if bruta.startswith("|"):
            if not re.fullmatch(r"\|?[\s:|-]+\|?", bruta):  # a linha |---|---| do markdown fica de fora
                tabela.append(bruta.strip("|").split("|"))
            continue
        if tabela:
            largura = max(len(l) for l in tabela)
            xml.append(_tabela([l + [""] * (largura - len(l)) for l in tabela]))
            tabela = []
        if not bruta or re.fullmatch(r"[-*_]{3,}", bruta):
            continue
        if (m := re.match(r"(#{1,6})\s+(.*)", bruta)):
            xml.append(_p(_runs(m.group(2)), f"Titulo{min(len(m.group(1)), 3)}"))
        elif (m := re.match(r"[-*•]\s+(.*)", bruta)):
            recuo = 360 + 360 * min((len(linha) - len(linha.lstrip())) // 2, 2)
            xml.append(_p(_runs("•\t" + m.group(1)), recuo=recuo, depois=60))
        else:
            xml.append(_p(_runs(bruta)))
    return xml


def _logo(empresa: str) -> bytes | None:
    """PNG do logo da empresa, lido na hora (nunca vai para o git); None se não existe."""
    if empresa not in LOGOS:
        return None
    pasta, arquivo = LOGOS[empresa]
    raiz = Path(os.environ.get("DOCUMENTOS_MARCAS_DIR") or config.DADOS_DIR / "marcas")
    caminho = raiz / pasta / arquivo
    try:
        dados = caminho.read_bytes()
    except OSError:
        return None
    return dados if dados.startswith(b"\x89PNG\r\n\x1a\n") and len(dados) > 24 else None


def _imagem(dados: bytes) -> str:
    largura, altura = int.from_bytes(dados[16:20], "big") or 1, int.from_bytes(dados[20:24], "big") or 1
    cx = int(LARGURA_LOGO_CM * 360000)
    cy = int(cx * altura / largura)
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="1" name="Logo"/><a:graphic xmlns:a="{_A}"><a:graphicData uri="{_PIC}">'
            f'<pic:pic xmlns:pic="{_PIC}"><pic:nvPicPr><pic:cNvPr id="0" name="logo.png"/><pic:cNvPicPr/>'
            f'</pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdLogo"/><a:stretch><a:fillRect/></a:stretch>'
            f'</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            f'</wp:inline></w:drawing></w:r>')


def _capa(titulo: str, empresa: str, subtitulo: str, selo: str, confidencial: str, logo: bytes | None) -> str:
    """Faixa Verde com o logo (ou o nome) e o título; selo, confidencial e data logo abaixo; quebra de página."""
    nome = empresas.nome(empresa) if empresas.valida(empresa) else "Grupo Casa Veraneio"
    topo = _p(_imagem(logo), centro=True) if logo else _p(_runs(nome.upper(), 36, CREME, True), centro=True)
    faixa = (f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/></w:tblPr><w:tr><w:trPr><w:trHeight w:val="5200"/>'
             f'</w:trPr><w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{VERDE}"/><w:vAlign w:val="center"/>'
             f'</w:tcPr>{_p(depois=600)}{topo}{_p(depois=300)}{_p(_runs(titulo, 44, "FFFFFF", True), centro=True)}'
             f'{_p(_runs(subtitulo, 24, CREME), centro=True)}{_p(depois=600)}</w:tc></w:tr></w:tbl>')
    partes = [faixa, _p(depois=400)]
    if selo:
        partes.append(_p(_runs(selo, 28, CARAMELO, True), centro=True))
    if confidencial:
        partes.append(_p(_runs(confidencial, 22, "A61B1B", True), centro=True))
    partes.append(_p(_runs(f"{nome} · {hoje()}", 20, "6B6457"), centro=True))
    partes.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    return "".join(partes)


_ESTILOS = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{_W}"><w:docDefaults>'
            '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/>'
            '<w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="140" '
            'w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            + "".join(f'<w:style w:type="paragraph" w:styleId="Titulo{n}"><w:name w:val="heading {n}"/>'
                      f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing '
                      f'w:before="{360 - 60 * n}" w:after="120"/><w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/>'
                      f'<w:color w:val="{VERDE if n < 3 else CARAMELO}"/><w:sz w:val="{36 - 4 * n}"/></w:rPr></w:style>'
                      for n in (1, 2, 3)) + "</w:styles>")


def documento(titulo: str, texto: str, empresa: str, subtitulo: str = "", selo: str = "",
              confidencial: str = "") -> bytes:
    """Bytes do .docx: capa + o texto. `selo`: ex. "ESTUDO de 31/10/2026"; `confidencial`: aviso em vermelho."""
    logo = _logo(empresa)
    corpo = _capa(titulo, empresa, subtitulo, selo, confidencial, logo) + "".join(_corpo(texto))
    documento_xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{_W}" '
                     f'xmlns:r="{_R}" xmlns:wp="{_WP}"><w:body>{corpo}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                     '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" '
                     'w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/'
             'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
             'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default '
             'Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="'
             'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override '
             'PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
             'wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/'
             'vnd.openxmlformats-package.core-properties+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
            'core-properties" Target="docProps/core.xml"/></Relationships>')
    rels_doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
                'openxmlformats.org/package/2006/relationships"><Relationship Id="rIdEstilos" Type="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + ('<Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/image" Target="media/logo.png"/>' if logo else "") + "</Relationships>")
    agora = datetime.now(FUSO).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    nucleo = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.'
              'openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
              'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
              f'<dc:title>{_t(titulo)}</dc:title><dc:creator>Escritório Veraneio</dc:creator>'
              f'<dcterms:created xsi:type="dcterms:W3CDTF">{agora}</dcterms:created></cp:coreProperties>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", tipos)
        pacote.writestr("_rels/.rels", rels)
        pacote.writestr("word/document.xml", documento_xml)
        pacote.writestr("word/styles.xml", _ESTILOS)
        pacote.writestr("word/_rels/document.xml.rels", rels_doc)
        pacote.writestr("docProps/core.xml", nucleo)
        if logo:
            pacote.writestr("word/media/logo.png", logo)
    return saida.getvalue()
