// Laboratório do Cérebro (Cobertura): pedestal, tanques, bancada, monitores de ondas
// cerebrais, quadro de fórmulas e mapa da empresa; mesas dos estagiários e canto de leitura.

const ELEVACAO_PEDESTAL = 22; // altura (px) do topo do pedestal
const CIANO = 0x66d9e8;

// Elipse "deitada" no chão (screen space), útil para peças redondas.
function pontosElipse(cx, cy, rx, ry, a0 = 0, a1 = Math.PI * 2, n = 28) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const a = a0 + ((a1 - a0) * i) / n;
    pts.push({ x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry });
  }
  return pts;
}

// Cilindro visto de cima-frente: lateral, base e tampo.
function cilindro(g, cx, cy, rx, ry, z0, z1, cor) {
  g.fillStyle(tomCor(cor, 0.7));
  g.fillPoints([...pontosElipse(cx, cy - z0, rx, ry, 0, Math.PI), ...pontosElipse(cx, cy - z1, rx, ry, Math.PI, 0)], true);
  g.fillStyle(tomCor(cor, 0.85));
  g.fillRect(cx - rx, cy - z1, rx * 0.5, z1 - z0);
  g.fillStyle(cor);
  g.fillEllipse(cx, cy - z1, rx * 2, ry * 2);
}

Object.assign(ESTACOES, {
  // Pedestal iluminado do Cérebro: o agente fica de pé sobre ele.
  pedestal: {
    atras(g, x, y) {
      const p = isoParaTela(x + AGENTE_NO_TILE, y + AGENTE_NO_TILE);
      const h = ELEVACAO_PEDESTAL;
      for (let i = 0; i < 6; i++) { // coluna de luz atrás do Cérebro
        g.fillStyle(CIANO, 0.035);
        g.fillRect(p.x - 26 + i * 3, p.y - h - 130 + i * 8, 52 - i * 6, 130 - i * 8);
      }
      g.fillStyle(0x000000, 0.3);
      g.fillEllipse(p.x, p.y + 2, 96, 44);
      cilindro(g, p.x, p.y, 44, 21, 0, 7, 0x343a40);
      cilindro(g, p.x, p.y, 36, 17, 7, h, 0x495057);
      g.lineStyle(2, 0xd4af37, 0.9);
      g.strokePoints(pontosElipse(p.x, p.y - 7, 44, 21, 0, Math.PI), false);
      g.fillStyle(0x1b1e24);
      g.fillEllipse(p.x, p.y - h, 66, 30);
      g.lineStyle(3, CIANO, 0.9);
      g.strokeEllipse(p.x, p.y - h, 62, 28);
      g.lineStyle(8, CIANO, 0.15);
      g.strokeEllipse(p.x, p.y - h, 62, 28);
      [-0.6, 0, 0.6].forEach((a) => { // luzes na lateral
        g.fillStyle(CIANO, 0.9);
        g.fillCircle(p.x + Math.sin(a) * 30, p.y - 14 + Math.cos(a) * 9, 1.8);
      });
    },
    frente(g, x, y) {
      // Meia-argola de vidro na frente dos pés (o Cérebro fica "dentro" do anel).
      const p = isoParaTela(x + AGENTE_NO_TILE, y + AGENTE_NO_TILE);
      const cy = p.y - ELEVACAO_PEDESTAL - 6;
      g.lineStyle(2, 0xa5f3fc, 0.55);
      g.strokePoints(pontosElipse(p.x, cy, 40, 18, 0.05, Math.PI - 0.05), false);
      [-1, 1].forEach((l) => {
        g.lineStyle(2, 0xadb5bd, 0.8);
        g.lineBetween(p.x + l * 40, cy, p.x + l * 40, cy + 6);
      });
    },
  },

  // Estagiário: mesa simples, notebook, papéis e post-its.
  estagiario: {
    atras: cadeiraAtras(0x4dabf7),
    frente(g, x, y) {
      const z = mesaPadrao(g, x, y, 0xe9d8a6);
      desenharNotebook(g, x + 0.64, y + 0.48, z);
      [0, 1].forEach((i) => caixaIso(g, x + 0.46, y + 0.7, x + 0.62, y + 0.9, z + i, z + i + 1, 0xf8f9fa, false));
      caixaIso(g, x + 0.47, y + 0.5, x + 0.53, y + 0.56, z, z + 0.6, 0xffe066, false);
      caixaIso(g, x + 0.5, y + 0.58, x + 0.56, y + 0.64, z, z + 0.6, 0xff8fab, false);
      desenharCaneca(g, x + 0.84, y + 0.84, z, 0x4dabf7);
    },
  },
});

Object.assign(MOVEIS, {
  // Tanque de vidro com líquido, bolhas e (opcional) um cérebro reserva flutuando.
  tanque: {
    w: 1, d: 1,
    desenhar(g, { x, y, cor = 0x63e6be, reserva }, ctx) {
      const p = isoParaTela(x + 0.5, y + 0.5);
      cilindro(g, p.x, p.y, 20, 10, 0, 10, 0x343a40);
      g.fillStyle(cor, 0.35);
      g.fillRect(p.x - 15, p.y - 74, 30, 64);
      g.fillEllipse(p.x, p.y - 10, 30, 14);
      g.fillStyle(cor, 0.5);
      g.fillEllipse(p.x, p.y - 74, 30, 14);
      g.fillStyle(0xffffff, 0.12);
      g.fillRect(p.x - 15, p.y - 82, 30, 72);
      g.fillStyle(0xffffff, 0.45);
      g.fillRect(p.x - 11, p.y - 78, 3, 60);
      g.lineStyle(1, 0xe3fafc, 0.6);
      g.strokeRect(p.x - 15, p.y - 82, 30, 72);
      cilindro(g, p.x, p.y, 17, 8, 82, 88, 0x495057);
      const prof = ctx.profundidade + 1;
      if (reserva) {
        const b = ctx.cena.add.graphics().setDepth(prof);
        b.fillStyle(ROSA_CEREBRO, 0.85);
        b.fillEllipse(0, 0, 18, 12);
        b.lineStyle(1, DOBRA, 0.8);
        b.lineBetween(0, -5, 0, 5);
        b.strokeEllipse(-3.5, 0, 6, 6);
        b.strokeEllipse(3.5, 0, 6, 6);
        b.setPosition(p.x, p.y - 44);
        ctx.extras.push(b);
        ctx.anima({ targets: b, y: p.y - 52, duration: 1800, yoyo: true, ease: 'Sine.inOut' });
      }
      [[-6, 0], [5, 700], [0, 1300]].forEach(([dx, atraso]) => {
        const bolha = ctx.cena.add.circle(p.x + dx, p.y - 14, 1.8, 0xffffff, 0.7).setDepth(prof);
        ctx.extras.push(bolha);
        ctx.anima({ targets: bolha, y: p.y - 74, alpha: 0, duration: 2000, delay: atraso });
      });
    },
  },

  // Bancada encostada na parede da esquerda: tubos de ensaio, frascos e microscópio.
  bancadaLab: {
    w: 1, d: 2,
    desenhar(g, { x, y }) {
      caixaIso(g, x + 0.05, y + 0.1, x + 0.62, y + 1.9, 0, 28, 0xdee2e6);
      caixaIso(g, x + 0.03, y + 0.08, x + 0.64, y + 1.92, 28, 31, 0x343a40);
      const z = 31;
      caixaIso(g, x + 0.2, y + 0.25, x + 0.45, y + 0.75, z, z + 6, 0x8b5e34, false);
      [0xff6b6b, 0x69db7c, 0x4dabf7, 0xffd43b].forEach((cor, i) => {
        const p = pIso(x + 0.32, y + 0.32 + i * 0.12, z + 6);
        g.fillStyle(0xe3fafc, 0.7);
        g.fillRoundedRect(p.x - 2, p.y - 16, 4, 16, 2);
        g.fillStyle(cor);
        g.fillRoundedRect(p.x - 2, p.y - 8, 4, 8, 2);
      });
      [[0.35, 1.0, 0xc77dff], [0.42, 1.3, 0x63e6be]].forEach(([dx, dy, cor]) => {
        const p = pIso(x + dx, y + dy, z);
        g.fillStyle(0xe3fafc, 0.55);
        g.fillTriangle(p.x - 8, p.y, p.x + 8, p.y, p.x, p.y - 16);
        g.fillRect(p.x - 2, p.y - 22, 4, 8);
        g.fillStyle(cor, 0.9);
        g.fillTriangle(p.x - 7, p.y, p.x + 7, p.y, p.x, p.y - 8);
      });
      const m = pIso(x + 0.32, y + 1.65, z);
      g.fillStyle(0x212529);
      g.fillRect(m.x - 7, m.y - 3, 14, 3);
      g.fillRect(m.x - 1.5, m.y - 18, 3, 16);
      g.lineStyle(4, 0x495057);
      g.lineBetween(m.x - 4, m.y - 22, m.x + 5, m.y - 10);
      g.fillStyle(0xadb5bd);
      g.fillCircle(m.x - 4, m.y - 22, 2.5);
    },
  },

  // Mesa com três monitores mostrando ondas cerebrais (a do meio pulsa).
  monitoresCerebro: {
    w: 2, d: 1,
    desenhar(g, { x, y }, ctx) {
      const z = desenharMesa(g, x + 0.1, y + 0.35, x + 1.9, y + 0.95, 24, 0x343a40, 0x1b1b1b);
      const onda = (cor, fase, amp) => (gg, x0, x1, ty, z0, z1) => {
        const pts = [];
        for (let t = 0; t <= 1.001; t += 0.04) {
          const zc = (z0 + z1) / 2 + Math.sin(t * 14 + fase) * amp * (0.6 + 0.4 * Math.sin(t * 5));
          pts.push(pIso(x0 + (x1 - x0) * t, ty, zc));
        }
        gg.lineStyle(1.3, cor, 0.95);
        gg.strokePoints(pts, false);
      };
      [[0.15, 0x69db7c, 0], [0.75, 0xff8fab, 1], [1.35, 0x66d9e8, 2]].forEach(([dx, cor, fase]) => {
        desenharMonitor(g, x + dx, x + dx + 0.5, y + 0.45, z, 0x0b1d22, onda(cor, fase, 4));
      });
      const brilho = ctx.cena.add.graphics().setDepth(ctx.profundidade + 1);
      onda(0xffffff, 1, 4)(brilho, x + 0.81, x + 1.19, y + 0.482, z + 10, z + 22);
      ctx.extras.push(brilho);
      ctx.anima({ targets: brilho, alpha: 0.1, duration: 700, yoyo: true });
      caixaIso(g, x + 0.6, y + 0.72, x + 1.3, y + 0.86, z, z + 1.5, 0x212529, false);
      desenharCaneca(g, x + 1.6, y + 0.78, z, 0xff8fab);
    },
  },
});

Object.assign(ELEMENTOS_PAREDE, {
  // Quadro-negro com fórmulas a giz (textos inclinados no ângulo da parede).
  formulas(g, e, ctx) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0x6c584c, 4);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, 0x1f3b36);
    const larg = m.t1 - m.t0;
    linhaParede(g, e.lado, m.t0 + larg * 0.1, m.z0 + 6, m.t0 + larg * 0.4, m.z0 + 14, 1.2, 0xffd166, 0.8);
    const angulo = e.lado === 'esq' ? -Math.atan2(TILE_H, TILE_W) : Math.atan2(TILE_H, TILE_W);
    [['E = mc²', 0.86, 14], ['Σ hóspedes × noites', 0.9, 30], ['∫ ψ dx = ★★★★★', 0.84, 46]].forEach(([texto, a, dz]) => {
      const p = pParede(e.lado, m.t0 + larg * (e.lado === 'esq' ? a : 1 - a), m.z1 - dz);
      ctx.extras.push(ctx.cena.add.text(p.x, p.y, texto, {
        fontFamily: '"Comic Sans MS", "Segoe Print", cursive', fontSize: '10px', color: '#f1f3f5',
      }).setOrigin(0, 0.5).setRotation(angulo).setAlpha(0.8).setDepth(PROF_PAREDE + 1));
    });
    caixaParede(g, e.lado, e.t0 + 0.05, e.t1 - 0.05, 0.12, e.z0 - 3, e.z0, 0x6c584c, false);
  },

  // Mapa da empresa: o cérebro no centro ligado aos andares e às casas.
  mapaEmpresa(g, e) {
    const m = molduraParede(g, e.lado, e.t0, e.t1, e.z0, e.z1, 0xd4af37, 3);
    quadParede(g, e.lado, m.t0, m.t1, m.z0, m.z1, 0xf1ece2);
    const larg = m.t1 - m.t0, alt = m.z1 - m.z0;
    const centro = [m.t0 + larg * 0.5, m.z0 + alt * 0.5];
    const nos = [[0.15, 0.78, 0xf4a261], [0.85, 0.78, 0xc77dff], [0.15, 0.22, 0x4dabf7], [0.85, 0.22, 0x2a9d8f], [0.5, 0.88, 0xd4af37]];
    nos.forEach(([a, b]) => linhaParede(g, e.lado, centro[0], centro[1], m.t0 + larg * a, m.z0 + alt * b, 1.2, 0x868e96));
    nos.forEach(([a, b, cor]) => {
      const t = m.t0 + larg * a, z = m.z0 + alt * b;
      discoParede(g, e.lado, t, z, 5, cor);
      // casinha (telhado + corpo)
      quadParede(g, e.lado, t - 0.03, t + 0.03, z - 2, z + 1, 0xffffff);
    });
    discoParede(g, e.lado, centro[0], centro[1], 9, DOBRA);
    discoParede(g, e.lado, centro[0], centro[1], 7.5, ROSA_CEREBRO);
    linhaParede(g, e.lado, centro[0], centro[1] - 6, centro[0], centro[1] + 6, 1, DOBRA);
  },
});
