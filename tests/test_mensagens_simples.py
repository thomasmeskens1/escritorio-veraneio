"""Mensagens que a pessoa vê, sem jargão e sem texto velho (Onda 1 de 11/11/2026: recepcionista-03, professor-08).

A tela dizia "Acesso negado.", "JSON inválido." e "exclusiva da conta do Thomas" (o Max está liberado para todos
desde 29/10/2026), e a escola ensinava outra coisa. O frontend tem a mesma conferência em
tests/frontend/chat_textos.test.js (o contêiner dos testes não monta o frontend).

Pendentes, fora deste pacote: agendamentos.py (aviso de produção) e orquestrador.py (aviso de tarefa adiada, que o
navegador já troca pelo texto simples de js/chat_textos.js).
"""

from pathlib import Path

import config

PROIBIDAS = ("exclusiva da conta do Thomas", "modelos imediatos", "fila de contingência", '"Acesso negado."',
             '"JSON inválido."', '"Agente não encontrado."', '"Tipo de mensagem desconhecido."')
ARQUIVOS = ("main.py",)


def test_mensagens_do_chat_sem_jargao():
    pasta = Path(config.__file__).resolve().parent  # backend/ (no contêiner, /app)
    for nome in ARQUIVOS:
        texto = (pasta / nome).read_text(encoding="utf-8")
        achadas = [p for p in PROIBIDAS if p in texto]
        assert not achadas, f"{nome}: troque por palavras simples: {achadas}"
