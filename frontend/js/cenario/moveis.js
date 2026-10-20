// Móveis e objetos de chão. Cada tipo declara a área ocupada (w x d tiles) e como se desenha.
// `m` traz x, y (canto de trás) e opções; `ctx` dá acesso à cena, extras animados e tweens.

function pernasMesa(g, x0, y0, x1, y1, z, cor) {
  const l = 0.06;
  [[x0, y1 - l], [x1 - l, y1 - l], [x1 - l, y0]].forEach(([x, y]) => caixaIso(g, x, y, x + l, y + l, 0, z, cor, false));
}

// Tampo com pernas; devolve a altura do tampo.
function desenharMesa(g, x0, y0, x1, y1, z, cor, corPernas = 0x343a40) {
  pernasMesa(g, x0 + 0.04, y0 + 0.04, x1 - 0.04, y1 - 0.04, z - 3, corPernas);
  caixaIso(g, x0, y0, x1, y1, z - 3, z, cor);
  return z;
}

function desenharCadeira(g, x, y, cor, encosto = 'tras') {
  caixaIso(g, x + 0.04, y + 0.04, x + 0.08, y + 0.08, 0, 11, 0x343a40, false);
  caixaIso(g, x - 0.12, y - 0.12, x + 0.12, y + 0.12, 11, 14, cor);
  if (encosto === 'tras') caixaIso(g, x - 0.12, y - 0.14, x + 0.12, y - 0.08, 14, 34, tomCor(cor, 0.9));
  if (encosto === 'esq') caixaIso(g, x - 0.14, y - 0.12, x - 0.08, y + 0.12, 14, 34, tomCor(cor, 0.9));
}

// Monitor com a tela virada para quem olha (face y = constante).
function desenharMonitor(g, x0, x1, y, z, cor = 0x1b2a3a, conteudo) {
  const meio = (x0 + x1) / 2;
  caixaIso(g, meio - 0.03, y - 0.02, meio + 0.03, y + 0.02, z, z + 6, 0x343a40, false);
  caixaIso(g, x0, y - 0.03, x1, y + 0.03, z + 6, z + 26, 0x212529, false);
  const tela = [pIso(x0 + 0.04, y + 0.031, z + 24), pIso(x1 - 0.04, y + 0.031, z + 24),
    pIso(x1 - 0.04, y + 0.031, z + 8), pIso(x0 + 0.04, y + 0.031, z + 8)];
  g.fillStyle(cor);
  g.fillPoints(tela, true);
  conteudo?.(g, x0 + 0.06, x1 - 0.06, y + 0.032, z + 10, z + 22);
}

// Barrinhas coloridas numa tela (gráficos / fila de tarefas).
function barrasTela(cores) {
  return (g, x0, x1, y, z0, z1) => {
    const n = cores.length;
    cores.forEach((cor, i) => {
      const x = x0 + ((x1 - x0) * i) / n;
      const h = z0 + (z1 - z0) * (0.35 + ((i * 37) % 60) / 100);
      g.fillStyle(cor);
      g.fillPoints([pIso(x, y, z0), pIso(x + (x1 - x0) / n * 0.7, y, z0),
        pIso(x + (x1 - x0) / n * 0.7, y, h), pIso(x, y, h)], true);
    });
  };
}

function linhasTela(cor) {
  return (g, x0, x1, y, z0, z1) => {
    for (let z = z1; z > z0; z -= 3) {
      const a = pIso(x0, y, z);
      const b = pIso(x0 + (x1 - x0) * (0.4 + ((z * 13) % 50) / 100), y, z);
      g.lineStyle(1.2, cor, 0.85);
      g.lineBetween(a.x, a.y, b.x, b.y);
    }
  };
}

// LED piscante como objeto separado (para tween).
function ledPiscante(ctx, x, y, z, cor, atraso) {
  const p = pIso(x, y, z);
  const c = ctx.cena.add.rectangle(p.x, p.y, 3, 2, cor).setDepth(ctx.profundidade + 1);
  ctx.extras.push(c);
  ctx.anima({ targets: c, alpha: 0.15, duration: 300 + (atraso % 5) * 140, yoyo: true, delay: atraso * 90 });
}

const MOVEIS = {
  planta: {
    w: 1, d: 1,
    desenhar(g, { x, y, alta }) {
      const cx = x + 0.5, cy = y + 0.5;
      caixaIso(g, cx - 0.16, cy - 0.16, cx + 0.16, cy + 0.16, 0, 18, 0xb5651d);
      quadChao(g, cx - 0.13, cy - 0.13, cx + 0.13, cy + 0.13, 0x3b2a1a, 1, 18);
      const base = pIso(cx, cy, 18);
      const folhas = alta ? [[0, -40, 13], [-10, -28, 11], [10, -26, 11], [-5, -16, 10], [7, -12, 9]]
        : [[0, -18, 11], [-9, -10, 9], [9, -9, 9], [0, -6, 8]];
      if (alta) {
        g.lineStyle(3, 0x5c3d1e);
        g.lineBetween(base.x, base.y, base.x, base.y - 34);
      }
      folhas.forEach(([dx, dy, r], i) => {
        g.fillStyle(i % 2 ? 0x2d6a4f : 0x40916c);
        g.fillCircle(base.x + dx, base.y + dy, r);
      });
      g.fillStyle(0x74c69d, 0.6);
      g.fillCircle(base.x - 3, base.y + folhas[0][1] - 3, 4);
    },
  },

  rack: {
    w: 1, d: 1,
    desenhar(g, { x, y }, ctx) {
      caixaIso(g, x + 0.1, y + 0.15, x + 0.85, y + 0.9, 0, 92, 0x2b2d31);
      for (let i = 0; i < 6; i++) {
        const z = 10 + i * 13;
        const face = [pIso(x + 0.85, y + 0.2, z + 9), pIso(x + 0.85, y + 0.85, z + 9),
          pIso(x + 0.85, y + 0.85, z), pIso(x + 0.85, y + 0.2, z)];
        g.fillStyle(0x16181c);
        g.fillPoints(face, true);
        ledPiscante(ctx, x + 0.85, y + 0.3 + (i % 3) * 0.1, z + 5, i % 2 ? 0x40c057 : 0x4dabf7, i + x * 3 + y);
        if (i % 2 === 0) ledPiscante(ctx, x + 0.85, y + 0.72, z + 5, 0xf4a261, i + 7);
      }
    },
  },

  caixas: {
    w: 1, d: 1,
    desenhar(g, { x, y, pilha = 2 }) {
      caixaIso(g, x + 0.1, y + 0.1, x + 0.6, y + 0.6, 0, 22, 0xc19a6b);
      caixaIso(g, x + 0.45, y + 0.4, x + 0.9, y + 0.88, 0, 20, 0xb08968);
      if (pilha > 1) caixaIso(g, x + 0.15, y + 0.15, x + 0.55, y + 0.55, 22, 40, 0xd4a373);
      const p = pIso(x + 0.35, y + 0.6, 12);
      g.fillStyle(0x6c584c, 0.6);
      g.fillRect(p.x - 2, p.y - 1, 6, 2);
    },
  },

  tambores: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      [[0.3, 0.35, 0x1971c2], [0.65, 0.6, 0x2f9e44], [0.3, 0.75, 0x1971c2]].forEach(([dx, dy, cor]) => {
        const base = pIso(x + dx, y + dy);
        g.fillStyle(tomCor(cor, 0.7));
        g.fillRect(base.x - 11, base.y - 30, 22, 30);
        g.fillEllipse(base.x, base.y, 22, 10);
        g.fillStyle(tomCor(cor, 0.85));
        g.fillRect(base.x - 11, base.y - 30, 11, 30);
        g.fillStyle(0x000000, 0.25);
        g.fillRect(base.x - 11, base.y - 20, 22, 2);
        g.fillRect(base.x - 11, base.y - 10, 22, 2);
        g.fillStyle(cor);
        g.fillEllipse(base.x, base.y - 30, 22, 10);
        g.fillStyle(0x000000, 0.3);
        g.fillCircle(base.x + 4, base.y - 31, 2);
      });
    },
  },

  // Manequim de agente em construção (oficina do Construtor).
  prototipo: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      const cx = x + 0.5, cy = y + 0.5;
      caixaIso(g, cx - 0.25, cy - 0.25, cx + 0.25, cy + 0.25, 0, 6, 0x495057);
      caixaIso(g, cx - 0.03, cy - 0.03, cx + 0.03, cy + 0.03, 6, 22, 0x868e96, false);
      const p = pIso(cx, cy, 22);
      g.fillStyle(0xadb5bd);
      g.fillRoundedRect(p.x - 10, p.y - 22, 20, 22, 5);
      g.fillStyle(0xced4da);
      g.fillEllipse(p.x, p.y - 34, 25, 23);
      g.lineStyle(1.5, 0x4dabf7, 0.9);
      g.strokeRoundedRect(p.x - 10, p.y - 22, 20, 22, 5);
      g.lineBetween(p.x - 4, p.y - 15, p.x + 4, p.y - 15);
      g.lineBetween(p.x, p.y - 19, p.x, p.y - 8);
      g.fillStyle(0x4dabf7);
      g.fillCircle(p.x - 5, p.y - 34, 2);
      g.fillCircle(p.x + 5, p.y - 34, 2);
      g.lineStyle(1, 0xffc300);
      g.lineBetween(p.x + 10, p.y - 18, p.x + 18, p.y - 4);
    },
  },

  estante: {
    w: 1, d: 2,
    desenhar(g, { x, y }) {
      const x1 = x + 0.45;
      caixaIso(g, x, y + 0.05, x1, y + 1.95, 0, 96, 0x8b5e34);
      const cores = [0xe76f51, 0x2a9d8f, 0xe9c46a, 0x457b9d, 0x6d597a, 0xf4a261];
      for (let n = 0; n < 4; n++) {
        const z = 8 + n * 22;
        g.fillStyle(0x5c3d1e);
        g.fillPoints([pIso(x1, y + 0.12, z + 18), pIso(x1, y + 1.88, z + 18),
          pIso(x1, y + 1.88, z), pIso(x1, y + 0.12, z)], true);
        for (let t = y + 0.16, i = n; t < y + 1.8; t += 0.11, i++) {
          const h = 11 + ((i * 7) % 6);
          g.fillStyle(cores[i % cores.length]);
          g.fillPoints([pIso(x1, t, z + h), pIso(x1, t + 0.08, z + h),
            pIso(x1, t + 0.08, z), pIso(x1, t, z)], true);
        }
      }
    },
  },

  carteira: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      desenharCadeira(g, x + 0.62, y + 0.5, 0x457b9d, 'esq');
      desenharMesa(g, x + 0.2, y + 0.25, x + 0.5, y + 0.8, 22, 0xd4a373);
      caixaIso(g, x + 0.27, y + 0.4, x + 0.42, y + 0.6, 22, 24, 0xf8f9fa, false);
    },
  },

  tapete: {
    w: 0, d: 0, chao: true,
    desenhar(g, { x, y, w, d, cores, texto }, ctx) {
      quadChao(g, x, y, x + w, y + d, cores[0]);
      const n = cores.length - 1;
      for (let i = 0; i < n; i++) {
        const a = x + 0.12 + ((w - 0.24) * i) / n;
        quadChao(g, a, y + 0.12, a + (w - 0.24) / n, y + d - 0.12, cores[i + 1]);
      }
      if (texto) {
        const p = pIso(x + w / 2, y + d / 2);
        ctx.extras.push(ctx.cena.add.text(p.x, p.y, texto, {
          fontFamily: 'system-ui, sans-serif', fontSize: '9px', fontStyle: 'bold', color: '#fff8e7',
        }).setOrigin(0.5).setDepth(PROF_PAREDE + 2).setAlpha(0.9));
      }
    },
  },

  sofa: {
    w: 2, d: 1,
    desenhar(g, { x, y, cor = 0x6d597a }) {
      caixaIso(g, x + 0.1, y + 0.15, x + 1.9, y + 0.85, 0, 16, tomCor(cor, 0.85));
      caixaIso(g, x + 0.1, y + 0.15, x + 1.9, y + 0.35, 16, 38, cor);
      caixaIso(g, x + 0.1, y + 0.35, x + 0.3, y + 0.85, 16, 26, cor);
      caixaIso(g, x + 1.7, y + 0.35, x + 1.9, y + 0.85, 16, 26, cor);
      caixaIso(g, x + 0.35, y + 0.4, x + 0.95, y + 0.8, 16, 20, tomCor(cor, 1.15));
      caixaIso(g, x + 1.05, y + 0.4, x + 1.65, y + 0.8, 16, 20, tomCor(cor, 1.15));
      caixaIso(g, x + 0.45, y + 0.38, x + 0.65, y + 0.48, 20, 32, 0xe9c46a, false);
    },
  },

  cafeteira: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      caixaIso(g, x + 0.05, y + 0.05, x + 0.95, y + 0.55, 0, 30, 0x495057);
      caixaIso(g, x + 0.05, y + 0.05, x + 0.95, y + 0.55, 30, 33, 0xdee2e6);
      caixaIso(g, x + 0.2, y + 0.1, x + 0.5, y + 0.4, 33, 58, 0x212529);
      caixaIso(g, x + 0.22, y + 0.38, x + 0.48, y + 0.41, 40, 50, 0xc92a2a, false);
      caixaIso(g, x + 0.62, y + 0.2, x + 0.72, y + 0.3, 33, 41, 0xf8f9fa, false);
      caixaIso(g, x + 0.78, y + 0.2, x + 0.88, y + 0.3, 33, 41, 0xe76f51, false);
    },
  },

  tripe: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      const cx = x + 0.5, cy = y + 0.5;
      const topo = pIso(cx, cy, 62);
      g.lineStyle(2, 0x212529);
      [[cx - 0.3, cy], [cx + 0.2, cy - 0.25], [cx + 0.15, cy + 0.3]].forEach(([px, py]) => {
        const p = pIso(px, py);
        g.lineBetween(p.x, p.y, topo.x, topo.y + 16);
      });
      g.lineBetween(topo.x, topo.y + 16, topo.x, topo.y);
      g.lineStyle(5, 0xfff3bf);
      g.strokeCircle(topo.x, topo.y - 12, 13);
      g.lineStyle(1.5, 0xffffff, 0.8);
      g.strokeCircle(topo.x, topo.y - 12, 13);
      g.fillStyle(0x212529);
      g.fillRoundedRect(topo.x - 5, topo.y - 16, 10, 8, 2);
    },
  },

  mesaReuniao: {
    w: 3, d: 2,
    desenhar(g, { x, y }) {
      for (let i = 0; i < 3; i++) desenharCadeira(g, x + 0.5 + i, y + 0.15, 0x3d2b1f);
      desenharMesa(g, x + 0.1, y + 0.4, x + 2.9, y + 1.5, 26, 0x5c3d2e, 0x1b1b1b);
      quadChao(g, x + 0.2, y + 0.9, x + 2.8, y + 1.0, 0xd4af37, 1, 26);
      [0.6, 1.5, 2.4].forEach((dx) => caixaIso(g, x + dx - 0.1, y + 0.6, x + dx + 0.1, y + 0.75, 26, 27, 0xf8f9fa, false));
      caixaIso(g, x + 1.4, y + 1.1, x + 1.6, y + 1.3, 26, 34, 0x2d6a4f, false);
    },
  },

  cadeirasFrente: {
    w: 3, d: 1,
    desenhar(g, { x, y }) {
      for (let i = 0; i < 3; i++) {
        const cx = x + 0.5 + i, cy = y + 0.45;
        caixaIso(g, cx - 0.04, cy - 0.04, cx + 0.04, cy + 0.04, 0, 11, 0x343a40, false);
        caixaIso(g, cx - 0.14, cy - 0.14, cx + 0.14, cy + 0.14, 11, 15, 0x3d2b1f);
        caixaIso(g, cx - 0.14, cy + 0.1, cx + 0.14, cy + 0.17, 15, 32, 0x4a3426);
      }
    },
  },

  poltrona: {
    w: 1, d: 1,
    desenhar(g, { x, y, cor = 0x7f5539 }) {
      caixaIso(g, x + 0.15, y + 0.15, x + 0.85, y + 0.85, 0, 16, tomCor(cor, 0.85));
      caixaIso(g, x + 0.15, y + 0.15, x + 0.85, y + 0.32, 16, 40, cor);
      caixaIso(g, x + 0.15, y + 0.32, x + 0.3, y + 0.85, 16, 26, cor);
      caixaIso(g, x + 0.7, y + 0.32, x + 0.85, y + 0.85, 16, 26, cor);
      quadChao(g, x + 0.15, y + 0.15, x + 0.85, y + 0.18, 0xd4af37, 1, 40);
    },
  },

  mesinha: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      caixaIso(g, x + 0.45, y + 0.45, x + 0.55, y + 0.55, 0, 18, 0xd4af37, false);
      caixaIso(g, x + 0.25, y + 0.25, x + 0.75, y + 0.75, 18, 21, 0x212529);
      caixaIso(g, x + 0.4, y + 0.4, x + 0.5, y + 0.5, 21, 28, 0xa5d8ff, false);
    },
  },

  abajur: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      const cx = x + 0.5, cy = y + 0.5;
      caixaIso(g, cx - 0.15, cy - 0.15, cx + 0.15, cy + 0.15, 0, 3, 0xd4af37, false);
      caixaIso(g, cx - 0.02, cy - 0.02, cx + 0.02, cy + 0.02, 3, 70, 0xd4af37, false);
      const p = pIso(cx, cy, 70);
      g.fillStyle(0xffe066, 0.05);
      g.fillCircle(p.x, p.y - 6, 30);
      g.fillCircle(p.x, p.y - 6, 18);
      g.fillStyle(0xfff3bf);
      g.fillPoints([{ x: p.x - 9, y: p.y }, { x: p.x + 9, y: p.y }, { x: p.x + 6, y: p.y - 16 }, { x: p.x - 6, y: p.y - 16 }], true);
    },
  },

  bar: {
    w: 1, d: 2,
    desenhar(g, { x, y }) {
      caixaIso(g, x, y + 0.05, x + 0.45, y + 1.95, 0, 40, 0x3d2b1f);
      quadChao(g, x, y + 0.05, x + 0.45, y + 1.95, 0xd4af37, 1, 40);
      const cores = [0x2b9348, 0x9d0208, 0xe9c46a, 0x6a4c93, 0x2b9348];
      cores.forEach((cor, i) => {
        const t = y + 0.3 + i * 0.32;
        caixaIso(g, x + 0.15, t, x + 0.25, t + 0.1, 40, 56, cor, false);
        caixaIso(g, x + 0.18, t + 0.03, x + 0.22, t + 0.07, 56, 62, cor, false);
      });
    },
  },

  // Arquivo de aço com gavetas etiquetadas.
  arquivo: {
    w: 1, d: 1,
    desenhar(g, { x, y, cor = 0x6c7a72 }) {
      const x0 = x + 0.15, y0 = y + 0.2, x1 = x + 0.75, y1 = y + 0.8;
      caixaIso(g, x0, y0, x1, y1, 0, 72, cor);
      for (let i = 0; i < 4; i++) {
        const z0 = 5 + i * 16.5, z1 = z0 + 14;
        g.fillStyle(tomCor(cor, 0.92));
        g.fillPoints([pIso(x1, y0 + 0.05, z1), pIso(x1, y1 - 0.05, z1), pIso(x1, y1 - 0.05, z0), pIso(x1, y0 + 0.05, z0)], true);
        const et = pIso(x1, (y0 + y1) / 2, z1 - 4);
        g.fillStyle(0xf8f9fa);
        g.fillRect(et.x - 1, et.y - 2, 5, 3);
        const puxador = pIso(x1, (y0 + y1) / 2, z0 + 5);
        g.fillStyle(0xdee2e6);
        g.fillRect(puxador.x - 2, puxador.y - 1, 7, 2);
      }
      [0xe9c46a, 0xd4a373].forEach((c, i) => caixaIso(g, x0 + 0.08, y0 + 0.1, x0 + 0.4, y0 + 0.45, 72 + i * 3, 75 + i * 3, c, false));
    },
  },
};
