"""Onda 2, grupo L (31/10/2026): pasta FINAL e folha de aprovação (designer-09/10), aprender com o 👎 e guardar o 👍
(cerebro-08/20, designer-16, email_marketing-05) e e-mail com as fotos reais dos Lodges (email_marketing-04).
Banco temporário (tests/conftest.py); o site e o Brevo são falsos em memória (nada sai para a internet).
"""

import sys
import time
from pathlib import Path

import pytest

import avaliacoes
import consolidacao_semanal
import correcoes
import insatisfacoes
import reranker
import tarefas
from agents import ferramentas_brevo as fb
from agents import fotos_email

tarefas.iniciar()


def _tarefa(agente: str = "copywriter", resposta: str = "Resposta pronta.", texto: str = "Legenda do Lodge 28") -> int:
    tarefa_id = tarefas.criar("usuario.teste", "marketing", agente, texto, "simples")
    tarefas.atualizar(tarefa_id, status="concluida", resposta=resposta, tempo_segundos=1.0)
    return tarefa_id


# --- Elogios e linha aprovada do e-mail (email_marketing-05) ------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Ficou ótimo, salva para os próximos e-mails", "Pode salvar isso para as próximas campanhas",
    "Guarda como referência", "Aprovei, pode disparar", "Arrasou!", "Ficou perfeito", "top", "Parabéns, nota 10",
    "Gostei demais desse assunto", "Adorei",
])
def test_frases_de_elogio_reconhecidas(texto):
    assert correcoes.e_elogio(texto)


@pytest.mark.parametrize("texto", [
    "Não ficou bom", "Ficou bom?", "Ficou bom, mas troca o título", "Não precisa salvar isso",
    "Não gostei muito", "Pode mandar uma versão mais curta?", "Salva em PDF",
    "Legenda: área gourmet perfeita para a família, com piscina aquecida e espaço para todos " * 3,
])
def test_nao_e_elogio(texto):
    assert not correcoes.e_elogio(texto)


RESPOSTA_EMAIL = ("Segue o e-mail:\n\n**Assunto:** Já sabe onde vai passar janeiro?\n"
                  "Pré-header: Casas inteiras para o seu grupo, com serviço\nTítulo: Janeiro com o grupo\n"
                  + "Texto do corpo. " * 60 + "\nBotão principal: CONHEÇA NOSSOS LODGES\n")


def test_ganchos_da_resposta_vao_com_o_elogio_do_email():
    ganchos = correcoes.ganchos_aprovados(RESPOSTA_EMAIL)
    assert "Assunto: Já sabe onde vai passar janeiro?" in ganchos
    assert "Pré-header: Casas inteiras" in ganchos and "CONHEÇA NOSSOS LODGES" in ganchos  # mesmo depois de 400 chars
    guardado = correcoes.resposta_da_observacao("email_marketing", "elogio", RESPOSTA_EMAIL)
    assert guardado.startswith("Linha aprovada: Assunto:")
    assert correcoes.resposta_da_observacao("copywriter", "elogio", RESPOSTA_EMAIL) == RESPOSTA_EMAIL[:400]


def test_joinha_sem_comentario_no_email_guarda_a_linha_uma_vez():
    tarefa_id = _tarefa("email_marketing", RESPOSTA_EMAIL, "E-mail de férias de janeiro")
    linha = tarefas.obter(tarefa_id)
    avaliacoes.avaliar(linha, "usuario.teste", 1)
    avaliacoes.avaliar(linha, "usuario.teste", 0)
    avaliacoes.avaliar(linha, "usuario.teste", 1)  # tira e põe de novo: não duplica
    obs = correcoes._db().execute("SELECT tipo, status, resposta_anterior FROM observacoes WHERE tarefa_anterior = ?",
                                  (tarefa_id,)).fetchall()
    assert len(obs) == 1 and obs[0]["tipo"] == "elogio" and obs[0]["status"] == "nova"  # espera o Thomas aprovar
    assert "Linha aprovada: Assunto: Já sabe" in obs[0]["resposta_anterior"]
    copy = _tarefa("copywriter")  # nos outros agentes, 👍 sem comentário continua sem observação
    avaliacoes.avaliar(tarefas.obter(copy), "usuario.teste", 1)
    assert not correcoes._db().execute("SELECT 1 FROM observacoes WHERE tarefa_anterior = ?", (copy,)).fetchone()


# --- 👎 que ensina (cerebro-08, cerebro-20) -----------------------------------------------------------------------

def test_insatisfacao_guarda_etapa_e_vai_filtrada_para_a_consolidacao():
    tarefa_id = _tarefa("criador_imagens", texto="Carrossel dos Lodges 02, 119 e 18")
    linha = tarefas.obter(tarefa_id)
    insatisfacoes.registrar(linha, "usuario.teste", "voto", "dados",
                            "Ligue para cliente.teste@exemplo.com ou (11) 98765-4321, o Lodge saiu errado", etapa="plano")
    insatisfacoes.registrar(linha, "usuario.teste", "voto", "dados", "Faltou o Lodge 119", etapa="nao_sei")
    da_semana = [i for i in insatisfacoes.da_semana("2000-01-01T00:00:00Z") if "Lodges 02" in i["pedido"]]
    assert da_semana[0]["etapa"] == "Plano/briefing" and da_semana[1]["etapa"] == ""
    assert "@exemplo.com" not in da_semana[0]["motivo"] and "98765" not in da_semana[0]["motivo"]
    assert "[e-mail]" in da_semana[0]["motivo"] and "[telefone]" in da_semana[0]["motivo"]
    grupo = next(g for g in consolidacao_semanal.coletar()["grupos"] if g["agente"] == "criador_imagens")
    assert grupo["motivos_do_negativo"]["Dados errados ou inventados"] >= 2
    assert any(i.get("etapa") == "Plano/briefing" for i in grupo["insatisfacoes"])
    prompt = consolidacao_semanal._prompt({"grupos": [grupo]})
    assert "motivos_do_negativo" in prompt and "Plano/briefing = gestor" in prompt and "3 de 4" in prompt


def test_negativo_so_por_demora_nao_vira_rotulo_da_rede():
    demora, dados = _tarefa(), _tarefa()
    for tarefa_id, categoria in ((demora, "demora"), (dados, "dados")):
        avaliacoes.avaliar(tarefas.obter(tarefa_id), "usuario.teste", -1)
        insatisfacoes.registrar(tarefas.obter(tarefa_id), "usuario.teste", "voto", categoria)
    rotulos = reranker._rotulos()
    assert demora not in rotulos and rotulos[dados] == 0


# --- E-mail com as fotos dos Lodges (email_marketing-04) ----------------------------------------------------------

def _imovel(nome: str, link: str) -> fb._Imovel:
    return fb._Imovel(local="Atibaia / SP | Até 40 hóspedes", nome=nome, texto="Piscina e área verde.",
                      botao_texto=f"QUERO CONHECER O {nome.upper()}", botao_link=link)


PAGINAS = {
    "https://www.casaveraneio.com/lodges/lodge-16": '<html><head><meta property="og:image" '
        'content="https://cdn.exemplo.com/lodge16-capa.jpg"><meta property="og:image:alt" '
        'content="Lodge 16, piscina com vista"></head></html>',
    "https://www.casaveraneio.com/lodges/lodge-18": '<img src="/img/logo.png"><img src="/fotos/lodge18.webp" alt="">',
    "https://www.casaveraneio.com/lodges/lodge-40": "<html><body>sem foto</body></html>",
}


def _site_falso(abertas: list):
    def pagina(link):
        abertas.append(link)
        if link not in PAGINAS:
            raise OSError("site fora do ar")
        return PAGINAS[link]
    return pagina


def test_fotos_da_pagina_do_lodge_ou_aviso(monkeypatch):
    abertas = []
    monkeypatch.setattr(fotos_email, "_pagina", _site_falso(abertas))
    imoveis = [_imovel("Lodge 16", "https://www.casaveraneio.com/lodges/lodge-16"),
               _imovel("Lodge 18", "https://www.casaveraneio.com/lodges/lodge-18"),
               _imovel("Lodge 40", "https://www.casaveraneio.com/lodges/lodge-40"),
               _imovel("Lodge 7", "https://www.casaveraneio.com/lodges/lodge-7"),  # site fora do ar
               _imovel("Vero 76", "https://www.casaveroimoveis.com/imovel/76"),  # outra empresa: nem abre
               _imovel("Lodge 9", "https://corporativo.casaveraneio.com/espacos/9")]
    fotos = fotos_email.fotos(imoveis, "casa_veraneio")
    assert fotos[0].url == "https://cdn.exemplo.com/lodge16-capa.jpg" and fotos[0].alt == "Lodge 16, piscina com vista"
    assert fotos[1].url == "https://www.casaveraneio.com/fotos/lodge18.webp"  # sem og:image: 1ª foto, sem o logo
    assert fotos[1].alt == "Lodge 18, Atibaia / SP | Até 40 hóspedes"
    assert [f.aviso for f in fotos[2:]] == ["FOTO DO LODGE 40 AQUI", "FOTO DO LODGE 7 AQUI", "FOTO DO VERO 76 AQUI",
                                            "FOTO DO LODGE 9 AQUI"]
    assert not any("casaveroimoveis" in a or "corporativo" in a for a in abertas)


def test_mesma_capa_em_varios_lodges_e_banner_do_site(monkeypatch):
    monkeypatch.setattr(fotos_email, "_pagina", lambda link: '<meta property="og:image" content="https://x.exemplo.com/b.jpg">')
    imoveis = [_imovel("Lodge 1", "https://www.casaveraneio.com/lodges/1"),
               _imovel("Lodge 2", "https://www.casaveraneio.com/lodges/2")]
    assert [f.aviso for f in fotos_email.fotos(imoveis, "casa_veraneio")] == ["FOTO DO LODGE 1 AQUI",
                                                                               "FOTO DO LODGE 2 AQUI"]


def test_rascunho_sobe_com_foto_clicavel_e_lista_as_fotos(monkeypatch):
    monkeypatch.setattr(fotos_email, "_pagina", _site_falso([]))
    corpos = []

    def brevo(metodo, caminho, chave, corpo=None):
        if metodo == "GET" and caminho.startswith("/emailCampaigns?status=sent"):
            return {"campaigns": [{"name": "[Rascunho Escritório] VERANEIO | x", "sender": {"name": "Casa Veraneio",
                                                                                            "email": "usuario.teste@exemplo.com"}}]}
        if metodo == "POST":
            corpos.append(corpo)
            return {"id": 501}
        if metodo == "GET":
            return {"status": "draft", "modifiedAt": "m1"}
        raise AssertionError(f"chamada inesperada {metodo} {caminho}")

    monkeypatch.setattr(fb, "_chave", lambda: "chave-ficticia")
    monkeypatch.setattr(fb, "_api", brevo)
    campos = {"nome_campanha": "Férias", "mes_do_tema": "2027-01", "assunto": "Janeiro com o grupo?",
              "pre_header": "Casas inteiras para o seu grupo.", "titulo": "Janeiro", "abertura": "Oi.",
              "botao_principal_texto": "CONHEÇA", "botao_principal_link": "https://www.casaveraneio.com/lodges",
              "imoveis": [_imovel("Lodge 16", "https://www.casaveraneio.com/lodges/lodge-16").model_dump(),
                          _imovel("Lodge 40", "https://www.casaveraneio.com/lodges/lodge-40").model_dump()]}
    resposta = fb.CriarRascunhoBrevo(empresa="casa_veraneio", tarefa_id=0)._run(**campos)
    corpo = corpos[0]["htmlContent"]
    assert ('<a href="https://www.casaveraneio.com/lodges/lodge-16"' in corpo
            and 'src="https://cdn.exemplo.com/lodge16-capa.jpg" alt="Lodge 16, piscina com vista"' in corpo)
    assert "FOTO DO LODGE 40 AQUI" in corpo and "listIds" not in corpos[0] and "recipients" not in corpos[0]
    assert "Lodge 16: foto de capa" in resposta and "Lodge 40: sem foto (FOTO DO LODGE 40 AQUI)" in resposta
    sem = fb.CriarRascunhoBrevo(empresa="casa_veraneio", tarefa_id=0)._run(**campos, com_fotos=False)
    assert "<img" not in corpos[1]["htmlContent"] and "Fotos dos blocos" not in sem


# --- Folha de aprovação no chat (designer-10) ---------------------------------------------------------------------

def test_folha_vira_anexo_do_dono_e_vai_com_a_resposta(tmp_path, monkeypatch):
    import anexos
    import folha_aprovacao
    import historico

    monkeypatch.setattr(anexos, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(anexos, "PASTA", tmp_path / "dados" / "anexos")
    tarefa_id = _tarefa("criador_imagens")
    with pytest.raises(Exception):
        folha_aprovacao.guardar(tarefa_id, b"\x89PNG\r\n\x1a\nnao-e-jpg")
    anexo_id = folha_aprovacao.guardar(tarefa_id, b"\xff\xd8\xff\xe0jpg-falso")
    assert (tmp_path / "dados" / "anexos" / f"{anexo_id}.jpg").is_file()
    assert anexos._db().execute("SELECT usuario FROM anexos WHERE id = ?", (anexo_id,)).fetchone()[0] == "usuario.teste"
    novo = folha_aprovacao.guardar(tarefa_id, b"\xff\xd8\xff\xe0versao-2")  # ajuste: a folha nova substitui
    assert [a["id"] for a in folha_aprovacao.de(tarefa_id)] == [novo]
    mensagens = historico._mensagens_da_tarefa(tarefas.obter(tarefa_id))
    assert mensagens[-1]["anexos"][0]["mime"] == "image/jpeg"


# --- Pasta FINAL e folha (scripts/max/pasta_final.py, roda no PC) ------------------------------------------------

def _pasta_final():
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "pasta_final.py").exists():
            sys.path.insert(0, str(pasta))
            import pasta_final
            return pasta_final
    pytest.skip("scripts/max não montado")


@pytest.mark.parametrize("nome, esperado", [
    ("slide_02_v2.png", ("slide_02.png", 2)), ("slide_02.png", ("slide_02.png", 1)),
    ("EDITÁVEL/Carrossel_v3_editavel.pptx", ("EDITÁVEL/Carrossel_editavel.pptx", 3)),
    ("arte_v12_2.png", ("arte.png", 12)), ("Legenda - Lodge 35.docx", ("Legenda - Lodge 35.docx", 1)),
])
def test_nome_base_e_versao(nome, esperado):
    assert _pasta_final().chave_e_versao(nome) == esperado


def _png(caminho: Path, cor, tamanho=(1080, 1350)):
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", tamanho, cor).save(caminho)


def test_final_tem_so_a_versao_vigente_e_a_folha(tmp_path):
    pytest.importorskip("PIL")
    pf = _pasta_final()
    for n in (1, 2, 3, 10):
        _png(tmp_path / f"slide_{n:02d}.png", (200, 180, 160))
    (tmp_path / "EDITÁVEL").mkdir()
    (tmp_path / "EDITÁVEL" / "Carrossel_editavel.pptx").write_bytes(b"v1")
    (tmp_path / "EDITÁVEL" / "CENAS").mkdir()
    (tmp_path / "EDITÁVEL" / "CENAS" / "cena.png").write_bytes(b"x")
    assert pf.atualizar(tmp_path) == ["EDITÁVEL/Carrossel_editavel.pptx", "slide_01.png", "slide_02.png",
                                      "slide_03.png", "slide_10.png"]
    time.sleep(0.05)
    _png(tmp_path / "slide_02_v2.png", (10, 20, 30))  # ajuste só no slide 2
    (tmp_path / "EDITÁVEL" / "Carrossel_v2_editavel.pptx").write_bytes(b"v2")
    (tmp_path / "FINAL" / "sobra_antiga.png").write_bytes(b"x")
    vigentes = pf.atualizar(tmp_path)
    final = tmp_path / "FINAL"
    assert "sobra_antiga.png" not in vigentes and not (final / "sobra_antiga.png").exists()
    assert not list(final.glob("*_v2*")) and (final / "EDITÁVEL" / "Carrossel_editavel.pptx").read_bytes() == b"v2"
    from PIL import Image

    with Image.open(final / "slide_02.png") as img:
        assert img.getpixel((5, 5)) == (10, 20, 30)
    with Image.open(final / "slide_01.png") as img:
        assert img.getpixel((5, 5)) == (200, 180, 160)
    folha = pf.folha(final, vigentes, "VERANEIO ｜ CARROSSEL - TESTE")
    assert folha == final / pf.NOME_FOLHA and folha.read_bytes()[:3] == b"\xff\xd8\xff"
    assert pf.NOME_FOLHA not in pf.atualizar(tmp_path) and folha.exists()  # a folha não vira peça nem some
    assert pf.folha(final, ["slide_01.png"], "uma arte só") is None
