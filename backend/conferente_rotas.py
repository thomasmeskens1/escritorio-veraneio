"""Botão "Corrigir o mecânico" da legenda no chat (Onda 2 de novembro, copywriter-03; js/conferencia.js).

Em código e sem IA: acha a legenda dentro da resposta do agente e devolve o antes e o depois com as trocas que não
mudam o sentido (travessão, hashtag e "Cidade / UF"). Nada é gravado: a pessoa vê o depois e copia se quiser. O que
não é mecânico (fatos, CTA, palavras vetadas) continua só como aviso.
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import conferente
import conferente_motor as motor
import empresas
from auth import validar_token

rotas = APIRouter(prefix="/api/conferencia")


class PedidoMecanico(BaseModel):
    texto: str = Field(max_length=20000)
    empresa: str = Field("", max_length=40)


def corrigir(texto: str, empresa: str = "") -> dict:
    """{"antes", "depois", "trocas", "avisos"}: "avisos" é o que sobra para a pessoa olhar (não mecânico)."""
    legenda = motor.legenda_do_texto(texto)
    if not legenda:
        return {"antes": "", "depois": "", "trocas": [], "avisos": []}
    empresa = empresa if empresas.valida(empresa) else motor.empresa_pela_assinatura(legenda)
    depois, trocas = motor.corrigir_mecanico(legenda, empresa)
    avisos = conferente.conferir(depois, empresa, "legenda") if empresa else motor.formato_legenda(depois, "")
    return {"antes": legenda, "depois": depois, "trocas": trocas, "avisos": avisos}


@rotas.post("/mecanico")
def mecanico(corpo: PedidoMecanico, authorization: str = Header("")):
    if not validar_token(authorization.removeprefix("Bearer ").strip()):
        raise HTTPException(status_code=401, detail="Token inválido")
    return corrigir(corpo.texto, corpo.empresa)
