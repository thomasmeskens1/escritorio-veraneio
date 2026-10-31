"""E-mail certo por empresa (email_marketing-02 e lacunas do crítico, 31/10/2026): remetente da empresa da tarefa,
Casa Vero reconhecida, rodapé de descadastro/LGPD e um rascunho por e-mail. A API do Brevo é um falso em memória
(nada sai para a internet); banco temporário (tests/conftest.py).
"""

import itertools
from datetime import date

import pytest

import tarefas
from agents import ferramentas_brevo as fb

tarefas.iniciar()

CAMPOS = {"nome_campanha": "Férias de janeiro", "mes_do_tema": "2025-01", "assunto": "Já sabe onde vai passar janeiro?",
          "pre_header": "Casas inteiras para o seu grupo, com serviço e privacidade.", "titulo": "Janeiro com o grupo",
          "abertura": "Separamos casas para o verão.", "botao_principal_texto": "CONHEÇA NOSSOS LODGES",
          "botao_principal_link": "https://exemplo.com/lodges", "imoveis": [], "fecho": ""}


class BrevoFalso:
    def __init__(self, enviadas=None, remetentes=None):
        self.enviadas = enviadas or []
        self.remetentes = remetentes or []
        self.campanhas: dict[int, dict] = {}
        self.chamadas: list[tuple[str, str]] = []
        self.proximo = 100

    def __call__(self, metodo, caminho, chave, corpo=None):
        self.chamadas.append((metodo, caminho))
        if metodo == "GET" and caminho.startswith("/emailCampaigns?status=sent"):
            return {"campaigns": self.enviadas}
        if metodo == "GET" and caminho == "/senders":
            return {"senders": self.remetentes}
        if metodo == "POST" and caminho == "/emailCampaigns":
            assert "recipients" not in corpo and "scheduledAt" not in corpo  # nunca lista nem agendamento
            self.proximo += 1
            self.campanhas[self.proximo] = {**corpo, "status": "draft", "modifiedAt": f"m{self.proximo}-1"}
            return {"id": self.proximo}
        numero = int(caminho.rsplit("/", 1)[1])
        if metodo == "GET":
            return self.campanhas[numero]
        if metodo == "PUT":
            assert "recipients" not in corpo and "scheduledAt" not in corpo
            versao = int(self.campanhas[numero]["modifiedAt"].split("-")[1]) + 1
            self.campanhas[numero].update({**corpo, "modifiedAt": f"m{numero}-{versao}"})
            return {}
        raise AssertionError(f"chamada inesperada {metodo} {caminho}")


ENVIADAS = [
    {"name": "Casa Vero | Vero 76", "subject": "Uma casa rara", "sender": {"name": "Casa Vero", "email": "vero@exemplo.com"}},
    {"name": "OFF-SITE | Seu time", "subject": "Confraternização", "sender": {"name": "Corp", "email": "corp@exemplo.com"}},
    {"name": "Réveillon", "subject": "Já sabe onde vai passar a virada?",
     "sender": {"name": "Casa Veraneio", "email": "veraneio@exemplo.com"}},
]


@pytest.fixture
def brevo(monkeypatch):
    falso = BrevoFalso(ENVIADAS)
    monkeypatch.setattr(fb, "_chave", lambda: "chave-ficticia")
    monkeypatch.setattr(fb, "_api", falso)
    return falso


_numeros = itertools.count(1)


def _tarefa(empresa="casa_veraneio", usuario=None):
    """Cada teste com um usuário próprio (conversas separadas), salvo quando o teste passa o mesmo."""
    usuario = usuario or f"usuario.teste{next(_numeros)}@exemplo.com"
    return tarefas.criar(usuario, "marketing", "email_marketing", "E-mail de férias", "media", empresa=empresa)


def _rodar(empresa, tarefa_id, **extra):
    return fb.CriarRascunhoBrevo(empresa=empresa, tarefa_id=tarefa_id)._run(**{**CAMPOS, **extra})


def test_empresa_da_campanha_reconhece_as_tres():
    assert fb.empresa_da_campanha("Casa Vero | Vero 76") == "casa_vero"
    assert fb.empresa_da_campanha("x", "y", "Casa Vero Imóveis") == "casa_vero"
    assert fb.empresa_da_campanha("OFF-SITE | Seu time") == "cv_corporativo"
    assert fb.empresa_da_campanha("Réveillon", "Já sabe onde vai passar a virada?") == "casa_veraneio"
    assert fb.empresa_da_campanha("Verão no Lodge 20") == "casa_veraneio"  # "Verão" e "Veraneio" não são Vero
    # o "[Rascunho Escritório]" do nome não faz a campanha virar Corporativo ("escritório")
    assert fb.empresa_da_campanha(fb.nome_interno("casa_veraneio", "2027-01", "Férias")) == "casa_veraneio"
    assert fb.empresa_da_campanha("[Rascunho Escritório] Antigo sem prefixo") == "casa_veraneio"
    assert fb.empresa_da_campanha(fb.nome_interno("casa_vero", "2027-01", "Casas")) == "casa_vero"


def test_mes_do_tema_corrige_ano():
    hoje = date(2026, 10, 31)
    assert fb.mes_do_tema("2025-01", hoje) == "2027-01"   # ano errado do modelo
    assert fb.mes_do_tema("01", hoje) == "2027-01"
    assert fb.mes_do_tema("2026-12", hoje) == "2026-12"
    assert fb.mes_do_tema("2027-12", hoje) == "2027-12"   # planejamento de um ano à frente
    assert fb.mes_do_tema("2026-10", hoje) == "2026-10"


@pytest.mark.parametrize("empresa,email", [("casa_vero", "vero@exemplo.com"), ("cv_corporativo", "corp@exemplo.com"),
                                           ("casa_veraneio", "veraneio@exemplo.com")])
def test_remetente_vem_da_empresa_da_tarefa(brevo, empresa, email):
    resposta = _rodar(empresa, _tarefa(empresa))
    assert "Rascunho criado" in resposta
    criada = brevo.campanhas[max(brevo.campanhas)]
    assert criada["sender"]["email"] == email
    assert criada["name"].startswith(f"[Rascunho Escritório] {fb.PREFIXOS[empresa]} | ")


def test_sem_remetente_da_empresa_nao_usa_o_de_outra(monkeypatch):
    falso = BrevoFalso(ENVIADAS[2:], [{"name": "Casa Veraneio", "email": "veraneio@exemplo.com", "active": True}])
    monkeypatch.setattr(fb, "_chave", lambda: "chave-ficticia")
    monkeypatch.setattr(fb, "_api", falso)
    resposta = _rodar("casa_vero", _tarefa("casa_vero"))
    assert "Não achei no Brevo um remetente da Casa Vero" in resposta
    assert not falso.campanhas
    falso.remetentes.append({"name": "Casa Vero Imóveis", "email": "vero2@exemplo.com", "active": True})
    assert "Rascunho criado" in _rodar("casa_vero", _tarefa("casa_vero"))
    assert falso.campanhas[max(falso.campanhas)]["sender"]["email"] == "vero2@exemplo.com"


def test_rodape_com_descadastro_e_lgpd(brevo):
    _rodar("casa_vero", _tarefa("casa_vero"))
    conteudo = brevo.campanhas[max(brevo.campanhas)]["htmlContent"]
    assert 'href="{{ unsubscribe }}"' in conteudo
    assert "LGPD" in conteudo and "Casa Vero Imóveis" in conteudo
    assert 'name="viewport"' in conteudo


def test_ajustes_atualizam_o_mesmo_rascunho(brevo):
    usuario = "ajuste.teste@exemplo.com"
    primeira = _rodar("casa_veraneio", _tarefa(usuario=usuario))
    assert "Rascunho criado" in primeira and len(brevo.campanhas) == 1
    segunda = _rodar("casa_veraneio", _tarefa(usuario=usuario), assunto="Janeiro com o grupo todo?")
    terceira = _rodar("casa_veraneio", _tarefa(usuario=usuario), nome_campanha="Melhores destinos de verão")
    assert len(brevo.campanhas) == 1  # 3 pedidos, 1 rascunho
    assert "versão 2" in segunda and "versão 3" in terceira
    unica = next(iter(brevo.campanhas.values()))
    assert unica["name"] == f"[Rascunho Escritório] VERANEIO | {fb.mes_do_tema('2025-01')} | Melhores destinos de verão"
    # outro e-mail pedido de propósito, ou outro mês: rascunho novo
    _rodar("casa_veraneio", _tarefa(usuario=usuario), novo_email=True)
    _rodar("casa_veraneio", _tarefa(usuario=usuario), mes_do_tema="02")
    assert len(brevo.campanhas) == 3


def test_outra_conversa_ou_empresa_nao_reaproveita(brevo):
    _rodar("casa_veraneio", _tarefa(usuario="a.teste@exemplo.com"))
    _rodar("casa_veraneio", _tarefa(usuario="b.teste@exemplo.com"))
    _rodar("cv_corporativo", _tarefa("cv_corporativo", usuario="a.teste@exemplo.com"))
    assert len(brevo.campanhas) == 3


def test_rascunho_editado_a_mao_ou_enviado_nao_e_sobrescrito(brevo):
    usuario = "mao.teste@exemplo.com"
    _rodar("casa_veraneio", _tarefa(usuario=usuario))
    numero = max(brevo.campanhas)
    brevo.campanhas[numero]["modifiedAt"] = "editado-no-brevo"
    resposta = _rodar("casa_veraneio", _tarefa(usuario=usuario))
    assert f"O rascunho {numero} já foi editado" in resposta and len(brevo.campanhas) == 2
    novo = max(brevo.campanhas)
    brevo.campanhas[novo]["status"] = "sent"
    _rodar("casa_veraneio", _tarefa(usuario=usuario))
    assert len(brevo.campanhas) == 3
    assert not any(m == "PUT" and c.endswith(f"/{novo}") for m, c in brevo.chamadas)
