"""Revisar proposta antes de enviar (N2-estrategista-19, Onda 3 de novembro).

"Estrategista, revise esta proposta: <texto colado>" ou o arquivo anexo. A revisão roda pelo caminho SEM web da
análise de negócio (estrategista-18): Max sem ferramentas, com os nomes de clientes trocados por "[cliente]"
(carteira.ocultar). Com anexo, o pedido segue pelo caminho normal do Estrategista, que lê o anexo e já é sigiloso
(Max ou modelo local), com estas mesmas instruções no contexto.
O Estrategista confere clareza, tom do Corporativo (manual 11 e persona do manual 14), objeções sem resposta, CTA e
prazos, e devolve a proposta com as sugestões marcadas. Nota baixa não bloqueia o envio: é sugestão.
Valores: a resposta não repete os valores; se repetir, só quem tem acesso ao andar Comercial (e a Diretoria) os vê
(Thomas, 12/11/2026).
"""

import re

import config

AGENTE = "estrategista"
PEDIDO = re.compile(r"\brevis(?:ar|e|em|[aã]o|ando)\b.{0,40}\bpropostas?\b|\bpropostas?\b.{0,40}\brevis(?:ar|e|[aã]o)\b|"
                    r"\b(?:confer(?:ir|e)|checar?|cheque)\b.{0,30}\bpropostas?\b.{0,30}\bantes de enviar\b", re.I)
MANUAL_CORP = "11_casa_veraneio_corporativo.md"
MAX_MANUAL = 6000
# Thomas, 12/11/2026: valores das propostas só para quem tem acesso ao setor Comercial (andar liberado no painel de
# usuários); a Diretoria sempre vê.
ANDAR_VALORES = "comercial"
OCULTO_VALOR = "[valor]"
VALOR = re.compile(r"R\$\s*\d[\d.,]*(?:\s*(?:mil|milh[oõ]es|milh[aã]o|k)\b)?|\b\d[\d.,]*\s*(?:mil\s+)?reais\b", re.I)

INSTRUCOES = (
    "COMO REVISAR A PROPOSTA (pedido \"Revisar proposta\"; não há pesquisa na web): revise só com o texto da proposta, "
    "o manual do Corporativo e a persona acima. Confira:\n"
    "1) Clareza: frases longas, jargão, o que o cliente não entenderia de primeira.\n"
    "2) Tom do Corporativo: produtora 360° (produção completa do evento), nunca \"aluguel de espaço\" nem a promessa "
    "de que todo serviço está incluído; fala com quem decide na empresa.\n"
    "3) Objeções que ficaram sem resposta para esse tipo de evento (até 3, cada uma com a resposta sugerida).\n"
    "4) CTA: um próximo passo claro, com data e com quem fala.\n"
    "5) Prazos: validade da proposta, data do evento, datas de pagamento e de confirmação coerentes entre si e com "
    "hoje; aponte qualquer data que se contradiga ou que já passou.\n"
    "ENTREGUE: (a) uma nota de 0 a 10 com uma linha por ponto acima; (b) a PROPOSTA DEVOLVIDA, com o texto da "
    "pessoa e as sugestões marcadas no lugar: [SUGESTÃO: ...] para inserir ou trocar e ~~trecho~~ para cortar; (c) "
    "os 3 ajustes mais importantes. Não repita valores em reais: onde houver valor, escreva [valor]. Nomes trocados por "
    "[cliente] ficam como estão. O limite de palavras não vale para a proposta devolvida. Nota baixa não impede o "
    "envio: é sugestão.")


def e_pedido(agente_id: str, texto: str) -> bool:
    return agente_id == AGENTE and bool(PEDIDO.search(texto or ""))


def _manual_corp() -> str:
    """Manual 11, da abertura até a comunicação (seções 1 a 5); a identidade visual não interessa aqui."""
    try:
        texto = (config.PASTA_CONHECIMENTO / MANUAL_CORP).read_text(encoding="utf-8")
    except OSError:
        return ""
    return texto.split("\n## 6.", 1)[0].strip()[:MAX_MANUAL]


def blocos(ocultar) -> list[str]:
    """Blocos do prompt da revisão (o manual passa pelo mesmo filtro de nomes do resto do prompt)."""
    manual = _manual_corp()
    return [f"MANUAL DO CORPORATIVO (manual 11):\n{ocultar(manual)}" if manual else "", INSTRUCOES]


def contexto_anexo(agente_id: str, texto: str) -> str:
    """Instruções para o caminho normal (proposta anexada)."""
    return INSTRUCOES if e_pedido(agente_id, texto) else ""


def ve_valores(login: str) -> bool:
    if not login:
        return False
    import acesso
    from auth import ve_financeiro

    return ve_financeiro(login) or acesso.pode_ver_andar({"sub": login}, ANDAR_VALORES)


def sem_valores(texto: str, login: str) -> str:
    """Tira os valores em reais da resposta de quem não pode vê-los."""
    return texto if ve_valores(login) else VALOR.sub(OCULTO_VALOR, texto or "")
