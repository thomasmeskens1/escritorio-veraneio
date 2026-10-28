"""Teste de estresse do Gestor coordenando a equipe (plano -> etapas dos especialistas -> consolidação).

O teste dos agentes (estresse_agentes.py) roda o Gestor sozinho. Aqui roda o projeto inteiro, como no chat, para
pegar erros que só aparecem na passagem entre agentes:
- plano com agente errado (produção de arquivo num pedido de ideias; vídeo com o Criador de Imagens);
- regra perdida na consolidação (WhatsApp, site na arte, preço da Casa Vero, mistura de empresas, casal);
- etapa que falha e derruba o projeto; tempo total.
Mesmas garantias do outro teste: só modelos gratuitos, nada gravado em tarefa, Monday, Brevo ou produção. O projeto
usa uma pasta de teste (dados/projetos/99xxxx) que é apagada no fim.

  docker exec -w /app -e PYTHONPATH=/app escritorio-veraneio-api-1 python /tmp/estresse_gestor.py 6 7
"""

import json
import random
import shutil
import sys
import threading
import time
from datetime import datetime

import config
import empresas
from agents import executor, projeto
from agents.perfis import contexto
from estado import ANDARES
from roteamento import etapas_contingencia

sys.path.insert(0, "/tmp")
import estresse_agentes as E  # noqa: E402  (verificadores e proteções do teste dos agentes)

PEDIDOS = {
    "ideias": "Me dá 3 ideias de post para a semana sobre {tema}.",
    "peca_video": "Peça final: um reels de 20 s sobre {tema}.",
    "peca_imagem": "Peça final: um carrossel de 5 slides sobre {tema}.",
}
PRODUZEM = {"criador_imagens", "editor_video"}


def checar_plano(plano: list[dict], tipo: str) -> list[str]:
    problemas = []
    agentes = [p["agente"] for p in plano]
    validos = set(ANDARES["marketing"])
    if not plano:
        return ["plano vazio"]
    if any(a not in validos for a in agentes):
        problemas.append(f"agente inexistente no plano: {[a for a in agentes if a not in validos]}")
    if tipo == "ideias" and PRODUZEM & set(agentes):
        problemas.append("pedido de ideias acionou produção de arquivo")
    if tipo == "peca_video" and "editor_video" not in agentes:
        problemas.append("reels sem o Editor de Vídeo no plano")
    if tipo == "peca_video" and "criador_imagens" in agentes and "editor_video" in agentes:
        problemas.append("reels com dois produtores (Criador de Imagens e Editor de Vídeo)")
    if tipo == "peca_imagem" and "criador_imagens" not in agentes:
        problemas.append("carrossel sem o Criador de Imagens no plano")
    return problemas


def rodar(rodadas: int, semente: int) -> None:
    sorteio = random.Random(semente)
    empresa_atual = ["casa_veraneio"]
    E._sem_efeitos_colaterais(empresa_atual)
    modelos = [e for e in etapas_contingencia() if not e.modelo.startswith("ollama/")]
    saida = config.DADOS_DIR / "testes" / f"estresse_gestor_{datetime.now():%Y%m%d_%H%M}.jsonl"
    saida.parent.mkdir(parents=True, exist_ok=True)

    def executar(agente: str, descricao: str, esperado: str, _papel: str) -> str:
        erros = []
        for etapa in sorteio.sample(modelos, len(modelos)):
            try:
                return executor._rodar(agente, descricao, esperado, etapa.modelo, etapa.limite_s,
                                       executor.Resultado(texto=""), 0)
            except Exception as erro:
                erros.append(f"{etapa.modelo.split('/')[-1]}: {str(erro)[:80]}")
        raise RuntimeError(f"nenhum modelo gratuito respondeu ({'; '.join(erros[:3])})")

    for n in range(1, rodadas + 1):
        empresa = sorteio.choice(E.EMPRESAS)
        tipo = sorteio.choice(list(PEDIDOS))
        cenario = sorteio.choice(["normal", "whatsapp", "outra_empresa", "casal", "site_na_arte"])
        empresa_atual[0] = empresa
        pedido = PEDIDOS[tipo].format(tema=E.TEMAS[empresa])
        if cenario != "normal":
            pedido = f"{pedido} {E.ADVERSARIAIS[cenario]}"
        tarefa_id = 990000 + n  # pasta de teste, apagada no fim
        pasta = projeto.PASTA_PROJETOS / str(tarefa_id)
        registro = {"n": n, "empresa": empresa, "tipo": tipo, "cenario": cenario, "pedido": pedido}
        inicio = time.monotonic()
        try:
            final = projeto.executar_projeto(tarefa_id, f"[Pedido feito ao Gestor] {pedido}",
                                             contexto("gestor", [], pedido, empresa), executar, threading.Event())
            final = empresas.sem_precos(final, empresa, pedido)  # o filtro que o executor aplica na resposta
            plano = json.loads((pasta / "plano.json").read_text(encoding="utf-8"))
            registro.update(plano=[{"agente": p["agente"], "fase": p.get("fase")} for p in plano], resposta=final,
                            problemas=checar_plano(plano, tipo) + E.verificar(final, empresa, cenario))
        except Exception as erro:
            registro.update(resposta="", problemas=[f"projeto falhou: {str(erro)[:200]}"])
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        registro["segundos"] = round(time.monotonic() - inicio)
        with saida.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        plano_txt = " > ".join(p["agente"] for p in registro.get("plano", []))
        print(f"{n}/{rodadas} [{empresa}] {tipo} {cenario} ({registro['segundos']} s) plano: {plano_txt or '-'} -> "
              f"{'OK' if not registro['problemas'] else '; '.join(registro['problemas'])}", flush=True)
        time.sleep(5)
    print(saida)


if __name__ == "__main__":
    rodar(int(sys.argv[1]) if len(sys.argv) > 1 else 6, int(sys.argv[2]) if len(sys.argv) > 2 else 7)
