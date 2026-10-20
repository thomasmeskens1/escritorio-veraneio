"""Planilha "Info Lodges .xlsx" do acervo (Drive, SOMENTE LEITURA) para o Cérebro.

Cada lodge ocupa um bloco de linhas: número, descrição, endereço e quartos na primeira; a tabela de valores
(diária por época e estadia mínima) nas colunas L..Q. Vira um documento por lodge (fonte "drive"); o site
tem peso maior no Cérebro, então, se os dois divergirem, vale o site. Só envia o que mudou desde o último envio.

Uso avulso: python scripts/max/planilha_lodges.py
"""

import hashlib
import json
from datetime import datetime

import openpyxl

import comum
from comum import log

PLANILHA = comum.ACERVO / "Info Lodges .xlsx"
ARQUIVO_HASHES = comum.DADOS / "planilha_lodges.hashes.json"
COL_LODGE, COL_DESCRICAO, COL_ENDERECO, COL_QUARTOS, COL_VALORES = 0, 1, 7, 9, 11
EPOCAS = ["Ano todo (baixa temporada)", "Alta temporada", "Feriados", "Ano Novo", "Carnaval", "Taxa de ativação"]
ROTULOS = {"ano todo", "estadia mínima"}


def _celula(linha: tuple, coluna: int) -> str:
    valor = linha[coluna] if coluna < len(linha) else None
    if isinstance(valor, float):
        return f"R$ {valor:,.0f}".replace(",", ".")
    return str(valor).strip() if valor is not None else ""


def blocos(caminho=PLANILHA) -> list[list[tuple]]:
    """Linhas agrupadas por lodge (um bloco começa onde a coluna A tem o número)."""
    planilha = openpyxl.load_workbook(caminho, read_only=True, data_only=True)  # leitura apenas
    try:
        grupos: list[list[tuple]] = []
        for linha in planilha.worksheets[0].iter_rows(values_only=True):
            numero = _celula(linha, COL_LODGE)
            if numero.isdigit():
                grupos.append([linha])
            elif grupos:
                grupos[-1].append(linha)
        return grupos
    finally:
        planilha.close()


def lodge(bloco: list[tuple]) -> dict | None:
    valores = [[_celula(l, COL_VALORES + i) for i in range(len(EPOCAS))] for l in bloco]
    marco = next((i for i, v in enumerate(valores) if v[0].lower() == "estadia mínima"), None)
    diarias = valores[marco - 1] if marco else []
    estadias = valores[marco + 1] if marco is not None and marco + 1 < len(valores) else []
    if diarias and diarias[0].lower() in ROTULOS:  # só os rótulos, sem valores
        diarias = []
    dados = {"numero": _celula(bloco[0], COL_LODGE).zfill(2), "descricao": _celula(bloco[0], COL_DESCRICAO),
             "endereco": _celula(bloco[0], COL_ENDERECO), "quartos": _celula(bloco[0], COL_QUARTOS),
             "diarias": diarias, "estadias": estadias}
    vazio = not (dados["descricao"] or dados["endereco"] or dados["quartos"] or any(diarias))
    return None if vazio else dados


def documento(dados: dict, atualizada: str) -> dict:
    linhas = [f"# Lodge {dados['numero']} — planilha Info Lodges",
              f"Fonte: planilha interna \"Info Lodges .xlsx\" (Drive, última alteração em {atualizada}). "
              "Se divergir do site www.casaveraneio.com, vale o site."]
    if dados["endereco"]:
        linhas.append(f"Endereço: {dados['endereco']}")
    if dados["quartos"]:
        linhas += ["", "Configuração dos quartos:", dados["quartos"]]
    if any(dados["diarias"]):
        linhas += ["", "Tabela de valores (diária e estadia mínima):"]
        for i, epoca in enumerate(EPOCAS):
            diaria = dados["diarias"][i] if i < len(dados["diarias"]) else ""
            estadia = dados["estadias"][i] if i < len(dados["estadias"]) else ""
            if diaria or estadia:
                linhas.append(f"- {epoca}: {diaria or '—'}" + (f" | {estadia}" if estadia else ""))
    if dados["descricao"]:
        linhas += ["", "Descrição:", dados["descricao"]]
    return {"fonte_tipo": "drive", "fonte_ref": f"drive/planilha/info-lodges/lodge-{dados['numero']}",
            "titulo": f"Lodge {dados['numero']} — planilha Info Lodges", "conteudo": "\n".join(linhas)}


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sincronizar(enviar=comum.enviar_ao_cerebro) -> dict:
    if not PLANILHA.is_file():
        raise RuntimeError(f"Planilha não encontrada: {PLANILHA}")
    atualizada = f"{datetime.fromtimestamp(PLANILHA.stat().st_mtime):%d/%m/%Y}"
    documentos = [documento(d, atualizada) for d in map(lodge, blocos()) if d]
    try:
        hashes = json.loads(ARQUIVO_HASHES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hashes = {}
    mudados = [d for d in documentos if hashes.get(d["fonte_ref"]) != _hash(d["conteudo"])]
    enviados = len(mudados) if mudados and enviar(mudados) else 0
    if enviados:
        hashes.update({d["fonte_ref"]: _hash(d["conteudo"]) for d in mudados})
        ARQUIVO_HASHES.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"lodges": len(documentos), "mudados": len(mudados), "enviados": enviados}


def rodar() -> None:
    """Versão tolerante a erros para o laço do trabalhador."""
    try:
        r = sincronizar()
        log(f"Planilha Info Lodges: {r['lodges']} lodges; {r['mudados']} alterado(s), "
            f"{r['enviados']} enviado(s) ao Cérebro.")
    except Exception as erro:
        log(f"Planilha Info Lodges falhou: {erro}")


if __name__ == "__main__":
    rodar()
