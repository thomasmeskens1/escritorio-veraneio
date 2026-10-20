// Estações de trabalho: o agente fica no fundo do tile e o móvel à frente dele.
// `atras` é desenhado antes do agente (cadeira); `frente` depois (mesa e objetos).

const AGENTE_NO_TILE = 0.3; // posição do agente dentro do tile (0..1)

function mesaPadrao(g, x, y, cor, alturaTampo = 22) {
  return desenharMesa(g, x + 0.4, y + 0.4, x + 0.98, y + 0.98, alturaTampo, cor);
}

function cadeiraAtras(cor) {
  return (g, x, y) => {
    const cx = x + AGENTE_NO_TILE - 0.12, cy = y + AGENTE_NO_TILE - 0.12;
    caixaIso(g, cx - 0.2, cy - 0.06, cx + 0.12, cy + 0.02, 12, 44, tomCor(cor, 0.85));
  };
}

function desenharCaneca(g, x, y, z, cor = 0xf8f9fa) {
  caixaIso(g, x, y, x + 0.07, y + 0.07, z, z + 6, cor, false);
}

function desenharNotebook(g, x, y, z) {
  caixaIso(g, x, y, x + 0.22, y + 0.16, z, z + 1.5, 0xadb5bd, false);
  const tela = [pIso(x, y + 0.16, z + 1.5), pIso(x + 0.22, y + 0.16, z + 1.5),
    pIso(x + 0.22, y + 0.2, z + 14), pIso(x, y + 0.2, z + 14)];
  g.fillStyle(0xced4da);
  g.fillPoints(tela, true);
  g.fillStyle(0xf8f9fa, 0.9);
  const meio = pIso(x + 0.11, y + 0.18, 8 + z);
  g.fillCircle(meio.x, meio.y, 1.5);
}

function pilhaLivros(g, x, y, z, cores) {
  cores.forEach((cor, i) => caixaIso(g, x, y, x + 0.18, y + 0.12, z + i * 3, z + i * 3 + 3, cor, false));
}

const ESTACOES = {
  mesa: {
    atras: cadeiraAtras(0x495057),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xb08968);
      desenharNotebook(g, x + 0.6, y + 0.5, z);
      desenharCaneca(g, x + 0.5, y + 0.8, z);
    },
  },

  design: {
    atras: cadeiraAtras(0x7b2cbf),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xf1f3f5);
      desenharMonitor(g, x + 0.62, x + 0.96, y + 0.5, z, 0xfff1e6, (gg, x0, x1, ty, z0, z1) => {
        [0xe76f51, 0x2a9d8f, 0xe9c46a].forEach((cor, i) => {
          const a = x0 + (x1 - x0) * (0.05 + i * 0.32);
          gg.fillStyle(cor);
          gg.fillPoints([pIso(a, ty, z0 + 2), pIso(a + 0.07, ty, z0 + 2), pIso(a + 0.07, ty, z1 - 2 - i * 3), pIso(a, ty, z1 - 2 - i * 3)], true);
        });
      });
      caixaIso(g, x + 0.48, y + 0.72, x + 0.74, y + 0.92, z, z + 1.5, 0x343a40, false);
      caixaIso(g, x + 0.82, y + 0.78, x + 0.85, y + 0.92, z + 1.5, z + 3, 0xe9ecef, false);
    },
  },

  video: {
    atras: cadeiraAtras(0x212529),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0x343a40);
      desenharMonitor(g, x + 0.58, x + 0.96, y + 0.5, z, 0x111317, (gg, x0, x1, ty, z0, z1) => {
        [0xe76f51, 0x4dabf7, 0xe9c46a].forEach((cor, i) => {
          const zz = z0 + 2 + i * 4;
          gg.fillStyle(cor);
          gg.fillPoints([pIso(x0 + i * 0.05, ty, zz + 2.5), pIso(x1 - 0.1 + i * 0.03, ty, zz + 2.5), pIso(x1 - 0.1 + i * 0.03, ty, zz), pIso(x0 + i * 0.05, ty, zz)], true);
        });
      });
      caixaIso(g, x + 0.5, y + 0.75, x + 0.7, y + 0.9, z, z + 2, 0x212529, false);
      caixaIso(g, x + 0.5, y + 0.75, x + 0.7, y + 0.78, z + 2, z + 6, 0xf8f9fa, false);
    },
  },

  graficos: {
    atras: cadeiraAtras(0x2a9d8f),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xdee2e6);
      desenharMonitor(g, x + 0.44, x + 0.7, y + 0.5, z, 0x1b2a3a, barrasTela([0x2a9d8f, 0xe9c46a, 0x2a9d8f, 0xf4a261]));
      desenharMonitor(g, x + 0.72, x + 0.98, y + 0.5, z, 0x1b2a3a, linhasTela(0x8ecae6));
      desenharCaneca(g, x + 0.5, y + 0.82, z, 0xe76f51);
    },
  },

  executiva: {
    atras: (g, x, y) => {
      const c = x + AGENTE_NO_TILE - 0.08, d = y + AGENTE_NO_TILE - 0.08;
      caixaIso(g, c - 0.18, d - 0.16, c + 0.16, d - 0.08, 12, 54, 0x3d2b1f);
      quadChao(g, c - 0.18, d - 0.16, c + 0.16, d - 0.08, 0xd4af37, 1, 54);
    },
    frente(g, x, y) {
      const z = desenharMesa(g, x + 0.35, y + 0.4, x + 1, y + 1, 24, 0x5c3d2e, 0x1b1b1b);
      caixaIso(g, x + 0.35, y + 0.4, x + 1, y + 1, 0, z - 3, 0x4a3426);
      quadChao(g, x + 0.35, y + 0.95, x + 1, y + 1, 0xd4af37, 1, z);
      desenharNotebook(g, x + 0.62, y + 0.48, z);
      caixaIso(g, x + 0.45, y + 0.82, x + 0.65, y + 0.88, z, z + 4, 0xd4af37, false);
      pilhaLivros(g, x + 0.8, y + 0.78, z, [0x1d3557, 0x9d0208]);
    },
  },

  bancada: {
    frente(g, x, y) {
      pernasMesa(g, x + 0.3, y + 0.42, x + 1, y + 1, 26, 0x495057);
      caixaIso(g, x + 0.3, y + 0.42, x + 1, y + 1, 4, 8, 0x495057);
      caixaIso(g, x + 0.28, y + 0.4, x + 1.02, y + 1.02, 26, 31, 0xa0703c);
      const z = 31;
      caixaIso(g, x + 0.4, y + 0.85, x + 0.58, y + 0.95, z, z + 8, 0x1971c2, false);
      caixaIso(g, x + 0.62, y + 0.55, x + 0.92, y + 0.6, z, z + 2, 0x8b5e34, false);
      caixaIso(g, x + 0.86, y + 0.5, x + 0.96, y + 0.66, z, z + 4, 0xadb5bd, false);
      const p = pIso(x + 0.72, y + 0.82, z);
      g.lineStyle(2, 0x868e96);
      g.strokeCircle(p.x, p.y - 4, 4);
      g.fillStyle(0xffc300);
      g.fillCircle(p.x + 9, p.y - 2, 2.5);
    },
  },

  central: {
    atras: cadeiraAtras(0x1d3557),
    frente(g, x, y) {
      const z = desenharMesa(g, x + 0.3, y + 0.42, x + 1.02, y + 1, 22, 0x6c757d, 0x212529);
      desenharMonitor(g, x + 0.74, x + 1.0, y + 0.46, z, 0x0b1d14, linhasTela(0x69db7c));
      caixaIso(g, x + 0.82, y + 0.7, x + 0.96, y + 0.86, z, z + 5, 0xdee2e6, false);
      caixaIso(g, x + 0.85, y + 0.86, x + 0.93, y + 0.9, z + 1, z + 9, 0xf8f9fa, false);
      caixaIso(g, x + 0.45, y + 0.82, x + 0.7, y + 0.92, z, z + 1.5, 0x212529, false);
    },
  },

  balcao: {
    frente(g, x, y) {
      caixaIso(g, x + 0.3, y + 0.45, x + 1, y + 1, 0, 34, 0x2a9d8f);
      caixaIso(g, x + 0.26, y + 0.41, x + 1.04, y + 1.04, 34, 38, 0xf1f3f5);
      desenharMonitor(g, x + 0.78, x + 1.0, y + 0.62, 38, 0x1b2a3a, linhasTela(0x8ecae6));
      const p = pIso(x + 0.5, y + 0.85, 38);
      g.fillStyle(0xd4af37);
      g.fillEllipse(p.x, p.y - 3, 9, 7);
      g.fillRect(p.x - 6, p.y, 12, 2);
    },
  },

  pulpito: {
    frente(g, x, y) {
      caixaIso(g, x + 0.42, y + 0.42, x + 0.78, y + 0.78, 0, 32, 0x8b5e34);
      caixaIso(g, x + 0.36, y + 0.36, x + 0.84, y + 0.84, 32, 36, 0xa0703c);
      caixaIso(g, x + 0.46, y + 0.5, x + 0.74, y + 0.7, 36, 38, 0xf8f9fa, false);
      caixaIso(g, x + 0.46, y + 0.5, x + 0.74, y + 0.52, 36, 38.5, 0xc92a2a, false);
    },
  },
};
