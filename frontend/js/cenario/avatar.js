// Avatar humano (chibi) desenhado proceduralmente a partir do campo `aparencia`.
// Coordenadas locais: (0, 0) são os pés; y negativo sobe.

const CORES_STATUS = { dormindo: 0x868e96, disponivel: 0x40c057, trabalhando: 0xf4a261 };

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
function criarRotulo(cena, x, y, nome, sistema) {
  const texto = cena.add.text(5, 0, sistema ? `⚙ ${nome}` : nome, {
    fontFamily: 'system-ui, sans-serif', fontSize: '12px', color: '#f1f3f5',
  }).setOrigin(0.5);
  const largura = texto.width + 26;
  const fundo = cena.add.graphics();
  fundo.fillStyle(0x15171c, 0.78);
  fundo.fillRoundedRect(-largura / 2, -10, largura, 20, 10);
  fundo.lineStyle(1, sistema ? 0x8ecae6 : 0xffffff, sistema ? 0.55 : 0.12);
  fundo.strokeRoundedRect(-largura / 2, -10, largura, 20, 10);
  const bolinha = cena.add.circle(-largura / 2 + 11, 0, 4.5, CORES_STATUS.dormindo).setStrokeStyle(1.5, 0x15171c);
  const rotulo = cena.add.container(x, y, [fundo, texto, bolinha]).setDepth(PROF_ROTULOS + y);
  return { rotulo, bolinha };
}

// Cria o avatar nos pés (x, y). Retorna objetos e controles de status.
// `escalaRotulo` compensa o zoom da câmera em telas pequenas para o nome continuar legível.
function criarAvatar(cena, x, y, { id, aparencia, nome, tipo, status, aoClicar, escalaRotulo = 1 }) {
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

  const avatar = cena.add.container(x, y, [sombra, boneco, balao, zzz]).setDepth(PROF_BASE + y);
  const { rotulo, bolinha } = criarRotulo(cena, x, y + CABECA_Y - CABECA_R - 26, nome, tipo === 'sistema');
  rotulo.setScale(escalaRotulo);

  // Área de clique generosa: corpo inteiro + rótulo.
  const alvo = cena.add.zone(x, y - 44, 48, 100).setDepth(PROF_ROTULOS + y + 1)
    .setInteractive({ useHandCursor: true });
  alvo.on('pointerdown', aoClicar);
  alvo.on('pointerover', () => rotulo.setScale(escalaRotulo * 1.08));
  alvo.on('pointerout', () => rotulo.setScale(escalaRotulo));

  let animacoes = [];
  const anima = (cfg) => animacoes.push(cena.tweens.add({ repeat: -1, ...cfg }));

  function definirStatus(novoStatus) {
    const s = novoStatus in CORES_STATUS ? novoStatus : 'dormindo';
    animacoes.forEach((t) => t.remove());
    animacoes = [];
    [boneco, bracos, cabeca, balao, zzz, bolinha, ...pontos].forEach((o) => {
      o.setScale(1).setAlpha(1);
    });
    bracos.y = 0;
    cabeca.y = PESCOCO;
    cabeca.angle = 0;
    bolinha.setFillStyle(CORES_STATUS[s]);
    olhosAbertos.setVisible(s !== 'dormindo');
    olhosFechados.setVisible(s === 'dormindo');
    balao.setVisible(s === 'trabalhando');
    zzz.setVisible(s === 'dormindo');
    const atraso = hashTexto(id) % 900; // agentes não respiram em sincronia

    if (s === 'trabalhando') {
      anima({ targets: bracos, y: -2, duration: 130, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: cabeca, y: PESCOCO + 1.2, duration: 420, yoyo: true, ease: 'Sine.inOut', delay: atraso / 3 });
      anima({ targets: boneco, scaleY: 1.02, duration: 700, yoyo: true, ease: 'Sine.inOut' });
      anima({ targets: bolinha, scale: 1.45, duration: 500, yoyo: true });
      pontos.forEach((p, i) => anima({ targets: p, alpha: 0.2, duration: 380, yoyo: true, delay: i * 130 }));
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

  definirStatus(status);
  return { objetos: [avatar, rotulo, alvo], definirStatus };
}