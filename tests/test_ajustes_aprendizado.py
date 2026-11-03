"""Ajustes pedidos pela equipe viram aprendizado (Thomas, 03/11/2026): vão ao contexto do agente e à consolidação
semanal. Banco temporário (tests/conftest.py); dados fictícios.
"""

import ajustes
import consolidacao_semanal
import tarefas

tarefas.iniciar()


def _pedido(agente: str, texto: str, empresa: str = "casa_veraneio") -> int:
    return tarefas.criar("usuario.teste", "marketing", agente, texto, "complexa", empresa)


def test_reconhece_ajuste():
    for texto in ("Ajuste na peça #33: aumente a logo", "troque o título por algo mais curto", "Aumente a logo"):
        assert ajustes.e_ajuste(texto), texto
    for texto in ("Carrossel do Lodge 12 para o Réveillon", "Qual a capacidade do Lodge 3?"):
        assert not ajustes.e_ajuste(texto), texto


def test_ajuste_entra_no_contexto_do_produtor_e_dos_afins_so_da_empresa():
    _pedido("designer", "Aumente a logo zzajuste no fechamento\n\nContexto do chat que não é do pedido")
    _pedido("criador_imagens", "Ajuste na peça #900: texto zzajuste mais para cima")
    _pedido("criador_imagens", "Diminua a logo zzajuste da Vero", empresa="casa_vero")
    _pedido("criador_imagens", "Carrossel novo zzajuste do Lodge 801")
    bloco = ajustes.para_contexto("criador_imagens", "casa_veraneio")
    assert "Aumente a logo zzajuste no fechamento" in bloco and "texto zzajuste mais para cima" in bloco
    assert "Contexto do chat" not in bloco and "da Vero" not in bloco and "Carrossel novo" not in bloco


def test_consolidacao_recebe_os_ajustes_da_semana():
    _pedido("copywriter", "Troque o CTA zzsemana por link da bio")
    grupos = consolidacao_semanal.coletar()["grupos"]
    copy = next(g for g in grupos if g["agente"] == "copywriter" and g["empresa"] == "Casa Veraneio")
    assert copy["ajustes_pedidos"] >= 1 and any("zzsemana" in p for p in copy["pedidos_de_ajuste"])
    assert "pedidos_de_ajuste" in consolidacao_semanal._prompt({"grupos": grupos})
