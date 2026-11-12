"""Ler e revisar o e-mail que já está no Brevo pelo número (email_marketing-01, 11/11/2026). SÓ LEITURA: a API do
Brevo é um falso em memória (nada sai para a internet) e o teste confere que só há GET.
"""

import pytest

from agents import brevo_leitura
from agents import ferramentas_brevo as fb

HTML = ('<html><head><style>.x{color:red}</style></head><body><span style="display:none">Pré</span>'
        '<table><tr><td><h1>Janeiro com o grupo</h1></td></tr>'
        '<tr><td>Separamos casas para o verão. Chama no WhatsApp!</td></tr>'
        '<tr><td><a href="https://exemplo.com/lodges">CONHEÇA NOSSOS LODGES</a></td></tr>'
        '<tr><td><h3>Lodge 16</h3><p>Vista para o mar.</p><a href="https://exemplo.com/16">QUERO O LODGE 16</a></td></tr>'
        '<tr><td><h3>Lodge 20</h3><p>Piscina aquecida.</p><a href="#">VER</a></td></tr>'
        '<tr><td><a href="{{ unsubscribe }}">Não quero mais receber</a></td></tr></table></body></html>')
CAMPANHA = {"id": 56, "name": "[Rascunho Escritório] VERANEIO | 2027-01 | Férias", "status": "draft",
            "subject": "Já sabe onde vai passar janeiro?", "previewText": "Casas inteiras para o seu grupo.",
            "htmlContent": HTML, "sender": {"name": "Casa Veraneio", "email": "usuario.teste@exemplo.com"}}


@pytest.fixture
def brevo(monkeypatch):
    chamadas = []

    def api(metodo, caminho, chave, corpo=None):
        fb._conferir(metodo, caminho, corpo)
        chamadas.append((metodo, caminho))
        assert metodo == "GET"
        return dict(CAMPANHA, id=int(caminho.rsplit("/", 1)[1]))

    monkeypatch.setattr(fb, "_chave", lambda: "chave-falsa")
    monkeypatch.setattr(fb, "_api", api)
    return chamadas


def test_le_textos_links_e_confere_o_email_inteiro(brevo):
    texto = brevo_leitura.LerRascunhoBrevo(empresa="casa_veraneio")._run(numero=56)
    assert brevo == [("GET", "/emailCampaigns/56")]
    assert "ASSUNTO: Já sabe onde vai passar janeiro?" in texto and "Separamos casas para o verão" in texto
    assert '"QUERO O LODGE 16" -> https://exemplo.com/16' in texto and "<td" not in texto and "color:red" not in texto
    assert "WhatsApp" in texto and "link quebrado" in texto and "nº 20" in texto  # Lodge 20 sem botão próprio
    assert "descadastro" not in texto  # o {{ unsubscribe }} está lá
    assert "nada foi alterado" in texto


def test_campanha_de_outra_empresa_nao_e_lida(brevo):
    texto = brevo_leitura.LerRascunhoBrevo(empresa="casa_vero")._run(numero=57)
    assert "não li o conteúdo" in texto and "Separamos" not in texto


def test_e_mail_marketing_recebe_as_ferramentas(brevo):
    nomes = [f.name for f in fb.para("email_marketing", "casa_veraneio", 0)]
    # trocar_assunto_brevo: Onda 3 (email_marketing-02), só assunto e pré-header
    assert nomes == ["criar_rascunho_brevo", "ler_rascunho_brevo", "trocar_assunto_brevo"]
    assert fb.para("copywriter", "casa_veraneio", 0) == []


def test_leitura_nunca_vai_a_contatos_nem_listas():
    with pytest.raises(fb.BrevoBloqueado):
        fb._conferir("GET", "/contacts/lists/3", None)
