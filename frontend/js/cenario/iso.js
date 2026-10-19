// Utilitários de desenho isométrico compartilhados pelo cenário.
// Grade: x cresce para baixo-direita, y para baixo-esquerda; z é altura em pixels.

const TILE_W = 80;
const TILE_H = 40;
const GRADE = 8; // chão de 8x8 tiles
const ALTURA_PAREDE = 120;
const PX_POR_T = Math.hypot(TILE_W / 2, TILE_H / 2); // pixels por unidade ao longo da parede
const PROF_PAREDE = 2; // profundidade (depth) das paredes e seus elementos
const PROF_BASE = 1000; // objetos do chão: PROF_BASE + y de tela do canto frontal
const PROF_ROTULOS = 100000;

// Converte '#rgb' / '#rrggbb' em número; usa `padrao` se o valor for inválido.
function corHex(valor, padrao = 0x888888) {
  if (typeof valor === 'number') return valor;
  if (typeof valor !== 'string') return padrao;
  let h = valor.trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(h)) h = h.split('').map((c) => c + c).join('');
  return /^[0-9a-f]{6}$/i.test(h) ? parseInt(h, 16) : padrao;
}

// f < 1 escurece multiplicando; f > 1 clareia misturando com branco.
function tomCor(cor, f) {
  const canal = (d) => {
    const v = (cor >> d) & 255;
    const r = f <= 1 ? v * f : v + (255 - v) * Math.min(1, f - 1);
    return Math.max(0, Math.min(255, Math.round(r)));
  };
  return (canal(16) << 16) | (canal(8) << 8) | canal(0);
}

function luminancia(cor) {
  return (0.299 * ((cor >> 16) & 255) + 0.587 * ((cor >> 8) & 255) + 0.114 * (cor & 255)) / 255;
}

// Ponto da grade (x, y) elevado z pixels, em coordenadas de tela.
function pIso(x, y, z = 0) {
  const p = isoParaTela(x, y);
  return { x: p.x, y: p.y - z };
}

// Profundidade de um objeto cujo canto frontal da base está em (x, y).
function profundidade(x, y) {
  return PROF_BASE + isoParaTela(x, y).y;
}

// Quadrilátero no chão (ou em altura z) cobrindo [x0,x1] x [y0,y1].
function quadChao(g, x0, y0, x1, y1, cor, alfa = 1, z = 0) {
  g.fillStyle(cor, alfa);
  g.fillPoints([pIso(x0, y0, z), pIso(x1, y0, z), pIso(x1, y1, z), pIso(x0, y1, z)], true);
}

// Caixa com base [x0,x1] x [y0,y1] entre as alturas z0 e z1 (topo + duas faces visíveis).
function caixaIso(g, x0, y0, x1, y1, z0, z1, cor, contorno = true) {
  g.fillStyle(tomCor(cor, 0.78));
  g.fillPoints([pIso(x0, y1, z1), pIso(x1, y1, z1), pIso(x1, y1, z0), pIso(x0, y1, z0)], true);
  g.fillStyle(tomCor(cor, 0.62));
  g.fillPoints([pIso(x1, y0, z1), pIso(x1, y1, z1), pIso(x1, y1, z0), pIso(x1, y0, z0)], true);
  quadChao(g, x0, y0, x1, y1, cor, 1, z1);
  if (contorno) {
    g.lineStyle(1, 0x000000, 0.22);
    g.strokePoints([
      pIso(x0, y0, z1), pIso(x1, y0, z1), pIso(x1, y0, z0), pIso(x1, y1, z0),
      pIso(x0, y1, z0), pIso(x0, y1, z1),
    ], true);
  }
}

// Ponto numa parede de trás: 'esq' corre em y (x = 0), 'dir' corre em x (y = 0).
function pParede(lado, t, z, afasta = 0) {
  return lado === 'esq' ? pIso(afasta, t, z) : pIso(t, afasta, z);
}

// Retângulo pintado na parede entre t0..t1 e alturas z0..z1.
function quadParede(g, lado, t0, t1, z0, z1, cor, alfa = 1, afasta = 0) {
  g.fillStyle(cor, alfa);
  g.fillPoints([
    pParede(lado, t0, z0, afasta), pParede(lado, t1, z0, afasta),
    pParede(lado, t1, z1, afasta), pParede(lado, t0, z1, afasta),
  ], true);
}

// Caixa presa à parede, saindo `prof` unidades da superfície (prateleiras, armários).
function caixaParede(g, lado, t0, t1, prof, z0, z1, cor, contorno = true) {
  if (lado === 'esq') caixaIso(g, 0, t0, prof, t1, z0, z1, cor, contorno);
  else caixaIso(g, t0, 0, t1, prof, z0, z1, cor, contorno);
}

// Linha na parede de (t0, z0) a (t1, z1).
function linhaParede(g, lado, t0, z0, t1, z1, largura, cor, alfa = 1, afasta = 0) {
  const a = pParede(lado, t0, z0, afasta);
  const b = pParede(lado, t1, z1, afasta);
  g.lineStyle(largura, cor, alfa);
  g.lineBetween(a.x, a.y, b.x, b.y);
}

// Gerador pseudoaleatório determinístico (mesma decoração a cada renderização).
function sementeAleatoria(semente) {
  let s = semente >>> 0 || 1;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function hashTexto(texto) {
  let h = 2166136261;
  for (const c of String(texto)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}
