// O Cérebro (visual "cerebro"): ratinho de laboratório gênio, cabeçorra com o cérebro
// rosa à mostra. Mesma interface de criarAvatar (status, mover, virar, rótulo, clique).
// Coordenadas locais: (0, 0) são os pés; y negativo sobe.

const ESCALA_CEREBRO = 1.4;
const CEREBRO_Y = -54; // centro do cérebro (antes da escala)
const PELO = 0xe9ecef;
const PELO_SOMBRA = 0xc5ccd3;
const ROSA = 0xf4a6b4;
const ROSA_CEREBRO = 0xf7a8c0;
const DOBRA = 0xd0607f;

// Curva de Bézier cúbica como linha (rabo, sorriso).
function curvaCerebro(g, pontos, largura, cor, alfa = 1) {
  const [a, b, c, d] = pontos.map(([x, y]) => new Phaser.Math.Vector2(x, y));
  g.lineStyle(largura, cor, alfa);
  g.strokePoints(new Phaser.Curves.CubicBezier(a, b, c, d).getPoints(18), false);
}

// Corpo: rabo, pés, barriga e as patinhas unidas (pose de quem trama algo).
function desenharCorpoRato(g) {
  curvaCerebro(g, [[5, -7], [22, -2], [30, -14], [22, -22]], 2.2, ROSA);
  g.fillStyle(ROSA);
  g.fillEllipse(-6, -1.5, 9, 4.5);
  g.fillEllipse(6, -1.5, 9, 4.5);
  g.fillStyle(PELO_SOMBRA);
  g.fillEllipse(0, -13, 24, 25);
  g.fillStyle(PELO);
  g.fillEllipse(-1, -14, 21, 23);
  g.fillStyle(0xf8f9fa);
  g.fillEllipse(0, -11, 12, 15);
}

function desenharPatas(g) {
  g.lineStyle(4, PELO_SOMBRA);
  g.lineBetween(-9, -20, -3, -16);
  g.lineBetween(9, -20, 3, -16);
  g.fillStyle(ROSA);
  g.fillEllipse(-2.2, -16.5, 4.5, 6.5);
  g.fillEllipse(2.2, -16.5, 4.5, 6.5);
  g.lineStyle(0.8, DOBRA, 0.7);
  g.lineBetween(0, -19.5, 0, -13.5);
}

// Orelhas grandes e o rosto (focinho, bigodes, sorriso de canto).
function desenharCabecaRato(g) {
  [-1, 1].forEach((l) => {
    g.fillStyle(PELO_SOMBRA);
    g.fillCircle(l * 18, -44, 10);
    g.fillStyle(ROSA);
    g.fillCircle(l * 18, -44, 6.5);
  });
  g.fillStyle(PELO_SOMBRA);
  g.fillEllipse(0, -35, 34, 26);
  g.fillStyle(PELO);
  g.fillEllipse(-0.5, -36, 31, 23);
  g.fillStyle(0xff6b8b, 0.25);
  g.fillCircle(-10, -31, 3);
  g.fillCircle(10, -31, 3);
  g.fillStyle(0xf8f9fa);
  g.fillEllipse(0, -29, 15, 10);
  g.lineStyle(0.8, 0x868e96, 0.7);
  [-1, 1].forEach((l) => {
    g.lineBetween(l * 5, -29.5, l * 17, -32);
    g.lineBetween(l * 5, -28.5, l * 17, -27.5);
  });
  g.fillStyle(0xff8fab);
  g.fillEllipse(0, -31.5, 5.5, 3.8);
  g.fillStyle(0xffffff, 0.8);
  g.fillCircle(-1, -32.3, 0.9);
  curvaCerebro(g, [[-3.5, -26.6], [-1, -25.2], [2, -25.4], [4.5, -27.6]], 1.1, 0x495057);
}

// Olhos semicerrados (pálpebra pesada e sobrancelha em V) ou fechados.
function desenharOlhosRato(g, abertos) {
  [-1, 1].forEach((l) => {
    const cx = l * 6.8, cy = -37.5;
    if (!abertos) {
      g.lineStyle(1.4, 0x343a40);
      g.beginPath();
      g.arc(cx, cy - 1, 3, 0.15 * Math.PI, 0.85 * Math.PI, false);
      g.strokePath();
      return;
    }
    g.fillStyle(0xffffff);
    g.fillEllipse(cx, cy, 7.5, 6);
    g.fillStyle(0x1b1e24);
    g.fillCircle(cx + l * 0.6, cy + 1, 2.2);
    g.fillStyle(0xffffff);
    g.fillCircle(cx + l * 0.6 + 0.8, cy + 0.2, 0.7);
    // pálpebra: cobre o alto do olho, mais baixa do lado de dentro
    const fora = cx + l * 4.2, dentro = cx - l * 4.2;
    g.fillStyle(PELO_SOMBRA);
    g.fillPoints([{ x: fora, y: cy - 1.6 }, { x: dentro, y: cy - 0.2 }, { x: dentro, y: cy - 4 }, { x: fora, y: cy - 4 }], true);
    g.lineStyle(1.2, 0x495057);
    g.lineBetween(fora, cy - 1.6, dentro, cy - 0.2);
    g.lineStyle(2, 0x6c757d);
    g.lineBetween(cx + l * 4.5, cy - 6.2, cx - l * 3, cy - 4.3);
  });
}

// Cérebro (centrado em 0, 0): hemisférios, dobras onduladas e brilho.
function desenharCerebroRosa(g) {
  const rx = 19, ry = 12.5;
  g.fillStyle(DOBRA);
  g.fillEllipse(0, 0.6, rx * 2 + 2, ry * 2 + 2);
  g.fillStyle(ROSA_CEREBRO);
  g.fillEllipse(0, 0, rx * 2, ry * 2);
  g.lineStyle(1.3, DOBRA, 0.95);
  [0.78, 0.52].forEach((s, n) => {
    [-1, 1].forEach((l) => {
      const pts = [];
      for (let t = 0; t <= 1.001; t += 0.05) {
        const a = Math.PI * (0.58 + 0.84 * t); // meia-volta do lado de fora de cada hemisfério
        const onda = Math.sin(t * Math.PI * (7 - n * 2)) * 1.3;
        pts.push({ x: l * (1.5 - Math.cos(a) * (rx * s + onda)), y: Math.sin(a) * (ry * s + onda) });
      }
      g.strokePoints(pts, false);
    });
  });
  // dobras curtas entre os arcos
  [[-13, -5, -9, -1], [-14, 4, -9, 6], [13, -5, 9, -1], [14, 4, 9, 6], [-5, -9, -6, -4], [5, -9, 6, -4]]
    .forEach(([a, b, c, d]) => g.lineBetween(a, b, c, d));
  // fissura do meio
  const meio = [];
  for (let y = -ry + 1; y <= ry - 2; y += 1.5) meio.push({ x: Math.sin(y * 0.9) * 0.9, y });
  g.lineStyle(1.6, DOBRA);
  g.strokePoints(meio, false);
  g.fillStyle(0xffffff, 0.4);
  g.fillEllipse(-8, -6.5, 10, 4);
  g.fillEllipse(7, -7.5, 5, 2.4);
}

// Raios e ondas que saem do cérebro quando ele trabalha.
function desenharFaiscas(g) {
  [[-22, -4, -1], [22, -4, 1], [-12, -15, -1], [12, -15, 1], [0, -17, 0]].forEach(([x, y, l]) => {
    const raio = [{ x, y }, { x: x + l * 5 - 2, y: y - 4 }, { x: x + l * 2 + 2, y: y - 6 }, { x: x + l * 8, y: y - 12 }];
    g.lineStyle(4, 0xffe066, 0.3);
    g.strokePoints(raio, false);
    g.lineStyle(1.8, 0xfff3bf);
    g.strokePoints(raio, false);
  });
  g.fillStyle(0x99e9f2);
  [[-29, -14], [29, -14], [-6, -24], [7, -25]].forEach(([x, y]) => g.fillCircle(x, y, 1.8));
}

// Cria o Cérebro nos pés (x, y). `elevacao` (px) o coloca sobre o pedestal.
function criarCerebro(cena, x, y, { id, nome, status, aoClicar, escalaRotulo = 1, rotuloAcima = 0, elevacao = 0 }) {
  const novo = (desenho, ...args) => {
    const g = cena.add.graphics();
    desenho(g, ...args);
    return g;
  };
  const sombra = cena.add.ellipse(0, 0, 34, 11, 0x000000, 0.3);
  const luzPes = cena.add.ellipse(0, 0, 54, 18, 0x66d9e8, elevacao ? 0.25 : 0);
  const corpo = novo(desenharCorpoRato);
  const patas = novo(desenharPatas);

  const brilho = cena.add.circle(0, 0, 27, 0xff8fab, 0.22);
  const ondas = [0, 1].map(() => cena.add.ellipse(0, 0, 44, 30).setStrokeStyle(1.5, 0xff8fab, 0.9).setVisible(false));
  const cerebroG = cena.add.container(0, 0, [novo(desenharCerebroRosa)]);
  const faiscas = novo(desenharFaiscas).setVisible(false);
  const topoCabeca = cena.add.container(0, CEREBRO_Y, [brilho, ...ondas, cerebroG, faiscas]);
  const olhosAbertos = novo(desenharOlhosRato, true);
  const olhosFechados = novo(desenharOlhosRato, false);
  // A cabeça gira em torno do pescoço (y = -24).
  const partesCabeca = [novo(desenharCabecaRato), topoCabeca, olhosAbertos, olhosFechados];
  partesCabeca.forEach((p) => p.setY(p.y + 24));
  const cabeca = cena.add.container(0, -24, partesCabeca);
  const boneco = cena.add.container(0, 0, [corpo, patas, cabeca]).setScale(ESCALA_CEREBRO);

  const zzz = cena.add.text(26, -84, 'zZ', {
    fontFamily: 'system-ui, sans-serif', fontSize: '15px', fontStyle: 'bold', color: '#e9ecef',
    stroke: '#15171c', strokeThickness: 3,
  }).setOrigin(0.5);

  const avatar = cena.add.container(x, y - elevacao, [luzPes, sombra, boneco, zzz]).setDepth(PROF_BASE + y);
  const alturaTopo = -66 * ESCALA_CEREBRO;
  let rotuloDy = alturaTopo - 14 - elevacao - rotuloAcima;
  const { rotulo, bolinha } = criarRotulo(cena, x, y + rotuloDy, nome, 'cerebro');
  rotulo.setScale(escalaRotulo);

  let alvo = null;
  if (aoClicar) {
    alvo = cena.add.zone(x, y - elevacao - 40, 56, 92).setDepth(PROF_ROTULOS + y + 1)
      .setInteractive({ useHandCursor: true });
    alvo.on('pointerdown', aoClicar);
    alvo.on('pointerover', () => rotulo.setScale(escalaRotulo * 1.08));
    alvo.on('pointerout', () => rotulo.setScale(escalaRotulo));
  }

  let animacoes = [];
  const anima = (cfg) => animacoes.push(cena.tweens.add({ repeat: -1, ...cfg }));

  function definirStatus(novoStatus) {
    const s = novoStatus in CORES_STATUS ? novoStatus : 'dormindo';
    animacoes.forEach((t) => t.remove());
    animacoes = [];
    [cerebroG, brilho, faiscas, cabeca, corpo, patas, bolinha, zzz, ...ondas].forEach((o) => o.setScale(1).setAlpha(1));
    boneco.setAlpha(1);
    cabeca.angle = 0;
    patas.y = 0;
    bolinha.setFillStyle(CORES_STATUS[s]);
    olhosAbertos.setVisible(s !== 'dormindo');
    olhosFechados.setVisible(s === 'dormindo');
    faiscas.setVisible(s === 'trabalhando');
    ondas.forEach((o) => o.setVisible(s === 'trabalhando'));
    zzz.setVisible(s === 'dormindo');
    brilho.setAlpha(0.22);
    luzPes.setAlpha(elevacao ? 0.25 : 0);
    const atraso = hashTexto(id) % 900;

    if (s === 'trabalhando') {
      anima({ targets: cerebroG, scale: 1.08, duration: 260, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: brilho, alpha: 0.6, scale: 1.25, duration: 260, yoyo: true });
      anima({ targets: faiscas, alpha: 0.15, duration: 140, yoyo: true, repeatDelay: 60 });
      ondas.forEach((o, i) => anima({ targets: o, scale: 1.9, alpha: 0, duration: 1100, delay: i * 550 }));
      anima({ targets: patas, y: -1.2, duration: 150, yoyo: true });
      anima({ targets: bolinha, scale: 1.45, duration: 500, yoyo: true });
      if (elevacao) anima({ targets: luzPes, alpha: 0.55, duration: 400, yoyo: true });
    } else if (s === 'construindo') {
      boneco.setAlpha(0.45);
      anima({ targets: boneco, alpha: 0.8, duration: 900, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: bolinha, scale: 1.35, duration: 700, yoyo: true });
    } else if (s === 'dormindo') {
      brilho.setAlpha(0.06);
      cerebroG.setAlpha(0.8);
      anima({ targets: cerebroG, scale: 1.02, duration: 2400, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      anima({ targets: cabeca, angle: 5, duration: 2400, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      zzz.y = -84;
      anima({ targets: zzz, y: -104, alpha: 0.2, duration: 2200, delay: atraso / 3 });
    } else {
      anima({ targets: cerebroG, scale: 1.035, duration: 1300, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      anima({ targets: brilho, alpha: 0.42, scale: 1.12, duration: 1300, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      anima({ targets: cabeca, angle: 2, duration: 2600, yoyo: true, ease: 'Sine.inOut', delay: atraso });
    }
  }

  function mover(nx, ny) {
    avatar.setPosition(nx, ny - elevacao).setDepth(PROF_BASE + ny);
    rotulo.setPosition(nx, ny + rotuloDy).setDepth(PROF_ROTULOS + ny);
    alvo?.setPosition(nx, ny - elevacao - 40).setDepth(PROF_ROTULOS + ny + 1);
  }

  function ajustarRotulo(acima) {
    rotuloDy = alturaTopo - 14 - elevacao - acima;
    rotulo.setY(avatar.y + elevacao + rotuloDy);
  }

  // Passinhos curtos (ele quase nunca sai do pedestal).
  let passos = [];
  function caminhar(ativo) {
    passos.forEach((t) => t.remove());
    passos = [];
    boneco.y = 0;
    if (ativo) passos.push(cena.tweens.add({ targets: boneco, y: -3, duration: 140, yoyo: true, repeat: -1 }));
  }

  const virar = (sentido) => avatar.setScale(sentido < 0 ? -1 : 1, 1);
  function definirAlfa(alfa) {
    avatar.setAlpha(alfa);
    rotulo.setAlpha(alfa);
  }

  definirStatus(status);
  return {
    objetos: [avatar, rotulo, alvo].filter(Boolean),
    definirStatus, mover, caminhar, virar, definirAlfa, ajustarRotulo,
    destruir: () => {
      caminhar(false);
      animacoes.forEach((t) => t.remove());
      [avatar, rotulo, alvo].forEach((o) => o?.destroy());
    },
  };
}

// Avatar conforme o `visual` do agente.
function criarBoneco(cena, x, y, opcoes) {
  return opcoes.visual === 'cerebro' ? criarCerebro(cena, x, y, opcoes) : criarAvatar(cena, x, y, opcoes);
}
