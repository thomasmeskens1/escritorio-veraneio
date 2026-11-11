"""Cadastro completo de cada agente (Onda 1 de 11/11/2026: construtor-04, recepcionista-02, professor-01).

Colocar um agente no escritório mexe em várias peças, e algumas ficavam para trás sem ninguém notar (o Sonoplasta
entrou em 05/11 sem linha no manual da escola). Aqui se confere, sem IA, que todo agente de chat do estado.py tem
ficha, perfil, gatilho na triagem, manual da função e está no manual da escola. O manual 16 (fichas de pedido) fica
fora do git: quando existe, a falta de ficha só AVISA, sem travar o commit (o Thomas aprova as fichas novas).

Faltou algo? A mensagem diz em palavras simples o que escrever e onde.
"""

import re
import warnings

import config
import encaminhamento
import triagem
from agents import diretrizes, perfis
from estado import ANDARES

# Agentes de chat (sem o Despachante, que é painel, e sem os Estagiários).
AGENTES = [(andar, a) for andar, agentes in ANDARES.items() for a in agentes.values() if a.tipo == "ia"]

# Sem documento de função em diretrizes.DA_FUNCAO, de propósito (11/11/2026). A escola usa o manual da escola, o
# Construtor tem contexto próprio e o Cérebro não tem chat. O Sonoplasta recebe as seções do manual 05 por SECOES.
SEM_MANUAL_DA_FUNCAO = {"construtor", "recepcionista", "professor", "cerebro", "sonoplasta"}


def _faltas(teste) -> list[str]:
    return [f"{a.nome} ({andar}): {falta}" for andar, a in AGENTES if (falta := teste(a))]


def test_ficha_do_agente_completa():
    def teste(a):
        vazios = [campo for campo in ("nome", "funcao", "descricao", "exemplo") if not getattr(a, campo).strip()]
        return f"falta {', '.join(vazios)} no estado.py" if vazios else ""
    assert not (faltas := _faltas(teste)), faltas


def test_perfil_em_perfis():
    def teste(a):
        perfil = perfis.PERFIS.get(a.id)
        if not perfil:
            return "falta o perfil em agents/perfis.py (PERFIS)"
        vazios = [campo for campo in ("role", "goal", "backstory") if not str(perfil.get(campo, "")).strip()]
        return f"falta {', '.join(vazios)} no perfil" if vazios else ""
    assert not (faltas := _faltas(teste)), faltas


def test_gatilho_na_triagem():
    def teste(a):
        if a.id in triagem.SEM_TRIAGEM or a.id in triagem.EXTRA or a.id in encaminhamento.ESCOPO:
            return ""
        return "falta o gatilho de palavras em triagem.EXTRA (ou encaminhamento.ESCOPO)"
    assert not (faltas := _faltas(teste)), faltas


def test_manual_da_funcao_ou_excecao():
    def teste(a):
        if a.id in diretrizes.DA_FUNCAO or a.id in SEM_MANUAL_DA_FUNCAO:
            return ""
        return "falta o manual em diretrizes.DA_FUNCAO (ou a exceção em SEM_MANUAL_DA_FUNCAO, com o motivo)"
    assert not (faltas := _faltas(teste)), faltas


def test_agente_no_manual_da_escola():
    andares = perfis.MANUAL_ESCOLA.split("## Andares", 1)[1].split("\n## ", 1)[0]
    assert not (faltas := _faltas(lambda a: "" if a.nome in andares else
                                  "falta o nome na seção \"Andares\" de agents/manual_escola.md")), faltas


def test_recursos_novos_no_manual_da_escola():
    """Uma linha por recurso da tela (recepcionista-01): a escola explica o botão que a pessoa vê."""
    for recurso in ("Desdobrar 4:5 e 9:16", "Repetir para…", "Parar", "Reenviar", "Produzir a semana",
                    "Lance no Monday", "FINAL", "_com_som", ".docx", "Mais curto", "3 variações",
                    "Levar para uma Peça final", "Enviar para", "Caixa de entrada", "Como pedir um ajuste"):
        assert recurso in perfis.MANUAL_ESCOLA, f"falta explicar \"{recurso}\" em agents/manual_escola.md"


def test_ficha_de_pedido_no_manual_16_so_avisa():
    achados = sorted(config.PASTA_CONHECIMENTO.glob("16_*.md"))
    if not achados:
        return  # manual fora do git (ambiente de teste): nada a conferir
    titulos = " ".join(re.findall(r"^#+\s*(.+)$", achados[0].read_text(encoding="utf-8"), re.M)).lower()
    faltas = [a.nome for _, a in AGENTES if a.id not in perfis.AGENTES_ESCOLA | {"construtor", "cerebro"}
              and a.nome.lower() not in titulos]
    if faltas:
        warnings.warn(f"Manual 16 sem ficha de pedido para: {', '.join(faltas)} (o Thomas aprova o texto)")
