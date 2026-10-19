// Escritório Veraneio — grade isométrica, andares e agentes (Phaser).
// Desenho do cenário e dos avatares fica em js/cenario/.

// Layout fixo no front: posição e estação de trabalho por id; o resto vem do servidor.
const ANDARES = {
  porao: {
    nome: 'Porão',
    agentes: [
      { id: 'construtor', nome: 'Construtor', x: 2, y: 2, estacao: 'bancada' },
      { id: 'despachante', nome: 'Despachante', x: 4, y: 1, estacao: 'central' },
    ],
  },
  terreo: {
    nome: 'Térreo',
    agentes: [
      { id: 'recepcionista', nome: 'Recepcionista', x: 6, y: 3, estacao: 'balcao' },
      { id: 'professor', nome: 'Professor', x: 1, y: 2, estacao: 'pulpito' },
      { id: 'tutora', nome: 'Tutora', x: 4, y: 5, estacao: 'livros' },
    ],
  },
  marketing: {
    nome: '1º Andar – Marketing',
    agentes: [
      { id: 'designer', nome: 'Designer', x: 1, y: 2, estacao: 'design' },
      { id: 'moviemaker', nome: 'Moviemaker', x: 1, y: 5, estacao: 'video' },
      { id: 'gestor_trafego', nome: 'Gestor de Tráfego', x: 3, y: 1, estacao: 'graficos' },
      { id: 'gestor', nome: 'Gestor', x: 5, y: 4, estacao: 'executiva' },
    ],
  },
  cobertura: { nome: 'Cobertura', agentes: [], restrito: true },
};

let jogo = null;
let cena = null;
let andarAtual = 'terreo';
let elementos = []; // objetos do andar renderizado
let avatares = {}; // id -> avatar do andar renderizado
let assinaturaAtual = ''; // agentes/aparências do andar renderizado
let estadoAgentes = {}; // último "estado" recebido: { andar: { id: {nome, funcao, status, tipo, aparencia} } }

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
    tipo: remoto.tipo === 'sistema' ? 'sistema' : 'ia',
    aparencia: remoto.aparencia && typeof remoto.aparencia === 'object' ? remoto.aparencia : null,
  };
}

// Converte coordenadas da grade (x, y) para pixels, centralizando chão + paredes.
function isoParaTela(x, y) {
  const origemX = cena.scale.width / 2;
  const origemY = (cena.scale.height - GRADE * TILE_H + ALTURA_PAREDE) / 2;
  return {
    x: origemX + (x - y) * (TILE_W / 2),
    y: origemY + (x + y) * (TILE_H / 2),
  };
}

// Ids exibidos: os do servidor quando houver estado do andar; senão, o layout local.
function idsDoAndar(nivel) {
  const remoto = estadoAgentes[nivel];
  return remoto ? Object.keys(remoto) : ANDARES[nivel].agentes.map((a) => a.id);
}

// Quanto o rótulo/corpo de um agente em `a` cobre o de `b` na tela (0 = nada).
function sobreposicao(a, b) {
  const coluna = Math.abs((a.x - a.y) - (b.x - b.y));
  const linha = Math.abs((a.x + a.y) - (b.x + b.y));
  return coluna <= 2 && linha <= 4 ? 5 - linha : 0;
}

// Melhor célula livre para um agente sem posição: longe de móveis/agentes, perto do centro.
function melhorCelulaLivre(ocupadas, agentes) {
  let melhor = null;
  for (let x = 1; x < GRADE; x++) {
    for (let y = 1; y < GRADE; y++) {
      if (ocupadas.has(`${x},${y}`)) continue;
      let vizinhos = 0;
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) vizinhos += ocupadas.has(`${x + dx},${y + dy}`) ? 1 : 0;
      }
      const colisoes = agentes.reduce((soma, a) => soma + sobreposicao(a, { x, y }), 0);
      const custo = vizinhos * 2 + colisoes * 2 +Math.hypot(x - 3.5, y - 3.5) + (x === GRADE - 1 || y === GRADE - 1 ? 3 : 0);
      if (!melhor || custo < melhor.custo) melhor = { x, y, custo };
    }
  }
  return melhor;
}

// Posição e estação de cada agente; ids desconhecidos ganham uma mesa padrão numa célula livre.
function posicionarAgentes(nivel, ocupadas) {
  const locais = ANDARES[nivel].agentes;
  locais.forEach((a) => ocupadas.add(`${a.x},${a.y}`));
  const ids = idsDoAndar(nivel);
  const novos = ids.filter((id) => !locais.some((a) => a.id === id)).sort();
  const posicionados = locais.filter((a) => ids.includes(a.id));
  novos.forEach((id) => {
    const celula = melhorCelulaLivre(ocupadas, posicionados);
    if (!celula) return; // andar lotado
    ocupadas.add(`${celula.x},${celula.y}`);
    posicionados.push({ id, estacao: 'mesa', x: celula.x, y: celula.y });
  });
  return posicionados;
}

// Muda quando entram/saem agentes ou mudam nome/aparência (status não conta).
function assinatura(nivel) {
  return JSON.stringify(idsDoAndar(nivel).sort().map((id) => {
    const { nome, tipo, aparencia } = dadosAgente(nivel, id);
    return [id, nome, tipo, aparencia];
  }));
}

function clicarAgente(nivel, id) {
  if (typeof abrirAgente === 'function') abrirAgente(nivel, id);
  else abrirChat(nivel, id);
}

function limparAndar() {
  cena.tweens.killAll();
  elementos.forEach((e) => e.destroy());
  elementos = [];
  avatares = {};
}

// Limpa o andar atual e desenha o andar pedido.
function renderizarAndar(nivel) {
  if (!cena || !ANDARES[nivel] || !podeAcessar(nivel)) return;
  limparAndar();
  andarAtual = nivel;

  // Zoom para chão e paredes caberem inteiros, deixando espaço para o elevador lateral.
  const { width, height } = cena.scale;
  const margem = width > 640 ? 200 : 16;
  const zoom = Math.min(1.3, (width - 2 * margem) / (GRADE * TILE_W), height / (GRADE * TILE_H + ALTURA_PAREDE + 90));
  cena.cameras.main.setZoom(zoom);
  const escalaRotulo = Math.min(1.4, Math.max(1, 0.9 / zoom));

  const ctx = {
    cena,
    extras: elementos,
    anima: (cfg) => cena.tweens.add({ repeat: -1, ...cfg }),
  };
  const ocupadas = montarCenario(nivel, ctx);

  posicionarAgentes(nivel, ocupadas).forEach((a) => {
    const estacao = ESTACOES[a.estacao] || ESTACOES.mesa;
    const pos = { x: a.x + AGENTE_NO_TILE, y: a.y + AGENTE_NO_TILE };
    const pes = isoParaTela(pos.x, pos.y);

    if (estacao.atras) {
      const g = cena.add.graphics().setDepth(PROF_BASE + pes.y - 1);
      estacao.atras(g, a.x, a.y);
      elementos.push(g);
    }
    const frente = cena.add.graphics().setDepth(profundidade(a.x + 1, a.y + 1));
    estacao.frente(frente, a.x, a.y);
    elementos.push(frente);

    const dados = dadosAgente(nivel, a.id);
    const avatar = criarAvatar(cena, pes.x, pes.y, {
      ...dados,
      escalaRotulo,
      aoClicar: () => clicarAgente(nivel, a.id),
    });
    avatares[a.id] = avatar;
    elementos.push(...avatar.objetos);
  });

  assinaturaAtual = assinatura(nivel);
  atualizarUI(nivel);
}

// Só troca status/animações, sem recriar a cena.
function atualizarStatus() {
  Object.entries(avatares).forEach(([id, avatar]) => avatar.definirStatus(dadosAgente(andarAtual, id).status));
}

function atualizarUI(nivel) {
  document.getElementById('andar-atual').textContent = ANDARES[nivel].nome;
  document.querySelectorAll('.andar').forEach((botao) => {
    botao.classList.toggle('ativo', botao.dataset.andar === nivel);
  });
}

// Recebe o estado completo do servidor; recria o andar só se os agentes mudaram.
function aplicarEstado(andares) {
  estadoAgentes = andares || {};
  if (cena) {
    if (assinatura(andarAtual) === assinaturaAtual) atualizarStatus();
    else renderizarAndar(andarAtual);
  }
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
  avatares = {};
  assinaturaAtual = '';
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
