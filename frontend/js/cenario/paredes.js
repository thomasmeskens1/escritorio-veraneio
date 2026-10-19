// Paredes de trás (lado 'esq' em x = 0 e 'dir' em y = 0) e o que fica pendurado nelas.

// Base das duas paredes com acabamento: 'blocos' | 'lambri' | 'painel' | 'liso'.
function desenharParedes(g, { cor, acabamento, rodape = 0x2b2d31 }) {
  ['esq', 'dir'].forEach((lado) => {
    const base = lado === 'esq' ? tomCor(cor, 0.82) : cor;
    quadParede(g, lado, 0, GRADE, 0, ALTURA_PAREDE, base);

    if (acabamento === 'blocos') {
      for (let z = 14, linha = 0; z < ALTURA_PAREDE; z += 14, linha++) {
        linhaParede(g, lado, 0, z, GRADE, z, 1, 0x000000, 0.18);
        for (let t = linha % 2 ? 0.5 : 0; t < GRADE; t += 1) {
          linhaParede(g, lado, t, z - 14, t, z, 1, 0x000000, 0.12);
        }
      }
    } else if (acabamento === 'lambri') {
      quadParede(g, lado, 0, GRADE, 0, 38, tomCor(base, 0.78));
      for (let t = 0.25; t < GRADE; t += 0.5) linhaParede(g, lado, t, 4, t, 36, 1, 0x000000, 0.15);
      linhaParede(g, lado, 0, 38, GRADE, 38, 3, tomCor(base, 1.25));
    } else if (acabamento === 'painel') {
      for (let t = 0; t < GRADE; t += 1) {
        quadParede(g, lado, t + 0.08, t + 0.92, 10, ALTURA_PAREDE - 10, tomCor(base, 1.08));
      }
    }

    quadParede(g, lado, 0, GRADE, 0, 6, rodape);
    // Topo da parede (espessura) para dar acabamento.
    const fora = lado === 'esq' ? [pIso(-0.12, 0, ALTURA_PAREDE), pIso(-0.12, GRADE, ALTURA_PAREDE)]
      : [pIso(0, -0.12, ALTURA_PAREDE), pIso(GRADE, -0.12, ALTURA_PAREDE)];
    g.fillStyle(tomCor(cor, 1.25));
    g.fillPoints([pParede(lado, 0, ALTURA_PAREDE), pParede(lado, GRADE, ALTURA_PAREDE), fora[1], fora[0]], true);
  });
  // Quina do fundo.
  const a = pIso(0, 0, 0);
  g.lineStyle(1, 0x000000, 0.3);
  g.lineBetween(a.x, a.y, a.x, a.y - ALTURA_PAREDE);
}

// Círculo "colado" na parede (vira elipse inclinada).
function discoParede(g, lado, tc, zc, raio, cor, alfa = 1) {
  const pontos = [];
  for (let i = 0; i < 20; i++) {
    const a = (i / 20) * Math.PI * 2;
    pontos.push(pParede(lado, tc + (Math.cos(a) * raio) / PX_POR_T, zc + Math.sin(a) * raio));
  }
  g.fillStyle(cor, alfa);
  g.fillPoints(pontos, true);
}

function molduraParede(g, lado, t0, t1, z0, z1, cor, borda = 3) {
  quadParede(g, lado, t0, t1, z0, z1, cor);
  return { t0: t0 + borda / PX_POR_T, t1: t1 - borda / PX_POR_T, z0: z0 + borda, z1: z1 - borda };
}

const ELEMENTOS_PAREDE = {
  janela(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, e.moldura || 0xdee2e6, 4);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, e.ceu || 0x8ecae6);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, (m.z0 + m.z1) / 2, 0xffffff, 0.12);
    if (e.skyline) {
      const rand = sementeAleatoria(hashTexto(`${e.lado}${e.t0}`));
      for (let t = m.t0; t < m.t1 - 0.05; t += 0.14 + rand() * 0.12) {
        const larg = Math.min(0.12 + rand() * 0.12, m.t1 - t);
        const alt = m.z0 + 8 + rand() * (m.z1 - m.z0) * 0.6;
        quadParede(g, e.lado, t, t + larg, m.z0, alt, 0x14182b);
        for (let z = m.z0 + 5; z < alt - 4; z += 6) {
          if (rand() < 0.45) quadParede(g, e.lado, t + 0.03, t + 0.06, z, z + 2.5, 0xffd166, 0.85);
        }
      }
    }
    const divisoes = Math.max(1, Math.round((e.t1 - e.t0) / 0.9));
    for (let i = 1; i < divisoes; i++) {
      const t = e.t0 + ((e.t1 - e.t0) * i) / divisoes;
      linhaParede(g, e.lado, t, e.z0, t, e.z1, 3, e.moldura || 0xdee2e6);
    }
    if (!e.skyline) linhaParede(g, e.lado, e.t0, (e.z0 + e.z1) / 2, e.t1, (e.z0 + e.z1) / 2, 2, e.moldura || 0xdee2e6);
  },

  quadro(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, e.moldura || 0x3d2b1f, 3);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, e.fundo || 0xf8f9fa);
    const cores = e.cores || [0xe76f51, 0x2a9d8f, 0xe9c46a];
    const larg = m.t1 - m.t0;
    quadParede(g, e.lado, m.t0 + larg * 0.1, m.t0 + larg * 0.55, m.z0 + 4, m.z1 - 8, cores[0]);
    discoParede(g, e.lado, m.t0 + larg * 0.68, (m.z0 + m.z1) / 2 + 3, Math.min(8, (m.z1 - m.z0) / 4), cores[1]);
    quadParede(g, e.lado, m.t0 + larg * 0.45, m.t1 - larg * 0.08, m.z0 + 3, m.z0 + 9, cores[2]);
  },

  lousa(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0x8b5e34, 4);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, 0x2f5d50);
    const larg = m.t1 - m.t0;
    [[0.08, 0.5, 10], [0.08, 0.38, 18], [0.08, 0.62, 26], [0.55, 0.9, 14], [0.55, 0.82, 22]].forEach(([a, b, dz]) => {
      linhaParede(g, e.lado, m.t0 + larg * a, m.z1 - dz, m.t0 + larg * b, m.z1 - dz, 1.5, 0xf1f3f5, 0.75);
    });
    discoParede(g, e.lado, m.t0 + larg * 0.25, m.z0 + 12, 7, 0xf1f3f5, 0.6);
    discoParede(g, e.lado, m.t0 + larg * 0.25, m.z0 + 12, 5.5, 0x2f5d50);
    linhaParede(g, e.lado, m.t0 + larg * 0.55, m.z0 + 6, m.t0 + larg * 0.85, m.z0 + 18, 1.5, 0xffd166, 0.8);
    caixaParede(g, e.lado, e.t0 + 0.05, e.t1 - 0.05, 0.12, e.z0 - 3, e.z0, 0x8b5e34, false);
  },

  moodboard(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0x6c584c, 3);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, 0xc9a77c);
    const rand = sementeAleatoria(7);
    const cores = [0xe76f51, 0xf4a261, 0xe9c46a, 0x2a9d8f, 0x8ecae6, 0xffafcc, 0xf8f9fa, 0x7b2cbf];
    for (let i = 0; i < 11; i++) {
      const t = m.t0 + rand() * (m.t1 - m.t0 - 0.3);
      const z = m.z0 + 3 + rand() * (m.z1 - m.z0 - 18);
      quadParede(g, e.lado, t, t + 0.18 + rand() * 0.12, z, z + 10 + rand() * 6, cores[i % cores.length]);
      discoParede(g, e.lado, t + 0.08, z + 13, 1.6, 0xc92a2a);
    }
  },

  prateleira(g, e) {
    caixaParede(g, e.lado, e.t0, e.t1, 0.22, e.z - 3, e.z, e.cor || 0x8b5e34);
    const rand = sementeAleatoria(hashTexto(`${e.lado}${e.t0}${e.z}`));
    const cores = e.itens || [0xe76f51, 0x2a9d8f, 0xe9c46a, 0x457b9d, 0xf1f3f5];
    for (let t = e.t0 + 0.08; t < e.t1 - 0.12; t += 0.13 + rand() * 0.08) {
      const alt = 10 + rand() * 9;
      caixaParede(g, e.lado, t, t + 0.09, 0.16, e.z, e.z + alt, cores[Math.floor(rand() * cores.length)], false);
    }
  },

  tv(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0x111317, 3);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, 0x1b2a3a);
    const larg = m.t1 - m.t0;
    const barras = [0.4, 0.65, 0.5, 0.85, 0.7];
    barras.forEach((h, i) => {
      const t = m.t0 + larg * (0.06 + i * 0.09);
      quadParede(g, e.lado, t, t + larg * 0.06, m.z0 + 3, m.z0 + 3 + h * (m.z1 - m.z0 - 8), [0x2a9d8f, 0xe9c46a][i % 2]);
    });
    const pts = [0.3, 0.5, 0.4, 0.75, 0.6, 0.9];
    for (let i = 1; i < pts.length; i++) {
      const ta = m.t0 + larg * (0.55 + (i - 1) * 0.08);
      const tb = m.t0 + larg * (0.55 + i * 0.08);
      const alt = m.z1 - m.z0 - 6;
      linhaParede(g, e.lado, ta, m.z0 + 3 + pts[i - 1] * alt, tb, m.z0 + 3 + pts[i] * alt, 2, 0xf4a261);
    }
  },

  canos(g, e) {
    (e.alturas || [ALTURA_PAREDE - 18, ALTURA_PAREDE - 28]).forEach((z, i) => {
      const cor = i % 2 ? 0xb07d4f : 0x8d99ae;
      linhaParede(g, e.lado, 0, z, GRADE, z, 6, tomCor(cor, 0.7));
      linhaParede(g, e.lado, 0, z + 1, GRADE, z + 1, 4, cor);
      for (let t = 0.7 + i * 0.4; t < GRADE; t += 1.6) linhaParede(g, e.lado, t, z - 4, t, z + 4, 4, tomCor(cor, 0.6));
    });
    if (e.descida !== undefined) {
      linhaParede(g, e.lado, e.descida, 0, e.descida, ALTURA_PAREDE - 18, 6, 0x6c757d);
      discoParede(g, e.lado, e.descida, 46, 6, 0xc92a2a);
      discoParede(g, e.lado, e.descida, 46, 2.5, 0x6c757d);
    }
  },

  painel(g, e) {
    caixaParede(g, e.lado, e.t0, e.t1, 0.1, e.z0, e.z1, 0x868e96);
    const meio = (e.t0 + e.t1) / 2;
    const p = (dt, dz) => pParede(e.lado, meio + dt, e.z1 - dz, 0.1);
    g.fillStyle(0xffd43b);
    g.fillPoints([p(0, 6), p(0.12, 20), p(-0.12, 20)], true);
    g.fillStyle(0x212529);
    g.fillPoints([p(0, 10), p(0.03, 16), p(-0.03, 16)], true);
  },

  ferramentas(g, e) {
    quadParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0x6b5844);
    for (let t = e.t0 + 0.1; t < e.t1; t += 0.15) {
      for (let z = e.z0 + 5; z < e.z1; z += 7) discoParede(g, e.lado, t, z, 0.9, 0x000000, 0.35);
    }
    const larg = e.t1 - e.t0;
    const ferramenta = (a, z, comp, cor, cabeca) => {
      const t = e.t0 + larg * a;
      linhaParede(g, e.lado, t, z - comp, t, z, 3, cor);
      if (cabeca) linhaParede(g, e.lado, t - 0.08, z, t + 0.08, z, 5, 0xadb5bd);
    };
    ferramenta(0.15, e.z1 - 8, 22, 0x8b5e34, true);
    ferramenta(0.32, e.z1 - 6, 26, 0xc92a2a);
    ferramenta(0.5, e.z1 - 8, 20, 0xffc300, true);
    ferramenta(0.68, e.z1 - 6, 24, 0x1971c2);
    discoParede(g, e.lado, e.t0 + larg * 0.85, e.z1 - 16, 8, 0x495057);
    discoParede(g, e.lado, e.t0 + larg * 0.85, e.z1 - 16, 4, 0x6b5844);
  },

  relogio(g, e) {
    discoParede(g, e.lado, e.t, e.z, 10, 0x343a40);
    discoParede(g, e.lado, e.t, e.z, 8.5, 0xf8f9fa);
    linhaParede(g, e.lado, e.t, e.z, e.t, e.z + 6, 1.5, 0x212529);
    linhaParede(g, e.lado, e.t, e.z, e.t + 4 / PX_POR_T, e.z, 1.5, 0x212529);
  },

  // Luminária de parede com halo de luz.
  arandela(g, e) {
    const { lado, t, z } = e;
    const p = (dt, dz, af = 0) => pParede(lado, t + dt, z + dz, af);
    g.fillStyle(0xffd166, 0.07);
    g.fillPoints([p(-0.18, -2, 0.02), p(0.18, -2, 0.02), p(0.6, -60, 0.02), p(-0.6, -60, 0.02)], true);
    discoParede(g, lado, t, z - 4, 12, 0xffd166, 0.12);
    linhaParede(g, lado, t, z + 10, t, z + 2, 2, 0x343a40);
    g.fillStyle(0x343a40);
    g.fillPoints([p(-0.05, 2), p(0.05, 2), p(0.2, -6), p(-0.2, -6)], true);
    g.fillStyle(0xffe8a3);
    g.fillPoints([p(-0.16, -6), p(0.16, -6), p(0.1, -9), p(-0.1, -9)], true);
  },

  elevador(g, e, ctx) {
    const { lado, t0, t1 } = e;
    const meio = (t0 + t1) / 2;
    molduraParede(g, lado, t0 - 0.12, t1 + 0.12, 0, 82, e.moldura || 0x868e96, 0);
    quadParede(g, lado, t0, meio - 0.01, 0, 76, 0xadb5bd);
    quadParede(g, lado, meio + 0.01, t1, 0, 76, 0xced4da);
    quadParede(g, lado, t0, t1, 52, 76, 0xffffff, 0.12);
    linhaParede(g, lado, meio, 0, meio, 76, 1.5, 0x495057);
    quadParede(g, lado, meio - 0.3, meio + 0.3, 86, 100, 0x111317);
    const p = pParede(lado, meio, 93);
    ctx.extras.push(ctx.cena.add.text(p.x, p.y, e.letra || '', {
      fontFamily: 'monospace', fontSize: '10px', color: '#ff6b6b',
    }).setOrigin(0.5).setDepth(PROF_PAREDE + 1));
    discoParede(g, lado, t1 + 0.28, 40, 3, 0x343a40);
    discoParede(g, lado, t1 + 0.28, 40, 1.6, 0xffd166);
  },

};

// Desenha todos os elementos de parede de um andar num único Graphics estático.
function desenharElementosParede(g, elementos, ctx) {
  elementos.forEach((e) => ELEMENTOS_PAREDE[e.tipo]?.(g, e, ctx));
}
