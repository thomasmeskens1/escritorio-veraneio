// Avatar humano (chibi) desenhado proceduralmente a partir do campo `aparencia`.
// Coordenadas locais: (0, 0) são os pés; y negativo sobe.

// construindo: agente sendo criado pelo Construtor (aparece translúcido, com martelo).
const CORES_STATUS = { dormindo: 0x868e96, disponivel: 0x40c057, trabalhando: 0xf4a261, construindo: 0x4dabf7 };

const PALETA_PELE = ['#ffdbac', '#f1c27d', '#e0ac69', '#c68642', '#a0522d', '#8d5524'];
const PALETA_CABELO = ['#1b1b1b', '#3b2f2f', '#7b4a12', '#b5651d', '#d8b26e', '#9e9e9e'];
const PALETA_ROUPA = ['#e76f51', '#2a9d8f', '#457b9d', '#6d597a', '#e9c46a', '#3a86ff', '#ff006e'];
const PALETA_CALCA = ['#22223b', '#264653', '#3d405b', '#343a40', '#14213d'];

const escolherDaLista = (lista, h, desloca) => lista[(h >>> desloca) % lista.length];

// Aparência determinística para agentes sem `aparencia` (ou com campos inválidos).
function aparenciaPadrao(id) {
  const h = hashTexto(id);
  return {
    pele: escolherDaLista(PALETA_PELE, h, 0),
    cabelo: { estilo: escolherDaLista(Object.keys(CABELOS), h, 3), cor: escolherDaLista(PALETA_CABELO, h, 6) },
    roupa: { estilo: escolherDaLista(Object.keys(ROUPAS), h, 9), cor: escolherDaLista(PALETA_ROUPA, h, 12) },
    calca: escolherDaLista(PALETA_CALCA, h, 15),
    acessorio: 'nenhum',
  };
}

// Aceita qualquer combinação; valores desconhecidos caem no padrão do id.
function normalizarAparencia(ap, id) {
  const base = aparenciaPadrao(id);
  const a = ap && typeof ap === 'object' ? ap : {};
  const cab = a.cabelo && typeof a.cabelo === 'object' ? a.cabelo : {};
  const roupa = a.roupa && typeof a.roupa === 'object' ? a.roupa : {};
  return {
    pele: corHex(a.pele, corHex(base.pele)),
    cabelo: {
      estilo: cab.estilo in CABELOS ? cab.estilo : base.cabelo.estilo,
      cor: corHex(cab.cor, corHex(base.cabelo.cor)),
    },
    roupa: {
      estilo: roupa.estilo in ROUPAS ? roupa.estilo : base.roupa.estilo,
      cor: corHex(roupa.cor, corHex(base.roupa.cor)),
    },
    calca: corHex(a.calca, corHex(base.calca)),
    acessorio: a.acessorio in ACESSORIOS ? a.acessorio : 'nenhum',
  };
}

// Rótulo com bolinha de status; fica acima de tudo para continuar legível.
// Borda azul: sistema (Despachante); rosa: o Cérebro; verde: estagiários.
const BORDAS_ROTULO = {
  sistema: [0x8ecae6, 0.55], cerebro: [0xff8fab, 0.75], estagiario: [0x8ce99a, 0.4], ia: [0xffffff, 0.12],
};

function criarRotulo(cena, x, y, nome, tipo = 'ia') {
  const texto = cena.add.text(5, 0, tipo === 'sistema' ? `⚙ ${nome}` : nome, {
    fontFamily: 'system-ui, sans-serif', fontSize: '12px', color: '#f1f3f5',
  }).setOrigin(0.5);
  const largura = texto.width + 26;
  const [borda, alfaBorda] = BORDAS_ROTULO[tipo] || BORDAS_ROTULO.ia;
  const fundo = cena.add.graphics();
  fundo.fillStyle(0x15171c, 0.78);
  fundo.fillRoundedRect(-largura / 2, -10, largura, 20, 10);
  fundo.lineStyle(1, borda, alfaBorda);
  fundo.strokeRoundedRect(-largura / 2, -10, largura, 20, 10);
  const bolinha = cena.add.circle(-largura / 2 + 11, 0, 4.5, CORES_STATUS.dormindo).setStrokeStyle(1.5, 0x15171c);
  // "!" vermelho: algo esperando o usuário (formulário sem resposta, produção em espera). Fica no rótulo, que não
  // espelha quando o boneco vira.
  const alerta = cena.add.container(largura / 2 + 2, -11, [
    cena.add.circle(0, 0, 8, 0xe03131).setStrokeStyle(1.5, 0x15171c),
    cena.add.text(0, 0, '!', { fontFamily: 'system-ui, sans-serif', fontSize: '12px', fontStyle: 'bold', color: '#ffffff' })
      .setOrigin(0.5),
  ]).setVisible(false);
  const rotulo = cena.add.container(x, y, [fundo, texto, bolinha, alerta]).setDepth(PROF_ROTULOS + y);
  return { rotulo, bolinha, alerta };
}

// Etiqueta informativa (pílula sem status), ex.: "Trabalhando em outro andar".
function criarEtiqueta(cena, x, y, texto, escala = 1) {
  const t = cena.add.text(0, 0, texto, {
    fontFamily: 'system-ui, sans-serif', fontSize: '11px', fontStyle: 'italic', color: '#f4a261',
  }).setOrigin(0.5);
  const largura = t.width + 20;
  const fundo = cena.add.graphics();
  fundo.fillStyle(0x15171c, 0.82);
  fundo.fillRoundedRect(-largura / 2, -10, largura, 20, 10);
  fundo.lineStyle(1, 0xf4a261, 0.55);
  fundo.strokeRoundedRect(-largura / 2, -10, largura, 20, 10);
  return cena.add.container(x, y, [fundo, t]).setDepth(PROF_ROTULOS + y).setScale(escala);
}

// Cria o avatar nos pés (x, y). Retorna objetos e controles de status/movimento.
// `escalaRotulo` compensa o zoom da câmera em telas pequenas para o nome continuar legível.
// Sem `aoClicar` o avatar não é interativo (cursor padrão). `rotuloAcima` sobe o nome (px).
function criarAvatar(cena, x, y, { id, aparencia, nome, tipo, status, aoClicar, escalaRotulo = 1, rotuloAcima = 0 }) {
  const ap = normalizarAparencia(aparencia, id);
  const novo = (desenho, ...args) => {
    const g = cena.add.graphics();
    desenho(g, ...args);
    return g;
  };

  const sombra = cena.add.ellipse(0, 0, 30, 10, 0x000000, 0.28);
  const corpo = novo(desenharCorpo, ap);
  const bracos = novo(desenharBracos, ap);
  const olhosAbertos = novo(desenharOlhos, true);
  const olhosFechados = novo(desenharOlhos, false);
  const topo = novo((g) => {
    CABELOS[ap.cabelo.estilo].frente(g, ap.cabelo.cor, ap.pele);
    ACESSORIOS[ap.acessorio].cabeca?.(g, ap);
  });
  // A cabeça gira em torno do pescoço (y = PESCOCO).
  const partesCabeca = [novo(desenharCabeca, ap), olhosAbertos, olhosFechados, topo];
  partesCabeca.forEach((p) => p.setY(-PESCOCO));
  const cabeca = cena.add.container(0, PESCOCO, partesCabeca);
  const boneco = cena.add.container(0, 0, [corpo, bracos, cabeca]);

  // Indicadores: "digitando" (três pontos) e "zzz" (dormindo).
  const balao = cena.add.container(18, CABECA_Y - 16);
  const fundoBalao = cena.add.graphics();
  fundoBalao.fillStyle(0xf8f9fa, 0.95);
  fundoBalao.fillRoundedRect(-11, -7, 22, 13, 6);
  fundoBalao.fillTriangle(-7, 4, -3, 4, -9, 9);
  const pontos = [-5, 0, 5].map((px) => cena.add.circle(px, -0.5, 1.8, 0xf4a261));
  balao.add([fundoBalao, ...pontos]);
  const zzz = cena.add.text(12, CABECA_Y - 14, 'z', {
    fontFamily: 'system-ui, sans-serif', fontSize: '13px', fontStyle: 'bold', color: '#adb5bd',
  }).setOrigin(0.5);

  // Martelo de "em construção" (status construindo).
  const martelo = cena.add.container(-20, CABECA_Y - 10);
  const gm = cena.add.graphics();
  gm.fillStyle(0x8b5e34);
  gm.fillRect(-1.5, -2, 3, 14);
  gm.fillStyle(0xadb5bd);
  gm.fillRect(-6, -6, 12, 5);
  gm.lineStyle(1, 0x15171c, 0.6);
  gm.strokeRect(-6, -6, 12, 5);
  martelo.add(gm);

  const avatar = cena.add.container(x, y, [sombra, boneco, balao, zzz, martelo]).setDepth(PROF_BASE + y);
  let rotuloDy = CABECA_Y - CABECA_R - 26 - rotuloAcima;
  const { rotulo, bolinha, alerta } = criarRotulo(cena, x, y + rotuloDy, nome, tipo);
  let pulsoAlerta = null;
  function definirPendente(pendente) {
    if (alerta.visible === pendente) return;
    alerta.setVisible(pendente).setScale(1);
    pulsoAlerta?.remove();
    pulsoAlerta = pendente ? cena.tweens.add({ targets: alerta, scale: 1.25, duration: 600, yoyo: true, repeat: -1 }) : null;
  }
  rotulo.setScale(escalaRotulo);

  // Área de clique generosa: corpo inteiro + rótulo.
  let alvo = null;
  if (aoClicar) {
    alvo = cena.add.zone(x, y - 44, 48, 100).setDepth(PROF_ROTULOS + y + 1)
      .setInteractive({ useHandCursor: true });
    alvo.on('pointerdown', aoClicar);
    alvo.on('pointerover', () => rotulo.setScale(escalaRotulo * 1.08));
    alvo.on('pointerout', () => rotulo.setScale(escalaRotulo));
  }

  let animacoes = [];
  let statusAtual = 'dormindo';
  let andando = false;
  const anima = (cfg) => animacoes.push(cena.tweens.add({ repeat: -1, ...cfg }));

  function definirStatus(novoStatus) {
    const s = novoStatus in CORES_STATUS ? novoStatus : 'dormindo';
    animacoes.forEach((t) => t.remove());
    animacoes = [];
    [boneco, bracos, cabeca, balao, zzz, martelo, bolinha, ...pontos].forEach((o) => {
      o.setScale(1).setAlpha(1);
    });
    bracos.y = 0;
    cabeca.y = PESCOCO;
    cabeca.angle = 0;
    bolinha.setFillStyle(CORES_STATUS[s]);
    olhosAbertos.setVisible(s !== 'dormindo');
    olhosFechados.setVisible(s === 'dormindo');
    statusAtual = s;
    balao.setVisible(s === 'trabalhando' && !andando);
    zzz.setVisible(s === 'dormindo');
    martelo.setVisible(s === 'construindo');
    martelo.angle = 0;
    const atraso = hashTexto(id) % 900; // agentes não respiram em sincronia

    if (s === 'trabalhando') {
      anima({ targets: bracos, y: -2, duration: 130, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: cabeca, y: PESCOCO + 1.2, duration: 420, yoyo: true, ease: 'Sine.inOut', delay: atraso / 3 });
      anima({ targets: boneco, scaleY: 1.02, duration: 700, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: bolinha, scale: 1.45, duration: 500, yoyo: true });
      pontos.forEach((p, i) => anima({ targets: p, alpha: 0.2, duration: 380, yoyo: true, delay: i * 130 }));
    } else if (s === 'construindo') {
      boneco.setAlpha(0.45);
      anima({ targets: boneco, alpha: 0.8, duration: 900, yoyo: true, ease: 'Sine.inOut', delay: atraso / 3 });
      anima({ targets: martelo, angle: -35, duration: 260, yoyo: true, ease: 'Quad.in' });
      anima({ targets: bolinha, scale: 1.35, duration: 700, yoyo: true });
    } else if (s === 'dormindo') {
      anima({ targets: boneco, scaleY: 1.015, duration: 2400, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      anima({ targets: cabeca, angle: 4, duration: 2400, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      zzz.y = CABECA_Y - 14;
      anima({ targets: zzz, y: CABECA_Y - 30, alpha: 0, duration: 2200, delay: atraso });
    } else {
      anima({ targets: boneco, scaleY: 1.025, duration: 1500, yoyo: true, ease: 'Sine.inOut', delay: atraso });
      anima({ targets: cabeca, angle: 2.5, duration: 2600, yoyo: true, ease: 'Sine.inOut', delay: atraso });
    }
  }

  // Leva os pés para (nx, ny) na tela, junto com rótulo, área de clique e profundidade.
  function mover(nx, ny) {
    avatar.setPosition(nx, ny).setDepth(PROF_BASE + ny);
    rotulo.setPosition(nx, ny + rotuloDy).setDepth(PROF_ROTULOS + ny);
    alvo?.setPosition(nx, ny - 44).setDepth(PROF_ROTULOS + ny + 1);
  }

  // Sobe/desce o nome (ex.: ao parar ao lado de outro agente).
  function ajustarRotulo(acima) {
    rotuloDy = CABECA_Y - CABECA_R - 26 - acima;
    rotulo.setY(avatar.y + rotuloDy);
  }

  // Passos: balanço do corpo enquanto caminha.
  let passos = [];
  function caminhar(ativo) {
    passos.forEach((t) => t.remove());
    passos = [];
    boneco.y = 0;
    boneco.angle = 0;
    andando = ativo;
    balao.setVisible(statusAtual === 'trabalhando' && !ativo); // sem "digitando" enquanto anda
    if (!ativo) return;
    passos.push(cena.tweens.add({ targets: boneco, y: -3, duration: 160, yoyo: true, repeat: -1, ease: 'Sine.out' }));
    boneco.angle = -4;
    passos.push(cena.tweens.add({ targets: boneco, angle: 4, duration: 320, yoyo: true, repeat: -1, ease: 'Sine.inOut' }));
  }

  // Vira para a esquerda (-1) ou direita (1); o balão acompanha o lado.
  const virar = (sentido) => avatar.setScale(sentido < 0 ? -1 : 1, 1);

  function definirAlfa(alfa) {
    avatar.setAlpha(alfa);
    rotulo.setAlpha(alfa);
  }

  definirStatus(status);
  return {
    objetos: [avatar, rotulo, alvo].filter(Boolean),
    definirStatus, mover, caminhar, virar, definirAlfa, ajustarRotulo, definirPendente,
    destruir: () => {
      caminhar(false);
      pulsoAlerta?.remove();
      animacoes.forEach((t) => t.remove());
      [avatar, rotulo, alvo].forEach((o) => o?.destroy());
    },
  };
}
