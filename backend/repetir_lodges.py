"""'Repetir para…' (Onda 3, item 5; copywriter-04, primeira entrega): o mesmo texto refeito para até 5 Lodges.

Tarefas 103 a 111 (29/10/2026): nove idas e voltas, casa por casa, e cada texto saiu num padrão. Agora, depois de uma
legenda ou texto pronto para um Lodge, a pessoa escolhe até 5 outros e o sistema refaz o texto para cada um, um de
cada vez, com os dados da ficha (catálogo em tabela, cerebro_imoveis) e SÓ em modelo gratuito (o local por último).
Cada Lodge vira uma tarefa própria no mesmo chat (👍/👎 em cada um, e uma queda não perde os outros), e cada texto
passa pelo conferente (regras duras) e pela conferência dos dados do imóvel (cerebro_conferir) antes de chegar.
Sem preço por padrão (decisão 3): a ficha vai ao modelo sem as linhas de valor e o texto volta sem elas.
Por ora só a Casa Veraneio (o catálogo em tabela só tem ela).
"""

import asyncio
import logging
import re
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import cerebro_conferir
import cerebro_imoveis as imoveis
import conferente
import config
import correcoes
import empresas
import fichas
import roteamento
import saude
import tarefas
from auth import validar_token
from conexoes import gerenciador

log = logging.getLogger(__name__)
rotas = APIRouter(prefix="/api")

MAX_LODGES = 5
AGENTES = conferente.AGENTES  # agentes cujo resultado é texto de peça
EMPRESAS = set(imoveis.ORIGENS)  # só quem tem catálogo em tabela
MAX_GRATUITOS = 3
LIMITE_LOCAL_S = 10 * 60
CABECALHO = re.compile(r"^Lodge \d+:\s*\n")  # o texto repetido abre com "Lodge N:" (repetir de um repetido)
LINHA_DE_VALOR = re.compile(r"R\$|\bdi[aá]rias?\b|\btaxa\b|\bvalor(es)?\b|\bpre[çc]os?\b|temporada:", re.I)
PENSAMENTO = re.compile(r"<think>.*?</think>", re.S | re.I)


def _sem_valores(texto: str) -> str:
    """Tira as linhas com preço, diária ou taxa (a peça sai sem valores; decisão 3)."""
    return "\n".join(l for l in (texto or "").splitlines() if not LINHA_DE_VALOR.search(l)).strip()


def sem_linhas_de_preco(texto: str, pedido: str = "") -> str:
    """Linhas com "R$" saem, a menos que o pedido peça valores (decisão 3)."""
    if empresas.PEDE_PRECO.search(pedido or ""):
        return texto
    return "\n".join(l for l in (texto or "").splitlines() if not empresas.PRECO.search(l)).strip()


def texto_base(resposta: str, pedido: str = "") -> str:
    """O texto aprovado, sem o rodapé de avisos que o sistema acrescenta e sem as linhas de preço."""
    import cerebro_modelos  # mesmo corte do rodapé usado nos modelos de estilo

    texto = CABECALHO.sub("", cerebro_modelos.RODAPE.sub("", resposta or "").strip(), count=1).strip()
    return sem_linhas_de_preco(texto, pedido)


def lodge_de_origem(linha) -> int | None:
    citados = cerebro_conferir.citados(f"{linha['texto']}\n{linha['resposta'] or ''}", linha["empresa"])
    return int(citados[0]) if citados else None


def ficha_para_o_modelo(numero: int, empresa: str) -> str:
    """Ficha do Lodge sem valores: a linha do catálogo em tabela (números conferidos e comodidades) e o resumo do
    site (fichas.ficha), sem as linhas de preço, diária e taxa."""
    linha = imoveis.linha(numero, empresa) or {}
    campos = [("Nome", linha.get("nome")), ("Local", " / ".join(x for x in (linha.get("cidade"), linha.get("uf")) if x)),
              ("Bairro", linha.get("bairro")), ("Quartos", linha.get("quartos")), ("Suítes", linha.get("suites")),
              ("Capacidade", linha.get("pessoas") and f"até {linha['pessoas']} pessoas"),
              ("Categoria", linha.get("categorias")), ("Comodidades", linha.get("comodidades"))]
    tabela = "\n".join(f"{r}: {v}" for r, v in campos if v)
    site = _sem_valores(fichas.ficha(str(numero), empresa) or "")
    return "\n".join(p for p in (f"Lodge {numero}", tabela, site and f"Do site:\n{site}") if p)


def montar_prompt(agente: str, empresa: str, original: str, origem: int | None, numero: int, pedido: str) -> str:
    regras = correcoes.regras_para(agente, empresa)
    de_onde = f" (escrito para o Lodge {origem})" if origem else ""
    return (
        f"Você escreve textos da {empresas.nome(empresa)}. Reescreva o TEXTO APROVADO{de_onde} para o Lodge {numero}.\n"
        "Regras:\n"
        "- Mesmo formato, tom, estrutura, tamanho aproximado, chamada (CTA), hashtags e assinatura do texto aprovado.\n"
        f"- Troque TODOS os dados do imóvel (número, nome, cidade / UF, quartos, suítes, capacidade, comodidades) pelos "
        f"da FICHA DO LODGE {numero}. Nada do outro Lodge pode ficar.\n"
        "- Use só o que está na ficha; se faltar um dado, deixe de fora (nunca invente).\n"
        "- Sem preço, diária, taxa ou qualquer valor.\n"
        "- Localização sempre no formato \"Cidade / UF\". Nunca cite WhatsApp nem telefone.\n"
        "- Responda só com o texto novo, sem comentários antes ou depois.\n"
        + (f"\n{regras}\n" if regras else "")
        + f"\nFICHA DO LODGE {numero} (dados oficiais):\n{ficha_para_o_modelo(numero, empresa)}\n\n"
        f"TEXTO APROVADO:\n{original}\n"
        + (f"\nPedido original da pessoa (contexto): {pedido[:600]}\n" if pedido else ""))


def _chamar(modelo: str, prompt: str, limite_s: int) -> str:
    """Uma chamada direta ao modelo (sem agente nem ferramentas). Os testes trocam esta função."""
    from agents.executor import _llm  # import tardio: CrewAI é pesado

    return str(_llm(modelo, limite_s).call([{"role": "user", "content": prompt}]) or "")


def modelos_gratuitos(agente: str, texto: str) -> list[tuple[str, int]]:
    """Gratuitos de fora (se o texto não for sigiloso) e o local por último. Nunca Max nem API paga."""
    rota = [] if roteamento.sigilosa(agente, texto) else [
        (e.modelo, e.limite_s) for e in roteamento._gratuitos(MAX_GRATUITOS)]
    if config.MODELO_LOCAL and config.modelo_disponivel(config.MODELO_LOCAL):
        rota.append((config.MODELO_LOCAL, LIMITE_LOCAL_S))
    return rota


def gerar(tarefa_id: int, prompt: str, rota: list[tuple[str, int]]) -> tuple[str, str] | None:
    """(modelo, texto) do primeiro gratuito que responder; None se todos falharem."""
    for modelo, limite in rota:
        if tarefas.parada(tarefa_id):
            return None
        tarefas.registrar_evento(tarefa_id, "tentativa", modelo=modelo)
        inicio = time.monotonic()
        try:
            texto = PENSAMENTO.sub("", _chamar(modelo, prompt, limite)).strip()
        except Exception as erro:  # o próximo da rota assume
            if not modelo.startswith("ollama/"):  # o local demora por natureza: não sai da rota
                saude.registrar_falha(modelo, str(erro)[:300])
            tarefas.registrar_evento(tarefa_id, "falha_modelo", modelo=modelo, detalhe=str(erro)[:300])
            continue
        finally:
            tarefas.registrar_tentativa(tarefa_id, time.monotonic() - inicio)
        if len(texto) >= 20:
            saude.registrar_sucesso(modelo)
            return modelo, texto
        tarefas.registrar_evento(tarefa_id, "falha_modelo", modelo=modelo, detalhe="resposta vazia")
    return None


def conferir(texto: str, numero: int, empresa: str, pedido: str) -> str:
    """Texto final (sem valores, a menos que o pedido peça) + rodapé com os avisos do conferente e da ficha."""
    texto = sem_linhas_de_preco(texto, pedido)
    avisos = conferente.conferir(texto, empresa, "resposta", pedido)
    avisos += cerebro_conferir.divergencias(texto, empresa, "o texto")
    if (outros := [n for n in cerebro_conferir.citados(texto, empresa) if int(n) != numero]):
        avisos.append(f"cita o Lodge {', '.join(outros)}: confira se sobrou dado do texto original")
    rodape = conferente.rodape(avisos)
    return f"Lodge {numero}:\n\n{texto}" + (f"\n\n{rodape}" if rodape else "")


async def _rodar(origem, pendentes: list[tuple[int, int]]) -> None:
    """Um Lodge de cada vez (o gratuito não mistura casas e a queda de um não leva os outros)."""
    import orquestrador  # import tardio: o orquestrador importa quase tudo
    from agents.executor import Resultado

    original = texto_base(origem["resposta"], origem["texto"])
    de = lodge_de_origem(origem)
    rota = modelos_gratuitos(origem["agente"], original)
    for tarefa_id, numero in pendentes:
        if tarefas.parada(tarefa_id):
            continue
        try:
            prompt = await asyncio.to_thread(montar_prompt, origem["agente"], origem["empresa"], original, de, numero,
                                             origem["texto"])
            gerado = await asyncio.to_thread(gerar, tarefa_id, prompt, rota)
            if gerado:
                modelo, texto = gerado
                final = await asyncio.to_thread(conferir, texto, numero, origem["empresa"], origem["texto"])
                await orquestrador._concluir(tarefa_id, modelo, Resultado(texto=final))
                continue
            motivo = "Nenhum modelo gratuito conseguiu refazer o texto agora. Tente de novo em alguns minutos."
        except Exception as erro:
            log.exception("Repetir para o Lodge %s (tarefa %s) falhou.", numero, tarefa_id)
            motivo = f"Erro ao refazer o texto para o Lodge {numero}: {str(erro)[:150]}"
        orquestrador._falhar(tarefa_id, motivo)
        await orquestrador.entregar(tarefas.obter(tarefa_id))


def validar(linha, lodges: list[int]) -> list[int]:
    """Lodges a refazer (sem repetidos e sem o de origem). ValueError com a mensagem para a pessoa."""
    if linha["status"] != "concluida" or not (linha["resposta"] or "").strip():
        raise ValueError("Só dá para repetir um texto já pronto.")
    if linha["agente"] not in AGENTES:
        raise ValueError("\"Repetir para…\" vale para os agentes de texto (Copywriter, Social Media, E-mail, Tráfego).")
    if linha["empresa"] not in EMPRESAS:
        raise ValueError("Por enquanto só a Casa Veraneio tem o catálogo de Lodges para repetir o texto.")
    de = lodge_de_origem(linha)
    numeros = [n for n in dict.fromkeys(lodges) if n != de]
    if not numeros:
        raise ValueError("Escolha pelo menos um Lodge diferente do texto original.")
    if len(numeros) > MAX_LODGES:
        raise ValueError(f"No máximo {MAX_LODGES} Lodges por vez.")
    if (faltam := [n for n in numeros if not imoveis.linha(n, linha["empresa"])]):
        raise ValueError(f"Sem ficha no catálogo: Lodge {', '.join(map(str, faltam))}. Confira os números.")
    return numeros


async def repetir(linha, lodges: list[int], login: str) -> list[int]:
    """Cria uma tarefa por Lodge e roda em segundo plano. Devolve os ids das tarefas novas."""
    import orquestrador

    numeros = await asyncio.to_thread(validar, linha, lodges)
    if not modelos_gratuitos(linha["agente"], texto_base(linha["resposta"], linha["texto"])):
        raise ValueError("Nenhum modelo gratuito disponível agora. Tente de novo em alguns minutos.")
    pendentes = []
    for numero in numeros:
        tarefa_id = tarefas.criar(login, linha["andar"], linha["agente"],
                                  f"Repetir para o Lodge {numero}: mesmo texto da tarefa #{linha['id']}, com os dados "
                                  "da ficha.", "simples", linha["empresa"])
        tarefas.registrar_evento(tarefa_id, "recebida", linha["agente"], detalhe=f"Repetir da tarefa #{linha['id']}")
        pendentes.append((tarefa_id, numero))
    await gerenciador.enviar_para_usuario(login, {
        "tipo": "aviso", "andar": linha["andar"], "agente": linha["agente"], "titulo": "Repetir para…",
        "texto": f"Refazendo o texto para {', '.join(f'Lodge {n}' for n in numeros)} (modelo gratuito, um de cada "
                 "vez). Cada um chega aqui com a conferência da ficha."})
    orquestrador._em_segundo_plano(_rodar(linha, pendentes))
    return [t for t, _ in pendentes]


class Pedido(BaseModel):
    lodges: list[int] = Field(min_length=1, max_length=10)


@rotas.post("/tarefas/{tarefa_id}/repetir")
async def repetir_rota(tarefa_id: int, pedido: Pedido, authorization: str = Header("")):
    usuario = validar_token(authorization.removeprefix("Bearer ").strip())
    if not usuario:
        raise HTTPException(status_code=401, detail="Token inválido")
    linha = tarefas.obter(tarefa_id)
    if not linha or (linha["usuario"] != usuario["sub"] and not usuario.get("master")):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    try:
        ids = await repetir(linha, pedido.lodges, usuario["sub"])
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    return {"ok": True, "tarefas": ids}
