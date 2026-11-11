"""Onda 2 de novembro (11/11/2026), grupo J: inventário do material do imóvel antes do plano (moviemaker-01,
editor_video-01, despachante-11, gestor-04) e uma pasta por peça do Monday com o kit POSTAR (social_media-01,
social_media-02, designer-35, gestor-07). Banco temporário (conftest); acervo e Drive em pastas temporárias com
arquivos fictícios; o ffprobe é falso (o teste com o ffprobe de verdade só roda onde ele existe).
"""

import asyncio
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import drive_pc
import inventario
import monday
import pasta_peca as pasta_peca_backend
import producao
import tarefas

tarefas.iniciar()


def _pasta_max() -> Path:
    for pasta in (Path("/repo/scripts/max"), Path(__file__).resolve().parents[1] / "scripts" / "max"):
        if (pasta / "inventario_acervo.py").exists():
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return pasta
    pytest.skip("scripts/max não montado")


@pytest.fixture
def max_(monkeypatch, tmp_path):
    _pasta_max()
    monkeypatch.setenv("ESCRITORIO_DRIVE", str(tmp_path / "drive"))  # nunca o Drive de verdade
    import inventario_acervo as inv_max
    import kit_postar
    import pasta_final
    import pasta_da_peca
    return {"inventario": inv_max, "kit": kit_postar, "final": pasta_final, "peca": pasta_da_peca}


@pytest.fixture(autouse=True)
def _sem_trabalhos_sobrando():
    yield  # trabalhos "inventario" deste arquivo não ficam pendentes para os testes da fila
    with producao._db() as db:
        db.execute("UPDATE trabalhos_max SET status = 'cancelado' WHERE tipo = 'inventario' "
                   "AND status IN ('pendente', 'executando')")


# --- Inventário no PC (scripts/max/inventario_acervo.py) ------------------------------------------------------------

def _acervo(raiz: Path) -> Path:
    acervo = raiz / "acervo"
    lodge = acervo / "Lodges 31-40" / "LODGE 32 BEIRA-MAR"
    (lodge / "VIDEOS").mkdir(parents=True)
    (lodge / "PISCINA").mkdir()
    (lodge / "VIDEOS" / "DJI_0001.MP4").write_bytes(b"video" * 1000)
    (lodge / "VIDEOS" / "DJI_0001 (1).MP4").write_bytes(b"video" * 1000)  # a mesma filmagem duas vezes
    (lodge / "VIDEOS" / "sala.mov").write_bytes(b"outro" * 500)
    for n in range(3):
        (lodge / "PISCINA" / f"p{n}.jpg").write_bytes(b"x")
    (lodge / "fachada.jpg").write_bytes(b"x")
    (lodge / "desktop.ini").write_bytes(b"x")
    outro = acervo / "Lodges 1-10" / "LODGE 3"  # outro Lodge: nunca é lido
    outro.mkdir(parents=True)
    (outro / "nao_ler.mp4").write_bytes(b"x")
    return acervo


def _sonda_falsa(lidos: list):
    def sonda(arquivo: Path) -> dict:
        lidos.append(arquivo.name)
        if arquivo.suffix.lower() == ".mov":  # celular: 1920x1080 com rotação 90 = vertical, com áudio
            return {"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001",
                                 "side_data_list": [{"rotation": -90}]}, {"codec_type": "audio"}],
                    "format": {"duration": "12.4"}}
        return {"streams": [{"codec_type": "video", "width": 3840, "height": 2160, "avg_frame_rate": "30/1"}],
                "format": {"duration": "88.04", "tags": {"encoder": "DJI FC3582"}}}
    return sonda


def test_inventario_le_so_a_pasta_do_lodge_e_acha_copias(max_, tmp_path):
    inv = max_["inventario"]
    acervo, lidos = _acervo(tmp_path), []
    cache = tmp_path / "cache.json"
    ficha = inv.inventariar("Lodge 32", acervo, _sonda_falsa(lidos), cache)
    assert ficha["encontrado"] and ficha["pasta"] == "Lodges 31-40/LODGE 32 BEIRA-MAR"
    assert "nao_ler.mp4" not in lidos and sorted(lidos) == ["DJI_0001 (1).MP4", "DJI_0001.MP4", "sala.mov"]
    videos = {v["nome"]: v for v in ficha["videos"]}
    principal = videos["VIDEOS/DJI_0001 (1).MP4"]  # o primeiro em ordem de nome
    assert principal["duracao_s"] == 88.0 and principal["orientacao"] == "horizontal" and principal["drone"]
    assert videos["VIDEOS/DJI_0001.MP4"]["copia_de"] == "VIDEOS/DJI_0001 (1).MP4"
    sala = videos["VIDEOS/sala.mov"]
    assert sala["orientacao"] == "vertical" and sala["audio"] and sala["fps"] == 29.97 and not sala["drone"]
    assert ficha["fotos"] == 4 and ficha["fotos_por_pasta"] == {"(raiz)": 1, "PISCINA": 3}
    # Cache por arquivo: a segunda leitura não chama o ffprobe; o acervo continua igual (só leitura).
    lidos.clear()
    assert inv.inventariar("Lodge 32", acervo, _sonda_falsa(lidos), cache)["videos"] == ficha["videos"]
    assert lidos == [] and sorted(p.name for p in (acervo / "Lodges 31-40" / "LODGE 32 BEIRA-MAR" / "VIDEOS")
                                  .iterdir()) == ["DJI_0001 (1).MP4", "DJI_0001.MP4", "sala.mov"]


def test_inventario_lodge_sem_pasta_e_acervo_fora(max_, tmp_path):
    inv = max_["inventario"]
    acervo = _acervo(tmp_path)
    assert inv.inventariar("Lodge 39", acervo, _sonda_falsa([]), tmp_path / "c.json")["encontrado"] is False
    with pytest.raises(RuntimeError, match="Acervo"):
        inv.inventariar("Lodge 32", tmp_path / "nao_existe", _sonda_falsa([]), tmp_path / "c.json")


def test_inventario_com_ffprobe_de_verdade(max_, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe não instalados aqui")
    pasta = tmp_path / "acervo" / "Lodges 1-10" / "LODGE 4" / "VIDEOS"
    pasta.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=108x192:d=2", "-r", "25",
                    str(pasta / "vertical.mp4")], check=True, timeout=60)
    ficha = max_["inventario"].inventariar("lodge 04", tmp_path / "acervo", arquivo_cache=tmp_path / "c.json")
    video = ficha["videos"][0]
    assert video["orientacao"] == "vertical" and video["duracao_s"] == 2.0 and video["audio"] is False


# --- Inventário no backend: cache de 7 dias e bloco do contexto -------------------------------------------------

def _concluir(imovel: str, ficha: dict, dias_atras: float = 0) -> int:
    trabalho_id = producao.criar_trabalho_agora("inventario", {"imovel": imovel})
    quando = (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with producao._db() as db:
        db.execute("UPDATE trabalhos_max SET status = 'concluido', resultado = ?, concluido_em = ? WHERE id = ?",
                   (json.dumps(ficha), quando, trabalho_id))
    return trabalho_id


FICHA = {"imovel": "Lodge 77", "lido_em": "2026-11-11T10:00:00Z", "encontrado": True,
         "pasta": "Lodges 71-80/LODGE 77", "fotos": 4, "fotos_por_pasta": {"PISCINA": 3, "(raiz)": 1},
         "videos": [{"nome": "VIDEOS/DJI_0001.MP4", "duracao_s": 88.0, "largura": 3840, "altura": 2160,
                     "orientacao": "horizontal", "fps": 30.0, "audio": False, "drone": True},
                    {"nome": "VIDEOS/DJI_0001 (1).MP4", "duracao_s": 88.0, "copia_de": "VIDEOS/DJI_0001.MP4"}]}


def test_so_pedido_de_video_ou_carrossel_com_lodge_e_dos_agentes_certos():
    assert inventario.precisa("gestor", "casa_veraneio", "Reels do Lodge 32 com drone") == ["Lodge 32"]
    assert inventario.precisa("moviemaker", "cv_corporativo", "roteiro de vídeo do lodge 08") == ["Lodge 8"]
    assert inventario.precisa("editor_video", "casa_veraneio", "Carrossel Lodge 3 e Lodge 12") == ["Lodge 3", "Lodge 12"]
    assert inventario.precisa("copywriter", "casa_veraneio", "Reels do Lodge 32") == []
    assert inventario.precisa("gestor", "casa_vero", "Reels do Lodge 32") == []  # o acervo dos Lodges não é da Vero
    assert inventario.precisa("gestor", "casa_veraneio", "Legenda para o Lodge 32") == []
    assert inventario.precisa("gestor", "casa_veraneio", "Reels de Réveillon") == []


def test_ficha_vale_7_dias_e_nada_e_apagado():
    antiga = _concluir("Lodge 77", {**FICHA, "fotos": 1}, dias_atras=8)
    assert inventario.guardada("Lodge 77") is None  # expirou: só deixa de valer
    _concluir("Lodge 77", FICHA, dias_atras=1)
    assert inventario.guardada("Lodge 77")["fotos"] == 4
    assert producao.obter_trabalho(antiga)["resultado"]  # o registro antigo continua no banco
    _concluir("Lodge 78", {"imovel": "Lodge 78", "encontrado": False}, dias_atras=2)
    assert inventario.guardada("Lodge 78") is None  # pasta não achada vale só 1 dia


def test_texto_do_bloco_tem_arquivos_copias_drone_e_conta_de_material():
    texto = inventario.texto(FICHA, "casa_veraneio")
    assert "MATERIAL DO LODGE 77" in texto and "DJI_0001.MP4: 88 s, 3840×2160 (4K), horizontal" in texto
    assert "provável DRONE" in texto and "CÓPIA do arquivo 1" in texto and "1 útil" in texto
    assert "Fotos: 4 (PISCINA 3, (raiz) 1)" in texto
    assert "em 0,75x um take de 4 s gasta 3 s" in texto and "117 s na tela" in texto
    assert "0,75x" not in inventario.texto(FICHA, "cv_corporativo")  # decisão 1 em aberto nas outras marcas
    sem_video = inventario.texto({**FICHA, "videos": []}, "casa_veraneio")
    assert "NENHUM" in sem_video and "movimento lento" in sem_video
    assert "NÃO foi achada" in inventario.texto({"imovel": "Lodge 9", "encontrado": False})


def test_bloco_pede_a_leitura_sem_esperar_e_usa_a_ficha_guardada(monkeypatch):
    drive_pc.registrar("", False)
    _concluir("Lodge 77", FICHA)
    assert "MATERIAL DO LODGE 77 NO ACERVO" in inventario.bloco("gestor", "casa_veraneio", "Reels do Lodge 77", 0)
    vazio = inventario.bloco("moviemaker", "casa_veraneio", "Roteiro de reels do Lodge 91", 0)
    assert "ainda não lido" in vazio and "Não prometa" in vazio
    pendente = producao.trabalho_em_aberto("inventario", "imovel", "Lodge 91")
    assert pendente  # entrou na fila, uma vez só
    inventario.bloco("editor_video", "casa_veraneio", "Reels do Lodge 91", 0)
    assert producao.trabalho_em_aberto("inventario", "imovel", "Lodge 91") == pendente
    # Acervo fora do PC (drive_pc): não pede a leitura e diz por quê.
    drive_pc.registrar("acervo dos Lodges", True)
    try:
        fora = inventario.bloco("gestor", "casa_veraneio", "Reels do Lodge 92", 0)
        assert "não está acessível" in fora and not producao.trabalho_em_aberto("inventario", "imovel", "Lodge 92")
    finally:
        drive_pc.registrar("", False)


def test_bloco_espera_o_trabalhador_livre(monkeypatch):
    def trabalhador(imovel):  # o trabalhador "lê" enquanto o contexto espera
        trabalho_id = producao.criar_trabalho_agora("inventario", {"imovel": imovel})
        with producao._db() as db:
            db.execute("UPDATE trabalhos_max SET status = 'concluido', resultado = ?, concluido_em = ? WHERE id = ?",
                       (json.dumps({**FICHA, "imovel": imovel}), producao._agora(), trabalho_id))
        return trabalho_id

    monkeypatch.setattr(inventario, "pedir", trabalhador)
    assert "MATERIAL DO LODGE 93 NO ACERVO" in inventario.bloco("gestor", "casa_veraneio", "Reels do Lodge 93", 5)


def test_contexto_do_gestor_recebe_o_inventario():
    from agents import perfis

    _concluir("Lodge 77", FICHA)
    assert "MATERIAL DO LODGE 77 NO ACERVO" in perfis.contexto("gestor", [], "Reels do Lodge 77", "casa_veraneio")
    assert "MATERIAL DO LODGE" not in perfis.contexto("copywriter", [], "Reels do Lodge 77", "casa_veraneio")


def test_inventario_tem_prioridade_na_fila(monkeypatch):
    monkeypatch.setattr(producao, "_exigir_operador", lambda _a: None)
    monkeypatch.setattr(producao, "_retomar_orfaos", lambda: [])
    monkeypatch.setattr(producao.max_texto, "registrar_contato", lambda: None)  # não "liga" o trabalhador
    with producao._db() as db:  # sobra de outros testes não passa na frente
        db.execute("UPDATE trabalhos_max SET status = 'cancelado' WHERE status = 'pendente'")
    site = producao.criar_trabalho_agora("site", {})
    trabalho_id = producao.criar_trabalho_agora("inventario", {"imovel": "Lodge 94"})
    item = asyncio.run(producao.proxima(authorization=""))
    assert item["trabalho"]["id"] == trabalho_id and item["trabalho"]["tipo"] == "inventario"
    producao.cancelar_trabalho(site, "teste")


# --- Uma pasta por peça do Monday ---------------------------------------------------------------------------------

def test_item_da_producao_sai_do_briefing(monkeypatch):
    monkeypatch.setattr(monday, "item_da_tarefa", lambda _t: 1234)
    texto = "Pedido original: Item do Monday: REELS | Réveillon Lodge 239 (grupo Dezembro)\n- FORMATO DA PEÇA..."
    assert pasta_peca_backend.item_da_producao(1, texto) == {
        "id": 1234, "nome": "REELS | Réveillon Lodge 239", "tipo": "REELS", "descricao": "Réveillon Lodge 239"}
    monkeypatch.setattr(monday, "item_da_tarefa", lambda _t: None)
    assert pasta_peca_backend.item_da_producao(1, texto) is None


def _producao_item(**extra) -> dict:
    return {"tarefa_id": 1, "agente": "editor_video", "empresa": "casa_veraneio", "pasta_andar": "MARKETING",
            "titulo": "Reels Lodge 239", "texto": "x",
            "item_monday": {"id": 1234, "tipo": "REELS", "descricao": "Réveillon Lodge 239 - Casa Veraneio"}, **extra}


def test_nome_da_pasta_do_item_e_versoes_na_mesma_pasta(max_, tmp_path):
    peca = max_["peca"]
    nome = peca.nome_do_item(_producao_item())
    assert nome == "VERANEIO ｜ REELS - RÉVEILLON LODGE 239 #1234"
    longo = peca.nome_do_item(_producao_item(item_monday={"id": 99, "tipo": "POST", "descricao": "A" * 200}))
    assert len(longo) <= 90 and longo.endswith(" #99")
    raiz = tmp_path / "MARKETING"
    raiz.mkdir()
    assert peca.pasta_da_versao(raiz, _producao_item()) is None  # 1ª produção: pasta nova
    (raiz / nome).mkdir()
    assert peca.pasta_da_versao(raiz, _producao_item()) == raiz / nome  # criada e vazia: usa a raiz
    (raiz / nome / "reels.mp4").write_bytes(b"v1")
    assert peca.pasta_da_versao(raiz, _producao_item()) == raiz / nome / "v2"
    (raiz / nome / "v2").mkdir()
    # Item renomeado no Monday: o "#1234" ainda acha a pasta.
    renomeado = _producao_item(item_monday={"id": 1234, "tipo": "REELS", "descricao": "Outro nome"})
    assert peca.pasta_da_versao(raiz, renomeado) == raiz / nome / "v3"
    assert peca.raiz_da_peca(raiz / nome / "v3") == raiz / nome and peca.raiz_da_peca(raiz / nome) == raiz / nome
    assert peca.pasta_da_versao(raiz, _producao_item(item_monday=None)) is None


def test_tipo_da_pasta_pelos_arquivos_quando_o_pedido_nao_diz(max_, tmp_path):
    peca = max_["peca"]
    padroes = [("CARROSSEL", r"carross[eé]is|carrossel"), ("REELS", r"\breels?\b"), ("POST", r"\bposts?\b")]
    sem_tipo = {"titulo": "Capa e contexto janeiro no Nordeste", "texto": "capa e contexto", "empresa": "casa_veraneio"}
    entrega = tmp_path / "MARKETING" / "VERANEIO ｜ VÍDEO - CAPA E CONTEXTO JANEIRO NO NORDESTE"
    nova, linhas = peca.antes_de_copiar(sem_tipo, entrega, ["Carrossel_01.png", "Carrossel_02.png",
                                                            "EDITÁVEL/x.pptx"], padroes)
    assert nova.name == "VERANEIO ｜ CARROSSEL - CAPA E CONTEXTO JANEIRO NO NORDESTE" and "CARROSSEL" in linhas[0]
    vertical = peca.antes_de_copiar(sem_tipo, entrega.with_name("VERANEIO ｜ ARTE - X"), ["a.mp4"], padroes,
                                    lambda _n: (1080, 1920, 20.0))[0]
    assert vertical.name == "VERANEIO ｜ REELS - X"
    # Pedido com tipo, ajuste ou item do Monday: a pasta fica como está.
    assert peca.antes_de_copiar({**sem_tipo, "texto": "um post"}, entrega, ["a.png", "b.png"], padroes)[0] == entrega
    assert peca.antes_de_copiar({**sem_tipo, "base": {"pasta": "x"}}, entrega, ["a.png", "b.png"], padroes)[0] == entrega


def test_aviso_de_pasta_parecida_da_mesma_empresa(max_, tmp_path):
    peca = max_["peca"]
    raiz = tmp_path / "MARKETING"
    (raiz / "VERANEIO ｜ REELS - LODGE 32 BEIRA-MAR").mkdir(parents=True)
    (raiz / "VERO ｜ REELS - LODGE 32 BEIRA MAR").mkdir()  # outra empresa: não conta
    aviso = peca.aviso_de_parecidas(raiz / "VERANEIO ｜ REELS - LODGE 32 BEIRA MAR")
    assert "LODGE 32 BEIRA-MAR" in aviso and "VERO" not in aviso
    assert peca.aviso_de_parecidas(raiz / "VERANEIO ｜ POST - CHECK-IN NATAL") == ""


# --- FINAL na raiz da peça e kit POSTAR ---------------------------------------------------------------------------

def _docx(caminho: Path, texto: str) -> bool:
    try:
        from docx import Document
    except ImportError:
        return False
    documento = Document()
    for linha in texto.split("\n"):
        documento.add_paragraph(linha)
    documento.save(str(caminho))
    return True


def test_final_da_v2_fica_na_raiz_e_postar_sai_pronto(max_, tmp_path):
    final_mod, kit = max_["final"], max_["kit"]
    peca = tmp_path / "VERANEIO ｜ CARROSSEL - JANEIRO NO NORDESTE #55"
    peca.mkdir()
    for n in (1, 2, 3):
        (peca / f"slide_{n}.png").write_bytes(b"v1")
    v2 = peca / "v2"
    v2.mkdir()
    for n in (1, 2, 10):
        (v2 / f"slide_{n}.png").write_bytes(b"v2" * n)
    tem_docx = _docx(v2 / "Legenda - Janeiro.docx", "Janeiro no Nordeste.\n\n#casaveraneio #ferias")
    vigentes = final_mod.atualizar(v2, (), peca / final_mod.PASTA)
    assert [n for n in vigentes if n.endswith(".png")] == ["slide_1.png", "slide_2.png", "slide_10.png"]
    assert not (v2 / final_mod.PASTA).exists()  # uma FINAL só, na raiz da peça
    # A FINAL da raiz (produção v1) não pega a subpasta v2/.
    assert "v2/slide_1.png" not in final_mod.vigentes(peca)
    arquivos, avisos = kit.montar(peca / final_mod.PASTA, vigentes, peca.name, "Legenda aprovada #um")
    postar = peca / final_mod.PASTA / kit.PASTA
    assert sorted(p.name for p in postar.glob("*.png")) == [
        "VERANEIO_CARROSSEL_01.png", "VERANEIO_CARROSSEL_02.png", "VERANEIO_CARROSSEL_03.png"]
    assert (postar / "VERANEIO_CARROSSEL_03.png").read_bytes() == b"v2" * 10  # slide_10 é o 3º no feed
    legenda = (postar / kit.LEGENDA).read_text(encoding="utf-8")
    assert legenda.startswith("Janeiro no Nordeste." if tem_docx else "Legenda aprovada")
    leia_me = (postar / kit.LEIA_ME).read_text(encoding="utf-8")
    assert "o 1º é a capa" in leia_me and "1. VERANEIO_CARROSSEL_01.png" in leia_me and avisos == []
    assert "LEGENDA.txt" in kit.linha_do_resumo(arquivos, avisos)
    # Nova atualização da FINAL não apaga o kit; o kit refeito tira a cópia que deixou de valer.
    (peca / final_mod.PASTA / "slide_10.png").unlink()
    vigentes = final_mod.atualizar(v2, (), peca / final_mod.PASTA)
    assert (postar / "VERANEIO_CARROSSEL_03.png").exists()
    kit.montar(peca / final_mod.PASTA, [n for n in vigentes if n != "slide_10.png"], peca.name, "x")
    assert not (postar / "VERANEIO_CARROSSEL_03.png").exists() and (peca / "v2" / "slide_10.png").exists()


def test_postar_confere_tipo_hashtags_e_usa_o_video_com_som(max_, tmp_path):
    kit = max_["kit"]
    final = tmp_path / "FINAL"
    final.mkdir()
    (final / "reels.mp4").write_bytes(b"sem som")
    (final / "reels_com_som.mp4").write_bytes(b"com som")
    arquivos, avisos = kit.montar(final, ["reels.mp4", "reels_com_som.mp4"], "VERANEIO ｜ REELS - LODGE 3 #7",
                                  "Lodge 3 " + " ".join(f"#tag{n}" for n in range(7)))
    assert (final / kit.PASTA / "VERANEIO_REELS.mp4").read_bytes() == b"com som"
    assert any("7 hashtags" in a for a in avisos)
    _, avisos = kit.montar(final, ["reels.mp4"], "CORP ｜ CARROSSEL - X", "")
    assert any("CARROSSEL" in a for a in avisos) and any("sem legenda" in a for a in avisos)
    assert (final / kit.PASTA / "CORP_CARROSSEL.mp4").exists() and not (final / kit.PASTA / "VERANEIO_REELS.mp4").exists()
    _, avisos = kit.montar(final, ["reels.mp4"], "VERO ｜ STORIES - X", None)
    assert avisos == []  # stories não têm legenda
    assert kit.conferir_tipo("POST", ["a.png", "b.png"]) and kit.conferir_tipo("REELS", ["a.png"])
    assert kit.conferir_tipo("POST", ["a.png"]) == ""
