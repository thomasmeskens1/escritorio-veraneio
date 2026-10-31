"""Gera o gabarito da prova semanal do Cérebro (cerebro_prova.py) a partir das fichas oficiais que já estão no banco.

Nada é inventado: cada resposta esperada sai, por expressão regular, de um documento do site já ingerido (ficha do
Lodge, espaço do Corporativo, imóvel da Casa Vero, resumo do catálogo, política de cancelamento). As três empresas
ficam em blocos separados e cada pergunta proíbe trechos das outras duas.

O arquivo gerado tem dados do negócio e fica FORA do git (backend/dados/cerebro_prova.json). Só usa a biblioteca
padrão, para rodar no contêiner com o banco aberto só para leitura:

  docker exec -i escritorio-veraneio-api-1 python - --banco "file:/var/lib/escritorio/escritorio.db?mode=ro" \
      < backend/cerebro_prova_gabarito.py > backend/dados/cerebro_prova.json

Formato de cada pergunta: {"id", "pergunta", "ref" (fonte_ref do trecho que deve voltar; opcional), "contem" (textos
que esse trecho precisa ter), "nao_contem" (textos que nenhum trecho pode ter), "proibido_ref" (prefixos de fonte_ref
que não podem voltar: dados de outra empresa ou Orlando)}.
"""

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone

POR_EMPRESA = 30
# Prefixos das fontes de cada empresa: a pergunta de uma empresa nunca pode trazer trecho das outras.
PREFIXOS = {"casa_veraneio": "site/", "cv_corporativo": "corporativo/", "casa_vero": "vero/"}
# Citados na revisão de 30/10/2026 (homônimos e capacidade pendente): entram sempre que existirem.
PREFERIDOS = ("20", "31", "76")


def _outros(empresa: str) -> list[str]:
    return [p for e, p in PREFIXOS.items() if e != empresa]


def _documentos(db, empresa: str, padrao: str) -> dict[str, dict]:
    """{número: {"ref", "titulo", "texto"}} dos documentos `padrao` (LIKE) da empresa, só os de número puro."""
    docs: dict[str, dict] = {}
    for l in db.execute("SELECT fonte_ref, titulo, conteudo FROM conhecimento WHERE ativo = 1 AND empresa = ? "
                        "AND fonte_ref LIKE ? ORDER BY id", (empresa, padrao)):
        numero = l[0].rsplit("-", 1)[-1]
        if not numero.isdigit():
            continue  # lodge-1-orlando e afins
        doc = docs.setdefault(str(int(numero)), {"ref": l[0], "titulo": l[1].split(" › ")[0], "texto": ""})
        doc["texto"] += f"\n{l[1]}\n{l[2]}"
    return docs


def _espalhados(numeros: list[str], quantos: int) -> list[str]:
    """Os preferidos e, depois, números espalhados pelo catálogo (sempre os mesmos enquanto o catálogo não muda)."""
    ordem = sorted(numeros, key=int)
    escolhidos = [n for n in PREFERIDOS if n in ordem][:quantos]
    restantes = [n for n in ordem if n not in escolhidos]
    falta = quantos - len(escolhidos)
    if falta > 0 and restantes:
        passo = max(len(restantes) / falta, 1)
        escolhidos += [restantes[int(i * passo)] for i in range(min(falta, len(restantes)))]
    return sorted(dict.fromkeys(escolhidos), key=int)


def _item(id_: str, pergunta: str, empresa: str, ref: str | None = None, contem=(), nao_contem=(),
          proibido_ref=()) -> dict:
    return {"id": id_, "pergunta": pergunta, "ref": ref, "contem": list(contem), "nao_contem": list(nao_contem),
            "proibido_ref": _outros(empresa) + list(proibido_ref)}


def _casa_veraneio(db) -> list[dict]:
    e, itens, fatos = "casa_veraneio", [], {}
    for n, d in _documentos(db, e, "site/lodges/lodge-%").items():
        cidade = re.search(r"Lodge \d+ — (.+?) - [A-Z]{2}\b", d["titulo"])
        pessoas = re.search(r"até (\d+) pessoas", d["texto"])
        quartos = re.search(r"Resumo: (\d+) quartos", d["texto"])
        if cidade and pessoas and quartos:
            fatos[n] = (d["ref"], cidade.group(1).strip(), pessoas.group(0), quartos.group(1))
    fixas = []
    if (resumo := db.execute("SELECT conteudo FROM conhecimento WHERE ativo = 1 AND empresa = ? AND fonte_ref = "
                             "'site/resumo-lodges' AND conteudo LIKE '%Lodges: %' LIMIT 1", (e,)).fetchone()):
        if (total := re.search(r"Lodges: \d+", resumo[0])):
            fixas.append(_item("cv-catalogo", "Quantos lodges a Casa Veraneio tem no site?", e, "site/resumo-lodges",
                               [total.group(0)]))
    if (politica := db.execute("SELECT conteudo FROM conhecimento WHERE ativo = 1 AND empresa = ? AND fonte_ref = "
                               "'site/politicas-cancelamento' ORDER BY id LIMIT 1", (e,)).fetchone()):
        if (prazo := re.search(r"até \d+ \(\w+\) dias antes", politica[0])):
            fixas.append(_item("cv-cancelamento", "Qual a política de cancelamento da reserva na baixa temporada?", e,
                               "site/politicas-cancelamento", [prazo.group(0)]))
    fixas.append(_item("cv-sem-orlando", "Sugira casas de veraneio com piscina para o fim de semana", e,
                       proibido_ref=["site/lodges-orlando"], nao_contem=["Orlando", "Kissimmee"]))
    for n in _espalhados(list(fatos), (POR_EMPRESA - len(fixas)) // 3):
        ref, cidade, pessoas, quartos = fatos[n]
        itens += [_item(f"cv-{n}-cidade", f"Em que cidade fica o Lodge {n}?", e, ref, [cidade]),
                  _item(f"cv-{n}-pessoas", f"Para quantas pessoas é o Lodge {n}?", e, ref, [pessoas]),
                  _item(f"cv-{n}-quartos", f"Quantos quartos tem o Lodge {n}?", e, ref, [f"{quartos} quartos"])]
    return fixas + itens


def _corporativo(db) -> list[dict]:
    e, itens, fatos = "cv_corporativo", [], {}
    for n, d in _documentos(db, e, "corporativo/espacos/lodge-%").items():
        local = re.search(r"^Local: (.+?) - [A-Z]{2}\b", d["texto"], re.MULTILINE)
        convidados = re.search(r"^Convidados: (até \d+ pessoas)", d["texto"], re.MULTILINE)
        if local and convidados:
            fatos[n] = (d["ref"], local.group(1).strip(), convidados.group(1))
    fixas = []
    if db.execute("SELECT 1 FROM conhecimento WHERE ativo = 1 AND empresa = ? AND fonte_ref = "
                  "'corporativo/eventos/off-site-e-team-building' LIMIT 1", (e,)).fetchone():
        fixas.append(_item("corp-offsite", "O Corporativo faz eventos de off-site e team building?", e,
                           "corporativo/eventos/off-site-e-team-building"))
    for n in _espalhados(list(fatos), (POR_EMPRESA - len(fixas)) // 2):
        ref, local, convidados = fatos[n]
        itens += [_item(f"corp-{n}-local", f"Onde fica o espaço de eventos Lodge {n} do Corporativo?", e, ref, [local]),
                  _item(f"corp-{n}-convidados", f"Quantos convidados cabem no Lodge {n} do Corporativo?", e, ref,
                        [convidados])]
    return fixas + itens


def _casa_vero(db) -> list[dict]:
    e, itens, fatos = "casa_vero", [], {}
    for n, d in _documentos(db, e, "vero/imoveis/vero-%").items():
        negocio = re.search(r"Negócio e localização: (\w+) — ", d["texto"])
        dormitorios = re.search(r"Resumo: (\d+) dormitórios", d["texto"])
        titulo = re.search(r"Vero \d+ — (.+?) \(Casa Vero\)", d["titulo"])
        if negocio and dormitorios and titulo:
            fatos[n] = (d["ref"], negocio.group(1), dormitorios.group(1), titulo.group(1).strip())
    fixas = []
    if db.execute("SELECT 1 FROM conhecimento WHERE ativo = 1 AND empresa = ? AND fonte_ref = 'vero/sobre' LIMIT 1",
                  (e,)).fetchone():
        fixas.append(_item("vero-sobre", "Qual a missão da Casa Vero Imóveis?", e, "vero/sobre"))
    escolhidos = _espalhados(list(fatos), (POR_EMPRESA - len(fixas)) // 3)
    for n in escolhidos:
        ref, negocio, dormitorios, titulo = fatos[n]
        itens += [_item(f"vero-{n}-negocio", f"O Vero {n} é para venda ou locação?", e, ref,
                        [f"Negócio e localização: {negocio}"]),
                  _item(f"vero-{n}-dormitorios", f"Quantos dormitórios tem o Vero {n}?", e, ref,
                        [f"{dormitorios} dormitórios"]),
                  _item(f"vero-{n}-onde", f"Onde fica o imóvel Vero {n}?", e, ref, [titulo])]
    if "76" in fatos:  # imóvel à venda: não pode vir diária de hospedagem (dado da Casa Veraneio)
        itens.append(_item("vero-76-sem-diaria", "Qual o valor do Vero 76?", e, fatos["76"][0], nao_contem=["diária"]))
    return fixas + itens


def gerar(db) -> dict:
    blocos = {"casa_veraneio": _casa_veraneio(db), "cv_corporativo": _corporativo(db), "casa_vero": _casa_vero(db)}
    return {"versao": 1, "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "observacao": "Gerado de fichas oficiais do banco (cerebro_prova_gabarito.py). Fora do git.",
            "empresas": {e: itens[:POR_EMPRESA] for e, itens in blocos.items()}}


if __name__ == "__main__":
    import os

    partes = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    partes.add_argument("--banco", default=os.getenv("ARQUIVO_BANCO", "dados/escritorio.db"),
                        help="caminho ou URI file:...?mode=ro (o banco é só lido)")
    partes.add_argument("--saida", help="arquivo de saída (padrão: imprime)")
    args = partes.parse_args()
    uri = args.banco.startswith("file:")
    conexao = sqlite3.connect(args.banco if uri else f"file:{args.banco}?mode=ro", uri=True)
    texto = json.dumps(gerar(conexao), ensure_ascii=False, indent=1)
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")
    else:
        print(texto)
