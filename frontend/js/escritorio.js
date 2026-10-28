// Escritório Veraneio — grade isométrica, andares e agentes (Phaser).
// Desenho do cenário, dos setores e dos avatares fica em js/cenario/.

// Layout fixo no front: setor e estação de trabalho por id; o resto vem do servidor.
// No Térreo (escola) as posições são fixas; nos outros andares cada agente ocupa uma mesa
// do seu setor (js/cenario/setores.js), na ordem desta lista.
const ANDARES = {
  porao: {
    nome: 'Porão',
    agentes: [
      { id: 'construtor', nome: 'Construtor', setor: 'oficina', estacao: 'bancada' },
      { id: 'despachante', nome: 'Despachante', setor: 'operacoes', estacao: 'central' },
    ],
  },
  terreo: {
    nome: 'Térreo',
    agentes: [
      { id: 'recepcionista', nome: 'Recepcionista', setor: 'escola', x: 6, y: 3, estacao: 'balcao' },
      { id: 'professor', nome: 'Professor', setor: 'escola', x: 1, y: 2, estacao: 'pulpito' },
    ],
  },
  marketing: {
    nome: '1º Andar – Marketing',
    agentes: [
      { id: 'gestor', nome: 'Gestor', setor: 'gestao', estacao: 'executiva' },
      { id: 'designer', nome: 'Designer', setor: 'criacao', estacao: 'design' },
      { id: 'criador_imagens', nome: 'Criador de Imagens', setor: 'criacao', estacao: 'ilustracao' },
      { id: 'copywriter', nome: 'Copywriter', setor: 'conteudo', estacao: 'redacao' },
      { id: 'social_media', nome: 'Social Media', setor: 'conteudo', estacao: 'social' },
      { id: 'email_marketing', nome: 'E-mail Marketing', setor: 'conteudo', estacao: 'redacao' },
      { id: 'analista_tendencias', nome: 'Analista de Tendências', setor: 'conteudo', estacao: 'social' },
      { id: 'moviemaker', nome: 'Moviemaker', setor: 'video', estacao: 'video' },
      { id: 'editor_video', nome: 'Editor de Vídeo', setor: 'video', estacao: 'edicao' },
      { id: 'gestor_trafego', nome: 'Gestor de Tráfego', setor: 'performance', estacao: 'graficos' },
      { id: 'analista_metricas', nome: 'Analista de Métricas', setor: 'performance', estacao: 'metricas' },
    ],
  },
  // Comercial: Hospedagem (Casa Veraneio, por enquanto só a mesa vaga), Corporativo (Casa Veraneio Corporativo) e
  // o Estrategista (as três empresas) à mesa de Reunião.
  comercial: {
    nome: '2º Andar – Comercial',
    agentes: [
      { id: 'prospectador', nome: 'Prospectador', setor: 'corporativo', estacao: 'executiva' },
      { id: 'estrategista', nome: 'Estrategista', setor: 'reuniao', estacao: 'nenhuma' },
    ],
  },
  // Cérebro (RAG central) e os estagiários que levam o conhecimento aos outros andares.
  cobertura: {
    nome: 'Cobertura',
    restrito: true,
    agentes: [
      { id: 'cerebro', nome: 'Cérebro', setor: 'laboratorio', estacao: 'pedestal', visual: 'cerebro' },
      ...[1, 2, 3, 4].map((n) => ({ id: `estagiario_${n}`, nome: `Estagiário ${n}`, setor: 'reuniao', estacao: 'nenhuma', tipo: 'estagiario' })),
    ],
  },
};

// Espaço ocupado pela interface sobre o canvas (px de tela).
const BARRA_TOPO = 64;
const PAINEL_ELEVADOR = 200; // elevador à esquerda (desktop)
const BARRA_ELEVADOR = 90; // elevador embaixo (telas ≤ 640px)

let jogo = null;
let cena = null;
let andarAtual = 'terreo';
let elementos = []; // objetos do andar renderizado
let avatares = {}; // id -> avatar do andar renderizado
let assinaturaAtual = ''; // agentes/aparências do andar renderizado
let estadoAgentes = {}; // último "estado" recebido: { andar: { id: {nome, funcao, status, tipo, aparencia, visitando, setor, visual} } }
let posicoesAndar = {}; // id -> { x, y } (tile) dos agentes do andar renderizado
let ocupadasAndar = new Set(); // células com móveis/agentes no andar renderizado
let setoresAndar = {}; // setor -> tapete/brilho desenhado no andar renderizado
let setorDosAgentes = {}; // id -> setor da mesa ocupada no andar renderizado

const TIPOS_AGENTE = ['ia', 'sistema', 'estagiario'];
const VISUAIS = ['humano', 'cerebro'];

function podeAcessar(nivel) {
  return !ANDARES[nivel]?.restrito || sessao?.role === 'diretoria';
}

// `visitando` só vale com andar conhecido e id de agente: { andar, agente } ou null.
function lerVisita(v) {
  return v && typeof v === 'object' && ANDARES[v.andar] && typeof v.agente === 'string'
    ? { andar: v.andar, agente: v.agente } : null;
}

// Junta o layout local com o estado do servidor (nome/setor locais como fallback).
function dadosAgente(nivel, id) {
  const local = ANDARES[nivel]?.agentes.find((a) => a.id === id);
  const remoto = estadoAgentes[nivel]?.[id] || {};
  return {
    id,
    nome: remoto.nome || local?.nome || id,
    funcao: remoto.funcao || '',
    status: remoto.status in CORES_STATUS ? remoto.status : 'dormindo',
    tipo: TIPOS_AGENTE.includes(remoto.tipo) ? remoto.tipo : local?.tipo || 'ia',
    aparencia: remoto.aparencia && typeof remoto.aparencia === 'object' ? remoto.aparencia : null,
    visitando: lerVisita(remoto.visitando),
    setor: typeof remoto.setor === 'string' && remoto.setor ? remoto.setor : local?.setor || '',
    visual: VISUAIS.includes(remoto.visual) ? remoto.visual : local?.visual || 'humano',
  };
}

// Agentes que andam pelo prédio (estagiários, ou quem estiver visitando): o avatar
// fica a cargo de js/visitas.js, na estação ou ao lado de quem ele atende.
const ehVisitante = (dados) => dados.tipo === 'estagiario' || !!dados.visitando;

// Estagiários não são interativos (sem área de clique).
function cliqueDoAgente(nivel, id, dados) {
  return dados.tipo === 'estagiario' ? undefined : () => clicarAgente(nivel, id);
}

// Converte coordenadas da grade (x, y) para pixels do mundo, centralizando chão + paredes
// em (largura/2, altura/2); a câmera depois enquadra esse centro na área livre da tela.
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
  const meio = (GRADE - 1) / 2;
  for (let x = 1; x < GRADE; x++) {
    for (let y = 1; y < GRADE; y++) {
      if (ocupadas.has(`${x},${y}`)) continue;
      let vizinhos = 0;
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) vizinhos += ocupadas.has(`${x + dx},${y + dy}`) ? 1 : 0;
      }
      const colisoes = agentes.reduce((soma, a) => soma + sobreposicao(a, { x, y }), 0);
      const custo = vizinhos * 2 + colisoes * 2 + Math.hypot(x - meio, y - meio) + (x === GRADE - 1 || y === GRADE - 1 ? 3 : 0);
      if (!melhor || custo < melhor.custo) melhor = { x, y, custo };
    }
  }
  return melhor;
}

// Ordem estável: a do layout local; ids desconhecidos depois, em ordem alfabética.
function ordenarIds(nivel, ids) {
  const locais = ANDARES[nivel].agentes;
  const ordem = (id) => {
    const i = locais.findIndex((a) => a.id === id);
    return i < 0 ? locais.length : i;
  };
  return [...ids].sort((a, b) => ordem(a) - ordem(b) || a.localeCompare(b));
}

// Mesas do setor garantindo uma vaga: se os agentes ocupam todas, acrescenta mesas seguindo o
// espaçamento da fileira (e depois uma fileira nova) dentro da área. Sem espaço: o layout precisa de ajuste.
function mesasComVaga(setor, agentes, ocupadas) {
  const mesas = [...(setor.mesas || [])];
  if (setor.semVagas || !mesas.length) return mesas;
  const [ax, ay, largura, profundidade] = setor.area;
  const passo = mesas.length > 1 && mesas[1][0] > mesas[0][0] ? mesas[1][0] - mesas[0][0] : 2;
  while (mesas.length < agentes + 1) {
    const [ux, uy] = mesas[mesas.length - 1];
    let proxima = [ux + passo, uy];
    if (proxima[0] > ax + largura - 1) proxima = [mesas[0][0], uy + 2];
    const [px, py] = proxima;
    if (py > ay + profundidade - 1 || ocupadas.has(`${px},${py}`)) {
      console.warn(`Setor "${setor.nome}" sem espaço para mais uma mesa: ajuste o layout do andar.`);
      break;
    }
    mesas.push(proxima);
  }
  return mesas;
}

// Posição e estação de cada agente: mesa do seu setor, posição fixa (Térreo) ou, sem
// nenhuma das duas, uma mesa padrão numa célula livre. Mesas de setor que sobram viram vagas.
function posicionarAgentes(nivel, ocupadas) {
  const locais = ANDARES[nivel].agentes;
  const setores = setoresDoAndar(nivel);
  const ids = idsDoAndar(nivel);
  const livres = {};
  setores.forEach((s) => {
    const agentes = ids.filter((id) => dadosAgente(nivel, id).setor === s.id).length;
    livres[s.id] = mesasComVaga(s, agentes, ocupadas);
    livres[s.id].forEach(([x, y]) => ocupadas.add(`${x},${y}`));
  });
  locais.forEach((a) => a.x !== undefined && ocupadas.add(`${a.x},${a.y}`));

  const posicionados = [];
  const semLugar = [];
  ordenarIds(nivel, ids).forEach((id) => {
    const local = locais.find((a) => a.id === id);
    const setor = setores.find((s) => s.id === dadosAgente(nivel, id).setor);
    const mesa = setor && livres[setor.id].shift();
    if (mesa) {
      const estacao = local?.estacao || setor.estacao || 'mesa';
      posicionados.push({ id, setor: setor.id, estacao, x: mesa[0], y: mesa[1] });
    } else if (local && local.x !== undefined) posicionados.push({ ...local, setor: '' });
    else semLugar.push(id);
  });
  semLugar.forEach((id) => {
    const celula = melhorCelulaLivre(ocupadas, posicionados);
    if (!celula) return; // andar lotado
    ocupadas.add(`${celula.x},${celula.y}`);
    posicionados.push({ id, setor: '', estacao: 'mesa', x: celula.x, y: celula.y });
  });
  const vagas = [];
  setores.forEach((s) => livres[s.id].forEach(([x, y]) => vagas.push(s.semVagas
    ? { x, y, estacao: s.estacao || 'mesa', setor: s.id, semRotulo: true }
    : { x, y, estacao: s.vaga || 'vaga', setor: s.id })));
  return { agentes: posicionados, vagas };
}

// Muda quando entram/saem agentes ou mudam nome/aparência/setor (status não conta).
function assinatura(nivel) {
  return JSON.stringify(idsDoAndar(nivel).sort().map((id) => {
    const dados = dadosAgente(nivel, id);
    const { nome, tipo, aparencia, setor, visual } = dados;
    return [id, nome, tipo, aparencia, setor, visual, ehVisitante(dados)];
  }));
}

// abrirAgente (UI) decide: chat, painel do Despachante ou nada (estagiários).
function clicarAgente(nivel, id) {
  if (typeof abrirAgente === 'function') abrirAgente(nivel, id);
  else abrirChat(nivel, id);
}

function limparAndar() {
  cena.tweens.killAll();
  elementos.forEach((e) => e.destroy());
  elementos = [];
  avatares = {};
  setoresAndar = {};
  setorDosAgentes = {};
  setorDestacado = null;
  limparVisitas();
}

// Área da tela não coberta pela barra do topo e pelo elevador (à esquerda ou embaixo).
// Desconta só o que de fato cobre o canvas, caso o layout já o tenha recuado.
function areaLivre(width, height) {
  const r = cena.game.canvas.getBoundingClientRect();
  const estreita = window.innerWidth <= 640;
  const topo = Math.max(0, BARRA_TOPO - r.top);
  const esquerda = estreita ? 0 : Math.max(0, PAINEL_ELEVADOR - r.left);
  const base = estreita ? Math.max(0, r.bottom - (window.innerHeight - BARRA_ELEVADOR)) : 0;
  return { x: esquerda, y: topo, w: Math.max(1, width - esquerda), h: Math.max(1, height - topo - base) };
}

// Zoom para chão e paredes caberem inteiros (largura e altura), centralizados na área livre.
function enquadrarCamera() {
  const cam = cena.cameras.main;
  const { width, height } = cena.scale;
  const area = areaLivre(width, height);
  const largura = GRADE * TILE_W + 24;
  const altura = GRADE * TILE_H + ALTURA_PAREDE + 12 + 28;
  const zoom = Math.max(0.2, Math.min(1.3, (area.w - 16) / largura, (area.h - 12) / altura));
  cam.setZoom(zoom);
  // Centro do conteúdo no mundo (um pouco acima, pela folga dos rótulos sobre a parede).
  const cx = width / 2, cy = height / 2 - 8;
  cam.setScroll(
    cx - width / 2 - (area.x + area.w / 2 - width / 2) / zoom,
    cy - height / 2 - (area.y + area.h / 2 - height / 2) / zoom,
  );
  return zoom;
}

// Acende os setores com algum agente trabalhando (sem recriar a cena).
function atualizarSetores() {
  const ativos = new Set();
  Object.entries(setorDosAgentes).forEach(([id, setor]) => {
    if (setor && dadosAgente(andarAtual, id).status === 'trabalhando') ativos.add(setor);
  });
  Object.entries(setoresAndar).forEach(([id, reg]) => definirBrilhoSetor(reg, ativos.has(id)));
}

// Limpa o andar atual e desenha o andar pedido.
function renderizarAndar(nivel) {
  if (!cena || !ANDARES[nivel] || !podeAcessar(nivel)) return;
  limparAndar();
  andarAtual = nivel;
  definirGrade(nivel);

  const zoom = enquadrarCamera();
  const escalaRotulo = Math.min(2.2, Math.max(1, 0.9 / zoom)); // nomes legíveis em telas pequenas

  const ctx = {
    cena,
    extras: elementos,
    anima: (cfg) => cena.tweens.add({ repeat: -1, ...cfg }),
  };
  const ocupadas = montarCenario(nivel, ctx);
  setoresAndar = desenharSetores(nivel, ctx, Math.min(1.8, Math.max(1, 0.8 / zoom)));
  distribuirMoveisNosSetores(ctx.moveis);
  posicoesAndar = {};
  ocupadasAndar = ocupadas;

  const { agentes, vagas } = posicionarAgentes(nivel, ocupadas);
  vagas.forEach((v) => registrarObjetosSetor(v.setor, () => desenharVaga(ctx, v, escalaRotulo)));
  agentes.forEach((a) => registrarObjetosSetor(a.setor, () => {
    posicoesAndar[a.id] = { x: a.x, y: a.y };
    setorDosAgentes[a.id] = a.setor;
    desenharEstacao(ctx, a.estacao, a.x, a.y);
    const pos = { x: a.x + AGENTE_NO_TILE, y: a.y + AGENTE_NO_TILE };
    const pes = isoParaTela(pos.x, pos.y);

    const dados = dadosAgente(nivel, a.id);
    if (ehVisitante(dados)) {
      registrarCasa(a.id, pos, escalaRotulo); // avatar fica a cargo de js/visitas.js
      return;
    }
    const avatar = criarBoneco(cena, pes.x, pes.y, {
      ...dados,
      escalaRotulo,
      elevacao: a.estacao === 'pedestal' ? ELEVACAO_PEDESTAL : 0,
      aoClicar: cliqueDoAgente(nivel, a.id, dados),
    });
    avatares[a.id] = avatar;
    elementos.push(...avatar.objetos);
  }));
  atualizarSetores();

  assinaturaAtual = assinatura(nivel);
  sincronizarVisitas(false, escalaRotulo);
  atualizarUI(nivel);
}

// Só troca status/animações, brilho dos setores e anima visitas, sem recriar a cena.
function atualizarStatus() {
  Object.entries(avatares).forEach(([id, avatar]) => avatar.definirStatus(dadosAgente(andarAtual, id).status));
  atualizarSetores();
  sincronizarVisitas(true);
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
    configurarDestaqueSetores();
    this.scale.on('resize', () => renderizarAndar(andarAtual)); // reenquadra
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
    input: { windowEvents: false }, // cliques em popups da interface não chegam ao canvas
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
  posicoesAndar = {};
  ocupadasAndar = new Set();
  setoresAndar = {};
  setorDosAgentes = {};
  setorDestacado = null;
  limparVisitas();
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
