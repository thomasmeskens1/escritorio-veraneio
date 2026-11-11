"""Prazo comercial "fechar até", por empresa e por momento: o início dos "fatos com validade" (Onda 1 de novembro;
copywriter-01, analista_tendencias-01, gestor-03).

O sistema sabia QUANDO cada momento acontece, mas não ATÉ QUANDO dá para fechar. Os agentes perguntavam de novo a
cada peça e a urgência saía vaga ("faltam dois meses"). Agora o prazo fica em dados/calendario.json (fora do git),
na chave "prazos_comerciais", com quem confirmou e quando:
  {"prazos_comerciais": {"cv_corporativo": [{"momento": "Confraternizações de fim de ano", "fechar_ate": "2026-11-30",
   "estado": "poucas datas", "confirmado_por": "login", "confirmado_em": "2026-11-11"}]}}
Validade: 7 dias a partir da confirmação. Vencido, o prazo não sustenta urgência até alguém reconfirmar. Nada aqui
apaga dado (decisão 17 em aberto): o prazo vencido continua no arquivo, só deixa de valer. Sem valores (o
repositório é público e valor não entra em peça por padrão).
"""

import json
import re
import threading
import unicodedata
from datetime import date, timedelta

import calendario
import empresas

VALIDADE_DIAS = 7
ESTADOS = ("aberta", "poucas datas", "quase fechado")
_trava = threading.Lock()


def _chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def _data(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def prazos(empresa: str, hoje: date | None = None) -> list[dict]:
    """Prazos da empresa com a validade calculada: "vale_ate", "valido" e "faltam" (dias até o fechamento)."""
    hoje = hoje or date.today()
    lista = []
    for p in calendario._config().get("prazos_comerciais", {}).get(empresa) or []:
        if not isinstance(p, dict) or not p.get("momento") or not (fechar := _data(p.get("fechar_ate"))):
            continue
        # Sem data de confirmação (editado à mão): conta como vencido, nunca como válido para sempre.
        confirmado = _data(p.get("confirmado_em")) or date.min
        vale_ate = confirmado + timedelta(days=VALIDADE_DIAS)
        lista.append({**p, "fechar_ate": fechar, "confirmado_em": confirmado, "vale_ate": vale_ate,
                      "faltam": (fechar - hoje).days, "valido": hoje <= vale_ate and fechar >= hoje})
    return sorted(lista, key=lambda p: p["fechar_ate"])


def registrar(empresa: str, momento: str, fechar_ate: str, por: str, estado: str = "",
              hoje: date | None = None) -> dict:
    """Grava (ou reconfirma) o prazo de um momento. Valida tudo na entrada: o arquivo é lido por todos os agentes."""
    hoje = hoje or date.today()
    momento = re.sub(r"\s+", " ", str(momento or "")).strip()
    fechar = _data(fechar_ate)
    if not empresas.valida(empresa):
        raise ValueError("Empresa inválida.")
    if not momento or len(momento) > 80:
        raise ValueError("Diga o momento (até 80 caracteres), ex.: \"Réveillon\".")
    if not fechar or fechar < hoje:
        raise ValueError("A data de fechamento precisa ser AAAA-MM-DD e não pode ter passado.")
    if estado and estado not in ESTADOS:
        raise ValueError(f"Estado da agenda: {', '.join(ESTADOS)}.")
    if not re.fullmatch(r"[\w.@-]{1,60}", por or ""):
        raise ValueError("Quem confirmou precisa ser o login.")
    novo = {"momento": momento, "fechar_ate": fechar.isoformat(), "estado": estado, "confirmado_por": por,
            "confirmado_em": hoje.isoformat()}
    with _trava:
        dados = calendario._config()
        lista = [p for p in dados.setdefault("prazos_comerciais", {}).get(empresa) or []
                 if isinstance(p, dict) and _chave(p.get("momento", "")) != _chave(momento)]
        dados["prazos_comerciais"][empresa] = lista + [novo]
        temporario = calendario.ARQUIVO.with_suffix(".tmp")
        calendario.ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(calendario.ARQUIVO)
    return novo


def citados(empresa: str, texto: str, hoje: date | None = None) -> list[dict]:
    """Prazos cujo momento aparece no texto (por palavra: "Réveillon 2027" casa com "Réveillon")."""
    alvo = f" {_chave(texto)} "
    return [p for p in prazos(empresa, hoje)
            if (palavras := [w for w in _chave(p["momento"]).split() if len(w) >= 5])
            and any(f" {w} " in alvo for w in palavras)]


def vigente(empresa: str, texto: str, hoje: date | None = None) -> dict | None:
    """O prazo válido que sustenta a urgência do texto: o do momento citado ou, sem momento citado, qualquer válido."""
    candidatos = citados(empresa, texto, hoje) or prazos(empresa, hoje)
    return next((p for p in candidatos if p["valido"]), None)


def bloco(empresa: str, hoje: date | None = None) -> str:
    """Linhas para o bloco de datas de quem planeja e escreve."""
    hoje = hoje or date.today()
    lista = prazos(empresa, hoje)
    if not lista:
        return ("PRAZO DE FECHAMENTO: nenhum cadastrado para esta empresa. Sem prazo confirmado, nada de urgência de "
                "data (\"últimos dias\", \"só até\", \"ainda dá tempo\"): convide sem prazo ou marque PENDENTE.")
    linhas = [f"PRAZOS DE FECHAMENTO (confirmados pela equipe; cada um vale {VALIDADE_DIAS} dias):"]
    for p in lista:
        quem = (f"confirmado por {p.get('confirmado_por') or '?'} em {p['confirmado_em']:%d/%m}"
                if p["confirmado_em"] != date.min else "sem data de confirmação")
        estado = f"; agenda: {p['estado']}" if p.get("estado") else ""
        if p["valido"]:
            linhas.append(f"- {p['momento']}: fechar até {p['fechar_ate']:%d/%m/%Y}, faltam {p['faltam']} dias{estado} "
                          f"({quem}, vale até {p['vale_ate']:%d/%m})")
        else:
            motivo = ("o prazo já passou" if p["fechar_ate"] < hoje else "sem confirmação válida"
                      if p["confirmado_em"] == date.min else f"confirmação vencida em {p['vale_ate']:%d/%m}")
            linhas.append(f"- {p['momento']}: {motivo} ({quem}). Não use urgência de data até reconfirmar.")
    linhas.append("Urgência (\"últimos dias\", \"só até\") só com prazo válido acima; sem ele, convite sem prazo.")
    return "\n".join(linhas)
