"""Sigilo por linha no Cérebro (N2-gestor-09, N2-cerebro-09; conserto 17 da Onda 1, 11/11/2026).

Antes, um gratuito de fora que consultava o Cérebro perdia a resposta INTEIRA se um único trecho fosse sigiloso (ou
se a tarefa já tivesse visto um): "as casas do Nordeste" saía vazio (tarefa 270). Agora sai só o que é sigiloso:
  - o trecho inteiro marcado como financeiro ou carteira (base.SIGILOSO_REF: painel de CRM/Ads, ":financeiro",
    ":carteira", manual 14);
  - a linha com nome de cliente (carteira.tem_nomes).
A definição do que é sigiloso é a mesma de antes (a decisão 9a está aberta): muda só o tamanho do corte. Se sobrar
menos de 20% do texto, a resposta continua bloqueada inteira, como antes. Cada corte vai para o Registro de
atividade com o gatilho (trecho financeiro/carteira ou nome de cliente), sem o conteúdo cortado.
"""

import cerebro_base as base

MINIMO_RESTANTE = 0.20  # menos que isso do texto original: bloqueia tudo (sobra pouco para valer a pena)
BLOQUEIO = ("Esse conhecimento é sigiloso (CRM, carteira de clientes ou financeiro) e não pode ser usado aqui. "
            "Responda sem ele e diga ao usuário que esse detalhe fica com a Diretoria.")
AVISO = ("\n\n(Parte do conhecimento ficou de fora por ser sigilosa: CRM, carteira de clientes ou financeiro. Use o "
         "resto normalmente; se o pedido depender desse detalhe, diga que ele fica com a Diretoria.)")


def sigiloso(trecho: dict) -> bool:
    """Trecho financeiro ou da carteira (mesma regra da rota sigilosa, roteamento.sigilosa)."""
    return bool(base.SIGILOSO_REF.search(trecho.get("fonte_ref") or ""))


def separar(trechos: list[dict]) -> tuple[list[dict], list[dict]]:
    """(trechos que podem ir a um gratuito de fora, trechos sigilosos que ficam de fora)."""
    return [t for t in trechos if not sigiloso(t)], [t for t in trechos if sigiloso(t)]


def sem_nomes(texto: str) -> tuple[str, int]:
    """Tira as linhas com nome de cliente. Devolve (texto, nº de linhas tiradas). Sem Monday: nada a tirar."""
    import carteira  # import tardio: a carteira lê o Monday

    if not texto or not carteira.tem_nomes(texto):
        return texto, 0
    linhas = texto.split("\n")
    ficam = [l for l in linhas if not carteira.tem_nomes(l)]
    return "\n".join(ficam), len(linhas) - len(ficam)


def filtrar(texto: str, tamanho_original: int, trechos_fora: int = 0) -> tuple[str, str]:
    """Texto pronto para um gratuito de fora e o gatilho (vazio se nada saiu). `tamanho_original`: o texto antes de
    tirar os trechos sigilosos; `trechos_fora`: quantos saíram antes da montagem (separar)."""
    limpo, linhas_fora = sem_nomes(texto)
    if not trechos_fora and not linhas_fora:
        return texto, ""
    gatilho = ", ".join(p for p in (f"{trechos_fora} trecho(s) financeiro/carteira" if trechos_fora else "",
                                    f"{linhas_fora} linha(s) com nome de cliente" if linhas_fora else "") if p)
    if len(limpo.strip()) < MINIMO_RESTANTE * max(tamanho_original, 1):
        return BLOQUEIO, f"{gatilho}; sobrou menos de 20%: resposta bloqueada"
    return limpo.rstrip() + AVISO, gatilho
