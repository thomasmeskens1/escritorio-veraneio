"""Prospectador: só canais da empresa (LGPD) e nada de repetir quem já está no CRM (sem chamar o Monday).

Rodar no container: docker exec -w /app -e PYTHONPATH=/app escritorio-veraneio-api-1 python /tests/test_comercial.py
"""

import comercial as c


def test_email_so_caixa_generica_do_dominio():
    assert c.email_permitido("eventos@empresa.com.br", "https://www.empresa.com.br")
    assert c.email_permitido("rh@sp.empresa.com.br", "empresa.com.br")
    assert not c.email_permitido("joao.silva@empresa.com.br", "empresa.com.br")  # nominal
    assert not c.email_permitido("contato@gmail.com", "")                        # gratuito
    assert not c.email_permitido("contato@outra.com.br", "empresa.com.br")       # domínio de outra empresa


def test_telefone_so_fixo_ou_central():
    assert c.telefone_permitido("(19) 3521-2121")
    assert c.telefone_permitido("0800 123 4567")
    assert not c.telefone_permitido("(11) 98578-7011")  # celular


def test_validar_tira_conhecidos_e_sem_canal():
    nomes, dominios = {c._chave("1124 - ADITEX LTDA")}, {"conhecida.com.br"}
    aceitos, recusados = c.validar([
        {"empresa": "Aditex", "email": "contato@aditex.com.br"},
        {"empresa": "Outra", "site": "https://conhecida.com.br", "telefone": "(19) 3333-4444"},
        {"empresa": "Nova SA", "site": "novasa.com.br", "email": "maria@novasa.com.br", "telefone": "(19) 3333-4444"},
        {"empresa": "Sem Canal", "email": "a@gmail.com"},
    ], nomes, dominios)
    assert [a["empresa"] for a in aceitos] == ["Nova SA"] and aceitos[0]["email"] == ""
    assert len(recusados) == 3


def test_pedido_de_trabalho():
    assert c.e_pedido_de_trabalho("Prospecte 10 indústrias em Campinas")
    assert c.e_pedido_de_trabalho("Crie a persona do cliente corporativo")
    assert not c.e_pedido_de_trabalho("Qual o perfil dos nossos clientes?")
    assert c.PEDE_CRIACAO.search("Crie os leads da prévia #70")
    assert c.PEDE_CRIACAO.search("pode criar")
    assert not c.PEDE_CRIACAO.search("Prospecte 10 indústrias em Campinas")


if __name__ == "__main__":
    for nome, teste in list(globals().items()):
        if nome.startswith("test_"):
            teste()
            print("ok", nome)
