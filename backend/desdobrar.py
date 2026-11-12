"""Botão "Desdobrar" no chat (Onda 3, item 3; designer-07, gestor_trafego-11; 31/10/2026).

A peça pronta do Criador de Imagens ganha as versões 4:5 (1080x1350) e 9:16 (1080x1920). O backend só põe um
trabalho "desdobrar" na fila do PC: o trabalhador (scripts/max/desdobrar_formatos.py) relê o molde.json da peça e
renderiza em código, sem o Max, na subpasta FORMATOS/ da pasta da peça. Peça montada fora dos moldes volta com SEM_MOLDE e o
desdobramento entra na fila do Max como ajuste da peça já aprovada (mesma pasta, nova versão).
"""

import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException

import producao
import tarefas
from auth import validar_token
from conexoes import gerenciador
from estado import buscar_agente

log = logging.getLogger("veraneio.desdobrar")

rotas = APIRouter(prefix="/api/producao")

TIPO = "desdobrar"
producao.TIPOS_TRABALHO.add(TIPO)  # a fila do trabalhador passa a aceitar este tipo (sem mexer em producao.py)
SEM_MOLDE = "SEM_MOLDE:"  # mesmo marcador de scripts/max/desdobrar_formatos.py
FORMATOS = ("1080x1350", "1080x1920")
AGENTES = {"criador_imagens"}  # vídeo fica para depois (manifest do editor_video-02)
ESPERA_S = 2 * 3600
TITULO = "Desdobrar"
# "Desdobrar para anúncio" (gestor_trafego-13, designer-21, email_marketing-06; 12/11/2026): mesmo trabalho, com
# "destino": "anuncio"; 1:1, 1,91:1, 9:16 de anúncio e cabeçalho de e-mail na subpasta ANÚNCIO/. Só peça de molde
# (Casa Veraneio): sem molde não vai para o Max, porque o anúncio sai do mesmo layout aprovado.
FORMATOS_ANUNCIO = ("1080x1080", "1200x628", "1080x1920", "1200x600")
EMPRESAS_ANUNCIO = {"casa_veraneio"}  # Corp e Vero: sem moldes até a decisão 1
TITULO_ANUNCIO = "Desdobrar para anúncio"


def texto_do_ajuste(tarefa_id: int) -> str:
    """Pedido ao Max quando a peça não tem molde: ajuste da peça aprovada, só os formatos novos."""
    return (f"Ajuste na peça #{tarefa_id}: desdobrar a peça já aprovada nos formatos 4:5 (1080x1350) e 9:16 "
            "(1080x1920). Mantenha as mesmas fotos, textos, selo, logo e ordem; só recomponha cada slide para o "
            "formato, respeitando as zonas mortas do manual 08 (no 9:16, texto e logo entre ~300 e ~1560 px de "
            "altura). Não mude a versão 3:4 nem a legenda. Nomeie como <slide>_4x5.png e <slide>_9x16.png.")


def _usuario(authorization: str) -> dict:
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    return usuario


def conferir_peca(tarefa_id: int, usuario: dict):
    """A tarefa do usuário, concluída pelo Max, com pasta no Drive e feita pelo Criador de Imagens."""
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if linha["status"] != "concluida" or linha["modelo"] != producao.MODELO_MAX:
        raise HTTPException(status_code=409, detail="Só peças prontas do Max podem ser desdobradas.")
    if linha["agente"] not in AGENTES:
        raise HTTPException(status_code=409, detail="Por enquanto o Desdobrar vale só para artes (PNG) do Criador "
                                                    "de Imagens.")
    info = producao._db().execute("SELECT pasta FROM producao_info WHERE tarefa_id = ?", (tarefa_id,)).fetchone()
    if not info or not info["pasta"]:
        raise HTTPException(status_code=409, detail="Esta peça não tem pasta de entrega no Drive.")
    return linha, info["pasta"]


async def pedir(tarefa_id: int, usuario: dict) -> dict:
    linha, pasta = conferir_peca(tarefa_id, usuario)
    if (existente := producao.trabalho_em_aberto(TIPO, "tarefa_id", tarefa_id)):
        return {"ok": True, "trabalho_id": existente, "texto": f"O desdobramento da peça #{tarefa_id} já está na fila."}
    trabalho_id = await producao.criar_trabalho(TIPO, {
        "tarefa_id": tarefa_id, "raiz": producao._producao_raiz(tarefa_id), "pasta": pasta, "formatos": list(FORMATOS)})
    tarefas.registrar_evento(tarefa_id, TIPO, linha["agente"], detalhe="Desdobrar em 4:5 e 9:16 pedido no chat")
    asyncio.create_task(_acompanhar(trabalho_id, tarefa_id))
    return {"ok": True, "trabalho_id": trabalho_id,
            "texto": f"Desdobrando a peça #{tarefa_id} em 4:5 e 9:16 pelo molde, sem refazer a arte. Você recebe o "
                     "aviso aqui quando os arquivos estiverem na pasta FORMATOS/ da peça."}


async def pedir_anuncio(tarefa_id: int, usuario: dict) -> dict:
    linha, pasta = conferir_peca(tarefa_id, usuario)
    if linha["empresa"] not in EMPRESAS_ANUNCIO:
        raise HTTPException(status_code=409, detail="Por enquanto o Desdobrar para anúncio vale só para peças da Casa "
                                                    "Veraneio feitas com molde.")
    if (existente := producao.trabalho_em_aberto(TIPO, "anuncio_de", tarefa_id)):
        return {"ok": True, "trabalho_id": existente,
                "texto": f"As versões de anúncio da peça #{tarefa_id} já estão na fila."}
    trabalho_id = await producao.criar_trabalho(TIPO, {
        "anuncio_de": tarefa_id, "destino": "anuncio", "raiz": producao._producao_raiz(tarefa_id), "pasta": pasta,
        "formatos": list(FORMATOS_ANUNCIO)})
    tarefas.registrar_evento(tarefa_id, TIPO, linha["agente"], detalhe="Desdobrar para anúncio pedido no chat")
    asyncio.create_task(_acompanhar(trabalho_id, tarefa_id, anuncio=True))
    return {"ok": True, "trabalho_id": trabalho_id,
            "texto": f"Gerando as versões de anúncio da peça #{tarefa_id} (1:1, 1,91:1 e 9:16) e o cabeçalho de e-mail "
                     "pelo molde, sem refazer a arte. Você recebe o aviso aqui quando estiverem na pasta ANÚNCIO/ da peça."}


async def _acompanhar(trabalho_id: int, tarefa_id: int, anuncio: bool = False) -> None:
    try:
        await concluir(await producao.aguardar_trabalho(trabalho_id, ESPERA_S), tarefa_id, anuncio)
    except Exception:  # o aviso nunca derruba a API (os arquivos já estão no Drive)
        log.exception("Desdobrar da peça %s: não foi possível avisar o usuário.", tarefa_id)


async def concluir(trabalho: dict, tarefa_id: int, anuncio: bool = False) -> str:
    """Avisa no chat da peça. SEM_MOLDE: enfileira o ajuste no Max (o anúncio só avisa). Devolve o texto enviado."""
    linha = tarefas.obter(tarefa_id)
    resultado = (trabalho.get("resultado") or "").strip()
    if anuncio and trabalho["status"] == "concluido" and resultado.startswith(SEM_MOLDE):
        texto = (f"A peça #{tarefa_id} não foi montada com os moldes ({resultado.removeprefix(SEM_MOLDE).strip()}). "
                 "O Desdobrar para anúncio vale só para peças de molde; peça as versões de anúncio ao Criador de "
                 "Imagens como ajuste, se precisar.")
    elif anuncio and trabalho["status"] == "concluido":
        texto = f"↔ Peça #{tarefa_id} desdobrada para anúncio e e-mail.\n\n{resultado}"
    elif anuncio and trabalho["status"] not in ("pendente", "executando"):
        texto = (f"Não foi possível gerar as versões de anúncio da peça #{tarefa_id}: "
                 f"{resultado[:300] or 'erro no trabalhador'}.")
    elif trabalho["status"] == "concluido" and resultado.startswith(SEM_MOLDE):
        agente = buscar_agente(linha["andar"], linha["agente"])
        await producao.enfileirar(linha["usuario"], linha["andar"], agente, texto_do_ajuste(tarefa_id), base=tarefa_id,
                                  empresa=linha["empresa"])
        texto = (f"A peça #{tarefa_id} não foi montada com os moldes ({resultado.removeprefix(SEM_MOLDE).strip()}). "
                 "O desdobramento em 4:5 e 9:16 foi para a fila do Max como ajuste da peça aprovada.")
    elif trabalho["status"] == "concluido":
        texto = f"↔ Peça #{tarefa_id} desdobrada.\n\n{resultado}"
    elif trabalho["status"] in ("pendente", "executando"):
        texto = (f"O desdobramento da peça #{tarefa_id} segue na fila do PC (o trabalhador do Max parece desligado). "
                 f"Os arquivos vão para a pasta {'ANÚNCIO' if anuncio else 'FORMATOS'}/ da peça quando ele voltar.")
    else:
        texto = f"Não foi possível desdobrar a peça #{tarefa_id}: {resultado[:300] or 'erro no trabalhador'}."
    tarefas.registrar_evento(tarefa_id, TIPO, linha["agente"], detalhe=texto[:300])
    await gerenciador.enviar_para_usuario(linha["usuario"], {
        "tipo": "aviso", "andar": linha["andar"], "agente": linha["agente"],
        "titulo": TITULO_ANUNCIO if anuncio else TITULO, "texto": texto, "tarefa_id": tarefa_id})
    return texto


@rotas.post("/{tarefa_id}/desdobrar")
async def desdobrar(tarefa_id: int, authorization: str = Header("")):
    return await pedir(tarefa_id, _usuario(authorization))


@rotas.post("/{tarefa_id}/desdobrar-anuncio")
async def desdobrar_anuncio(tarefa_id: int, authorization: str = Header("")):
    return await pedir_anuncio(tarefa_id, _usuario(authorization))
