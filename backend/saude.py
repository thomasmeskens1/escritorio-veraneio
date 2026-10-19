"""Saúde dos modelos: quem estourou cota/crédito fica fora da rota até a cota voltar."""

import time
from datetime import datetime, timedelta, timezone

# modelo -> (timestamp até quando fica indisponível, motivo)
_indisponivel: dict[str, tuple[float, str]] = {}


def _proxima_meia_noite_utc() -> float:
    amanha = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime(amanha.year, amanha.month, amanha.day, tzinfo=timezone.utc).timestamp()


def _proximo_mes_utc() -> float:
    hoje = datetime.now(timezone.utc)
    ano, mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
    return datetime(ano, mes, 1, tzinfo=timezone.utc).timestamp()


def registrar_falha(modelo: str, erro: str) -> None:
    """Decide por quanto tempo o modelo sai da rota, conforme o tipo de erro."""
    texto = erro.lower()
    if "credit balance" in texto:                          # crédito Anthropic do mês acabou
        ate, motivo = _proximo_mes_utc(), "crédito do mês esgotado"
    elif "per-day" in texto or "per day" in texto:          # cota diária gratuita (OpenRouter)
        ate, motivo = _proxima_meia_noite_utc(), "cota diária esgotada"
    elif "429" in texto or "rate" in texto:                 # limite por minuto ou provedor sobrecarregado
        ate, motivo = time.time() + 120, "limite temporário"
    else:                                                   # erro desconhecido: pausa curta
        ate, motivo = time.time() + 60, "erro recente"
    _indisponivel[modelo] = (ate, motivo)


def disponivel(modelo: str) -> bool:
    ate, _ = _indisponivel.get(modelo, (0, ""))
    return time.time() >= ate


def resumo() -> list[dict]:
    """Modelos fora da rota agora (para o painel)."""
    agora = time.time()
    return [
        {"modelo": m, "motivo": motivo,
         "volta_em": datetime.fromtimestamp(ate, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for m, (ate, motivo) in _indisponivel.items() if ate > agora
    ]
