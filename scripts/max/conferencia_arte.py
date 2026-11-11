"""Lista fixa que o Max confere nos PNGs/quadros finais na MESMA rodada da produção (Onda 2, item 2; gestor-10 e
designer-03; 31/10/2026). Sem rodada extra: ele abre cada arte final com Read antes de terminar, corrige o que
falhar e diz no resumo o que conferiu. As regras de texto do backend ficam em backend/conferente_regras.py.
"""

COMUM = [
    "logo só desta empresa (pasta CÉREBRO/MARCAS dela), na cor certa para o fundo e sem redesenho",
    "paleta Verde #00361B, Creme #F0DBC3, Caramelo #D9A15B e Branco #FFFFFF; degradê ou caixa de leitura nunca "
    "preta",
    "nenhum rótulo interno do plano escrito na arte (GANCHO, URGÊNCIA, SLIDE 1, CTA, KICKER, TÍTULO)",
    "título sem palavra sozinha na última linha",
    "localização como \"Cidade / UF\"",
    "sem WhatsApp, telefone ou endereço de site escrito na arte",
    "sem valor (R$, diária, preço) se o pedido não pediu",
    "texto e logo fora das zonas mortas do manual 08 e longe da borda",
    "texto da arte combina com a foto do slide",
]
POR_EMPRESA = {
    "casa_veraneio": "nada do Corporativo (\"CORP.\") nem da Casa Vero",
    # designer-06 (Onda 2 de novembro): só aviso, nunca bloqueio; sem foto liberada, propõe alternativa sem rostos.
    "cv_corporativo": "nada da Casa Veraneio (Lodges) nem da Casa Vero; sem diária, estadia ou dado de hospedagem; "
                      "rosto reconhecível em destaque só com autorização de imagem; nenhuma logo ou crachá de "
                      "cliente; nenhum sinal de época (máscara, decoração de outra data); sem foto liberada, use "
                      "ambiente montado, mesa posta, palco ou pessoas de costas/desfocadas e avise no resumo",
    "casa_vero": "nada da Casa Veraneio nem do Corporativo, nem a palavra \"Lodge\"; sem valor de venda, condomínio "
                 "ou IPTU sem autorização no pedido",
}


def instrucao(empresa: str, entrega: str = "") -> str:
    """Bloco do prompt da produção. Entrega só de texto ou documento: sem arte, sem lista."""
    if entrega in ("texto", "documento"):
        return ""
    itens = COMUM + [POR_EMPRESA.get(empresa, POR_EMPRESA["casa_veraneio"])]
    return ("CONFERÊNCIA FINAL (na mesma rodada, sem rodada extra): antes de responder, abra com Read cada PNG final "
            "(no vídeo, 3 quadros extraídos com ffmpeg) e confira: " + "; ".join(f"({i}) {t}" for i, t in
                                                                               enumerate(itens, 1))
            + ". Falhou algum item: corrija só a arte que falhou, uma vez. No resumo, uma linha \"Conferência de "
            "marca: OK\" ou \"Conferência de marca: corrigido X / atenção Y\".")
