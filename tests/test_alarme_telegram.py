"""Alarme do Telegram (despachante-16): só o novo, repete a cada 6 h, avisa quando resolve. Sem rede."""

import alarme_telegram as at


def test_alarme_manda_novo_repete_e_resolve():
    enviadas = []
    alarme = at.Alarme(enviadas.append)
    max_parado = "Trabalhador do Max sem responder há 12 min. Confira o PC."
    assert alarme.conferir([max_parado], agora=0) and "12 min" in enviadas[-1]
    assert alarme.conferir(["Trabalhador do Max sem responder há 17 min. Confira o PC."], agora=300) == []
    assert alarme.conferir([max_parado], agora=at.REPETIR_S + 1)  # ainda parado depois de 6 h: lembra
    assert alarme.conferir([], agora=at.REPETIR_S + 400)[0].startswith("✅ Resolvido")
    assert len(enviadas) == 3


def test_alarme_desligado_sem_configuracao(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert not at.ativo()


def test_alarme_limpa_segredos(monkeypatch):
    enviados = []
    monkeypatch.setattr(at, "_api", lambda metodo, dados=None: enviados.append(dados))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    falsa = "sk-or-v1-" + "a" * 64
    at.enviar(f"erro com {falsa}")
    assert falsa not in enviados[0]["text"]
