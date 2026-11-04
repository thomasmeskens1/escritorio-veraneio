"""Vinheta animada do logo de cada empresa (Thomas, 04/11/2026): ~6 s antes do fechamento/CTA, no nível da
vinheta profissional feita para a Casa Vero (VINHETA_4K e LOGO_anima): uma pequena história em ícones chapados que
vira o logo, com antecipação, desaceleração que passa um pouco do ponto e assenta, desfoque de movimento nos
movimentos rápidos (várias amostras no tempo por quadro), faíscas, onda em anel, logo saindo do desfoque para o
foco, revelação do nome e ~1,2 s parado no fim.

Cada empresa tem a própria história (motion_roteiros.py) e só o próprio logo (pasta dela em CÉREBRO/MARCAS,
copiada para _referencias/<PASTA> da peça na produção). Ícones em motion_icones.py; só Pillow (sem numpy).

Uso: python motion.py vinheta --empresa casa_veraneio --formato 1080x1920 --saida vinheta_9x16.mp4
"""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

import motion_icones
import motion_roteiros
from motion_camadas import com_opacidade, cor, pasta_marcas
from motion_video import CODIFICACAO, FPS, _rodar, achar_ffmpeg

# empresa: (pasta em MARCAS, logo final, altura do logo no 9:16 (px), fundo, fundo do centro (luz suave)).
# Alturas um pouco acima das da vinheta anterior (170/185/240): só o logo na tela, e a linha "CORP." e o
# "IMÓVEIS ESPECIAIS" precisam ler no celular. A Vero fica no Creme, como a referência dela (bege).
VINHETAS = {
    "casa_veraneio": ("CASA_VERANEIO", "logo_caramelo_texto_creme.png", 180, "verde", (4, 66, 35)),
    "cv_corporativo": ("CORPORATIVO", "logo_corp_caramelo_texto_branco.png", 200, "verde", (4, 66, 35)),
    "casa_vero": ("CASA_VERO", "logo_vero_verde_caramelo.png", 300, "creme", (247, 231, 212)),
}
FORMATOS = ("1080x1920", "1080x1350", "1920x1080")
OBTURADOR = 0.6   # fração do quadro "exposta" no desfoque de movimento (0,5 = 180° do cinema)
MAX_AMOSTRAS = 28


def duracao(empresa: str) -> float:
    return motion_roteiros.ROTEIROS[empresa]["duracao"]


def arquivo_logo(empresa: str, base: Path) -> Path:
    """Logo da própria empresa: primeiro a cópia em _referencias/<PASTA> da peça, depois o CÉREBRO."""
    if empresa not in VINHETAS:
        raise ValueError(f"Empresa sem vinheta: {empresa!r} (use {', '.join(VINHETAS)})")
    pasta, nome = VINHETAS[empresa][:2]
    for candidato in (Path(base) / "_referencias" / pasta / nome, pasta_marcas() / pasta / nome):
        if candidato.is_file():
            return candidato
    raise ValueError(f"Logo {pasta}/{nome} não encontrado (nem em _referencias/ nem no CÉREBRO).")


# ---------------------------------------------------------------- logo em partes

@dataclass
class Peca:
    imagem: Image.Image  # RGBA no tamanho final
    x: int               # canto superior esquerdo na posição final (tela)
    y: int

    @property
    def centro(self) -> tuple[float, float]:
        return self.x + self.imagem.width / 2, self.y + self.imagem.height / 2


def _vazios(perfil: list[int], minimo: int) -> list[tuple[int, int]]:
    """Trechos [a, b) sem tinta (valor 0) de pelo menos `minimo` px."""
    trechos, inicio = [], None
    for i, v in enumerate(perfil + [1]):
        if v == 0 and inicio is None:
            inicio = i
        elif v and inicio is not None:
            if i - inicio >= minimo:
                trechos.append((inicio, i))
            inicio = None
    return trechos


def _perfil(alfa: Image.Image, colunas: bool) -> list[int]:
    reduzido = alfa.point(lambda v: 255 if v > 24 else 0)
    if colunas:
        return list(reduzido.resize((alfa.width, 1), Image.BOX).tobytes())
    return list(reduzido.resize((1, alfa.height), Image.BOX).tobytes())


def _faixas(nome: Image.Image) -> list[tuple[int, int]]:
    """Linhas do nome (Casa / Veraneio / CORP.), juntando acentos soltos à linha de baixo."""
    perfil = _perfil(nome.getchannel("A"), colunas=False)
    cortes = [0] + [round((a + b) / 2) for a, b in _vazios(perfil, 2)] + [nome.height]
    faixas = [(a, b) for a, b in zip(cortes, cortes[1:]) if any(perfil[a:b])]
    maior = max(b - a for a, b in faixas)
    juntas = []
    for a, b in faixas:
        if juntas and juntas[-1][2]:  # a anterior era só um acento: junta com esta
            a = juntas.pop()[0]
        juntas.append((a, b, b - a < maior * 0.3))
    return [(a, b) for a, b, _ in juntas]


def _mascara(alfa: Image.Image, regiao: Image.Image) -> Image.Image:
    return ImageChops.multiply(alfa, regiao)


def partes_do_logo(empresa: str, logo: Path, largura: int, altura: int) -> dict[str, Peca]:
    """Logo no tamanho final, centrado (um pouco acima do meio), em partes: símbolo (pino/chave na Vero, corpo/rastro
    no pino das montanhas) e cada linha do nome. Juntas, as partes refazem o PNG exato."""
    _, _, altura_916, *_ = VINHETAS[empresa]
    fator = min(largura, altura) / 1080 * (1.25 if largura > altura else 1.0)
    with Image.open(logo) as aberto:
        imagem = aberto.convert("RGBA")
    imagem = imagem.crop(imagem.getchannel("A").getbbox() or (0, 0, *imagem.size))
    alto = round(altura_916 * fator)
    imagem = imagem.resize((max(1, round(imagem.width * alto / imagem.height)), alto), Image.LANCZOS)
    x0, y0 = round((largura - imagem.width) / 2), round(altura * 0.47 - alto / 2)
    perfil = _perfil(imagem.getchannel("A"), colunas=True)
    vaos = [v for v in _vazios(perfil, max(2, round(imagem.width * 0.004))) if v[0] > imagem.width * 0.2]
    corte = vaos[0] if vaos else (round(imagem.width * 0.33),) * 2
    simbolo = imagem.crop((0, 0, corte[0], alto))
    pecas: dict[str, Peca] = {}
    alfa = simbolo.getchannel("A")
    if empresa == "casa_vero":
        # Pino Caramelo (com o aro Creme) e chave Verde separados pela cor: a chave sobe para dentro do pino.
        claro = simbolo.getchannel("R").point(lambda v: 255 if v > 110 else 0)
        for nome, regiao in (("pino", claro), ("chave", ImageChops.invert(claro))):
            parte = simbolo.copy()
            parte.putalpha(_mascara(alfa, regiao))
            pecas[nome] = Peca(parte, x0, y0)
    else:
        # Pino das montanhas: corpo (círculo + ponta) e o rastro da seta orbital, que se desenha em volta.
        geo = geometria_do_pino(simbolo.size)
        regiao = Image.new("L", simbolo.size, 0)
        ImageDraw.Draw(regiao).polygon(motion_icones.gota(geo["cx"], geo["cy"], geo["r"], geo["ponta"]), fill=255)
        for nome, mascara in (("corpo", regiao), ("rastro", ImageChops.invert(regiao))):
            parte = simbolo.copy()
            parte.putalpha(_mascara(alfa, mascara))
            pecas[nome] = Peca(parte, x0, y0)
    nome_logo = imagem.crop((corte[1], 0, imagem.width, alto))
    for n, (a, b) in enumerate(_faixas(nome_logo), 1):
        pecas[f"nome{n}"] = Peca(nome_logo.crop((0, a, nome_logo.width, b)), x0 + corte[1], y0 + a)
    return pecas


def geometria_do_pino(tamanho: tuple[int, int]) -> dict:
    """Círculo e ponta do pino das montanhas (medidos no simbolo_caramelo.png), em px do recorte do símbolo."""
    w, h = tamanho
    return {"cx": 0.434 * w, "cy": 0.4275 * h, "r": 0.425 * w, "ponta": 0.995 * h,
            "rastro_inicio": 150.0, "rastro_fim": -22.0}  # graus: da cauda (embaixo, à esquerda) até a seta


# ---------------------------------------------------------------- camadas de um quadro

@dataclass
class Camada:
    """Um sprite na tela: ícone (`icone` + `params`, lado em px) ou peça do logo (`peca`, tamanho final)."""
    nome: str                 # identidade (acompanha a camada entre amostras do desfoque de movimento)
    x: float                  # centro na tela (ou o ponto `pivo` do sprite)
    y: float
    icone: str = ""
    lado: float = 0.0
    params: dict = field(default_factory=dict)
    peca: str = ""
    escala: float = 1.0
    esticar: tuple = (1.0, 1.0)
    giro: float = 0.0         # graus, anti-horário
    opacidade: float = 1.0
    desfoque: float = 0.0     # raio do desfoque gaussiano (px)
    pivo: tuple | None = None  # fração do sprite que fica em (x, y) e serve de eixo do giro
    revela: tuple | None = None  # ("direita" | "baixo" | "cima", progresso 0-1, pena em px)
    setor: tuple | None = None   # (cx, cy, ângulo atual, ângulo inicial) em px do sprite e graus do Pillow
    corte_esq: float | None = None  # nada à esquerda deste x da tela (nome saindo de trás do símbolo)


@dataclass
class Anel:
    nome: str
    x: float
    y: float
    raio: float
    espessura: float
    cor: tuple
    opacidade: float = 1.0


def _rampa(largura: int, altura: int, borda: float, pena: float, horizontal: bool) -> Image.Image:
    """Máscara L: 255 antes de `borda` (px), 0 depois, com transição de `pena` px."""
    n = largura if horizontal else altura
    pena = max(1.0, pena)
    valores = [round(255 * max(0.0, min(1.0, (borda - i) / pena + 0.5))) for i in range(n)]
    linha = Image.new("L", (n, 1))
    linha.putdata(valores)
    return linha.resize((largura, altura), Image.NEAREST) if horizontal else \
        linha.transpose(Image.Transpose.ROTATE_270).resize((largura, altura), Image.NEAREST)


def _setor(imagem: Image.Image, cx: float, cy: float, atual: float, inicial: float) -> Image.Image:
    """Revela só o setor angular entre `atual` e `inicial` (sentido horário do Pillow), com borda suave."""
    if inicial - atual >= 359.9:
        return imagem
    k = 2
    w, h = imagem.size
    mascara = Image.new("L", (w * k, h * k), 0)
    r = 3 * max(w, h) * k
    ImageDraw.Draw(mascara).pieslice((cx * k - r, cy * k - r, cx * k + r, cy * k + r), atual, inicial, fill=255)
    mascara = mascara.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(max(1.0, w / 120)))
    saida = imagem.copy()
    saida.putalpha(ImageChops.multiply(imagem.getchannel("A"), mascara))
    return saida


class Renderizador:
    """Compõe as camadas do roteiro sobre o fundo e faz o desfoque de movimento por superamostragem no tempo."""

    def __init__(self, empresa: str, formato: str, logo: Path):
        if formato not in FORMATOS:
            raise ValueError(f"Formato da vinheta: {', '.join(FORMATOS)}")
        self.empresa = empresa
        self.largura, self.altura = (int(v) for v in formato.split("x"))
        self.pecas = partes_do_logo(empresa, logo, self.largura, self.altura)
        self.palco = motion_roteiros.Palco(self.largura, self.altura, self.pecas, VINHETAS[empresa][3])
        self.roteiro = motion_roteiros.ROTEIROS[empresa]
        self.duracao = self.roteiro["duracao"]
        self.fundo = self._fundo()

    def _fundo(self) -> Image.Image:
        """Cor da marca nas bordas e um pouco de luz no centro (profundidade discreta, sem faixas)."""
        borda, centro = cor(VINHETAS[self.empresa][3])[:3], VINHETAS[self.empresa][4]
        lado = round(max(self.largura, self.altura) * 1.15)  # círculo (não elipse) em volta do logo
        luz = Image.radial_gradient("L").resize((lado, lado), Image.BICUBIC)
        topo = round(self.altura * 0.47 - lado / 2)
        luz = luz.crop(((lado - self.largura) // 2, -topo, (lado - self.largura) // 2 + self.largura,
                        -topo + self.altura)).filter(ImageFilter.GaussianBlur(6))
        luz = luz.point([round(255 * min(1.0, v / 255 / 0.62) ** 0.9) for v in range(256)])
        canais = [luz.point([round(c + (b - c) * v / 255) for v in range(256)]) for b, c in zip(borda, centro)]
        return Image.merge("RGB", canais)

    def camadas(self, t: float) -> list:
        return self.roteiro["camadas"](t, self.palco)

    # ------------------------------------------------ uma camada

    def _sprite(self, c: Camada) -> Image.Image | None:
        if c.peca:
            base = self.pecas[c.peca].imagem
            w, h = base.width * c.escala * c.esticar[0], base.height * c.escala * c.esticar[1]
        else:
            lado = c.lado * c.escala
            if lado < 2:
                return None
            molde = next(m for m in (32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 4096) if m >= lado * 1.1)
            base = motion_icones.icone(c.icone, molde, **c.params)
            w, h = lado * c.esticar[0], lado * c.esticar[1]
        w, h = round(w), round(h)
        if w < 1 or h < 1:
            return None
        imagem = base if (w, h) == base.size else base.resize((w, h), Image.LANCZOS, reducing_gap=2.0)
        if c.revela:
            direcao, progresso, pena = c.revela
            horizontal = direcao == "direita"
            n = w if horizontal else h
            borda = progresso * (n + pena) - pena / 2
            # "direita": da esquerda para a direita; "baixo": de cima para baixo; "cima": de baixo para cima
            rampa = _rampa(w, h, n - borda if direcao == "cima" else borda, pena, horizontal)
            if direcao == "cima":
                rampa = ImageChops.invert(rampa)
            imagem = imagem.copy()
            imagem.putalpha(ImageChops.multiply(imagem.getchannel("A"), rampa))
        if c.setor:
            cx, cy, atual, inicial = c.setor
            imagem = _setor(imagem, cx * w / base.width if c.peca else cx, cy * h / base.height if c.peca else cy,
                            atual, inicial)
        if c.opacidade < 0.999:
            imagem = com_opacidade(imagem, max(0.0, c.opacidade))
        if c.desfoque > 0.3:
            margem = math.ceil(c.desfoque * 2.5)
            maior = Image.new("RGBA", (w + 2 * margem, h + 2 * margem), (0, 0, 0, 0))
            maior.paste(imagem, (margem, margem))
            imagem = maior.filter(ImageFilter.GaussianBlur(c.desfoque))
        return imagem

    def _colar(self, tela: Image.Image, c: Camada) -> None:
        if c.opacidade <= 0.003:
            return
        imagem = self._sprite(c)
        if imagem is None:
            return
        largura0, altura0 = imagem.size
        dx = dy = 0.0
        if c.pivo:  # vetor do centro até o pivô, girado junto
            dx, dy = (c.pivo[0] - 0.5) * largura0, (c.pivo[1] - 0.5) * altura0
        if abs(c.giro) > 0.05:
            imagem = imagem.rotate(c.giro, Image.BICUBIC, expand=True)
            a = math.radians(c.giro)
            dx, dy = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
        esquerda = round(c.x - dx - imagem.width / 2)
        topo = round(c.y - dy - imagem.height / 2)
        if c.corte_esq is not None and c.corte_esq > esquerda:
            pena = 8 * self.palco.u
            rampa = ImageChops.invert(_rampa(imagem.width, imagem.height, c.corte_esq - esquerda + pena / 2, pena,
                                             True))
            imagem = imagem.copy()
            imagem.putalpha(ImageChops.multiply(imagem.getchannel("A"), rampa))
        tela.paste(imagem, (esquerda, topo), imagem)

    def _anel(self, tela: Image.Image, a: Anel) -> None:
        if a.opacidade <= 0.003 or a.raio < 1:
            return
        imagem = motion_icones.anel(a.raio, a.espessura, a.cor, a.opacidade)
        tela.paste(imagem, (round(a.x - imagem.width / 2), round(a.y - imagem.height / 2)), imagem)

    # ------------------------------------------------ quadro com desfoque de movimento

    def _amostra(self, camadas: list) -> Image.Image:
        tela = self.fundo.copy()
        for c in camadas:
            (self._anel if isinstance(c, Anel) else self._colar)(tela, c)
        return tela

    @staticmethod
    def _movimento(antes: list, depois: list) -> float:
        """Quanto (px) a camada mais rápida anda dentro do obturador: posição, giro e tamanho."""
        de = {c.nome: c for c in antes}
        maior = 0.0
        for c in depois:
            a = de.get(c.nome)
            if a is None or (getattr(c, "opacidade", 1) < 0.02 and getattr(a, "opacidade", 1) < 0.02):
                continue
            if isinstance(c, Anel):
                maior = max(maior, abs(c.raio - a.raio))
                continue
            raio = (c.lado * c.escala) / 2 if c.icone else 120.0 * c.escala
            andou = math.hypot(c.x - a.x, c.y - a.y) + abs(c.giro - a.giro) * math.pi / 180 * raio
            andou += abs(c.escala - a.escala) * (c.lado or 240.0) / 2
            maior = max(maior, andou)
        return maior

    def quadro(self, t: float) -> Image.Image:
        meio = OBTURADOR / FPS / 2
        antes, depois = self.camadas(t - meio), self.camadas(t + meio)
        n = max(1, min(MAX_AMOSTRAS, math.ceil(self._movimento(antes, depois) / (1.4 * self.palco.u))))
        if n == 1:
            return self._amostra(self.camadas(t))
        acumulado = None
        for k in range(n):
            amostra = self._amostra(self.camadas(t - meio + 2 * meio * k / (n - 1)))
            acumulado = amostra if acumulado is None else Image.blend(acumulado, amostra, 1 / (k + 1))
        return acumulado

    def quadros_crus(self):
        anterior, dados = None, b""
        total = round(self.duracao * FPS)
        for i in range(total):
            t = i / FPS
            estado = repr(self.camadas(t - 0.01)) + repr(self.camadas(t + 0.01))
            if estado != anterior:  # parado (o logo assentado no fim): reaproveita o quadro
                dados, anterior = self.quadro(t).tobytes(), estado
            yield dados


def vinheta(empresa: str, formato: str, saida: Path, base: Path | None = None) -> dict:
    """Renderiza a vinheta (MP4 H.264 yuv420p 30 fps, trilha AAC silenciosa). Devolve {"saida", "quadros",
    "segundos", "avisos"}."""
    if formato not in FORMATOS:
        raise ValueError(f"Formato da vinheta: {', '.join(FORMATOS)}")
    saida = Path(saida).resolve()
    base = Path(base or saida.parent).resolve()
    logo = arquivo_logo(empresa, base)
    comeco = time.perf_counter()
    render = Renderizador(empresa, formato, logo)
    saida.parent.mkdir(parents=True, exist_ok=True)
    total = round(render.duracao * FPS)
    comando = [achar_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", formato, "-framerate", str(FPS), "-i", "-", "-f", "lavfi", "-t", f"{render.duracao:.3f}",
               "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", *CODIFICACAO,
               "-t", f"{render.duracao:.3f}", str(saida)]
    _rodar(comando, render.quadros_crus())
    return {"saida": saida, "quadros": total, "segundos": round(time.perf_counter() - comeco, 1), "avisos": []}
