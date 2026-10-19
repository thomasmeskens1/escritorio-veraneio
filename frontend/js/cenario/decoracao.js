// Decoração exclusiva de cada andar: piso, paredes, elementos de parede e móveis.

const CENARIOS = {
  // Infraestrutura: oficina do Construtor e central de operações.
  porao: {
    chao: { estilo: 'concreto', cor: 0x5f646b },
    parede: { cor: 0x4a4f57, acabamento: 'blocos' },
    paredes: [
      { tipo: 'canos', lado: 'esq', descida: 6.7 },
      { tipo: 'canos', lado: 'dir', alturas: [ALTURA_PAREDE - 22] },
      { tipo: 'ferramentas', lado: 'esq', t0: 1.4, t1: 3.4, z0: 36, z1: 80 },
      { tipo: 'painel', lado: 'dir', t0: 0.5, t1: 1.3, z0: 42, z1: 82 },
      { tipo: 'tv', lado: 'dir', t0: 3.2, t1: 5.2, z0: 46, z1: 84 },
      { tipo: 'arandela', lado: 'esq', t: 0.9, z: 84 },
      { tipo: 'arandela', lado: 'dir', t: 2.3, z: 84 },
      { tipo: 'elevador', lado: 'dir', t0: 6.2, t1: 7.4, letra: 'P' },
    ],
    moveis: [
      { tipo: 'tapete', x: 6.2, y: 0.12, w: 1.2, d: 0.5, cores: [0x212529, 0xffc300, 0x212529, 0xffc300, 0x212529, 0xffc300] },
      { tipo: 'rack', x: 0, y: 4 },
      { tipo: 'rack', x: 0, y: 5 },
      { tipo: 'rack', x: 0, y: 6 },
      { tipo: 'caixas', x: 1, y: 0 },
      { tipo: 'caixas', x: 2, y: 0, pilha: 1 },
      { tipo: 'caixas', x: 7, y: 6 },
      { tipo: 'tambores', x: 5, y: 7 },
      { tipo: 'prototipo', x: 3, y: 4 },
    ],
  },

  // Escola do escritório e o arquivo da Diretora.
  terreo: {
    chao: { estilo: 'madeira', cor: 0xc8a27a },
    parede: { cor: 0xcfc3a8, acabamento: 'lambri' },
    paredes: [
      { tipo: 'lousa', lado: 'esq', t0: 1.1, t1: 3.9, z0: 44, z1: 96 },
      { tipo: 'relogio', lado: 'esq', t: 4.6, z: 92 },
      { tipo: 'quadro', lado: 'esq', t0: 5.2, t1: 6.6, z0: 48, z1: 84, cores: [0x457b9d, 0xe9c46a, 0xe76f51] },
      { tipo: 'janela', lado: 'dir', t0: 0.7, t1: 2.3, z0: 44, z1: 102 },
      { tipo: 'janela', lado: 'dir', t0: 2.8, t1: 4.4, z0: 44, z1: 102 },
      { tipo: 'prateleira', lado: 'dir', t0: 4.8, t1: 5.9, z: 72 },
      { tipo: 'elevador', lado: 'dir', t0: 6.2, t1: 7.4, letra: 'T' },
    ],
    moveis: [
      { tipo: 'tapete', x: 2.6, y: 0.8, w: 3.2, d: 3.6, cores: [0x8ecae6, 0xa8dadc] },
      { tipo: 'tapete', x: 6.25, y: 0.15, w: 1.1, d: 0.8, cores: [0x9d0208, 0xc92a2a], texto: 'BEM-VINDO' },
      { tipo: 'planta', x: 0, y: 0, alta: true },
      // Canto do arquivo (Diretora): arquivos de aço ao redor da estante.
      { tipo: 'arquivo', x: 0, y: 4 },
      { tipo: 'estante', x: 0, y: 5 },
      { tipo: 'arquivo', x: 0, y: 7 },
      { tipo: 'planta', x: 7, y: 5 },
      { tipo: 'carteira', x: 3, y: 1 },
      { tipo: 'carteira', x: 3, y: 3 },
      { tipo: 'carteira', x: 5, y: 1 },
      { tipo: 'carteira', x: 5, y: 3 },
    ],
  },

  // Agência criativa.
  marketing: {
    chao: { estilo: 'madeira', cor: 0x7f6a55 },
    parede: { cor: 0x2f4858, acabamento: 'liso' },
    paredes: [
      { tipo: 'moodboard', lado: 'esq', t0: 0.6, t1: 3.0, z0: 42, z1: 96 },
      { tipo: 'janela', lado: 'esq', t0: 3.6, t1: 5.2, z0: 42, z1: 102 },
      { tipo: 'quadro', lado: 'esq', t0: 5.8, t1: 7.0, z0: 50, z1: 86, fundo: 0xfff1e6, cores: [0xe76f51, 0x7b2cbf, 0xe9c46a] },
      { tipo: 'prateleira', lado: 'dir', t0: 0.6, t1: 2.0, z: 74, itens: [0xd4af37, 0xe9c46a, 0xf8f9fa] },
      { tipo: 'tv', lado: 'dir', t0: 2.6, t1: 4.6, z0: 44, z1: 88 },
      { tipo: 'relogio', lado: 'dir', t: 5.4, z: 92 },
      { tipo: 'elevador', lado: 'dir', t0: 6.2, t1: 7.4, letra: '1' },
    ],
    moveis: [
      { tipo: 'tapete', x: 2.4, y: 2.6, w: 2.4, d: 2.4, cores: [0x264653, 0xe76f51, 0xf4a261, 0xe9c46a, 0x2a9d8f] },
      { tipo: 'planta', x: 0, y: 0, alta: true },
      { tipo: 'cafeteira', x: 5, y: 0 },
      { tipo: 'planta', x: 7, y: 2 },
      { tipo: 'tripe', x: 1, y: 4 },
      { tipo: 'sofa', x: 4, y: 6, cor: 0x6d597a },
      { tipo: 'planta', x: 0, y: 7 },
    ],
  },

  // Diretoria: sala executiva.
  cobertura: {
    chao: { estilo: 'marmore', cor: 0x2b2d42 },
    parede: { cor: 0x1f2235, acabamento: 'painel', rodape: 0xd4af37 },
    paredes: [
      { tipo: 'janela', lado: 'esq', t0: 0.5, t1: 4.6, z0: 26, z1: 108, skyline: true, ceu: 0x23365f, moldura: 0x2b2b2b },
      { tipo: 'quadro', lado: 'esq', t0: 5.3, t1: 6.9, z0: 66, z1: 106, moldura: 0xd4af37, fundo: 0x14182b, cores: [0xd4af37, 0x9d0208, 0xf8f9fa] },
      { tipo: 'janela', lado: 'dir', t0: 0.5, t1: 5.6, z0: 26, z1: 108, skyline: true, ceu: 0x23365f, moldura: 0x2b2b2b },
      { tipo: 'elevador', lado: 'dir', t0: 6.2, t1: 7.4, letra: 'C', moldura: 0xd4af37 },
    ],
    moveis: [
      { tipo: 'tapete', x: 1.6, y: 1.6, w: 3.8, d: 3.8, cores: [0xd4af37, 0x4a0e17] },
      { tipo: 'planta', x: 0, y: 0, alta: true },
      { tipo: 'bar', x: 0, y: 5 },
      { tipo: 'mesaReuniao', x: 2, y: 2 },
      { tipo: 'cadeirasFrente', x: 2, y: 4 },
      { tipo: 'poltrona', x: 5, y: 6, cor: 0x7f5539 },
      { tipo: 'mesinha', x: 6, y: 6 },
      { tipo: 'poltrona', x: 6, y: 5, cor: 0x7f5539 },
      { tipo: 'abajur', x: 7, y: 4 },
      { tipo: 'planta', x: 5, y: 0, alta: true },
    ],
  },
};

// ---------- Pisos ----------
const PISOS = {
  concreto(g, cor) {
    const rand = sementeAleatoria(11);
    for (let x = 0; x < GRADE; x++) {
      for (let y = 0; y < GRADE; y++) {
        quadChao(g, x, y, x + 1, y + 1, tomCor(cor, 0.94 + rand() * 0.1));
        for (let i = 0; i < 3; i++) {
          const p = pIso(x + rand(), y + rand());
          g.fillStyle(0x000000, 0.15);
          g.fillRect(p.x, p.y, 2, 1);
        }
      }
    }
    linhasGrade(g, 0.18);
  },

  madeira(g, cor) {
    const rand = sementeAleatoria(5);
    for (let y = 0; y < GRADE; y += 0.5) {
      let x = -rand() * 1.5;
      while (x < GRADE) {
        const comp = 1.5 + rand() * 1.5;
        const a = Math.max(0, x), b = Math.min(GRADE, x + comp);
        quadChao(g, a, y, b, y + 0.5, tomCor(cor, 0.9 + rand() * 0.16));
        const p0 = pIso(b, y), p1 = pIso(b, y + 0.5);
        g.lineStyle(1, 0x000000, 0.18);
        g.lineBetween(p0.x, p0.y, p1.x, p1.y);
        x += comp;
      }
      const l0 = pIso(0, y), l1 = pIso(GRADE, y);
      g.lineStyle(1, 0x000000, 0.2);
      g.lineBetween(l0.x, l0.y, l1.x, l1.y);
    }
  },

  marmore(g, cor) {
    for (let x = 0; x < GRADE; x++) {
      for (let y = 0; y < GRADE; y++) quadChao(g, x, y, x + 1, y + 1, (x + y) % 2 ? cor : tomCor(cor, 1.12));
    }
    g.lineStyle(1, 0xd4af37, 0.35);
    for (let i = 0; i <= GRADE; i += 2) {
      const a = pIso(i, 0), b = pIso(i, GRADE), c = pIso(0, i), d = pIso(GRADE, i);
      g.lineBetween(a.x, a.y, b.x, b.y);
      g.lineBetween(c.x, c.y, d.x, d.y);
    }
  },
};

function linhasGrade(g, alfa) {
  g.lineStyle(1, 0x000000, alfa);
  for (let i = 0; i <= GRADE; i++) {
    const a = pIso(i, 0), b = pIso(i, GRADE), c = pIso(0, i), d = pIso(GRADE, i);
    g.lineBetween(a.x, a.y, b.x, b.y);
    g.lineBetween(c.x, c.y, d.x, d.y);
  }
}

// Células ocupadas por um móvel (para posicionar agentes novos em células livres).
function celulasDoMovel(m) {
  const def = MOVEIS[m.tipo];
  if (!def || def.chao) return [];
  const celulas = [];
  for (let x = Math.floor(m.x); x < Math.ceil(m.x + def.w); x++) {
    for (let y = Math.floor(m.y); y < Math.ceil(m.y + def.d); y++) celulas.push(`${x},${y}`);
  }
  return celulas;
}

// Desenha o cenário do andar. `ctx` = { cena, extras, anima }. Devolve as células ocupadas.
function montarCenario(nivel, ctx) {
  const cenario = CENARIOS[nivel];
  const ocupadas = new Set();
  if (!cenario) return ocupadas;

  const base = ctx.cena.add.graphics().setDepth(0);
  caixaIso(base, 0, 0, GRADE, GRADE, -12, 0, tomCor(cenario.chao.cor, 0.7), false);
  PISOS[cenario.chao.estilo](base, cenario.chao.cor);
  ctx.extras.push(base);

  const paredes = ctx.cena.add.graphics().setDepth(PROF_PAREDE);
  desenharParedes(paredes, cenario.parede);
  desenharElementosParede(paredes, cenario.paredes, ctx);
  ctx.extras.push(paredes);

  cenario.moveis.forEach((m) => {
    const def = MOVEIS[m.tipo];
    if (!def) return;
    ctx.profundidade = def.chao ? PROF_PAREDE + 1 : profundidade(m.x + def.w, m.y + def.d);
    const g = ctx.cena.add.graphics().setDepth(ctx.profundidade);
    def.desenhar(g, m, ctx);
    ctx.extras.push(g);
    celulasDoMovel(m).forEach((c) => ocupadas.add(c));
  });
  return ocupadas;
}
