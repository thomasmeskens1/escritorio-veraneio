// Escritório Veraneio — grade isométrica, andares e agentes (Phaser).

const TILE_W = 80;
const TILE_H = 40;
const GRADE = 8; // chão de 8x8 tiles
const MESA_ALTURA = 12;

const CORES_STATUS = { dormindo: 0x868e96, disponivel: 0x40c057, trabalhando: 0xf4a261 };

// Layout fixo no front (posição e cor por id); nome/função/status vêm do servidor.
const ANDARES = {
  porao: { nome: 'Porão', cor: 0x495057, agentes: [] },
  terreo: { nome: 'Térreo', cor: 0x52796f, agentes: [] },
  marketing: {
    nome: '1º Andar – Marketing',
    cor: 0x7f6a55,
    agentes: [
      { id: 'designer', nome: 'Designer', x: 1, y: 2, cor: 0xe76f51 },
      { id: 'moviemaker', nome: 'Moviemaker', x: 3, y: 2, cor: 0xf4a261 },
      { id: 'gestor_trafego', nome: 'Gestor de Tráfego', x: 5, y: 2, cor: 0xe9c46a },
      { id: 'gestor', nome: 'Gestor', x: 2, y: 5, cor: 0x2a9d8f },
      { id: 'carpinteiro', nome: 'Carpinteiro', x: 4, y: 5, cor: 0x8ecae6 },
    ],
  },
  cobertura: { nome: 'Cobertura', cor: 0x2b2d42, agentes: [], restrito: true },
};

let jogo = null;
let cena = null;
let andarAtual = 'terreo';
let elementos = []; // objetos do andar renderizado
let estadoAgentes = {}; // último "estado" recebido: { andar: { id: {nome, funcao, status} } }

function podeAcessar(nivel) {
  return !ANDARES[nivel]?.restrito || sessao?.role === 'diretoria';
}

// Junta o layout local com o estado do servidor (nome local como fallback).
function dadosAgente(nivel, id) {
  const local = ANDARES[nivel]?.agentes.find((a) => a.id === id);
  const remoto = estadoAgentes[nivel]?.[id] || {};
  return {
    id,
    nome: remoto.nome || local?.nome || id,
    funcao: remoto.funcao || '',
    status: remoto.status in CORES_STATUS ? remoto.status : 'dormindo',
  };
}

// Converte coordenadas da grade (x, y) para pixels, centralizando o chão.
function isoParaTela(x, y) {
  const origemX = cena.scale.width / 2;
  const origemY = (cena.scale.height - GRADE * TILE_H) / 2;
  return {
    x: origemX + (x - y) * (TILE_W / 2),
    y: origemY + (x + y) * (TILE_H / 2),
  };
}

function pontosLosango(cx, cy, w, h) {
  return [
    { x: cx, y: cy - h / 2 },
    { x: cx + w / 2, y: cy },
    { x: cx, y: cy + h / 2 },
    { x: cx - w / 2, y: cy },
  ];
}

function desenharChao(g, cor) {
  for (let x = 0; x < GRADE; x++) {
    for (let y = 0; y < GRADE; y++) {
      const { x: cx, y: cy } = isoParaTela(x + 0.5, y + 0.5);
      const pontos = pontosLosango(cx, cy, TILE_W, TILE_H);
      g.fillStyle(cor, (x + y) % 2 ? 1 : 0.85); // xadrez sutil
      g.fillPoints(pontos, true);
      g.lineStyle(1, 0x000000, 0.15);
      g.strokePoints(pontos, true);
    }
  }
}

// Mesa = losango no topo + duas faces laterais para dar volume.
function desenharMesa(g, cx, cy) {
  const w = TILE_W * 0.8;
  const h = TILE_H * 0.8;
  const topo = cy - MESA_ALTURA;

  g.fillStyle(0x7f5539);
  g.fillPoints([
    { x: cx - w / 2, y: topo }, { x: cx, y: topo + h / 2 },
    { x: cx, y: cy + h / 2 }, { x: cx - w / 2, y: cy },
  ], true);

  g.fillStyle(0x9c6644);
  g.fillPoints([
    { x: cx + w / 2, y: topo }, { x: cx, y: topo + h / 2 },
    { x: cx, y: cy + h / 2 }, { x: cx + w / 2, y: cy },
  ], true);

  g.fillStyle(0xb08968);
  g.fillPoints(pontosLosango(cx, topo, w, h), true);
}

function criarAgente(agente, nivel, cx, cy) {
  const topo = cy - MESA_ALTURA;
  const dados = dadosAgente(nivel, agente.id);

  const corpo = cena.add.rectangle(cx, topo - 16, 22, 32, agente.cor)
    .setStrokeStyle(2, 0x1b1e24)
    .setDepth(cy)
    .setInteractive({ useHandCursor: true })
    .on('pointerdown', () => abrirChat(nivel, agente.id));

  const rotulo = cena.add.text(cx, topo - 40, dados.nome, {
    fontFamily: 'system-ui, sans-serif',
    fontSize: '12px',
    color: '#e9ecef',
    backgroundColor: 'rgba(0,0,0,0.45)',
    padding: { x: 4, y: 2 },
  }).setOrigin(0.5, 1).setDepth(cy);

  // Bolinha de status no canto do sprite; pulsa enquanto trabalha.
  const status = cena.add.circle(cx + 11, topo - 32, 5, CORES_STATUS[dados.status])
    .setStrokeStyle(2, 0x1b1e24)
    .setDepth(cy + 1);
  if (dados.status === 'trabalhando') {
    cena.tweens.add({ targets: status, scale: 1.5, duration: 600, yoyo: true, repeat: -1 });
  }

  elementos.push(corpo, rotulo, status);
}

// Limpa o andar atual e desenha o andar pedido.
function renderizarAndar(nivel) {
  const andar = ANDARES[nivel];
  if (!cena || !andar || !podeAcessar(nivel)) return;

  elementos.forEach((e) => {
    cena.tweens.killTweensOf(e);
    e.destroy();
  });
  elementos = [];
  andarAtual = nivel;

  // Reduz o zoom em telas estreitas para o chão caber inteiro.
  cena.cameras.main.setZoom(Math.min(1, cena.scale.width / (GRADE * TILE_W + 32)));

  const chao = cena.add.graphics().setDepth(0);
  desenharChao(chao, andar.cor);
  elementos.push(chao);

  // Mesas em ordem de profundidade (fundo → frente).
  const mesas = cena.add.graphics().setDepth(1);
  [...andar.agentes]
    .sort((a, b) => a.x + a.y - (b.x + b.y))
    .forEach((agente) => {
      const { x: cx, y: cy } = isoParaTela(agente.x + 0.5, agente.y + 0.5);
      desenharMesa(mesas, cx, cy);
      criarAgente(agente, nivel, cx, cy);
    });
  elementos.push(mesas);

  atualizarUI(nivel);
}

function atualizarUI(nivel) {
  document.getElementById('andar-atual').textContent = ANDARES[nivel].nome;
  document.querySelectorAll('.andar').forEach((botao) => {
    botao.classList.toggle('ativo', botao.dataset.andar === nivel);
  });
}

// Recebe o estado completo do servidor e redesenha o andar visível.
function aplicarEstado(andares) {
  estadoAgentes = andares || {};
  renderizarAndar(andarAtual);
  atualizarChat();
}

// Ajusta o cadeado dos andares restritos conforme a role da sessão.
function configurarElevador() {
  document.querySelectorAll('.andar').forEach((botao) => {
    if (!ANDARES[botao.dataset.andar]?.restrito) return;
    const liberado = podeAcessar(botao.dataset.andar);
    botao.classList.toggle('bloqueado', !liberado);
    botao.querySelector('.icone').textContent = liberado ? botao.dataset.icone : '🔒';
    botao.title = liberado ? '' : 'Acesso restrito à diretoria';
  });
}

class EscritorioScene extends Phaser.Scene {
  constructor() {
    super('Escritorio');
  }

  create() {
    cena = this;
    this.scale.on('resize', () => renderizarAndar(andarAtual)); // recentraliza
    renderizarAndar(andarAtual);
  }
}

// Criado só após o login, quando o container já tem tamanho.
function iniciarEscritorio() {
  if (jogo) return;
  andarAtual = 'terreo';
  jogo = new Phaser.Game({
    type: Phaser.AUTO,
    parent: 'jogo',
    backgroundColor: '#1b1e24',
    scale: { mode: Phaser.Scale.RESIZE, width: '100%', height: '100%' },
    scene: EscritorioScene,
  });
}

function encerrarEscritorio() {
  if (jogo) jogo.destroy(true);
  jogo = null;
  cena = null;
  elementos = [];
  estadoAgentes = {};
}

document.querySelectorAll('.andar').forEach((botao) => {
  botao.addEventListener('click', () => {
    const nivel = botao.dataset.andar;
    if (!podeAcessar(nivel)) {
      alert('Acesso Negado');
      return;
    }
    renderizarAndar(nivel);
  });
});
