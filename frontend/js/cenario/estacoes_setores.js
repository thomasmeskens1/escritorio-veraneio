// Estações das novas funções do Marketing, mesas vagas dos setores e móveis extras.

// Mesa sem ninguém: cadeira afastada e tampo vazio (só um porta-lápis).
function mesaVaga(corMesa, corCadeira, corPernas) {
  return {
    atras: cadeiraAtras(corCadeira),
    frente(g, x, y) {
      const z = desenharMesa(g, x + 0.4, y + 0.4, x + 0.98, y + 0.98, 22, corMesa, corPernas);
      caixaIso(g, x + 0.82, y + 0.52, x + 0.9, y + 0.6, z, z + 6, tomCor(corMesa, 0.7), false);
    },
  };
}

Object.assign(ESTACOES, {
  // Criador de Imagens: mesa digitalizadora e tela com ilustração.
  ilustracao: {
    atras: cadeiraAtras(0xffb703),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xf8f9fa);
      desenharMonitor(g, x + 0.6, x + 0.96, y + 0.48, z, 0x8ecae6, (gg, x0, x1, ty, z0, z1) => {
        const sol = pIso((x0 + x1) / 2 + 0.06, ty, z1 - 4);
        gg.fillStyle(0xffd166);
        gg.fillCircle(sol.x, sol.y, 3);
        gg.fillStyle(0x2a9d8f);
        gg.fillPoints([pIso(x0, ty, z0), pIso(x1, ty, z0), pIso(x1 - 0.06, ty, z0 + 7), pIso(x0 + 0.1, ty, z0 + 9)], true);
      });
      caixaIso(g, x + 0.46, y + 0.7, x + 0.76, y + 0.92, z, z + 1.5, 0x212529, false);
      quadChao(g, x + 0.49, y + 0.73, x + 0.73, y + 0.89, 0x495057, 1, z + 1.5);
      caixaIso(g, x + 0.8, y + 0.74, x + 0.82, y + 0.92, z + 1.5, z + 3, 0xe76f51, false);
    },
  },

  // Copywriter: notebook, folhas rascunhadas e café.
  redacao: {
    atras: cadeiraAtras(0x6d6875),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xd4a373);
      desenharNotebook(g, x + 0.66, y + 0.48, z);
      [0, 1, 2].forEach((i) => caixaIso(g, x + 0.46, y + 0.7 + i * 0.01, x + 0.66, y + 0.92, z + i, z + i + 1, 0xf8f9fa, false));
      g.lineStyle(1, 0x868e96, 0.8);
      [0.76, 0.81, 0.86].forEach((ly) => {
        const a = pIso(x + 0.49, y + ly, z + 3), b = pIso(x + 0.62, y + ly, z + 3);
        g.lineBetween(a.x, a.y, b.x, b.y);
      });
      desenharCaneca(g, x + 0.82, y + 0.82, z, 0xe5989b);
    },
  },

  // Social Media: celular no suporte, ring light e tela com curtidas.
  social: {
    atras: cadeiraAtras(0xff006e),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xf1f3f5);
      desenharMonitor(g, x + 0.62, x + 0.96, y + 0.5, z, 0x3a0ca3, (gg, x0, x1, ty, z0, z1) => {
        [0, 1, 2].forEach((i) => {
          const p = pIso(x0 + 0.04 + i * 0.09, ty, z0 + 3 + ((i * 5) % 9));
          gg.fillStyle(i % 2 ? 0xffafcc : 0xff006e);
          gg.fillCircle(p.x - 1.5, p.y, 2);
          gg.fillCircle(p.x + 1.5, p.y, 2);
          gg.fillTriangle(p.x - 3.4, p.y + 0.6, p.x + 3.4, p.y + 0.6, p.x, p.y + 4);
        });
      });
      caixaIso(g, x + 0.5, y + 0.78, x + 0.56, y + 0.84, z, z + 4, 0x343a40, false);
      caixaIso(g, x + 0.47, y + 0.8, x + 0.59, y + 0.82, z + 4, z + 18, 0x111317, false);
      const anel = pIso(x + 0.5, y + 0.62, z + 30);
      caixaIso(g, x + 0.49, y + 0.61, x + 0.51, y + 0.63, z, z + 22, 0x343a40, false);
      g.lineStyle(3, 0xfff3bf, 0.95);
      g.strokeEllipse(anel.x, anel.y, 16, 16);
    },
  },

  // Editor de Vídeo: dois monitores com linha do tempo e mesa de corte.
  edicao: {
    atras: cadeiraAtras(0x264653),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0x343a40);
      const trilhas = (gg, x0, x1, ty, z0) => {
        [0xe76f51, 0x4dabf7, 0x69db7c, 0xe9c46a].forEach((cor, i) => {
          const a = x0 + ((i * 7) % 4) * 0.02, b = x1 - ((i * 5) % 3) * 0.03;
          gg.fillStyle(cor);
          gg.fillPoints([pIso(a, ty, z0 + 2 + i * 3), pIso(b, ty, z0 + 2 + i * 3), pIso(b, ty, z0 + 4 + i * 3), pIso(a, ty, z0 + 4 + i * 3)], true);
        });
      };
      desenharMonitor(g, x + 0.42, x + 0.69, y + 0.5, z, 0x111317, trilhas);
      desenharMonitor(g, x + 0.71, x + 0.98, y + 0.5, z, 0x1b2a3a, linhasTela(0x4dabf7));
      caixaIso(g, x + 0.5, y + 0.76, x + 0.78, y + 0.9, z, z + 2, 0x212529, false);
      const p = pIso(x + 0.86, y + 0.84, z + 2);
      g.fillStyle(0x495057);
      g.fillEllipse(p.x, p.y, 10, 5);
    },
  },

  // Analista de Métricas: painel com pizza e linha de tendência.
  metricas: {
    atras: cadeiraAtras(0x90be6d),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xe9ecef);
      desenharMonitor(g, x + 0.56, x + 0.98, y + 0.5, z, 0x22333b, (gg, x0, x1, ty, z0, z1) => {
        const c = pIso(x0 + 0.08, ty, (z0 + z1) / 2);
        gg.fillStyle(0x90be6d);
        gg.slice(c.x, c.y, 5, 0, Math.PI * 1.3, false);
        gg.fillPath();
        gg.fillStyle(0xf9c74f);
        gg.slice(c.x, c.y, 5, Math.PI * 1.3, Math.PI * 2, false);
        gg.fillPath();
        linhasTela(0x8ecae6)(gg, x0 + 0.17, x1, ty, z0, z1);
      });
      caixaIso(g, x + 0.46, y + 0.74, x + 0.66, y + 0.92, z, z + 1, 0xf8f9fa, false);
      desenharCaneca(g, x + 0.78, y + 0.82, z, 0x90be6d);
    },
  },

  vaga: mesaVaga(0xb08968, 0x6c757d),
  vagaExecutiva: {
    atras: ESTACOES.executiva.atras,
    frente(g, x, y) {
      const z = desenharMesa(g, x + 0.35, y + 0.4, x + 1, y + 1, 24, 0x5c3d2e, 0x1b1b1b);
      caixaIso(g, x + 0.35, y + 0.4, x + 1, y + 1, 0, z - 3, 0x4a3426);
      quadChao(g, x + 0.35, y + 0.95, x + 1, y + 1, 0xd4af37, 1, z);
      caixaIso(g, x + 0.78, y + 0.5, x + 0.92, y + 0.6, z, z + 4, 0xd4af37, false);
    },
  },
  vagaOficina: mesaVaga(0xa0703c, 0x495057, 0x495057),
  vagaOperacoes: {
    atras: cadeiraAtras(0x1d3557),
    frente(g, x, y) {
      const z = desenharMesa(g, x + 0.3, y + 0.42, x + 1.02, y + 1, 22, 0x6c757d, 0x212529);
      desenharMonitor(g, x + 0.74, x + 1.0, y + 0.46, z, 0x0b0d10); // desligado
    },
  },
});

Object.assign(MOVEIS, {
  // Bebedouro com galão (copa).
  bebedouro: {
    w: 1, d: 1,
    desenhar(g, { x, y }) {
      const cx = x + 0.5, cy = y + 0.5;
      caixaIso(g, cx - 0.2, cy - 0.2, cx + 0.2, cy + 0.2, 0, 40, 0xf1f3f5);
      caixaIso(g, cx + 0.2, cy - 0.06, cx + 0.23, cy + 0.06, 24, 28, 0x4dabf7, false);
      const p = pIso(cx, cy, 40);
      g.fillStyle(0x74c0fc, 0.75);
      g.fillRoundedRect(p.x - 9, p.y - 26, 18, 26, 6);
      g.fillStyle(0xffffff, 0.35);
      g.fillRect(p.x - 6, p.y - 22, 3, 18);
      g.fillStyle(0x1971c2);
      g.fillRect(p.x - 4, p.y - 30, 8, 4);
    },
  },
});
