"""Pasta de REFERÊNCIAS do Drive na produção do Max (Thomas, 12/11/2026; tarefas 290 a 294 do João).

Antes, o link do Drive no pedido não chegava a lugar nenhum: o Editor de Vídeo só lia as pastas fixas do acervo e
avisava "não consegui abrir a pasta". Agora, quando o pedido (ou a conversa) cita uma pasta de
ESCRITÓRIO VERANEIO > REFERENCIAS > <EMPRESA> (link do Drive ou nome/caminho), o trabalhador:
- acha a pasta no Drive do PC (link pelo banco do Drive para desktop, só leitura; nome pela própria pasta);
- só aceita pasta da MESMA empresa da peça (as três empresas são separadas em tudo);
- monta o ESTUDO: folhas de quadros de cada vídeo e miniaturas das imagens, em baixa resolução e com a marca
  "REFERÊNCIA – SÓ ESTUDO", em _estudo_referencias/ na pasta da peça, mais um índice com nome, duração e medida;
- SÓ ESTUDO (o padrão): os originais não chegam ao Max. A caixa de areia barra a pasta REFERENCIAS inteira e um
  final igual a uma folha de estudo sai da entrega;
- USO LIBERADO (marcado no popup do chat): a pasta citada também entra como acervo, só leitura, e o estudo continua.
Nos dois casos o Max grava _estudo_referencias/aprendizado.md, que vai ao backend como observação para aprovação
(backend/referencias_pedido.py). Nada daqui é ensinado ao Cérebro sem a Diretoria aprovar.
"""

import glob
import hashlib
import os
import re
import sqlite3
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import comum

RAIZ = comum.DRIVE / "REFERENCIAS"
PASTA_EMPRESA = {"casa_veraneio": "CASA VERANEIO", "cv_corporativo": "CORPORATIVO", "casa_vero": "CASA VERO"}
ESTUDO = "_estudo_referencias"
APRENDIZADO = "aprendizado.md"
MARCA = "REFERÊNCIA – SÓ ESTUDO"
LINK_PASTA = re.compile(r"https://drive\.google\.com/drive/(?:u/\d+/)?folders/([\w-]{10,80})", re.I)
MARCADOR = re.compile(r"\[Pasta de refer[eê]ncias:\s*([^\]]*)\]", re.I)
VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
IMAGENS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MAX_ARQUIVOS = 30
QUADROS = 9            # folha 3x3 por vídeo
LARGURA_QUADRO = 320
LADO_IMAGEM = 640
MAX_APRENDIZADO = 500
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Referencias:
    modo: str = "estudo"                                   # "estudo" ou "usar"
    pastas: list[Path] = field(default_factory=list)       # pastas citadas da empresa da peça
    avisos: list[str] = field(default_factory=list)        # vão no resumo da entrega
    indice: list[str] = field(default_factory=list)        # linhas do estudo (arquivo -> folha)
    folhas: list[Path] = field(default_factory=list)

    @property
    def bloquear(self) -> list[Path]:
        """Pastas que a caixa de areia barra: no estudo, a REFERENCIAS inteira; no uso, tudo menos as citadas."""
        if self.modo != "usar" or not self.pastas:
            return [RAIZ]
        citadas = {p.resolve() for p in self.pastas}
        return [p for p in _subpastas(RAIZ, 2) if p.resolve() not in citadas and not any(
            c.is_relative_to(p.resolve()) for c in citadas)]

    @property
    def add_dirs(self) -> list[Path]:
        return self.pastas if self.modo == "usar" else []


def _subpastas(raiz: Path, profundidade: int) -> list[Path]:
    if profundidade == 0 or not raiz.is_dir():
        return []
    filhas = [p for p in raiz.iterdir() if p.is_dir()]
    return filhas + [n for p in filhas for n in _subpastas(p, profundidade - 1)]


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w.]+", " ", sem_acento.lower()).split())


def textos_da_producao(producao: dict) -> list[str]:
    return [producao.get("texto") or ""] + [h.get("texto") or "" for h in producao.get("historico") or []]


def modo(textos: list[str]) -> str:
    marcadores = [m.group(1) for t in textos for m in MARCADOR.finditer(t)]
    return "usar" if marcadores and re.search(r"\bpode usar\b", marcadores[-1], re.I) else "estudo"


def _banco_drive() -> str | None:
    achados = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS", "*", "metadata_sqlite_db"))
    return achados[0] if achados else None


def cadeia_do_link(id_nuvem: str) -> list[str]:
    """Nomes das pastas, do topo do Drive até a do link (vazio se o Drive do PC não conhece o ID)."""
    caminho = _banco_drive()
    if not caminho:
        return []
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=5)
    conexao.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        linha = conexao.execute("SELECT stable_id, local_title FROM items WHERE id = ? AND is_folder = 1 AND trashed = 0",
                                (id_nuvem,)).fetchone()
        if not linha:
            return []
        atual, cadeia = linha[0], [linha[1]]
        for _ in range(20):
            pai = conexao.execute("SELECT parent_stable_id FROM stable_parents WHERE item_stable_id = ?",
                                  (atual,)).fetchone()
            titulo = pai and conexao.execute("SELECT local_title FROM items WHERE stable_id = ?", (pai[0],)).fetchone()
            if not titulo:
                break
            atual, cadeia = pai[0], [titulo[0], *cadeia]
        return cadeia
    finally:
        conexao.close()


def _pasta_do_link(id_nuvem: str) -> Path | None:
    """Pasta local do link, só se estiver dentro de REFERENCIAS (qualquer outra pasta do Drive é ignorada)."""
    cadeia = cadeia_do_link(id_nuvem)
    normais = [_normal(n) for n in cadeia]
    if _normal(RAIZ.name) not in normais:
        return None
    pasta = RAIZ.joinpath(*cadeia[normais.index(_normal(RAIZ.name)) + 1:])
    return pasta if pasta.is_dir() else None


def achar(producao: dict, empresa: str) -> Referencias:
    """Pastas citadas e o modo (estudo/usar). Pasta de outra empresa nunca entra: vira aviso."""
    textos = textos_da_producao(producao)
    tudo = "\n".join(textos)
    refs = Referencias(modo=modo(textos))
    candidatas: list[Path] = []
    for id_nuvem in dict.fromkeys(LINK_PASTA.findall(tudo)):
        if (pasta := _pasta_do_link(id_nuvem)):
            candidatas.append(pasta)
        else:
            refs.avisos.append("⚠ Uma pasta do Drive citada no pedido não está dentro de ESCRITÓRIO VERANEIO > "
                               "REFERENCIAS (ou ainda não sincronizou no PC): não foi aberta.")
    normal = _normal(tudo)
    for pasta in _subpastas(RAIZ, 2):  # nome da pasta escrito no pedido ("12.11.26 Gestor - Videos com serviços")
        if pasta.parent != RAIZ and len(_normal(pasta.name)) >= 6 and _normal(pasta.name) in normal:
            candidatas.append(pasta)
    propria = RAIZ / PASTA_EMPRESA.get(empresa, "-")
    for pasta in dict.fromkeys(candidatas):
        if pasta.resolve() == propria.resolve() or pasta.resolve().is_relative_to(propria.resolve()):
            refs.pastas.append(pasta)
        else:
            refs.avisos.append(f"⚠ A pasta de referências \"{pasta.name}\" é de outra empresa e não entrou nesta peça.")
    return refs


def _marcar(imagem):
    """Faixa "REFERÊNCIA – SÓ ESTUDO" no meio da imagem: a folha não serve de material."""
    from PIL import ImageDraw, ImageFont

    imagem = imagem.convert("RGB")
    desenho = ImageDraw.Draw(imagem, "RGBA")
    altura = max(24, imagem.height // 12)
    topo = (imagem.height - altura) // 2
    desenho.rectangle([0, topo, imagem.width, topo + altura], fill=(0, 0, 0, 150))
    texto, tamanho = MARCA, int(altura * 0.6)
    while True:  # fonte com acentos (a padrão do Pillow não tem "Ê" nem "Ó"), encolhida até caber na largura
        fonte = next((f for nome in FONTES_MARCA if (f := _fonte(ImageFont, nome, tamanho))), None)
        if fonte is None:
            fonte, texto = ImageFont.load_default(), "REFERENCIA - SO ESTUDO"
            break
        if desenho.textlength(texto, font=fonte) <= imagem.width * 0.9 or tamanho <= 8:
            break
        tamanho = int(tamanho * 0.85)
    desenho.text((imagem.width // 2, topo + altura // 2), texto, fill=(255, 255, 255, 230), font=fonte, anchor="mm")
    return imagem


FONTES_MARCA = ("arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _fonte(ImageFont, nome: str, tamanho: int):
    try:
        return ImageFont.truetype(nome, tamanho)
    except OSError:
        return None


def _ffmpeg(dir_ffmpeg: str | None, nome: str) -> str:
    exe = Path(dir_ffmpeg or "") / f"{nome}.exe"
    return str(exe) if dir_ffmpeg and exe.exists() else nome


def _duracao_e_medida(arquivo: Path, dir_ffmpeg: str | None) -> tuple[float, str]:
    saida = subprocess.run([_ffmpeg(dir_ffmpeg, "ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:format=duration", "-of", "default=nw=1", str(arquivo)],
                           capture_output=True, text=True, timeout=60, creationflags=SEM_JANELA).stdout
    valores = dict(l.split("=", 1) for l in saida.splitlines() if "=" in l)
    try:
        duracao = float(valores.get("duration", 0))
    except ValueError:
        duracao = 0.0
    return duracao, f"{valores.get('width', '?')}x{valores.get('height', '?')}"


def _folha_do_video(arquivo: Path, destino: Path, dir_ffmpeg: str | None) -> tuple[Path | None, str]:
    from PIL import Image

    duracao, medida = _duracao_e_medida(arquivo, dir_ffmpeg)
    quadros = []
    for i in range(QUADROS):
        instante = duracao * (i + 0.5) / QUADROS if duracao else i
        quadro = destino.with_name(f"{destino.stem}_{i}.jpg")
        subprocess.run([_ffmpeg(dir_ffmpeg, "ffmpeg"), "-v", "error", "-y", "-ss", f"{instante:.2f}", "-i", str(arquivo),
                        "-frames:v", "1", "-vf", f"scale={LARGURA_QUADRO}:-2", str(quadro)],
                       capture_output=True, timeout=120, creationflags=SEM_JANELA)
        if quadro.exists():
            with Image.open(quadro) as imagem:
                quadros.append(imagem.convert("RGB"))
            quadro.unlink()
    if not quadros:
        return None, f"{duracao:.1f} s, {medida}"
    largura, altura = quadros[0].size
    folha = Image.new("RGB", (largura * 3, altura * ((len(quadros) + 2) // 3)), "black")
    for i, quadro in enumerate(quadros):
        folha.paste(quadro.resize((largura, altura)), ((i % 3) * largura, (i // 3) * altura))
    _marcar(folha).save(destino, quality=70)
    return destino, f"{duracao:.1f} s, {medida}, {len(quadros)} quadros em ordem"


def _miniatura(arquivo: Path, destino: Path) -> tuple[Path | None, str]:
    from PIL import Image

    try:
        with Image.open(arquivo) as imagem:
            medida = f"{imagem.width}x{imagem.height}"
            imagem.thumbnail((LADO_IMAGEM, LADO_IMAGEM))
            _marcar(imagem).save(destino, quality=70)
        return destino, medida
    except OSError:
        return None, "não abriu"


def preparar(refs: Referencias, rascunho: Path, dir_ffmpeg: str | None) -> Referencias:
    """Folhas de estudo de cada arquivo das pastas citadas (lê os originais; nunca grava neles)."""
    if not refs.pastas:
        return refs
    destino = rascunho / ESTUDO
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = sorted({a for p in refs.pastas for a in p.rglob("*") if a.is_file()})
    if len(arquivos) > MAX_ARQUIVOS:
        refs.avisos.append(f"⚠ A pasta de referências tem {len(arquivos)} arquivos; estudei os {MAX_ARQUIVOS} primeiros.")
    for n, arquivo in enumerate(arquivos[:MAX_ARQUIVOS], 1):
        extensao = arquivo.suffix.lower()
        nome_limpo = re.sub(r"[^\w.-]+", "_", arquivo.stem)[:60]
        alvo = destino / f"{n:02d}_{nome_limpo}.jpg"
        try:
            if extensao in VIDEOS:
                folha, detalhe = _folha_do_video(arquivo, alvo, dir_ffmpeg)
            elif extensao in IMAGENS:
                folha, detalhe = _miniatura(arquivo, alvo)
            else:
                folha, detalhe = None, f"tipo {extensao or 'sem extensão'} não aberto no estudo"
        except (OSError, subprocess.SubprocessError) as erro:
            folha, detalhe = None, f"não abriu ({str(erro)[:80]})"
        if folha:
            refs.folhas.append(folha)
        refs.indice.append(f"- {arquivo.name} ({detalhe})" + (f" -> {ESTUDO}/{folha.name}" if folha else ""))
    (destino / "indice.md").write_text("Pasta(s) estudada(s): " + ", ".join(p.name for p in refs.pastas) + "\n\n"
                                       + "\n".join(refs.indice) + "\n", encoding="utf-8")
    return refs


def instrucao(refs: Referencias) -> str:
    if not refs.pastas:
        return ""
    comum_aos_dois = (f"ESTUDO: abra com Read as folhas em {ESTUDO}/ (índice em {ESTUDO}/indice.md; cada folha de vídeo "
                      "tem 9 quadros em ordem, da esquerda para a direita e de cima para baixo). Observe ritmo, ordem das "
                      "cenas, enquadramento, luz e quais serviços ou momentos aparecem. Ao terminar a peça, grave "
                      f"{ESTUDO}/{APRENDIZADO} com até 4 aprendizados curtos que valeriam para peças futuras desta "
                      f"empresa (total até 450 caracteres, sem nomes de arquivo). Eles só entram no Cérebro se a "
                      "Diretoria aprovar.")
    pastas = ", ".join(p.name for p in refs.pastas)
    if refs.modo == "usar":
        return (f"PASTA DE REFERÊNCIAS CITADA NO PEDIDO ({pastas}): quem pediu LIBEROU o uso dos arquivos na peça. Os "
                f"originais estão em {'; '.join(str(p) for p in refs.pastas)}, SOMENTE LEITURA: para usar, COPIE com "
                "python (shutil.copy2) para a subpasta acervo/ e trabalhe na cópia; nunca grave, mova ou apague nada "
                "lá. Registre a origem de cada arquivo usado como faz com o acervo. As folhas de estudo NÃO são "
                f"material (têm a marca \"{MARCA}\").\n{comum_aos_dois}")
    return (f"PASTA DE REFERÊNCIAS CITADA NO PEDIDO ({pastas}): SÓ PARA ESTUDO. Os arquivos servem de inspiração e NÃO "
            "entram na peça: nenhum quadro, trecho, foto ou folha deles vai para a entrega. O material da peça vem só "
            "do acervo oficial e dos anexos. Se o pedido pedir os takes da referência, use planos equivalentes do "
            f"acervo e diga no resumo que a pasta foi marcada como só estudo.\n{comum_aos_dois}")


def _hash(arquivo: Path) -> str:
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


def conferir_finais(refs: Referencias, final: Path, novos: list[str]) -> tuple[list[str], str]:
    """Só estudo: um final igual a uma folha de estudo sai da entrega (o Max não tem os originais)."""
    if refs.modo == "usar" or not refs.folhas:
        return novos, ""
    folhas = {_hash(f) for f in refs.folhas if f.exists()}
    fora = [n for n in novos if (final / n).is_file() and _hash(final / n) in folhas]
    for nome in fora:
        (final / nome).unlink(missing_ok=True)
    linha = (f"⚠ Tirei da entrega {', '.join(fora)}: era folha de estudo da pasta de referências (marcada como só "
             "estudo).") if fora else ""
    return [n for n in novos if n not in fora], linha


def aprendizado(rascunho: Path) -> str:
    arquivo = rascunho / ESTUDO / APRENDIZADO
    try:
        return arquivo.read_text(encoding="utf-8").strip()[:MAX_APRENDIZADO] if arquivo.is_file() else ""
    except OSError:
        return ""
