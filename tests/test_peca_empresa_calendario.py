"""Correções do teste real de 28/10/2026 (#84 a #88) e o calendário do Analista de Tendências.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_peca_empresa_calendario.py
"""

from datetime import date

import calendario_eventos as cal
import empresas
import monday
import producao
from agents.executor import sem_espanhol


def _pedido(tipo: str, texto: str = "Peça sobre o Carnaval no Lodge 1") -> str:
    return f"{texto}\n\nFORMATO DA PEÇA (obrigatório): {tipo} = {monday.TIPOS[tipo]}. Produza exatamente este formato."


def test_carrossel_vai_ao_criador_de_imagens():
    # A descrição do CARROSSEL cita "vídeo", "MP4" e "Editor de Vídeo"; antes isso mandava ao Editor (#86).
    pedido = _pedido("CARROSSEL")
    assert producao.produtor_da_peca(f"{pedido}\nConsolidado com cenas e vídeo do Reels anterior", pedido) \
        == "criador_imagens"
    assert producao.produtor_da_peca(_pedido("POST")) == "criador_imagens"


def test_video_vai_ao_editor():
    assert producao.produtor_da_peca(_pedido("REELS")) == "editor_video"
    assert producao.produtor_da_peca(_pedido("SHORTS")) == "editor_video"
    pedido = _pedido("CARROSSEL", "Carrossel com páginas em vídeo do Lodge 1")
    assert producao.produtor_da_peca(pedido, pedido) == "editor_video"
    assert producao.produtor_da_peca("Um vídeo do Lodge 1") == "editor_video"


def test_empresa_citada_no_pedido():
    assert empresas.citada("Carrossel do Lodge 1. A empresa é a Casa Veraneio") == "casa_veraneio"
    assert empresas.citada("Evento da Casa Veraneio Corporativo") == "cv_corporativo"
    assert empresas.citada("Vídeo da Casa Vero") == "casa_vero"
    assert empresas.citada("Compare a Casa Vero com a Casa Veraneio") is None  # duas: fica o seletor
    assert empresas.citada("Carrossel do Lodge 1") is None


def test_contexto_do_grupo_inteiro():
    texto = empresas.contexto(empresas.COMUM)
    assert all(d["nome"] in texto for d in empresas.EMPRESAS.values())
    assert "nunca some" in texto


def test_sem_espanhol():
    assert sem_espanhol("A peça de condición especial. También vale.") == "A peça de condição especial. Também vale."
    assert sem_espanhol("Las informaciones") == "Las informações"
    assert sem_espanhol("Comparação e posição") == "Comparação e posição"


def test_datas_calculadas():
    assert cal.pascoa(2026) == date(2026, 4, 5) and cal.pascoa(2027) == date(2027, 3, 28)
    carnaval = next(e for e in cal.eventos(2027) if e["nome"] == "Carnaval")
    assert carnaval["data"] == date(2027, 2, 6) and carnaval["fim"] == date(2027, 2, 10)  # sábado a quarta
    corpus = next(e for e in cal.eventos(2027) if e["nome"] == "Corpus Christi")
    assert corpus["data"] == date(2027, 5, 27)
    assert next(e for e in cal.eventos(2027) if e["nome"] == "Dia das Mães")["data"] == date(2027, 5, 9)
    assert next(e for e in cal.eventos(2026) if e["nome"] == "Black Friday")["data"] == date(2026, 11, 27)


def test_calendario_diz_prazo_e_feriadao():
    texto = cal.texto(date(2026, 10, 28))
    assert texto.startswith("HOJE É 28/10/2026")
    carnaval = next(linha for linha in texto.splitlines() if "Carnaval" in linha)
    assert "daqui a 11 dias: no prazo" in carnaval
    reveillon = next(linha for linha in texto.splitlines() if "Réveillon" in linha and "2026" in linha)
    assert "ponte na sexta" in reveillon
