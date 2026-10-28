"""Orquestra as tarefas: execução imediata (gratuito → local), fila adiada e entrega das respostas.

A fila nunca trava: tenta o Claude (Haiku/Sonnet) e, se ele estiver indisponível (crédito do mês
esgotado ou ritmo diário atingido), segue em contingência com os gratuitos e o modelo local.
"""

import asyncio
import json
import logging
import time

import aprendizado
import atividade
import cerebro
import config
import correcoes
import encaminhamento
import espera
import max_texto
import monday
import saude
import tarefas
from conexoes import gerenciador
from estado import Agente, Status, buscar_agente, snapshot
from roteamento import Dificuldade, Etapa, classificar, etapa_fila, etapas_contingencia, etapas_imediatas

log = logging.getLogger(__name__)

INTERVALO_FILA = 5  # segundos entre verificações da fila

_em_andamento: set[asyncio.Task] = set()  # referência forte às tarefas em segundo plano


async def atualizar_status(agente: Agente, status: Status) -> None:
    agente.status = status
    await gerenciador.transmitir(lambda usuario: snapshot(usuario["role"]))


def ha_modelo_disponivel() -> bool:
    return bool(etapas_contingencia() or etapa_fila(Dificuldade.simples))


async def nova_tarefa(login: str, andar: str, agente: Agente, texto: str, anexos_ids: list[str] = (),
                      contexto: str = "", ao_criar=None, empresa: str = "casa_veraneio") -> int:
    """`contexto`: dados extras para o agente (ex.: item do Monday citado), fora do texto exibido no chat.
    `ao_criar(tarefa_id)`: roda antes da execução (ex.: vincular a tarefa ao item do Monday)."""
    dificuldade = classificar(agente.id, texto)
    tarefa_id = tarefas.criar(login, andar, agente.id, texto, dificuldade.value, empresa)
    if anexos_ids:
        tarefas.atualizar(tarefa_id, anexos=json.dumps(list(anexos_ids)))
    if contexto:
        tarefas.atualizar(tarefa_id, contexto_anexos=contexto)
    if ao_criar:
        ao_criar(tarefa_id)
    tarefas.registrar_evento(tarefa_id, "recebida", agente.id, detalhe=f"Dificuldade: {dificuldade.value}")
    await atividade.ocupar(agente.id)
    _em_segundo_plano(_executar_imediata(tarefa_id, agente, dificuldade))
    return tarefa_id


def _em_segundo_plano(corrotina) -> None:
    execucao = asyncio.create_task(corrotina)
    _em_andamento.add(execucao)
    execucao.add_done_callback(_em_andamento.discard)


async def _tentar(tarefa, agente: Agente, etapa: Etapa):
    """Uma tentativa num modelo, com o histórico da conversa. Devolve (resultado ou None, erro)."""
    from agents.executor import LocalOcupado, MaxOcupado, executar  # import tardio: CrewAI é pesado

    historico = tarefas.historico(tarefa["usuario"], tarefa["andar"], tarefa["agente"], tarefa["id"], limite=4,
                                  empresa=tarefa["empresa"])  # 4 trocas: o briefing sobrevive a 3 rodadas de formulário
    inicio = time.monotonic()
    try:
        tarefas.registrar_evento(tarefa["id"], "tentativa", agente.id, etapa.modelo)
        texto = tarefa["texto"] + (f"\n\n{tarefa['contexto_anexos']}" if tarefa["contexto_anexos"] else "")
        return await executar(agente.id, texto, etapa, historico, tarefa["id"]), ""
    except LocalOcupado as motivo:  # também PedidoGrandeDemais (Groq): pula sem afastar o modelo
        return None, str(motivo) or "modelo local ocupado"
    except MaxOcupado:  # o Max está com outra tarefa: segue para a API, em paralelo
        tarefas.registrar_evento(tarefa["id"], "falha_modelo", agente.id, etapa.modelo, "Max ocupado; seguindo para a API")
        return None, "Max ocupado"
    except asyncio.TimeoutError:
        erro = f"excedeu {etapa.limite_s // 60} min"
        if not etapa.modelo.startswith(("claude-code/", "ollama/")):  # Max e local demoram por natureza
            saude.registrar_falha(etapa.modelo, erro)  # lento agora: outro modelo assume por 15 min
    except Exception as e:
        erro = str(e)
        saude.registrar_falha(etapa.modelo, erro)  # sai da rota por um tempo; falha recorrente afasta por 7 dias
    finally:
        tarefas.registrar_tentativa(tarefa["id"], time.monotonic() - inicio)
    tarefas.registrar_evento(tarefa["id"], "falha_modelo", agente.id, etapa.modelo, erro)
    log.warning("Tarefa %s: %s falhou (%s).", tarefa["id"], etapa.modelo, erro[:200])
    return None, erro


async def _executar_etapas(tarefa, agente: Agente, etapas: list[Etapa]) -> bool:
    """Troca de modelo a cada falha, até um concluir."""
    for etapa in etapas:
        resultado, _ = await _tentar(tarefa, agente, etapa)
        if resultado:
            saude.registrar_sucesso(etapa.modelo)  # modelo em teste depois de afastado: histórico limpo
            await _concluir(tarefa["id"], etapa.modelo, resultado)
            return True
    return False


async def _executar_imediata(tarefa_id: int, agente: Agente, dificuldade: Dificuldade) -> None:
    tarefa = tarefas.obter(tarefa_id)
    try:
        if tarefa["anexos"]:  # descreve os anexos uma vez (Max para o dono, API para os demais)
            import anexos
            contexto = await anexos.descrever(json.loads(tarefa["anexos"]), tarefa["usuario"])
            juntos = "\n\n".join(filter(None, [tarefa["contexto_anexos"], contexto]))  # mantém o contexto extra
            tarefas.atualizar(tarefa_id, contexto_anexos=juntos or None)
            tarefa = tarefas.obter(tarefa_id)
        if await _executar_etapas(tarefa, agente, _com_max(etapas_imediatas(dificuldade, agente.id),
                                                            tarefa["usuario"], agente.id)):
            return
        destino = "fila do Claude" if etapa_fila(dificuldade) else "fila de contingência (gratuitos e local)"
        tarefas.atualizar(tarefa_id, status="adiada", motivo="Os modelos imediatos não concluíram a tarefa a tempo.")
        tarefas.registrar_evento(tarefa_id, "adiada", agente.id, detalhe=destino)
        monday.andamento(tarefa_id, "adiada")
        await gerenciador.enviar_para_usuario(tarefa["usuario"], {
            "tipo": "tarefa_adiada", "andar": tarefa["andar"], "agente": agente.id, "tarefa_id": tarefa_id,
            "texto": f"Os modelos imediatos não concluíram a tarefa a tempo. Ela foi para a {destino}; "
                     "a resposta chega assim que for processada.",
        })
    finally:
        await atividade.liberar(agente.id)


async def _concluir(tarefa_id: int, modelo: str, resultado) -> None:
    tarefas.atualizar(tarefa_id, status="concluida", modelo=modelo, resposta=resultado.texto,
                      tokens_entrada=resultado.tokens_entrada, tokens_saida=resultado.tokens_saida, custo_usd=resultado.custo_usd)
    tarefas.registrar_evento(tarefa_id, "concluida", modelo=modelo)
    # Fora do loop: o Cérebro usa uma trava própria e não pode congelar o WebSocket e as rotas.
    await asyncio.to_thread(cerebro.registrar_resultado, tarefa_id, True)  # trechos usados ganham pontos
    await asyncio.to_thread(cerebro.aprender_tarefa, tarefa_id)            # o trabalho concluído vira conhecimento
    linha = tarefas.obter(tarefa_id)
    await _entregar(linha)
    await entregar_na_origem(linha)
    producao_a_seguir = False
    if linha["agente"] == "gestor" and linha["usuario"] == config.DONO_MAX:
        if (pergunta := espera.pergunta_pendente(resultado.texto)) and _vai_produzir(linha["id"]):
            await _esperar_resposta(linha, pergunta)  # a produção só começa quando o usuário responder
            producao_a_seguir = True                  # o item do Monday não vai para Revisão ainda
        else:
            producao_a_seguir = await _produzir_pecas(linha, resultado.texto)
    monday.andamento(tarefa_id, "concluida", resultado.texto, producao_a_seguir)


def _vai_produzir(tarefa_id: int) -> bool:
    from agents.projeto import agentes_de_producao

    return bool(agentes_de_producao(tarefa_id))


async def _esperar_resposta(linha, pergunta: str) -> None:
    """Guarda a produção e pergunta no chat onde o pedido nasceu (o do Gestor, se foi pedido direto a ele)."""
    andar, agente = encaminhamento.origem(linha["id"]) or (linha["andar"], linha["agente"])
    espera.guardar(linha["id"], linha["usuario"], andar, agente, pergunta)
    await gerenciador.enviar_para_usuario(linha["usuario"], {
        "tipo": "aviso", "andar": andar, "agente": agente, "titulo": "Produção em espera",
        "texto": f"Antes de produzir, o Gestor precisa da sua resposta: {pergunta}\n\nResponda aqui mesmo: a "
                 "produção no Max só começa depois disso.",
        "opcoes": [{"rotulo": "Seguir como está", "texto": "Pode seguir com a produção como está."},
                   {"rotulo": "Cancelar produção", "texto": "Cancelar a produção."}]})


async def retomar_producao(pendente, resposta: str) -> str:
    """Resposta do usuário a uma produção em espera: vira decisão final no briefing (ou cancela)."""
    espera.remover(pendente["tarefa_id"])
    linha = tarefas.obter(pendente["tarefa_id"])
    if espera.CANCELAR.search(resposta):
        monday.andamento(linha["id"], "concluida", "Produção cancelada pelo usuário.", False)
        return "Combinado: a produção foi cancelada. O plano do Gestor continua aqui no chat."
    consolidado = (f"{linha['resposta']}\n\nDECISÃO DO USUÁRIO sobre a pergunta \"{pendente['pergunta']}\" "
                   f"(vale sobre o que estiver acima): {resposta}")
    await _produzir_pecas(linha, consolidado)
    return "Anotado! Segui com a produção usando a sua resposta. A entrega chega aqui quando ficar pronta."


async def _produzir_pecas(linha, consolidado: str) -> bool:
    """Projeto do Gestor com Criador de Imagens/Editor de Vídeo: a peça final vai à produção no Max (só o dono)."""
    import producao  # import tardio: a produção depende do orquestrador
    from agents.projeto import agentes_de_producao, titulo_do_projeto

    # Pasta de entrega com o nome do projeto (ex.: "Post Réveillon Lodge 1"), não com o briefing.
    titulo = titulo_do_projeto(linha["id"]) or producao.titulo_curto(linha["texto"])
    produziu = False
    # Uma peça, um produtor: o especialista do formato (vídeo = Editor de Vídeo), mesmo que o plano cite os dois.
    # Teste real (26/10/2026): o plano com Criador e Editor gerou duas produções da mesma peça (#63 e #64).
    produtores = [producao.produtor_da_peca(f"{linha['texto']}\n{consolidado}")] if agentes_de_producao(linha["id"]) else []
    for agente_id in produtores:
        agente = buscar_agente(linha["andar"], agente_id)
        if not agente:
            continue
        briefing = (f"Produza a peça final do projeto #{linha['id']}, coordenado pelo Gestor. Siga o plano, os "
                    f"textos e as especificações abaixo, sem inventar dados.\n\nPedido original: {linha['texto']}"
                    f"\n\nResultado consolidado do Gestor:\n{consolidado[:8000]}")
        def vincular(producao_id: int) -> None:
            # A entrega volta ao chat onde o usuário pediu (o do Gestor, se ele pediu direto ao Gestor).
            encaminhamento.registrar(producao_id, *(encaminhamento.origem(linha["id"]) or (linha["andar"], "gestor")),
                                     pedido=False)
            if (vinculo := monday._vinculo(linha["id"])):  # os criativos voltam para o mesmo item do Monday
                monday.vincular(producao_id, vinculo["item_id"], vinculo["usuario_monday"], vinculo["origem"] or "botao")

        await producao.enfileirar(linha["usuario"], linha["andar"], agente, briefing, titulo=titulo, ao_criar=vincular,
                                  empresa=linha["empresa"])
        await avisar_na_origem(linha["id"], {"andar": linha["andar"], "agente": "gestor"},
                               f"A peça final foi para o {agente.nome} produzir no Claude Code (Max). "
                               "A entrega chega aqui quando ficar pronta.", "Produção")
        produziu = True
    return produziu


async def entregar_na_origem(linha) -> None:
    """Tarefa que nasceu em outro chat (encaminhada ao Gestor, produção do projeto): a resposta final, ou a
    falha, também aparece no chat onde o usuário pediu, assinada por quem respondeu."""
    if not (de := encaminhamento.origem(linha["id"])):
        return
    andar, agente = de
    if (andar, agente) == (linha["andar"], linha["agente"]):
        return
    quem = buscar_agente(linha["andar"], linha["agente"])
    mensagem = {**_mensagem(linha), "andar": andar, "agente": agente, "por": quem.nome if quem else linha["agente"]}
    await gerenciador.enviar_para_usuario(linha["usuario"], mensagem)


async def avisar_na_origem(tarefa_id: int, alvo: dict, texto: str, titulo: str) -> None:
    """Aviso que vale também para o chat de origem (ex.: "foi para a produção")."""
    linha = tarefas.obter(tarefa_id)
    destinos = [alvo, *([{"andar": d[0], "agente": d[1]}] if (d := encaminhamento.origem(tarefa_id)) else [])]
    for destino in {(d["andar"], d["agente"]): d for d in destinos}.values():
        await gerenciador.enviar_para_usuario(linha["usuario"], {"tipo": "aviso", **destino, "titulo": titulo,
                                                                 "texto": texto})


def _falhar(tarefa_id: int, motivo: str) -> None:
    tarefas.atualizar(tarefa_id, status="falhou", motivo=motivo)
    tarefas.registrar_evento(tarefa_id, "falhou", detalhe=motivo)
    cerebro.registrar_resultado(tarefa_id, False)
    monday.andamento(tarefa_id, "falhou", motivo)
    if encaminhamento.origem(tarefa_id):
        _em_segundo_plano(entregar_na_origem(tarefas.obter(tarefa_id)))


def _mensagem(linha) -> dict:
    alvo = {"andar": linha["andar"], "agente": linha["agente"], "tarefa_id": linha["id"]}
    if linha["status"] == "falhou":
        return {"tipo": "erro", "texto": linha["motivo"] or "Falha ao executar a tarefa.", **alvo}
    return {"tipo": "resposta_agente", **alvo, "texto": linha["resposta"], "modelo": linha["modelo"],
            "dificuldade": linha["dificuldade"], "tempo_segundos": round(linha["tempo_segundos"], 1),
            "adiada": linha["motivo"] is not None, "link": _link(linha)}


def _link(linha) -> str | None:
    """Pasta da entrega no Drive (botão "Visualizar"), só nas produções concluídas."""
    import producao  # import tardio: produção depende do orquestrador

    return producao.link_de(linha["id"]) if linha["modelo"] == producao.MODELO_MAX else None


async def _entregar(linha) -> None:
    if await gerenciador.enviar_para_usuario(linha["usuario"], _mensagem(linha)):
        tarefas.atualizar(linha["id"], entregue=1)
    if linha["status"] in ("concluida", "falhou"):
        _em_segundo_plano(aprendizado.talvez_treinar())


entregar = _entregar  # entrega pública (usada pelo ensino do Cérebro)


async def entregar_pendentes(login: str) -> None:
    """Respostas que ficaram prontas enquanto o usuário estava fora."""
    for linha in tarefas.nao_entregues(login):
        await _entregar(linha)
        await entregar_na_origem(linha)  # e no chat onde o pedido nasceu, se foi em outro
    if login == config.DONO_MAX and (aviso := correcoes.lembrete_semanal()):  # revisão semanal das correções
        await gerenciador.enviar_para_usuario(login, {"tipo": "aviso", "andar": "cobertura", "agente": "cerebro",
                                                      "titulo": "Correções para revisar", "texto": aviso})


# --- Fila adiada -------------------------------------------------------------------------

async def processar_fila() -> None:
    while True:
        try:
            espera = await _processar_proxima()
        except Exception:
            log.exception("Erro ao processar a fila.")
            espera = INTERVALO_FILA
        await asyncio.sleep(espera)


def _com_max(etapas: list[Etapa], usuario: str, agente_id: str) -> list[Etapa]:
    """Caminho imediato do dono: o Max entra antes da API do Claude (gratuitos continuam primeiro)."""
    if not max_texto.pode_usar(usuario, agente_id):
        return etapas
    posicao = next((i for i, e in enumerate(etapas) if e.modelo.startswith("anthropic/")), None)
    if posicao is None:
        return etapas
    return etapas[:posicao] + [Etapa(max_texto.MODELO, max_texto.LIMITE_S)] + etapas[posicao:]


def _etapas_fila(dificuldade: Dificuldade, usuario: str = "", agente_id: str = "") -> list[Etapa]:
    """Max primeiro, para o dono (custo zero; se ocupado, passa adiante); depois a API do Claude (se houver
    crédito e ritmo diário); depois a contingência."""
    claude = etapa_fila(dificuldade) if not tarefas.orcamento_pausado(agente_id) else None
    max_ = [Etapa(max_texto.MODELO, max_texto.LIMITE_S)] if max_texto.pode_usar(usuario, agente_id) else []
    return max_ + ([claude] if claude else []) + etapas_contingencia()


async def _processar_proxima() -> int:
    """Processa uma tarefa adiada; devolve quantos segundos esperar antes da próxima."""
    for linha in tarefas.proximas_adiadas():
        agente = buscar_agente(linha["andar"], linha["agente"])
        if not agente:
            _falhar(linha["id"], "Agente não existe mais.")
            await _entregar(tarefas.obter(linha["id"]))
            continue
        etapas = _etapas_fila(Dificuldade(linha["dificuldade"]), linha["usuario"], agente.id)
        if agente.status == Status.trabalhando or not etapas:
            continue  # agente ocupado ou nenhum modelo no ar agora: fica para a próxima rodada

        tarefas.atualizar(linha["id"], status="executando")
        await atividade.ocupar(agente.id)
        try:
            concluiu = await _executar_etapas(linha, agente, etapas)
        finally:
            await atividade.liberar(agente.id)

        if not concluiu and not tarefas.reagendar(linha["id"]):
            _falhar(linha["id"], "Nenhum modelo conseguiu concluir a tarefa após várias tentativas.")
            await _entregar(tarefas.obter(linha["id"]))
        return 0

    return INTERVALO_FILA
