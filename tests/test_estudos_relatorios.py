"""Estudos com pesquisa na web (Analista de Tendências, Estrategista) e o relatório visual do Analista de Métricas.

  docker exec -w /tmp -e PYTHONPATH=/app escritorio-veraneio-api-1 python -m pytest test_estudos_relatorios.py
"""

import empresas
import estudos
import relatorios


def test_estudo_so_quando_pede_analise():
    assert estudos.e_estudo("estrategista", "Onde estamos na Matriz BCG e para onde chegar?")
    assert estudos.e_estudo("analista_tendencias", "Avalie o mercado e as notícias e preveja bons caminhos")
    assert not estudos.e_estudo("estrategista", "O que é a matriz BCG?")  # explicação: resposta na hora
    assert not estudos.e_estudo("analista_tendencias", "Quando é o Carnaval?")
    assert not estudos.e_estudo("copywriter", "Avalie o mercado")


def test_estrategista_olha_o_grupo_salvo_se_citar_uma_empresa():
    assert estudos.empresa_do_estudo("estrategista", "Onde estamos na BCG?", "cv_corporativo") == empresas.COMUM
    assert estudos.empresa_do_estudo("estrategista", "SWOT da Casa Vero", empresas.COMUM) == "casa_vero"
    assert estudos.empresa_do_estudo("analista_tendencias", "Avalie o mercado", "casa_veraneio") == "casa_veraneio"


def test_prompt_de_tendencias_tem_calendario_e_regras():
    texto = estudos.prompt("analista_tendencias", "Avalie o mercado do verão", "casa_veraneio")
    assert "HOJE É" in texto and "Carnaval" in texto
    assert "FATO" in texto and "grau de confiança" in texto
    assert texto.rstrip().endswith("PEDIDO DO USUÁRIO: Avalie o mercado do verão")


def test_relatorio_link_e_rota_seguros():
    assert relatorios.NOME_ARQUIVO.match("87-om_uAugk-1-E8oMFaG1Df114.html")
    assert not relatorios.NOME_ARQUIVO.match("../escritorio.db")
    assert not relatorios.NOME_ARQUIVO.match("87-curto.html")


def test_relatorio_numeros_do_banco_e_analise_escapada():
    if not relatorios.BANCO.exists():  # painel não montado: nada a testar
        return
    numeros = relatorios.dados(empresas.COMUM)
    assert [b["conta"] for b in numeros["blocos"]] == list(relatorios.CONTAS_INSTAGRAM.values())
    pagina = relatorios.html_do_relatorio(1, "pedido", "**Ok** <script>x</script>", empresas.COMUM, numeros)
    assert "<strong>Ok</strong>" in pagina and "&lt;script&gt;x" in pagina
    assert "Chart.js/4.4.1" in pagina
