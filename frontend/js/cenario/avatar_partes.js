// Partes do avatar chibi: cabelos, roupas, acessórios e rosto (Phaser Graphics).
// Coordenadas locais: (0, 0) são os pés; y negativo sobe.

const CABECA_Y = -52; // centro da cabeça
const CABECA_R = 13;
const PESCOCO = -40;

// ---------- Cabelos: `tras` desenha atrás do corpo, `frente` sobre a cabeça ----------
function franjaCabelo(g, cor) {
  g.fillStyle(cor);
  g.slice(0, CABECA_Y - 2, CABECA_R + 1.5, Math.PI, 0, false);
  g.fillPath();
  g.fillEllipse(-7, CABECA_Y - 3, 11, 7);
  g.fillEllipse(0, CABECA_Y - 4, 10, 6);
  g.fillEllipse(7, CABECA_Y - 3, 11, 7);
  g.fillRect(-CABECA_R - 1, CABECA_Y - 4, 3, 7);
  g.fillRect(CABECA_R - 2, CABECA_Y - 4, 3, 7);
}

const CABELOS = {
  curto: { frente: franjaCabelo },
  longo: {
    tras: (g, cor) => {
      g.fillStyle(tomCor(cor, 0.85));
      g.fillRoundedRect(-16, CABECA_Y - 8, 32, 32, 8);
    },
    frente: (g, cor) => {
      franjaCabelo(g, cor);
      g.fillRoundedRect(-16, CABECA_Y - 6, 6, 24, 3);
      g.fillRoundedRect(10, CABECA_Y - 6, 6, 24, 3);
    },
  },
  coque: {
    frente: (g, cor) => {
      g.fillStyle(cor);
      g.slice(0, CABECA_Y - 2, CABECA_R + 1, Math.PI, 0, false);
      g.fillPath();
      g.fillEllipse(0, CABECA_Y - 4, 24, 7);
      g.fillCircle(0, CABECA_Y - CABECA_R - 5, 7);
      g.fillStyle(tomCor(cor, 1.35));
      g.fillRect(-5, CABECA_Y - CABECA_R, 10, 2);
    },
  },
  careca: {
    frente: (g) => {
      g.fillStyle(0xffffff, 0.28);
      g.fillEllipse(-4, CABECA_Y - 8, 9, 4);
    },
  },
  cacheado: {
    tras: (g, cor) => {
      g.fillStyle(tomCor(cor, 0.85));
      for (let a = 140; a <= 400; a += 26) {
        const r = (a * Math.PI) / 180;
        g.fillCircle(Math.cos(r) * 14, CABECA_Y + Math.sin(r) * 13 + 2, 7);
      }
    },
    frente: (g, cor) => {
      g.fillStyle(cor);
      for (let a = 190; a <= 350; a += 20) {
        const r = (a * Math.PI) / 180;
        g.fillCircle(Math.cos(r) * 11, CABECA_Y - 2 + Math.sin(r) * 11, 5.5);
      }
      g.fillCircle(0, CABECA_Y - 11, 6);
    },
  },
  moicano: {
    frente: (g, cor, pele) => {
      g.fillStyle(tomCor(pele, 0.82));
      g.slice(0, CABECA_Y - 2, CABECA_R - 0.5, Math.PI, 0, false);
      g.fillPath();
      g.fillStyle(cor);
      g.fillRect(-3.5, CABECA_Y - 15, 7, 12);
      g.fillTriangle(-4, CABECA_Y - 13, 0, CABECA_Y - 25, 4, CABECA_Y - 13);
      g.fillTriangle(-6, CABECA_Y - 10, -4, CABECA_Y - 21, 2, CABECA_Y - 12);
      g.fillTriangle(6, CABECA_Y - 10, 4, CABECA_Y - 21, -2, CABECA_Y - 12);
    },
  },
};

// ---------- Roupas: pintam tronco (e pernas no macacão) ----------
function decoteRoupa(g, pele) {
  g.fillStyle(pele);
  g.slice(0, -38, 4, 0, Math.PI, false);
  g.fillPath();
}

const ROUPAS = {
  camiseta: { curta: true, tronco: (g, ap) => decoteRoupa(g, ap.pele) },
  camisa: {
    tronco: (g, ap) => {
      g.fillStyle(tomCor(ap.roupa.cor, 0.7));
      g.fillRect(-0.5, -36, 1, 19);
      g.fillStyle(0xffffff, 0.85);
      [-31, -26, -21].forEach((y) => g.fillCircle(0, y, 0.9));
      g.fillTriangle(-5, -38, 0, -38, -2, -33);
      g.fillTriangle(5, -38, 0, -38, 2, -33);
    },
  },
  blazer: {
    tronco: (g, ap) => {
      g.fillStyle(0xf1f3f5);
      g.fillTriangle(-5, -38, 5, -38, 0, -26);
      g.fillStyle(tomCor(ap.roupa.cor, 0.7));
      g.fillTriangle(-6, -38, -1, -27, -6, -30);
      g.fillTriangle(6, -38, 1, -27, 6, -30);
      g.fillStyle(tomCor(ap.roupa.cor, 1.4));
      g.fillCircle(0, -22, 1.1);
    },
  },
  moletom: {
    tronco: (g, ap) => {
      g.fillStyle(tomCor(ap.roupa.cor, 0.78));
      g.fillEllipse(0, -38, 20, 7);
      g.fillRoundedRect(-7, -27, 14, 7, 2);
      g.lineStyle(1, 0xf8f9fa, 0.8);
      g.lineBetween(-2, -37, -2.5, -31);
      g.lineBetween(2, -37, 2.5, -31);
    },
  },
  macacao: {
    pernas: (ap) => ap.roupa.cor,
    base: (ap) => ap.calca, // camiseta por baixo
    tronco: (g, ap) => {
      decoteRoupa(g, ap.pele);
      g.fillStyle(ap.roupa.cor);
      g.fillRoundedRect(-7, -32, 14, 16, 2);
      g.fillRect(-8, -38, 3, 7);
      g.fillRect(5, -38, 3, 7);
      g.fillStyle(tomCor(ap.roupa.cor, 0.75));
      g.fillRect(-4, -29, 8, 5);
      g.fillStyle(0xdee2e6);
      g.fillCircle(-6.5, -31, 1.2);
      g.fillCircle(6.5, -31, 1.2);
    },
  },
  avental: {
    base: () => 0xf1f3f5,
    tronco: (g, ap) => {
      decoteRoupa(g, ap.pele);
      g.fillStyle(ap.roupa.cor);
      g.fillRoundedRect(-8, -33, 16, 25, 3);
      g.lineStyle(1.2, tomCor(ap.roupa.cor, 0.7));
      g.lineBetween(-7, -33, -4, -38);
      g.lineBetween(7, -33, 4, -38);
      g.fillStyle(tomCor(ap.roupa.cor, 0.8));
      g.fillRect(-5, -22, 10, 5);
    },
  },
};

// ---------- Acessórios: `corpo` sobre o tronco, `cabeca` sobre a cabeça ----------
const ACESSORIOS = {
  nenhum: {},
  oculos: {
    cabeca: (g) => {
      g.fillStyle(0xffffff, 0.22);
      g.fillCircle(-5, CABECA_Y + 1, 3.8);
      g.fillCircle(5, CABECA_Y + 1, 3.8);
      g.lineStyle(1.4, 0x1b1e24);
      g.strokeCircle(-5, CABECA_Y + 1, 3.8);
      g.strokeCircle(5, CABECA_Y + 1, 3.8);
      g.lineBetween(-1.2, CABECA_Y + 1, 1.2, CABECA_Y + 1);
    },
  },
  fone: {
    cabeca: (g) => {
      g.lineStyle(3, 0x343a40);
      g.beginPath();
      g.arc(0, CABECA_Y, CABECA_R + 2, Math.PI * 1.08, Math.PI * 1.92, false);
      g.strokePath();
      g.fillStyle(0x495057);
      g.fillRoundedRect(-CABECA_R - 4, CABECA_Y - 4, 6, 10, 2);
      g.fillRoundedRect(CABECA_R - 2, CABECA_Y - 4, 6, 10, 2);
      g.lineStyle(1.5, 0x343a40);
      g.lineBetween(-CABECA_R, CABECA_Y + 5, -5, CABECA_Y + 9);
      g.fillStyle(0x212529);
      g.fillCircle(-5, CABECA_Y + 9, 1.8);
    },
  },
  bone: {
    cabeca: (g, ap) => {
      const cor = luminancia(ap.roupa.cor) > 0.5 ? 0x264653 : tomCor(ap.roupa.cor, 1.25);
      g.fillStyle(cor);
      g.slice(0, CABECA_Y - 3, CABECA_R + 1.5, Math.PI, 0, false);
      g.fillPath();
      g.fillStyle(tomCor(cor, 0.75));
      g.fillEllipse(0, CABECA_Y - 3, 32, 6);
    },
  },
  capacete: {
    cabeca: (g) => {
      g.fillStyle(0xffc300);
      g.slice(0, CABECA_Y - 4, CABECA_R + 2, Math.PI, 0, false);
      g.fillPath();
      g.fillStyle(0xe0a800);
      g.fillEllipse(0, CABECA_Y - 4, 34, 6);
      g.fillRect(-1.5, CABECA_Y - 19, 3, 15);
      g.fillStyle(0xffffff, 0.35);
      g.fillEllipse(-6, CABECA_Y - 12, 6, 3);
    },
  },
  cracha: {
    corpo: (g) => {
      g.lineStyle(1, 0x1d3557);
      g.lineBetween(-4, -38, 0, -29);
      g.lineBetween(4, -38, 0, -29);
      g.fillStyle(0xf8f9fa);
      g.fillRect(-3.5, -29, 7, 9);
      g.fillStyle(0x457b9d);
      g.fillRect(-3.5, -29, 7, 2.5);
    },
  },
  gravata: {
    corpo: (g, ap) => {
      const cor = (ap.roupa.cor >> 16) > 0xb0 ? 0x1d3557 : 0xc92a2a;
      g.fillStyle(tomCor(cor, 0.8));
      g.fillRect(-1.8, -38, 3.6, 3);
      g.fillStyle(cor);
      g.fillPoints([
        { x: -1.6, y: -35 }, { x: 1.6, y: -35 }, { x: 2.8, y: -24 }, { x: 0, y: -21 }, { x: -2.8, y: -24 },
      ], true);
    },
  },
  camera: {
    corpo: (g) => {
      g.lineStyle(1.2, 0x212529);
      g.lineBetween(-7, -37, -4, -29);
      g.lineBetween(7, -37, 4, -29);
      g.fillStyle(0x212529);
      g.fillRoundedRect(-7, -30, 14, 9, 2);
      g.fillStyle(0x495057);
      g.fillCircle(0, -25.5, 3.6);
      g.fillStyle(0x74c0fc);
      g.fillCircle(0, -25.5, 1.8);
      g.fillStyle(0xf8f9fa);
      g.fillRect(3.5, -29, 2, 1.5);
    },
  },
  lapis: {
    cabeca: (g) => {
      g.lineStyle(3, 0xf2c94c);
      g.lineBetween(8, CABECA_Y - 12, 15, CABECA_Y - 1);
      g.fillStyle(0xf28482);
      g.fillCircle(8, CABECA_Y - 12, 1.6);
      g.fillStyle(0x343a40);
      g.fillTriangle(13.7, CABECA_Y - 2, 16.3, CABECA_Y - 0.4, 16, CABECA_Y + 2);
    },
  },
};

function desenharCorpo(g, ap) {
  const roupa = ROUPAS[ap.roupa.estilo];
  const corPernas = roupa.pernas ? roupa.pernas(ap) : ap.calca;
  const corTronco = roupa.base ? roupa.base(ap) : ap.roupa.cor;

  CABELOS[ap.cabelo.estilo].tras?.(g, ap.cabelo.cor, ap.pele);

  g.fillStyle(corPernas);
  g.fillRoundedRect(-8, -19, 7, 17, 2);
  g.fillRoundedRect(1, -19, 7, 17, 2);
  g.fillStyle(0x2b2d31);
  g.fillRoundedRect(-9, -4, 8, 4, 2);
  g.fillRoundedRect(1, -4, 8, 4, 2);

  g.fillStyle(tomCor(ap.pele, 0.9));
  g.fillRect(-3, -42, 6, 5);
  g.fillStyle(corTronco);
  g.fillRoundedRect(-11, -38, 22, 22, 6);
  roupa.tronco(g, ap);
  ACESSORIOS[ap.acessorio].corpo?.(g, ap);
}

function desenharBracos(g, ap) {
  const roupa = ROUPAS[ap.roupa.estilo];
  const manga = roupa.base ? roupa.base(ap) : ap.roupa.cor;
  [-1, 1].forEach((lado) => {
    const x = lado < 0 ? -15 : 10;
    g.fillStyle(roupa.curta ? ap.pele : manga);
    g.fillRoundedRect(x, -37, 5, 15, 2.5);
    if (roupa.curta) {
      g.fillStyle(manga);
      g.fillRoundedRect(x - 0.5, -37.5, 6, 6, 2.5);
    }
    g.fillStyle(ap.pele);
    g.fillCircle(x + 2.5, -21.5, 2.9);
  });
}

function desenharCabeca(g, ap) {
  g.fillStyle(tomCor(ap.pele, 0.92));
  g.fillCircle(-CABECA_R, CABECA_Y + 1, 3);
  g.fillCircle(CABECA_R, CABECA_Y + 1, 3);
  g.fillStyle(ap.pele);
  g.fillEllipse(0, CABECA_Y, CABECA_R * 2 + 1, CABECA_R * 2 - 1);
  g.fillStyle(0xff6b6b, 0.22);
  g.fillCircle(-7.5, CABECA_Y + 5, 2.6);
  g.fillCircle(7.5, CABECA_Y + 5, 2.6);
  g.lineStyle(1.2, tomCor(ap.pele, 0.45));
  g.beginPath();
  g.arc(0, CABECA_Y + 5, 2.4, 0.2 * Math.PI, 0.8 * Math.PI, false);
  g.strokePath();
}

function desenharOlhos(g, abertos) {
  if (abertos) {
    g.fillStyle(0x1b1e24);
    g.fillEllipse(-5, CABECA_Y + 1, 3, 4);
    g.fillEllipse(5, CABECA_Y + 1, 3, 4);
    g.fillStyle(0xffffff);
    g.fillCircle(-4.4, CABECA_Y, 0.8);
    g.fillCircle(5.6, CABECA_Y, 0.8);
  } else {
    g.lineStyle(1.3, 0x1b1e24);
    g.lineBetween(-7, CABECA_Y + 1.5, -3, CABECA_Y + 1.5);
    g.lineBetween(3, CABECA_Y + 1.5, 7, CABECA_Y + 1.5);
  }
}

