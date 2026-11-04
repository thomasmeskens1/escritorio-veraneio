"""Motion graphics dos vídeos da Casa Veraneio (Thomas, 04/11/2026: "os textos e formas não apresentam nenhuma
animação, conseguimos implementar Motion Graphics?").

Texto, caixa, filete, degradê, selo, contagem e logo entram ANIMADOS sobre a cena (manual 06 §2 e §3), com curvas
suaves (ease-out) de 0,5 a 0,9 s e em cascata de 0,12 a 0,2 s; nada de giro, quique ou brilho. O Max descreve a
cena num JSON e este script desenha os quadros (Pillow, motion_camadas.py) e compõe sobre o clipe com o ffmpeg,
sem PNG intermediário: os quadros vão crus pelo stdin (rawvideo RGBA) para o filtro overlay. Quadro igual ao
anterior (tudo já entrou) não é redesenhado.

Uso: python motion.py motion.json [--previa]
     python motion.py vinheta --empresa casa_veraneio --formato 1080x1920 --saida vinheta.mp4  (motion_vinheta.py)
     python motion.py vinheta --empresa casa_veraneio --variante B ...  (opções B, C e D: motion_opcoes.py)

motion.json (caminhos relativos à pasta dele, sempre dentro dela; fontes e logos vêm de _referencias/):
{"formato": "1080x1920", "cascata": 0.15, "inicio": 0.3, "sai": true,
 "cenas": [
  {"video": "acervo/drone.mp4", "de": 2.0, "duracao": 5.5, "velocidade": 0.75, "foco": 0.5,
   "saida": "trabalho/cena01.mp4", "elementos": [
     {"tipo": "degrade", "cor": "preto", "opacidade": 0.25},
     {"tipo": "texto", "texto": "RÉVEILLON 2027", "fonte": "muli", "peso": 700, "tamanho": 28,
      "cor": "caramelo", "espacamento": 9, "y": 700, "entrada": "letras"},
     {"tipo": "texto", "linhas": ["Onde o seu grupo", "vira o ano?"], "italico_ultima": true,
      "fonte": "playfair", "tamanho": 104, "entrelinha": 124, "cor": "branco", "y": 760, "entrada": "palavra"}]},
  {"fundo": "verde", "duracao": 4, "saida": "trabalho/cena02.mp4", "sai": false, "elementos": [
     {"tipo": "imagem", "logo": "caramelo", "altura": 135, "y": 1500, "entrada": "escala"}]}],
 "juntar": "entrega/Reels_Exemplo.mp4"}

Elementos: texto, caixa (com texto dentro opcional), filete, degrade, imagem (ou "logo": branca/caramelo), contagem.
Entradas: sobe, revela (direcao direita|cima), desenha (origem centro|esquerda), palavra, letras, escala,
contagem, aparece, nenhuma. "entrada" pode ser o nome ou {"efeito", "inicio", "duracao", "curva", "distancia",
"intervalo", "direcao", "origem"}; sem "inicio", entra em cascata depois do anterior. Saída suave ("sai": fade e
leve subida) antes do corte, por padrão em todos menos degradê; "sai": false no elemento ou na cena desliga.
Posição: "y" = topo do elemento em px; "x" = "centro" (padrão) ou px, com "alinhamento" centro|esquerda|direita.
Texto: fonte playfair|muli (+ "italico" por linha ou "italico_ultima"), peso, tamanho, entrelinha, espacamento (px),
maiusculas, sombra (0 a 1, leve). Caixa: cor, raio, largura/altura ou texto dentro (cor_texto, margem [h, v]).
Contagem: valor, de, casas, prefixo, sufixo. Degradê: y0, y1, opacidade número (véu) ou [topo, base]. Cena: "previas"
(segundos dos PNGs do --previa). Valores (R$, diária) só com "com_valor": true e só se o pedido pedir.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Velocidade do clipe quando a cena não diz outra (Thomas, 04/11/2026: vídeo em 0,75x; 1x só a pedido).
VELOCIDADE_PADRAO = 0.75

# Na caixa de areia o python não grava em scripts/max: sem isso, gravar o .pyc dos módulos abaixo viraria um
# "bloqueio" no painel da Diretoria a cada vídeo.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from motion_camadas import (CURVAS, LOGOS, Fontes, Sprite, _arquivo_imagem, _dentro, colar,  # noqa: E402,F401
                            com_opacidade, cor, ease_out_cubic, pasta_marcas, pastas_de_recursos,
                            ease_in_cubic, ease_in_out_cubic, ease_out_quint, juntar, linear, numero_br,
                            sprite_caixa, sprite_degrade, sprite_filete, sprite_imagem, sprites_de_palavras)
from motion_video import (CODIFICACAO, SEM_JANELA, _rodar, achar_ffmpeg, duracao_do_video,  # noqa: E402,F401
                          juntar_cenas, previa)
from PIL import Image  # noqa: E402

FPS = 30
FORMATOS = {"1080x1920", "1080x1350", "1080x1080", "1920x1080"}
TIPOS = ("texto", "caixa", "filete", "degrade", "imagem", "contagem")
FUNDOS = ("degrade",)  # entram juntos no começo, fora da cascata, e ficam até o corte
# Efeito: (duração padrão em s, curva padrão). Elegante e lento: 0,5 a 0,9 s (a contagem precisa de mais tempo).
EFEITOS = {"sobe": (0.7, "ease_out_quint"), "revela": (0.8, "ease_out_cubic"), "desenha": (0.8, "ease_in_out_cubic"),
           "palavra": (0.6, "ease_out_quint"), "letras": (0.9, "ease_out_cubic"), "escala": (0.9, "ease_out_cubic"),
           "contagem": (1.2, "ease_out_cubic"), "aparece": (0.6, "ease_out_cubic"), "nenhuma": (0.0, "linear")}
ENTRADA_DO_TIPO = {"texto": "sobe", "caixa": "revela", "filete": "desenha", "degrade": "aparece", "imagem": "escala",
                   "contagem": "contagem"}
SAIDA = {"duracao": 0.5, "curva": "ease_in_cubic", "distancia": 16, "margem": 0.1}  # termina 0,1 s antes do corte
DURACAO_LIMITES = (0.2, 3.0)
CAMPOS_COMUNS = {"tipo", "x", "y", "cor", "opacidade", "entrada", "sai", "alinhamento", "nome"}
CAMPOS_TEXTO = {"texto", "linhas", "fonte", "peso", "tamanho", "entrelinha", "espacamento", "italico",
                "italico_ultima", "maiusculas", "sombra"}
CAMPOS = {"texto": CAMPOS_TEXTO, "contagem": CAMPOS_TEXTO | {"valor", "de", "casas", "prefixo", "sufixo"},
          "caixa": CAMPOS_TEXTO | {"largura", "altura", "raio", "margem", "cor_texto"},
          "filete": {"largura", "espessura", "vertical"}, "degrade": {"y0", "y1", "curva_degrade"},
          "imagem": {"arquivo", "logo", "altura", "largura", "recorte"}}
CAMPOS_ENTRADA = {"efeito", "inicio", "duracao", "curva", "distancia", "intervalo", "direcao", "origem", "extra"}
CAMPOS_SAI = {"inicio", "duracao", "curva", "distancia"}
VALOR_NO_TEXTO = re.compile(r"R\$|\bdi[áa]ria", re.IGNORECASE)  # decisão 3: valores só quando o pedido pedir
ZONAS_916 = (250, 340)  # áreas da interface do Instagram em 9:16 (topo, base; manual 06 §3)


# ---------------------------------------------------------------- especificação e linha do tempo

def _entrada(el: dict) -> dict:
    bruta = el.get("entrada") or ENTRADA_DO_TIPO[el["tipo"]]
    entrada = {"efeito": bruta} if isinstance(bruta, str) else dict(bruta)
    entrada.setdefault("efeito", ENTRADA_DO_TIPO[el["tipo"]])
    if entrada["efeito"] not in EFEITOS:
        raise ValueError(f"Entrada desconhecida: {entrada['efeito']!r} (use {', '.join(EFEITOS)})")
    duracao, curva = EFEITOS[entrada["efeito"]]
    entrada.setdefault("duracao", duracao)
    entrada.setdefault("curva", curva)
    return entrada


def _palavras(el: dict) -> int:
    if el.get("linhas") is not None:
        return sum(len(str(l.get("texto", "") if isinstance(l, dict) else l).split()) for l in el["linhas"])
    return len(str(el.get("texto", "")).split())


def validar_elemento(el: dict, n: int = 1) -> None:
    rotulo = f"elemento {n} ({el.get('tipo')})" if isinstance(el, dict) else f"elemento {n}"
    if not isinstance(el, dict) or el.get("tipo") not in TIPOS:
        raise ValueError(f"{rotulo}: tipo desconhecido (use {', '.join(TIPOS)})")
    sobra = set(el) - CAMPOS_COMUNS - CAMPOS[el["tipo"]]
    if sobra:
        raise ValueError(f"{rotulo}: campo(s) desconhecido(s) {', '.join(sorted(sobra))}")
    if el["tipo"] == "texto" and not (el.get("texto") or el.get("linhas")):
        raise ValueError(f"{rotulo}: sem texto")
    if el["tipo"] == "contagem" and not isinstance(el.get("valor"), (int, float)):
        raise ValueError(f"{rotulo}: contagem sem \"valor\" numérico")
    if el["tipo"] == "imagem" and not (el.get("arquivo") or el.get("logo") in LOGOS):
        raise ValueError(f"{rotulo}: imagem sem \"arquivo\" nem \"logo\" (branca ou caramelo)")
    if el["tipo"] not in FUNDOS and not isinstance(el.get("y"), (int, float)):
        raise ValueError(f"{rotulo}: falta a posição \"y\" (px do topo do elemento)")
    if "x" in el and el["x"] != "centro" and not isinstance(el["x"], (int, float)):
        raise ValueError(f"{rotulo}: \"x\" deve ser número ou \"centro\"")
    if el.get("alinhamento", "centro") not in ("centro", "esquerda", "direita"):
        raise ValueError(f"{rotulo}: alinhamento deve ser centro, esquerda ou direita")
    for campo in ("cor", "cor_texto"):
        if campo in el:
            cor(el[campo])
    entrada = _entrada(el)
    if set(entrada) - CAMPOS_ENTRADA:
        raise ValueError(f"{rotulo}: entrada com campo(s) {', '.join(sorted(set(entrada) - CAMPOS_ENTRADA))}")
    if entrada["curva"] not in CURVAS:
        raise ValueError(f"{rotulo}: curva desconhecida {entrada['curva']!r} (use {', '.join(CURVAS)})")
    if entrada["efeito"] != "nenhuma" and not DURACAO_LIMITES[0] <= float(entrada["duracao"]) <= DURACAO_LIMITES[1]:
        raise ValueError(f"{rotulo}: duração da entrada fora de {DURACAO_LIMITES[0]} a {DURACAO_LIMITES[1]} s")
    if entrada["efeito"] == "desenha" and el["tipo"] not in ("filete", "caixa", "degrade", "imagem"):
        raise ValueError(f"{rotulo}: \"desenha\" é para filete (e formas), não para texto")
    if isinstance(el.get("sai"), dict) and set(el["sai"]) - CAMPOS_SAI:
        raise ValueError(f"{rotulo}: sai com campo(s) {', '.join(sorted(set(el['sai']) - CAMPOS_SAI))}")


def validar(spec: dict) -> dict:
    """Confere o motion.json inteiro (sem abrir vídeo nem fonte); devolve o próprio spec."""
    if not isinstance(spec, dict) or not isinstance(spec.get("cenas"), list) or not spec["cenas"]:
        raise ValueError("motion.json sem \"cenas\".")
    if spec.get("formato", "1080x1920") not in FORMATOS:
        raise ValueError(f"Formato fora da lista: {spec.get('formato')} (use {', '.join(sorted(FORMATOS))})")
    for c, cena in enumerate(spec["cenas"], 1):
        if not cena.get("video") and not cena.get("fundo"):
            raise ValueError(f"cena {c}: sem \"video\" nem \"fundo\" (cor)")
        if cena.get("fundo"):
            cor(cena["fundo"])
            if not cena.get("duracao"):
                raise ValueError(f"cena {c}: cena de fundo precisa de \"duracao\"")
        velocidade = float(cena.get("velocidade", VELOCIDADE_PADRAO))
        if velocidade > 1.0:
            raise ValueError(f"cena {c}: velocidade {velocidade} acelera o vídeo (nunca acelerar; manual 05 §5)")
        if velocidade < 0.5:
            raise ValueError(f"cena {c}: velocidade {velocidade} lenta demais (padrão: 0,75)")
        if not cena.get("saida"):
            raise ValueError(f"cena {c}: falta \"saida\" (MP4 da cena com o motion)")
        elementos = cena.get("elementos") or []
        for n, el in enumerate(elementos, 1):
            try:
                validar_elemento(el, n)
            except ValueError as erro:
                raise ValueError(f"cena {c}, {erro}") from None
        if not spec.get("com_valor"):
            textos = json.dumps([[el.get("texto"), el.get("linhas"), el.get("prefixo"), el.get("sufixo")]
                                 for el in elementos], ensure_ascii=False)
            if VALOR_NO_TEXTO.search(textos):
                raise ValueError(f"cena {c}: texto com R$ ou diária sem \"com_valor\": true (só se o pedido pedir).")
        if cena.get("duracao"):
            linha_do_tempo(elementos, float(cena["duracao"]), **_ritmo(spec, cena))
    return spec


def _ritmo(spec: dict, cena: dict) -> dict:
    return {"cascata": float(cena.get("cascata", spec.get("cascata", 0.15))),
            "inicio": float(cena.get("inicio", spec.get("inicio", 0.3))),
            "sai": cena.get("sai", spec.get("sai", True))}


def linha_do_tempo(elementos: list[dict], duracao: float, cascata: float = 0.15, inicio: float = 0.3,
                   sai=True) -> list[dict]:
    """Quando cada elemento entra, termina de entrar, começa a sair e some. Sem "inicio" na entrada, o elemento
    entra `cascata` s depois do anterior (no palavra a palavra, depois do começo da última palavra); degradês
    entram juntos em 0 s. A saída padrão termina SAIDA["margem"] s antes do corte."""
    tempos, cursor = [], inicio
    for n, el in enumerate(elementos, 1):
        entrada = _entrada(el)
        fundo = el["tipo"] in FUNDOS
        ini = float(entrada["inicio"]) if "inicio" in entrada else (0.0 if fundo else cursor)
        dur = 0.0 if entrada["efeito"] == "nenhuma" else float(entrada["duracao"])
        intervalo = float(entrada.get("intervalo", 0.12))
        extra = intervalo * max(0, _palavras(el) - 1) if entrada["efeito"] == "palavra" else 0.0
        if not fundo:
            cursor = ini + extra + cascata
        fim_entrada = ini + extra + dur
        pede = el.get("sai", None if fundo else sai)
        if isinstance(pede, dict) or pede:
            config = {**SAIDA, **(pede if isinstance(pede, dict) else {})}
            ini_saida = float(config.get("inicio", duracao - SAIDA["margem"] - float(config["duracao"])))
            saida = {**config, "inicio": ini_saida, "fim": ini_saida + float(config["duracao"])}
        else:
            saida = None
        if ini >= duracao:
            raise ValueError(f"elemento {n} ({el['tipo']}): entra em {ini:.2f} s, depois do fim da cena ({duracao} s)")
        if saida and fim_entrada > saida["inicio"] + 1e-6:
            raise ValueError(f"elemento {n} ({el['tipo']}): a entrada termina em {fim_entrada:.2f} s, depois do "
                             f"início da saída ({saida['inicio']:.2f} s); cena curta ou cascata longa demais")
        tempos.append({"inicio": ini, "fim_entrada": fim_entrada, "intervalo": intervalo, "entrada": entrada,
                       "saida": saida, "fim": saida["fim"] if saida else duracao})
    return tempos


# ---------------------------------------------------------------- preparo (sprites) e quadros

class Cena:
    """Elementos de uma cena prontos para desenhar: sprites feitos uma vez e a linha do tempo."""

    def __init__(self, elementos: list[dict], duracao: float, largura: int = 1080, altura: int = 1920,
                 base: Path | None = None, fps: int = FPS, cascata: float = 0.15, inicio: float = 0.3, sai=True,
                 fontes: Fontes | None = None, pastas: list[Path] | None = None):
        for n, el in enumerate(elementos, 1):
            validar_elemento(el, n)
        self.largura, self.altura, self.duracao, self.fps = largura, altura, float(duracao), fps
        self.base = Path(base or ".")
        pastas = list(pastas or []) + pastas_de_recursos(self.base)
        self.fontes = fontes or Fontes(pastas)
        self.tempos = linha_do_tempo(elementos, duracao, cascata, inicio, sai)
        self.itens = [self._preparar(el, tempo, pastas) for el, tempo in zip(elementos, self.tempos)]
        self.avisos = list(self.fontes.avisos) + self._zonas()
        self._cache_texto: dict = {}

    @property
    def quadros(self) -> int:
        return max(1, round(self.duracao * self.fps))

    def _preparar(self, el: dict, tempo: dict, pastas: list[Path]) -> dict:
        item = {"el": el, "tempo": tempo, "palavras": None}
        if el["tipo"] in ("texto", "contagem"):
            texto = self._texto_contagem(el, el.get("valor", 0)) if el["tipo"] == "contagem" else None
            item["palavras"] = sprites_de_palavras(el, self.largura, self.fontes, texto=texto)
            item["sprite"] = juntar(item["palavras"])
        elif el["tipo"] == "caixa":
            item["sprite"] = sprite_caixa(el, self.largura, self.fontes)
        elif el["tipo"] == "filete":
            item["sprite"] = sprite_filete(el, self.largura)
        elif el["tipo"] == "degrade":
            item["sprite"] = sprite_degrade(el, self.largura, self.altura)
        else:
            item["sprite"] = sprite_imagem(el, _arquivo_imagem(el, self.base, pastas), self.largura)
        return item

    @staticmethod
    def _texto_contagem(el: dict, valor: float) -> str:
        return f"{el.get('prefixo', '')}{numero_br(valor, int(el.get('casas', 0)))}{el.get('sufixo', '')}"

    def _zonas(self) -> list[str]:
        if (self.largura, self.altura) != (1080, 1920):
            return []
        topo, base = ZONAS_916[0], self.altura - ZONAS_916[1]
        return [f"elemento {n} ({i['el']['tipo']}) na área da interface do Instagram (y {s.y} a {s.y + s.altura})"
                for n, i in enumerate(self.itens, 1) if i["el"]["tipo"] not in FUNDOS
                and (s := i["sprite"]) and (s.y < topo or s.y + s.altura > base)]

    # Estado de cada elemento no instante t: tupla pequena e arredondada. Quadro com os mesmos estados do anterior
    # não é redesenhado (cache das partes paradas).
    def estado(self, item: dict, t: float):
        tempo, entrada = item["tempo"], item["tempo"]["entrada"]
        if t < tempo["inicio"] and entrada["efeito"] != "nenhuma" or t >= tempo["fim"]:
            return None
        saida, fade, sobe = tempo["saida"], 1.0, 0.0
        if saida and t >= saida["inicio"]:
            q = CURVAS[saida["curva"]]((t - saida["inicio"]) / float(saida["duracao"]))
            fade, sobe = 1.0 - q, float(saida["distancia"]) * q
        efeito = entrada["efeito"]
        if efeito == "palavra":
            curva = CURVAS[entrada["curva"]]
            ps = tuple(round(curva((t - tempo["inicio"] - k * tempo["intervalo"]) / float(entrada["duracao"])), 3)
                       for k in range(len(item["palavras"])))
            return (efeito, ps, round(fade, 3), round(sobe))
        dur = float(entrada["duracao"])
        p = 1.0 if efeito == "nenhuma" or dur <= 0 else CURVAS[entrada["curva"]]((t - tempo["inicio"]) / dur)
        return (efeito, round(p, 3), round(fade, 3), round(sobe))

    def desenhar(self, tela: Image.Image, item: dict, estado) -> None:
        efeito, p, fade, sobe = estado
        el, entrada, sprite = item["el"], item["tempo"]["entrada"], item["sprite"]
        distancia = float(entrada.get("distancia", 30 if efeito == "palavra" else 40))
        if efeito == "palavra":
            for palavra, pk in zip(item["palavras"], p):
                if pk > 0:
                    colar(tela, com_opacidade(palavra.imagem, pk * fade), palavra.x,
                          palavra.y + round((1 - pk) * distancia) - sobe)
            return
        if p <= 0:
            return
        imagem, x, y, alfa = sprite.imagem, sprite.x, sprite.y - sobe, fade
        if efeito in ("sobe", "contagem"):
            y += round((1 - p) * (distancia if efeito == "sobe" else 20))
            alfa *= p if efeito == "sobe" else min(1.0, p * 3)
            if efeito == "contagem":
                atual = float(el.get("de", 0)) + (float(el["valor"]) - float(el.get("de", 0))) * p
                s = self._texto_cache(el, texto=self._texto_contagem(el, atual))
                imagem, x, y = s.imagem, s.x, s.y - sobe + round((1 - p) * 20)
        elif efeito == "aparece":
            alfa *= p
        elif efeito == "letras":
            final = float(el.get("espacamento", 0))
            extra = float(entrada.get("extra", max(8.0, float(el.get("tamanho", 28)) * 0.5)))
            s = self._texto_cache(el, espacamento=round((final + extra * (1 - p)) * 4) / 4)
            imagem, x, y, alfa = s.imagem, s.x, s.y - sobe, alfa * p
        elif efeito == "escala":
            fator = 0.92 + 0.08 * p
            w, h = max(1, round(imagem.width * fator)), max(1, round(imagem.height * fator))
            if (w, h) != imagem.size:
                imagem = imagem.resize((w, h), Image.BICUBIC)
            x, y, alfa = x + (sprite.largura - w) // 2, y + (sprite.altura - h) // 2, alfa * p
        elif efeito == "revela":
            imagem = self._revelar(imagem, p, entrada.get("direcao", "direita"))
            alfa *= min(1.0, p * 1.6) if entrada.get("direcao", "direita") == "cima" else 1.0
        elif efeito == "desenha":
            imagem, dx, dy = self._desenhar_linha(imagem, p, entrada.get("origem", "centro"))
            x, y = x + dx, y + dy
        if imagem is not None:
            colar(tela, com_opacidade(imagem, alfa), x, y)

    def _texto_cache(self, el: dict, espacamento: float | None = None, texto: str | None = None) -> Sprite:
        chave = (id(el), espacamento, texto)
        if chave not in self._cache_texto:
            self._cache_texto[chave] = juntar(sprites_de_palavras(el, self.largura, self.fontes, espacamento, texto))
        return self._cache_texto[chave]

    @staticmethod
    def _revelar(imagem: Image.Image, p: float, direcao: str) -> Image.Image:
        w, h = imagem.size
        if direcao == "cima":  # sobe de dentro de uma máscara do tamanho do elemento
            nova = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            nova.paste(imagem, (0, round((1 - p) * h)))
            return nova
        borda = max(8, w // 6)  # cortina da esquerda para a direita com borda suave
        frente = round(p * (w + borda))
        mascara = Image.new("L", (w, h), 0)
        if frente - borda > 0:
            mascara.paste(255, (0, 0, min(w, frente - borda), h))
        rampa = Image.linear_gradient("L").rotate(90, expand=True).resize((borda, h))
        mascara.paste(rampa, (frente - borda, 0))
        alfa = Image.composite(imagem.getchannel("A"), Image.new("L", (w, h), 0), mascara)
        nova = imagem.copy()
        nova.putalpha(alfa)
        return nova

    @staticmethod
    def _desenhar_linha(imagem: Image.Image, p: float, origem: str):
        w, h = imagem.size
        vertical = h > w
        total = h if vertical else w
        visivel = max(1, round(total * p))
        inicio = 0 if origem == "esquerda" else (total - visivel) // 2
        if vertical:
            return imagem.crop((0, inicio, w, inicio + visivel)), 0, inicio
        return imagem.crop((inicio, 0, inicio + visivel, h)), inicio, 0

    def quadro(self, t: float, fundo=None) -> Image.Image:
        """A sobreposição (RGBA) no instante t; com `fundo` (cor), opaca."""
        tela = Image.new("RGBA", (self.largura, self.altura), cor(fundo) if fundo else (0, 0, 0, 0))
        for item in self.itens:
            if (estado := self.estado(item, t)) is not None:
                self.desenhar(tela, item, estado)
        return tela

    def quadros_crus(self, fundo=None):
        """Bytes RGBA de cada quadro, reaproveitando o anterior quando nada mudou."""
        anterior, dados = None, b""
        for k in range(self.quadros):
            t = k / self.fps
            estados = tuple(self.estado(item, t) for item in self.itens)
            if estados != anterior:
                tela = Image.new("RGBA", (self.largura, self.altura), cor(fundo) if fundo else (0, 0, 0, 0))
                for item, estado in zip(self.itens, estados):
                    if estado is not None:
                        self.desenhar(tela, item, estado)
                dados, anterior = tela.tobytes(), estados
            yield dados


# ---------------------------------------------------------------- composição com o ffmpeg

def aplicar(cena_mp4, saida_mp4, elementos: list[dict], formato: str = "1080x1920", duracao: float | None = None,
            de: float = 0.0, velocidade: float = 1.0, foco: float = 0.5, fundo=None, base=None, cascata: float = 0.15,
            inicio: float = 0.3, sai=True, pastas: list[Path] | None = None) -> dict:
    """Compõe os elementos animados sobre o clipe (recortado em "cover" no formato, a partir de `de` s, com câmera
    lenta suave opcional) ou sobre um fundo de cor. Sai MP4 H.264 30 fps com trilha AAC silenciosa (manual 06 §2).
    Devolve {"saida", "quadros", "segundos", "avisos"}."""
    if formato not in FORMATOS:
        raise ValueError(f"Formato fora da lista: {formato}")
    if velocidade > 1.0:
        raise ValueError("Nunca acelerar o vídeo (manual 05 §5): velocidade até 1.0.")
    largura, altura = (int(v) for v in formato.split("x"))
    ffmpeg = achar_ffmpeg() or "ffmpeg"
    if cena_mp4 is not None and duracao is None:
        duracao = (duracao_do_video(Path(cena_mp4)) - de) / velocidade  # câmera lenta alonga a cena
    if not duracao or duracao <= 0:
        raise ValueError("Cena sem duração.")
    comeco = time.perf_counter()
    cena = Cena(elementos, duracao, largura, altura, Path(base or Path(saida_mp4).parent), FPS, cascata, inicio, sai,
                 pastas=pastas)
    saida_mp4 = Path(saida_mp4)
    saida_mp4.parent.mkdir(parents=True, exist_ok=True)
    cru = ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", formato, "-framerate", str(FPS), "-i", "-"]
    silencio = ["-f", "lavfi", "-t", f"{duracao:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    if cena_mp4 is None:
        comando = [ffmpeg, "-y", "-loglevel", "error", *cru, *silencio, "-map", "0:v", "-map", "1:a"]
        quadros = cena.quadros_crus(fundo or "verde")
    else:
        filtro = (f"[0:v:0]setpts=(PTS-STARTPTS)/{velocidade},fps={FPS},scale={largura}:{altura}:"
                  f"force_original_aspect_ratio=increase,crop={largura}:{altura}:(iw-{largura})*{foco}:(ih-{altura})/2,"
                  f"setsar=1[b];[b][1:v]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]")
        comando = [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{de:.3f}", "-t", f"{duracao * velocidade + 0.5:.3f}",
                   "-i", str(cena_mp4), *cru, *silencio, "-filter_complex", filtro, "-map", "[v]", "-map", "2:a"]
        quadros = cena.quadros_crus()
    _rodar([*comando, *CODIFICACAO, "-t", f"{duracao:.3f}", str(saida_mp4)], quadros)
    return {"saida": saida_mp4, "quadros": cena.quadros, "segundos": round(time.perf_counter() - comeco, 1),
            "avisos": cena.avisos, "cena": cena}


def renderizar(arquivo: Path, com_previa: bool = False) -> list[dict]:
    arquivo = Path(arquivo).resolve()
    base, spec = arquivo.parent, validar(json.loads(Path(arquivo).read_text(encoding="utf-8")))
    formato, resultados = spec.get("formato", "1080x1920"), []
    for c, cena in enumerate(spec["cenas"], 1):
        video = _dentro(base, cena["video"], "video") if cena.get("video") else None
        if video and not video.is_file():
            raise ValueError(f"cena {c}: vídeo não encontrado: {cena['video']}")
        resultado = aplicar(video, _dentro(base, cena["saida"], "saida"), cena.get("elementos") or [], formato,
                            cena.get("duracao"), float(cena.get("de", 0)), float(cena.get("velocidade", VELOCIDADE_PADRAO)),
                            float(cena.get("foco", 0.5)), cena.get("fundo"), base, **_ritmo(spec, cena))
        if com_previa:
            fim = max([t["fim_entrada"] for t in resultado["cena"].tempos] or [0.5])
            tempos = cena.get("previas") or [round(min(fim + 0.2, resultado["cena"].duracao - 0.05), 2)]
            resultado["previas"] = previa(resultado["saida"], tempos, base / "previas", Path(cena["saida"]).stem)
        resultados.append(resultado)
    if spec.get("juntar"):
        juntar_cenas([r["saida"] for r in resultados], _dentro(base, spec["juntar"], "juntar"))
    return resultados


def main_vinheta(argumentos: list[str]) -> None:
    import motion_vinheta
    args = argparse.ArgumentParser(prog="motion.py vinheta", description=motion_vinheta.__doc__.splitlines()[0])
    args.add_argument("--empresa", required=True, choices=sorted(motion_vinheta.VINHETAS))
    args.add_argument("--formato", default="1080x1920", choices=motion_vinheta.FORMATOS)
    args.add_argument("--saida", required=True, help="MP4 da vinheta (dentro da pasta da peça)")
    args.add_argument("--variante", default="A", type=str.upper, choices=motion_vinheta.motion_opcoes.VARIANTES,
                      help="opção da vinheta: A (aprovada, padrão de produção), B, C ou D (alternativas)")
    opcoes = args.parse_args(argumentos)
    r = motion_vinheta.vinheta(opcoes.empresa, opcoes.formato, Path(opcoes.saida), Path.cwd(), opcoes.variante)
    print(f"Vinheta: {r['saida']} ({r['quadros']} quadros em {r['segundos']} s)")


def main() -> None:
    if sys.argv[1:2] == ["vinheta"]:
        return main_vinheta(sys.argv[2:])
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("dados", help="motion.json")
    args.add_argument("--previa", action="store_true", help="PNG de cada cena depois das entradas (em previas/)")
    opcoes = args.parse_args()
    for r in renderizar(Path(opcoes.dados), opcoes.previa):
        print(f"Cena com motion: {r['saida']} ({r['quadros']} quadros em {r['segundos']} s)")
        for aviso in r["avisos"]:
            print(f"  AVISO: {aviso}")
        for png in r.get("previas", []):
            print(f"  prévia: {png}")


if __name__ == "__main__":
    main()
