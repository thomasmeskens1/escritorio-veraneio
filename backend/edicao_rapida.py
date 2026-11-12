"""Edição rápida sem o Max (Onda 3 de novembro; criador_imagens-03, designer-02 e sonoplasta-02).

Dois botões na entrega da peça, sem fila do Max e sem gastar cota:
- "Editar textos" (artes da Casa Veraneio feitas com molde): o formulário vem do molde.json da peça (o PC lê); a
  pessoa troca título, CTA, contagem etc.; o conferente de texto confere ANTES de gravar (WhatsApp, telefone e
  valor barram; o resto pede confirmação) e o trabalhador re-renderiza só os slides alterados pelo molde.py, como
  nova versão na mesma pasta (scripts/max/edicao_rapida_pc.py).
- "Outra música" (vídeo com receita): a versão _com_som é refeita com outra faixa APROVADA da mesma marca.
O backend só enfileira o trabalho "edicao_rapida" (o PC tem o Drive) e avisa no chat quando termina, como o Desdobrar.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import conferente
import producao
import tarefas
from auth import validar_token
from conexoes import gerenciador

log = logging.getLogger("veraneio.edicao_rapida")

rotas = APIRouter(prefix="/api/producao")

TIPO = "edicao_rapida"
producao.TIPOS_TRABALHO.add(TIPO)  # a fila do trabalhador aceita o tipo (sem mexer na lista de producao.py)
producao.TIPOS_RAPIDOS.add(TIPO)   # e ele passa na frente das peças: são segundos, com alguém esperando
SEM_MOLDE, SEM_RECEITA = "SEM_MOLDE:", "SEM_RECEITA:"  # mesmos marcadores de scripts/max/edicao_rapida_pc.py
EMPRESAS_MOLDE = {"casa_veraneio"}  # Corp e Vero: moldes dependem da decisão 1
AGENTES_TEXTOS = {"criador_imagens"}
ESPERA_LER_S = 40          # o formulário espera o PC ler o molde.json
LEITURA_VALE = timedelta(minutes=10)
ESPERA_S = 2 * 3600
# Padrão de caracteres por campo, aprovado pelo Thomas em 12/11/2026 como ponto de partida: quem edita pode passar
# dele confirmando (validar); acima de TETO vezes o padrão, barra.
TETO = 2
LIMITES = {"kicker": 40, "titulo": 42, "subtitulo": 70, "local": 50, "cta": 45, "linha": 60, "linhas": 4,
           "contagem_numero": 4, "contagem_texto": 40}
CAMPOS = ("kicker", "titulo", "subtitulo", "local", "cta", "linhas", "contagem")
BARRAM = ("WhatsApp citado", "telefone escrito", "valor (")  # avisos do conferente que nunca vão para a arte
CLIMAS = {"": "", "calma": "Clima da música: mais calma", "animada": "Clima da música: mais animada"}
VIDEO = re.compile(r"\.(?:mp4|mov)\b", re.I)
TITULOS = {"ler": "Editar textos", "textos": "Editar textos", "musica": "Outra música"}


class Mudanca(BaseModel):
    n: int
    campo: str
    antes: str | list[str] | dict | None = None
    depois: str | list[str] | dict | None = None


class PedidoTextos(BaseModel):
    mudancas: list[Mudanca]
    confirmar: bool = False  # "gravar mesmo assim" depois dos avisos do conferente


class PedidoMusica(BaseModel):
    clima: str = ""


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def conferir_peca(tarefa_id: int, usuario: dict, acao: str):
    """(tarefa, pasta): peça do usuário, pronta pelo Max, com pasta no Drive e do tipo que o botão atende."""
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if linha["status"] != "concluida" or linha["modelo"] != producao.MODELO_MAX:
        raise HTTPException(status_code=409, detail="Só peças prontas do Max têm edição rápida.")
    if acao == "musica" and not VIDEO.search(linha["resposta"] or ""):
        raise HTTPException(status_code=409, detail="Esta peça não tem vídeo: \"Outra música\" vale só para vídeos.")
    if acao != "musica" and (linha["agente"] not in AGENTES_TEXTOS or linha["empresa"] not in EMPRESAS_MOLDE):
        raise HTTPException(status_code=409, detail="\"Editar textos\" vale por enquanto só para artes da Casa "
                                                    "Veraneio feitas com os moldes. Use \"Pedir ajuste\".")
    info = producao._db().execute("SELECT pasta FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    if not info or not info["pasta"]:
        raise HTTPException(status_code=409, detail="Esta peça não tem pasta de entrega no Drive.")
    return linha, info["pasta"]


def _em_aberto(raiz: int, acoes: tuple[str, ...]) -> int | None:
    marcadores = ",".join("?" * len(acoes))
    linha = producao._db().execute(
        f"SELECT id FROM trabalhos_max WHERE tipo = ? AND status IN ('pendente', 'executando') AND "
        f"json_extract(payload, '$.raiz') = ? AND json_extract(payload, '$.acao') IN ({marcadores}) ORDER BY id LIMIT 1",
        (TIPO, raiz, *acoes)).fetchone()
    return linha["id"] if linha else None


def _leitura_recente(raiz: int) -> str | None:
    """Molde lido há pouco (o PC estava ocupado e a leitura terminou depois), se nenhuma edição veio depois dela."""
    desde = (datetime.now(timezone.utc) - LEITURA_VALE).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = producao._db()
    lida = db.execute("SELECT id, resultado FROM trabalhos_max WHERE tipo = ? AND status = 'concluido' AND "
                      "json_extract(payload, '$.acao') = 'ler' AND json_extract(payload, '$.raiz') = ? AND "
                      "concluido_em >= ? ORDER BY id DESC LIMIT 1", (TIPO, raiz, desde)).fetchone()
    if not lida or (lida["resultado"] or "").startswith(SEM_MOLDE):
        return None
    depois = db.execute("SELECT 1 FROM trabalhos_max WHERE tipo = ? AND id > ? AND json_extract(payload, '$.raiz') = ? "
                        "AND json_extract(payload, '$.acao') = 'textos'", (TIPO, lida["id"], raiz)).fetchone()
    return None if depois else lida["resultado"]


async def campos(tarefa_id: int, usuario: dict) -> dict:
    """Os textos atuais de cada slide (lidos no PC) e os limites, para o formulário do chat."""
    _linha, pasta = conferir_peca(tarefa_id, usuario, "ler")
    raiz = producao._producao_raiz(tarefa_id)
    resultado = _leitura_recente(raiz)
    if resultado is None:
        trabalho_id = _em_aberto(raiz, ("ler",)) or await producao.criar_trabalho(
            TIPO, {"acao": "ler", "tarefa_id": tarefa_id, "raiz": raiz, "pasta": pasta})
        trabalho = await producao.aguardar_trabalho(trabalho_id, ESPERA_LER_S)
        if trabalho["status"] in ("pendente", "executando"):
            return {"ok": False, "texto": "O PC está terminando outra tarefa. A leitura dos textos ficou na fila: "
                                          "clique em \"Editar textos\" de novo daqui a alguns minutos."}
        if trabalho["status"] != "concluido":
            raise HTTPException(status_code=409, detail=f"Não foi possível ler os textos da peça: "
                                                        f"{(trabalho.get('resultado') or 'erro no PC')[:300]}")
        resultado = trabalho.get("resultado") or ""
    if resultado.startswith(SEM_MOLDE):
        raise HTTPException(status_code=409, detail=f"Esta peça não tem molde para editar "
                                                    f"({resultado.removeprefix(SEM_MOLDE).strip()}). Use \"Pedir ajuste\".")
    dados = json.loads(resultado)
    return {"ok": True, "tarefa_id": tarefa_id, "slides": dados.get("slides") or [], "limites": LIMITES}


def _textos(valor) -> list[str]:
    if isinstance(valor, list):
        return [str(v) for v in valor]
    if isinstance(valor, dict):
        return [str(valor.get("numero") or ""), str(valor.get("texto") or "")]
    return [str(valor or "")]


def validar(mudancas: list[Mudanca]) -> tuple[list[str], list[str]]:
    """(problemas que barram, textos acima do padrão). Os LIMITES são o padrão aprovado (Thomas, 12/11/2026), não
    regra absoluta: passar deles pede só a confirmação de quem edita. Barram o formato errado e o que passa de
    TETO vezes o padrão (o molde não comporta)."""
    problemas, acima = [], []
    if not mudancas or len(mudancas) > 40:
        return ["nenhuma mudança enviada" if not mudancas else "mudanças demais de uma vez (até 40)"], []

    def medir(nome: str, tamanho: int, limite: int, unidade: str) -> None:
        if tamanho > limite * TETO:
            problemas.append(f"{nome}: no máximo {limite * TETO} {unidade} (tem {tamanho})")
        elif tamanho > limite:
            acima.append(f"{nome}: {tamanho} {unidade}, acima do padrão de {limite}; pode cortar ou quebrar a linha")

    for m in mudancas:
        nome = f"slide {m.n}, {m.campo}"
        if m.campo not in CAMPOS:
            problemas.append(f"{nome}: campo desconhecido")
        elif m.campo == "linhas":
            if not isinstance(m.depois, list):
                problemas.append(f"{nome}: texto inválido")
                continue
            medir(nome, len(m.depois), LIMITES["linhas"], "linhas")
            medir(f"{nome} (linha mais longa)", max((len(str(l)) for l in m.depois), default=0), LIMITES["linha"],
                  "caracteres")
        elif m.campo == "contagem":
            if not isinstance(m.depois or {}, dict):
                problemas.append(f"{nome}: texto inválido")
                continue
            numero, texto = _textos(m.depois or {})
            medir(f"{nome} (número)", len(numero), LIMITES["contagem_numero"], "caracteres")
            medir(f"{nome} (texto)", len(texto), LIMITES["contagem_texto"], "caracteres")
        elif not isinstance(m.depois, str) and m.depois is not None:
            problemas.append(f"{nome}: texto inválido")
        else:
            medir(nome, len(m.depois or ""), LIMITES[m.campo], "caracteres")
    return problemas, acima


def conferir_textos(mudancas: list[Mudanca], empresa: str) -> tuple[list[str], list[str]]:
    """(avisos que barram, avisos para confirmar) do conferente de texto sobre os textos novos."""
    texto = "\n".join(t for m in mudancas for t in _textos(m.depois) if t.strip())
    # "arte": as regras comuns e as da empresa, sem as de formato de legenda; valor nunca é livre na arte (decisão 3)
    avisos = conferente.conferir(texto, empresa, "arte")
    barram = [a for a in avisos if a.startswith(BARRAM)]
    return barram, [a for a in avisos if a not in barram]


async def pedir_textos(tarefa_id: int, pedido: PedidoTextos, usuario: dict) -> dict:
    linha, pasta = conferir_peca(tarefa_id, usuario, "textos")
    problemas, acima = validar(pedido.mudancas)
    if problemas:
        raise HTTPException(status_code=422, detail="Confira os textos: " + "; ".join(problemas[:6]) + ".")
    barram, avisos = conferir_textos(pedido.mudancas, linha["empresa"])
    if barram:
        raise HTTPException(status_code=422, detail="O conferente barrou: " + "; ".join(barram) + ".")
    avisos = acima + avisos
    if avisos and not pedido.confirmar:
        return {"ok": False, "confirmar": True, "avisos": avisos,
                "texto": "O conferente de texto encontrou pontos para você olhar antes de gravar."}
    return await _enfileirar(linha, pasta, "textos", {"mudancas": [m.model_dump() for m in pedido.mudancas]},
                             f"Trocando os textos da peça #{tarefa_id} pelo molde, sem o Max. Só os slides alterados "
                             "são refeitos; o aviso chega aqui quando a versão nova estiver na pasta da peça.")


async def pedir_musica(tarefa_id: int, pedido: PedidoMusica, usuario: dict) -> dict:
    linha, pasta = conferir_peca(tarefa_id, usuario, "musica")
    if pedido.clima not in CLIMAS:
        raise HTTPException(status_code=422, detail=f"Clima deve ser um de: {', '.join(c or '(qualquer)' for c in CLIMAS)}")
    return await _enfileirar(linha, pasta, "musica", {"empresa": linha["empresa"], "pedido": CLIMAS[pedido.clima]},
                             f"Trocando a música da peça #{tarefa_id} por outra faixa aprovada da marca, sem o Max. "
                             "O vídeo sem som fica como está; o aviso chega aqui com a versão nova com som.")


async def _enfileirar(linha, pasta: str, acao: str, extra: dict, texto: str) -> dict:
    tarefa_id = linha["id"]
    raiz = producao._producao_raiz(tarefa_id)
    if (existente := _em_aberto(raiz, ("textos", "musica"))):
        return {"ok": True, "trabalho_id": existente,
                "texto": f"Já há uma edição rápida da peça #{tarefa_id} na fila; espere o aviso dela."}
    trabalho_id = await producao.criar_trabalho(TIPO, {"acao": acao, "tarefa_id": tarefa_id, "raiz": raiz,
                                                       "pasta": pasta, **extra})
    tarefas.registrar_evento(tarefa_id, f"edicao_{acao}", linha["agente"], detalhe=f"{TITULOS[acao]} pedido no chat")
    asyncio.create_task(_acompanhar(trabalho_id, tarefa_id, acao))
    return {"ok": True, "trabalho_id": trabalho_id, "texto": texto}


async def _acompanhar(trabalho_id: int, tarefa_id: int, acao: str) -> None:
    try:
        await concluir(await producao.aguardar_trabalho(trabalho_id, ESPERA_S), tarefa_id, acao)
    except Exception:  # o aviso nunca derruba a API (os arquivos já estão no Drive)
        log.exception("Edição rápida da peça %s: não foi possível avisar o usuário.", tarefa_id)


async def concluir(trabalho: dict, tarefa_id: int, acao: str) -> str:
    """Avisa no chat da peça e deixa o registro (com o antes e o depois) na tarefa. Devolve o texto enviado."""
    linha = tarefas.obter(tarefa_id)
    resultado = (trabalho.get("resultado") or "").strip()
    ajuste = "\"Pedir ajuste\"" + (" (ex.: \"troque a música\")" if acao == "musica" else "")
    if trabalho["status"] == "concluido" and resultado.startswith((SEM_MOLDE, SEM_RECEITA)):
        motivo = resultado.split(":", 1)[1].strip()
        texto = f"A edição rápida não serve para a peça #{tarefa_id} ({motivo}). Use {ajuste}: aí vai para o Max."
    elif trabalho["status"] == "concluido":
        texto = f"{'✏️' if acao == 'textos' else '🎵'} Peça #{tarefa_id}: {resultado}"
    elif trabalho["status"] in ("pendente", "executando"):
        texto = (f"A edição rápida da peça #{tarefa_id} segue na fila do PC (o trabalhador parece desligado). Ela "
                 "sai quando ele voltar.")
    else:
        texto = f"Não foi possível fazer a edição rápida da peça #{tarefa_id}: {resultado[:300] or 'erro no PC'}."
    tarefas.registrar_evento(tarefa_id, f"edicao_{acao}", linha["agente"], detalhe=texto[:600])
    await gerenciador.enviar_para_usuario(linha["usuario"], {
        "tipo": "aviso", "andar": linha["andar"], "agente": linha["agente"], "titulo": TITULOS[acao], "texto": texto,
        "tarefa_id": tarefa_id})
    return texto


@rotas.get("/{tarefa_id}/edicao/textos")
async def textos_atuais(tarefa_id: int, authorization: str = Header("")):
    return await campos(tarefa_id, _usuario(authorization))


@rotas.post("/{tarefa_id}/edicao/textos")
async def editar_textos(tarefa_id: int, pedido: PedidoTextos, authorization: str = Header("")):
    return await pedir_textos(tarefa_id, pedido, _usuario(authorization))


@rotas.post("/{tarefa_id}/edicao/musica")
async def outra_musica(tarefa_id: int, pedido: PedidoMusica, authorization: str = Header("")):
    return await pedir_musica(tarefa_id, pedido, _usuario(authorization))
