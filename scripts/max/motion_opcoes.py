"""Opções da vinheta de cada empresa (Thomas, 04/11/2026: "mais 3 opções de cada empresa, para eu ver outros
formatos e escolher a versão definitiva"). A opção A é a aprovada (motion_roteiros.ROTEIROS) e segue o padrão de
produção; B, C e D ficam nos arquivos motion_opcoes_<empresa>.py.

Cada opção: {"titulo", "duracao", "batidas", "camadas": f(t, palco)} e, se precisar de imagens próprias (cortina,
painel de LED, contorno do logo), "preparar": f(palco), chamado uma vez por renderização.
"""

import motion_roteiros
from motion_opcoes_corp import OPCOES_CORP
from motion_opcoes_veraneio import OPCOES_VERANEIO
from motion_opcoes_vero import OPCOES_VERO

VARIANTES = ("A", "B", "C", "D")
OPCOES = {
    empresa: {"A": {"titulo": "Aprovada", **motion_roteiros.ROTEIROS[empresa]}, **extras}
    for empresa, extras in (("casa_veraneio", OPCOES_VERANEIO), ("cv_corporativo", OPCOES_CORP),
                            ("casa_vero", OPCOES_VERO))
}


def roteiro(empresa: str, variante: str = "A") -> dict:
    if empresa not in OPCOES:
        raise ValueError(f"Empresa sem vinheta: {empresa!r} (use {', '.join(OPCOES)})")
    variante = str(variante or "A").upper()
    if variante not in OPCOES[empresa]:
        raise ValueError(f"Opção da vinheta: {', '.join(OPCOES[empresa])} (pedida: {variante!r})")
    return OPCOES[empresa][variante]
