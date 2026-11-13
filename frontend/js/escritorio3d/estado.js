// Escritório 3D (migração do visual, Fase 1, Thomas 13/11/2026): ponte entre a cena 3D (js/escritorio3d/1..6) e o
// sistema. Mantém a MESMA API do antigo escritório 2D (removido em 13/11/2026) que os outros módulos usam — ANDARES, andarAtual,
// estadoAgentes, cena, podeAcessar, dadosAgente, agenteBloqueado, renderizarAndar, aplicarEstado, configurarElevador,
// atualizarPendencias, iniciarEscritorio e encerrarEscritorio — com as mesmas regras (acesso por andar, agentes
// bloqueados, pendências, "Em uso", visitas). Só o desenho muda: nada de servidor, dados ou aprendizado é tocado.

// Layout do 2D (nomes e setores locais como fallback); o resto vem do servidor.
const ANDARES = {
  porao: { nome: 'Porão', agentes: [{ id: 'construtor', nome: 'Construtor', setor: 'oficina' }, { id: 'despachante', nome: 'Despachante', setor: 'operacoes' }] },
  terreo: { nome: 'Térreo', agentes: [{ id: 'recepcionista', nome: 'Recepcionista', setor: 'escola' }, { id: 'professor', nome: 'Professor', setor: 'escola' }] },
  marketing: {
    nome: '1º Andar – Marketing',
    agentes: [['gestor', 'Gestor', 'gestao'], ['designer', 'Designer', 'criacao'], ['criador_imagens', 'Criador de Imagens', 'criacao'],
      ['copywriter', 'Copywriter', 'conteudo'], ['social_media', 'Social Media', 'conteudo'], ['email_marketing', 'E-mail Marketing', 'conteudo'],
      ['analista_tendencias', 'Analista de Tendências', 'reuniao'], ['moviemaker', 'Moviemaker', 'video'], ['editor_video', 'Editor de Vídeo', 'video'],
      ['sonoplasta', 'Sonoplasta', 'video'], ['gestor_trafego', 'Gestor de Tráfego', 'performance'], ['analista_metricas', 'Analista de Métricas', 'performance'],
    ].map(([id, nome, setor]) => ({ id, nome, setor })),
  },
  comercial: { nome: '2º Andar – Comercial', agentes: [{ id: 'prospectador', nome: 'Prospectador', setor: 'corporativo' }, { id: 'estrategista', nome: 'Estrategista', setor: 'reuniao' }] },
  cobertura: {
    nome: 'Cobertura',
    restrito: true,
    agentes: [{ id: 'cerebro', nome: 'Cérebro', setor: 'laboratorio', visual: 'cerebro' },
      ...[1, 2, 3, 4].map((n) => ({ id: `estagiario_${n}`, nome: `Estagiário ${n}`, setor: 'reuniao', tipo: 'estagiario' }))],
  },
};
const CORES_STATUS = { dormindo: 0x868e96, disponivel: 0x40c057, trabalhando: 0xf4a261, construindo: 0x4dabf7 };
const TIPOS_AGENTE = ['ia', 'sistema', 'estagiario'];
const VISUAIS = ['humano', 'cerebro'];
const SCRIPTS_3D = ['vendor/three-0.158.0.min.js', 'js/escritorio3d/1_motor.js', 'js/escritorio3d/2_avatares.js',
  'js/escritorio3d/3_moveis.js', 'js/escritorio3d/4_predio.js', 'js/escritorio3d/5_camera_reuniao.js', 'js/escritorio3d/6_interacao.js', 'js/escritorio3d/7_otimizar.js',
  'js/escritorio3d/tour.js'];

let cena = null; // a cena 3D, depois de carregada (os outros módulos só conferem se ela existe)
let andarAtual = 'terreo';
let estadoAgentes = {}; // último "estado": { andar: { id: {nome, funcao, status, tipo, aparencia, visitando, setor, visual, em_uso, bloqueado} } }
let carregando3d = null;

// ---------- Regras (iguais às do 2D, js/escritorio.js) ----------
function podeAcessar(nivel) {
  if (!Object.keys(estadoAgentes).length) return !ANDARES[nivel]?.restrito || sessao?.role === 'diretoria';
  return Object.values(estadoAgentes[nivel] || {}).some((a) => a.tipo !== 'estagiario');
}

const agenteBloqueado = (nivel, id) => !!estadoAgentes[nivel]?.[id]?.bloqueado;

function lerVisita(v) {
  return v && typeof v === 'object' && ANDARES[v.andar] && typeof v.agente === 'string'
    ? { andar: v.andar, agente: v.agente } : null;
}

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

function clicarAgente(nivel, id) {
  if (!estadoAgentes[nivel]?.[id] && Object.keys(estadoAgentes).length) {
    mostrarToast(nivel, id, 'Você ainda não tem acesso a este agente. Fale com o Thomas para liberar.', 'Sem acesso');
    return;
  }
  if (agenteBloqueado(nivel, id)) {
    mostrarToast(nivel, id, 'Você ainda não tem acesso a este agente. Fale com o Thomas para liberar.', 'Sem acesso');
    return;
  }
  if (andarAtual !== nivel) renderizarAndar(nivel);
  if (typeof abrirAgente === 'function') abrirAgente(nivel, id);
  else abrirChat(nivel, id);
}

// ---------- Elevador (botões do próprio sistema) ----------
function configurarElevador() {
  document.querySelectorAll('.andar').forEach((botao) => {
    const icone = botao.querySelector('.icone');
    if (!botao.dataset.icone) botao.dataset.icone = icone.textContent.trim();
    const liberado = podeAcessar(botao.dataset.andar);
    botao.classList.toggle('bloqueado', !liberado);
    icone.textContent = liberado ? botao.dataset.icone : '🔒';
    botao.title = liberado ? '' : 'Sem acesso a este andar. Fale com o Thomas.';
  });
}

function atualizarUI(nivel) {
  document.getElementById('andar-atual').textContent = ANDARES[nivel].nome;
  document.querySelectorAll('.andar').forEach((botao) => botao.classList.toggle('ativo', botao.dataset.andar === nivel));
}

// No 3D, "renderizar o andar" é abrir o pavimento (a cena já tem o prédio inteiro).
function renderizarAndar(nivel) {
  if (!ANDARES[nivel] || !podeAcessar(nivel)) return;
  andarAtual = nivel;
  atualizarUI(nivel);
  if (cena && window.E3D) window.E3D.focarAndar(nivel);
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

// ---------- Pendências ("!" vermelho), iguais às do 2D ----------
const INTERVALO_PENDENCIAS = 30000;
let pendenciasAgentes = new Set();
let timerPendencias = null;

function aplicarPendencias() {
  window.E3D?.avatares.forEach((a) => window.E3D.definirPendente(a, pendenciasAgentes.has(`${a.andar.id}/${a.id}`)));
}

async function atualizarPendencias() {
  if (!sessao) return;
  timerPendencias ||= setInterval(atualizarPendencias, INTERVALO_PENDENCIAS);
  try {
    const resposta = await fetch('/api/pendencias', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (!resposta.ok) return;
    const dados = await resposta.json();
    pendenciasAgentes = new Set((dados.pendencias || []).map((p) => `${p.andar}/${p.agente}`));
    aplicarPendencias();
  } catch {
    // sem conexão: mantém o que estava
  }
}

// ---------- Estado do servidor -> cena ----------
function aplicarEstado(andares) {
  estadoAgentes = andares || {};
  configurarElevador(); // permissões mudam pelo painel de usuários
  if (cena) sincronizar3d();
  atualizarChat();
}

function sincronizar3d() {
  const E = window.E3D;
  if (!E) return;
  Object.entries(estadoAgentes).forEach(([nivel, agentes]) => Object.keys(agentes || {}).forEach((id) => {
    if (!E.avatares.some((a) => a.id === id)) criarAgenteNovo(nivel, id); // criado pelo Construtor
  }));
  const conhecido = Object.keys(estadoAgentes).length > 0;
  E.avatares.forEach((a) => {
    const nivel = a.andar.id;
    const remoto = estadoAgentes[nivel]?.[a.id];
    if (a.dinamico) a.raiz.visible = !!remoto || !!a.caminho; // agente removido some do prédio
    const d = dadosAgente(nivel, a.id);
    // Andar sem acesso: o prédio inteiro aparece, mas os agentes dele ficam neutros e sem clique.
    const status = remoto || !conhecido ? d.status : 'disponivel';
    if (status !== a.status) E.definirStatus(a, status);
    a.nome = d.nome;
    a.semAcesso = conhecido && (!remoto || agenteBloqueado(nivel, a.id));
    desenharEtiqueta(a, remoto);
    sincronizarVisita(a, remoto ? d : { visitando: null });
  });
  aplicarPendencias();
  const meu = document.getElementById('vista-reuniao');
  if (meu) meu.hidden = !sessao; // Sala de Reunião liberada para todos (Fase 6, Thomas 13/11/2026)
}

// Etiqueta: bolinha de status, nome, "Em uso"/"Trabalhando para" e cadeado (agente sem acesso).
function desenharEtiqueta(a, remoto) {
  if (!a.etiqueta) return;
  const outros = remoto?.em_uso || [];
  const ponto = a.etiqueta.querySelector('.ponto') || document.createElement('i');
  ponto.className = 'ponto';
  ponto.style.background = hex(STATUS[a.status] ?? STATUS.dormindo);
  const partes = [ponto, document.createTextNode(a.nome)];
  if (outros.length) {
    const trabalhando = outros.some((o) => o.acao === 'trabalhando');
    const uso = document.createElement('span');
    uso.className = 'etiqueta-uso';
    uso.textContent = `${trabalhando ? 'Trabalhando para' : 'Em uso:'} ${listaNomes(outros.map((o) => o.nome))}`;
    partes.push(uso);
  }
  a.etiqueta.replaceChildren(...partes);
  a.etiqueta.classList.toggle('bloqueado', !!a.semAcesso);
  a.etiqueta.title = a.semAcesso ? 'Sem acesso a este agente' : a.nome;
  a.etiqueta.disabled = a.id.startsWith('estagiario');
}

// ---------- Visitas: quem está visitando vai até o agente consultado e volta quando termina ----------
function sincronizarVisita(a, d) {
  const chave = d.visitando ? `${d.visitando.andar}/${d.visitando.agente}` : null;
  if ((a.visitaChave || null) === chave) return;
  a.visitaChave = chave;
  const E = window.E3D;
  if (chave) {
    const alvo = E.avatares.find((x) => x.id === d.visitando.agente && x.andar.id === d.visitando.andar);
    const nAlvo = ANDARES_3D.findIndex((x) => x.id === d.visitando.andar);
    const ponto = alvo ? alvo.raiz.position.clone().add(new THREE.Vector3(0.75, 0, 0.35)) : new THREE.Vector3(0, 0, 1.5);
    a.visitando = alvo || true;
    levar(a, nAlvo, ponto, -Math.PI / 2 - 0.3, false);
  } else if (a.visitando) {
    const nCasa = ANDARES_3D.findIndex((x) => x.id === a.andar.id);
    levar(a, nCasa, new THREE.Vector3(a.casa.x, 0, a.casa.z), a.casa.rot || 0, a.casa.sentado, () => { a.visitando = null; });
  }
}

// Leva o avatar até um ponto de outro andar (pelo elevador). Um pedido novo cancela o anterior; se ele estiver
// dentro do elevador, o pedido novo espera a porta abrir.
function levar(a, nDestino, ponto, rot, sentar, aoChegar) {
  const E = window.E3D;
  if (a.noElevador) { a.missaoPendente = [nDestino, ponto, rot, sentar, aoChegar]; a.tokenMov = (a.tokenMov || 0) + 1; return; }
  const token = (a.tokenMov = (a.tokenMov || 0) + 1);
  const valendo = (f) => () => { if (a.tokenMov === token) f(); };
  const final = () => E.andarAte(a, ponto, rot, valendo(() => aoChegar?.()), sentar);
  const nAgora = E.grupos.indexOf(a.raiz.parent?.parent);
  if (nAgora === nDestino || nDestino < 0) { final(); return; }
  E.andarAte(a, E.pontoDoElevador(ANDARES_3D[nAgora]), Math.PI / 2, valendo(() => {
    a.noElevador = true;
    E.trocarDeAndar(a, nDestino, () => {
      a.noElevador = false;
      if (a.tokenMov === token) { final(); return; }
      const pendente = a.missaoPendente;
      a.missaoPendente = null;
      if (pendente) levar(a, ...pendente);
    });
  }));
}

// ---------- Agentes novos (criados pelo Construtor): ocupam a mesa vaga do setor ----------
const PALETAS_3D = {
  pele: ['#ffdbac', '#f1c27d', '#e0ac69', '#c68642', '#a0522d', '#8d5524'],
  cabelo: ['curto', 'longo', 'coque', 'cacheado', 'moicano', 'careca'],
  corCabelo: ['#1b1b1b', '#3b2f2f', '#7b4a12', '#b5651d', '#d8b26e', '#9e9e9e'],
  roupa: ['camisa', 'blazer', 'moletom', 'camiseta'],
  corRoupa: ['#e76f51', '#2a9d8f', '#457b9d', '#6d597a', '#e9c46a', '#3a86ff', '#ff006e'],
  calca: ['#22223b', '#264653', '#3d405b', '#343a40', '#14213d'],
};
function aparencia3d(ap, id) {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const pega = (lista, d) => lista[(h >>> d) % lista.length];
  const cor = (v, padrao) => (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? v : padrao);
  const a = ap && typeof ap === 'object' ? ap : {};
  return [cor(a.pele, pega(PALETAS_3D.pele, 0)), a.cabelo?.estilo || pega(PALETAS_3D.cabelo, 3), cor(a.cabelo?.cor, pega(PALETAS_3D.corCabelo, 6)),
    a.roupa?.estilo || pega(PALETAS_3D.roupa, 9), cor(a.roupa?.cor, pega(PALETAS_3D.corRoupa, 12)), cor(a.calca, pega(PALETAS_3D.calca, 15)), a.acessorio || 'nenhum'];
}

// ---------- Mesas vagas (regra do 2D, mesasComVaga): sempre uma vaga por setor com estação ----------
const chaveMesa = ([x, y]) => `${x},${y}`;

// Na primeira vez, registra as mesas de cada setor e quais já têm estação desenhada (a da placa "Vaga").
function prepararMesas(andar, g) {
  if (g.userData.mesas) return;
  g.userData.mesas = Object.fromEntries(andar.setores.map((s) => [s.id, [...(s.mesas || [])]]));
  g.userData.comEstacao = new Set(andar.setores.filter((s) => g.userData.placas[s.id] && g.userData.livres[s.id]?.length)
    .map((s) => chaveMesa(g.userData.livres[s.id][0])));
}

function montarEstacao(andar, g, setor, mesa) {
  if (g.userData.comEstacao.has(chaveMesa(mesa))) return;
  g.userData.comEstacao.add(chaveMesa(mesa));
  const [x, z] = window.E3D.coord(andar, mesa[0] + 0.5, mesa[1] + 0.5);
  estacao(g.userData.piso, setor.estacao === 'design' ? 'mesa' : setor.estacao, x, z);
}

// Mesma regra do 2D: segue o espaçamento da fileira e, no fim dela, abre uma fileira nova dentro da área.
function acrescentarMesa(andar, g, setor) {
  const mesas = g.userData.mesas[setor.id];
  if (!mesas?.length) return false;
  const [ax, ay, largura, profundidade] = setor.area;
  const passo = mesas.length > 1 && mesas[1][0] > mesas[0][0] ? mesas[1][0] - mesas[0][0] : 2;
  const [ux, uy] = mesas[mesas.length - 1];
  let proxima = [ux + passo, uy];
  if (proxima[0] > ax + largura - 1) proxima = [mesas[0][0], uy + 2];
  const ocupadas = new Set(Object.values(g.userData.mesas).flat().map(chaveMesa));
  andar.agentes.forEach((ag) => ag[5] && ocupadas.add(chaveMesa(ag[5])));
  if (proxima[1] > ay + profundidade - 1 || ocupadas.has(chaveMesa(proxima))) {
    console.warn(`Setor "${setor.nome}" sem espaço para mais uma mesa: ajuste o layout do andar.`);
    return false;
  }
  mesas.push(proxima);
  g.userData.livres[setor.id].push(proxima);
  return true;
}

// Cada mesa livre do setor mostra a estação e a placa "Vaga", como no 2D; placas de mesas ocupadas somem.
function textoVaga(c) {
  c.fillStyle = '#f5efe3'; c.fillRect(0, 0, 128, 48);
  c.fillStyle = '#00361b'; c.font = 'bold 26px Georgia'; c.textAlign = 'center'; c.fillText('Vaga', 64, 34);
}
function mostrarVaga(andar, g, setor) {
  g.userData.placasVaga ||= {};
  const livres = g.userData.livres[setor.id] || [];
  const inicial = g.userData.placas[setor.id]; // a placa criada com o prédio (4_predio.js) fica com a 1ª vaga
  if (inicial && !Object.values(g.userData.placasVaga).includes(inicial) && livres[0]) g.userData.placasVaga[`${setor.id}|${chaveMesa(livres[0])}`] = inicial;
  const ativas = new Set(livres.map((m) => `${setor.id}|${chaveMesa(m)}`));
  Object.entries(g.userData.placasVaga).forEach(([k, placa]) => { if (k.startsWith(`${setor.id}|`)) placa.visible = ativas.has(k); });
  livres.forEach((mesa) => {
    montarEstacao(andar, g, setor, mesa);
    const k = `${setor.id}|${chaveMesa(mesa)}`;
    if (g.userData.placasVaga[k]) return;
    const placa = malha(new THREE.PlaneGeometry(0.5, 0.18), new THREE.MeshBasicMaterial({ map: textura(128, 48, textoVaga) }), 0, 0.95, 0, g.userData.piso, false);
    placa.rotation.x = -0.4;
    const [px, pz] = window.E3D.coord(andar, mesa[0] + 0.5, mesa[1] + 0.5);
    placa.position.set(px, 0.95, pz + 0.95);
    g.userData.placasVaga[k] = placa;
  });
}

// Ao abrir o prédio: todo setor com estação tem ao menos uma vaga, e todas as mesas livres aparecem.
function garantirVagas() {
  const E = window.E3D;
  ANDARES_3D.forEach((andar, n) => {
    const g = E.grupos[n];
    prepararMesas(andar, g);
    andar.setores.filter((s) => s.estacao && s.estacao !== 'nenhuma' && s.mesas?.length).forEach((s) => {
      if (!g.userData.livres[s.id].length) acrescentarMesa(andar, g, s);
      mostrarVaga(andar, g, s);
    });
  });
}

function criarAgenteNovo(nivel, id) {
  const E = window.E3D;
  const n = ANDARES_3D.findIndex((x) => x.id === nivel);
  if (n < 0) return;
  const andar = ANDARES_3D[n], g = E.grupos[n], d = dadosAgente(nivel, id);
  AP[id] ||= aparencia3d(estadoAgentes[nivel][id].aparencia, id);
  prepararMesas(andar, g);
  let setor = andar.setores.find((s) => s.id === d.setor && s.estacao && s.estacao !== 'nenhuma');
  if (setor && !g.userData.livres[setor.id].length) acrescentarMesa(andar, g, setor);
  if (!setor || !g.userData.livres[setor.id].length) setor = andar.setores.find((s) => g.userData.livres[s.id]?.length);
  const lugar = setor ? g.userData.livres[setor.id].shift() : [andar.grade / 2, andar.grade / 2];
  if (setor) {
    montarEstacao(andar, g, setor, lugar);
    // Sempre uma mesa vaga por setor, como no 2D (mesasComVaga): se esta era a última, acrescenta outra.
    if (!g.userData.livres[setor.id].length) acrescentarMesa(andar, g, setor);
    mostrarVaga(andar, g, setor);
  }
  const [x, z] = E.coord(andar, lugar[0] + 0.5, lugar[1] + 0.5);
  const a = E.avatar(id, d.nome, d.status, '', andar);
  a.dinamico = true;
  a.raiz.position.set(x, 0, z - 0.12);
  g.userData.piso.add(a.raiz);
  a.casa = { x, z: z - 0.12, rot: 0, sentado: a.sentado };
  E.criarIndicadores(a);
  E.juntarBoneco?.(a); // desempenho (7_otimizar.js)
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'etiqueta';
  el.hidden = true;
  el.addEventListener('click', () => E.mostrarAgente(a));
  document.getElementById('etiquetas').append(el);
  a.etiqueta = el;
}

// ---------- Início e fim ----------
function montarDom3d() {
  const jogoEl = document.getElementById('jogo');
  if (document.getElementById('cena3d')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'cena3d';
  canvas.setAttribute('aria-label', 'Prédio do Escritório Veraneio em 3D');
  const etiquetas = document.createElement('div');
  etiquetas.id = 'etiquetas';
  etiquetas.className = 'etiquetas';
  const acoes = document.createElement('nav');
  acoes.className = 'acoes-3d';
  acoes.setAttribute('aria-label', 'Vista do prédio');
  [['vista-predio', 'Vista do prédio'], ['vista-reuniao', 'Sala de reunião'], ['girar', 'Girar devagar']].forEach(([id, texto]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.id = id;
    b.className = 'botao-3d';
    b.setAttribute('aria-pressed', 'false');
    b.textContent = texto;
    acoes.append(b);
  });
  acoes.querySelector('#vista-reuniao').hidden = true;
  jogoEl.append(canvas, etiquetas, acoes);
}

function carregarScript(src) {
  return new Promise((ok, falha) => {
    const s = document.createElement('script');
    s.src = src;
    s.async = false;
    s.onload = ok;
    s.onerror = () => falha(new Error(`não carregou ${src}`));
    document.body.append(s);
  });
}

function iniciarEscritorio() {
  document.getElementById('jogo').hidden = false;
  andarAtual = 'terreo';
  if (cena) { sincronizar3d(); window.E3D.focarAndar(null); return; }
  if (carregando3d) return;
  montarDom3d();
  carregando3d = SCRIPTS_3D.reduce((fila, src) => fila.then(() => carregarScript(src)), Promise.resolve())
    .then(() => {
      cena = cena3d;
      garantirVagas();
      sincronizar3d();
    })
    .catch((erro) => {
      console.error(erro);
      carregando3d = null;
      document.getElementById('andar-atual').textContent = 'Não foi possível abrir o prédio 3D. Recarregue a página.';
    });
}

function encerrarEscritorio() {
  estadoAgentes = {};
  pendenciasAgentes = new Set();
  clearInterval(timerPendencias);
  timerPendencias = null;
  if (cena) {
    window.E3D.encerrarReuniao();
    window.E3D.focarAndar(null);
  }
}

