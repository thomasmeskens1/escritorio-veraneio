// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
const VERDE = 0x00361b, CARAMELO = 0xd9a15b, CREME = 0xf5efe3;
const STATUS = { disponivel: 0x40c057, trabalhando: 0xf4a261, construindo: 0x748ffc, dormindo: 0x868e96 };
const NOME_STATUS = { disponivel: 'Disponível', trabalhando: 'Trabalhando', construindo: 'Em construção', dormindo: 'Pausado' };
const ALTURA = 3.4, LARG = 16, FUNDO = 11, PAREDE_PX = 110;
const reduzir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- Dados reais do escritório (backend/estado.py e frontend/js/cenario/*.js) ----------
// Aparência: [pele, cabelo, cor do cabelo, roupa, cor da roupa, cor da calça, acessório]
const AP = {
  construtor: ['#c68642', 'curto', '#2b1d0e', 'macacao', '#f4a261', '#3d405b', 'capacete'],
  despachante: ['#8d5524', 'careca', '#000000', 'camisa', '#457b9d', '#1d3557', 'fone'],
  recepcionista: ['#ffdbac', 'longo', '#b5651d', 'blazer', '#2a9d8f', '#264653', 'cracha'],
  professor: ['#e0ac69', 'curto', '#9e9e9e', 'camisa', '#6d597a', '#355070', 'oculos'],
  gestor: ['#8d5524', 'curto', '#1b1b1b', 'blazer', '#343a40', '#212529', 'gravata'],
  designer: ['#f1c27d', 'cacheado', '#7b2cbf', 'camiseta', '#e76f51', '#22223b', 'oculos'],
  criador_imagens: ['#f1c27d', 'moicano', '#2a9d8f', 'camiseta', '#ffb703', '#023047', 'lapis'],
  copywriter: ['#c68642', 'longo', '#1b1b1b', 'camisa', '#e5989b', '#6d6875', 'oculos'],
  social_media: ['#ffdbac', 'coque', '#d4a373', 'moletom', '#ff006e', '#3a0ca3', 'fone'],
  email_marketing: ['#e0ac69', 'longo', '#3b2f2f', 'camisa', '#f4a261', '#2b2d42', 'oculos'],
  analista_tendencias: ['#8d5524', 'coque', '#1b1b1b', 'blazer', '#5e548e', '#2b2d42', 'oculos'],
  moviemaker: ['#c68642', 'curto', '#3b2f2f', 'moletom', '#1d3557', '#14213d', 'camera'],
  editor_video: ['#8d5524', 'cacheado', '#1b1b1b', 'moletom', '#264653', '#111111', 'bone'],
  sonoplasta: ['#a0522d', 'longo', '#2b1d0e', 'camiseta', '#e76f51', '#1b263b', 'fone'],
  gestor_trafego: ['#ffdbac', 'moicano', '#d62828', 'camiseta', '#2a9d8f', '#264653', 'fone'],
  analista_metricas: ['#e0ac69', 'curto', '#6f4e37', 'camisa', '#90be6d', '#22333b', 'cracha'],
  prospectador: ['#c68642', 'curto', '#2b1d0e', 'blazer', '#7f5347', '#1b263b', 'cracha'],
  estrategista: ['#f1c27d', 'curto', '#9a9a9a', 'blazer', '#22333b', '#111111', 'oculos'],
  estagiario_1: ['#ffdbac', 'curto', '#6f4e37', 'camisa', '#8ecae6', '#264653', 'cracha'],
  estagiario_2: ['#8d5524', 'coque', '#1b1b1b', 'camisa', '#ffd6a5', '#3d405b', 'cracha'],
  estagiario_3: ['#e0ac69', 'cacheado', '#3b2f2f', 'camisa', '#caffbf', '#22333b', 'cracha'],
  estagiario_4: ['#c68642', 'longo', '#b5651d', 'camisa', '#bdb2ff', '#2b2d42', 'cracha'],
};

// Andares com a grade, setores, agentes, paredes e móveis do 2D (cenarios_setores.js, decoracao.js e setores.js).
const ANDARES_3D = [
  { id: 'porao', nome: 'Porão', sub: 'Operação', grade: 12, chao: 'concreto', corChao: 0x6a6f76, parede: 0x4a4f57,
    setores: [
      { id: 'oficina', nome: 'Oficina', area: [0, 0, 6, 5], cor: 0xf4a261, estacao: 'bancada', mesas: [[2, 1], [4, 1], [2, 3]] },
      { id: 'operacoes', nome: 'Operações', area: [6, 0, 4, 5], cor: 0x4dabf7, estacao: 'central', mesas: [[7, 1], [9, 1], [7, 3]] },
      { id: 'servidores', nome: 'Servidores', area: [0, 6, 5, 6], cor: 0x69db7c },
      { id: 'deposito', nome: 'Depósito', area: [6, 6, 6, 6], cor: 0xadb5bd }],
    agentes: [['construtor', 'Construtor', 'oficina', 'construindo', 'Montando o agente pedido pelo Comercial'],
      ['despachante', 'Despachante', 'operacoes', 'trabalhando', '2 peças na fila do Max']],
    paredes: [['canos', 'esq', 0, 12, 92, 96], ['ferramentas', 'esq', 1.0, 3.6, 36, 80], ['arandela', 'esq', 4.4, 4.4, 84, 84],
      ['painel', 'esq', 7.4, 8.2, 46, 84], ['arandela', 'esq', 9.6, 9.6, 84, 84], ['arandela', 'dir', 1.6, 1.6, 84, 84],
      ['prateleira', 'dir', 2.6, 4.8, 70, 70], ['painel', 'dir', 5.0, 5.7, 42, 82], ['tv', 'dir', 7.1, 9.9, 44, 88], ['elevador', 'dir', 10.2, 11.4, 0, 0, 'P']],
    moveis: [['prototipo', 4, 3], ['caixas', 0, 0, 1], ['rack', 6, 0], ['rack', 0, 6], ['rack', 0, 7], ['rack', 0, 8], ['rack', 0, 9],
      ['rack', 2, 7], ['rack', 2, 8], ['rack', 2, 9], ['caixas', 7, 7], ['caixas', 8, 7, 1], ['caixas', 11, 7], ['tambores', 7, 9],
      ['tambores', 10, 9], ['caixas', 11, 10, 1]] },
  { id: 'terreo', nome: 'Térreo', sub: 'Recepção e escola', grade: 8, chao: 'madeira', corChao: 0xc8a27a, parede: 0xcfc3a8,
    setores: [{ id: 'recepcao', nome: 'Recepção', area: [5, 2, 3, 4], cor: 0xe9c46a }, { id: 'escola', nome: 'Escola', area: [0, 0, 5, 4], cor: 0x8ecae6 },
      { id: 'leitura', nome: 'Canto de leitura', area: [0, 4, 3, 4], cor: 0xb5838d }],
    agentes: [['recepcionista', 'Recepcionista', null, 'disponivel', 'Pronta para o próximo onboarding', [6, 3], 'balcao'],
      ['professor', 'Professor', null, 'trabalhando', 'Revisando um briefing do João', [1, 2], 'pulpito']],
    paredes: [['lousa', 'esq', 1.1, 3.9, 44, 96], ['relogio', 'esq', 4.6, 4.6, 92, 92], ['quadro', 'esq', 5.2, 6.6, 48, 84],
      ['janela', 'dir', 0.7, 2.3, 44, 102], ['janela', 'dir', 2.8, 4.4, 44, 102], ['prateleira', 'dir', 4.8, 5.9, 72, 72], ['elevador', 'dir', 6.2, 7.4, 0, 0, 'T']],
    moveis: [['tapete', 2.6, 0.8, 3.2, 3.6, 0x8ecae6], ['tapete', 6.25, 0.15, 1.1, 0.8, 0x9d0208], ['planta', 0, 0, 1],
      ['tapete', 0.7, 4.3, 1.8, 2.6, 0x6d597a], ['estante', 0, 4], ['estante', 0, 6], ['poltrona', 1, 5, 0x2a9d8f], ['abajur', 1, 4],
      ['mesinha', 1, 6], ['planta', 7, 5], ['carteira', 3, 1], ['carteira', 3, 3], ['carteira', 5, 1], ['carteira', 5, 3]] },
  { id: 'marketing', nome: '1º andar', sub: 'Marketing', grade: 14, chao: 'madeira', corChao: 0x7f6a55, parede: 0x2f4858,
    setores: [
      { id: 'gestao', nome: 'Gestão', area: [0, 0, 5, 4], cor: 0xd4af37, estacao: 'executiva', mesas: [[1, 1], [3, 1]] },
      { id: 'criacao', nome: 'Criação', area: [5, 0, 6, 4], cor: 0xc77dff, estacao: 'design', mesas: [[6, 1], [8, 1], [10, 1]] },
      { id: 'conteudo', nome: 'Conteúdo', area: [0, 5, 6, 4], cor: 0xff8fab, estacao: 'redacao', mesas: [[1, 6], [3, 6], [5, 6]] },
      { id: 'reuniao', nome: 'Reunião', area: [6, 5, 4, 4], cor: 0x8ecae6, estacao: 'nenhuma', mesas: [[6.7, 5.35], [8.7, 5.35]] },
      { id: 'copa', nome: 'Copa', area: [10, 4, 4, 5], cor: 0xe9c46a },
      { id: 'video', nome: 'Vídeo', area: [0, 10, 7, 4], cor: 0xff6b6b, estacao: 'video', mesas: [[1, 11], [3, 11], [5, 11]] },
      { id: 'performance', nome: 'Performance', area: [7, 10, 7, 4], cor: 0x2a9d8f, estacao: 'graficos', mesas: [[8, 11], [10, 11], [12, 11]] }],
    agentes: [['gestor', 'Gestor', 'gestao', 'trabalhando', 'Coordenando o anúncio de diferenciais', null, 'executiva'],
      ['designer', 'Designer', 'criacao', 'disponivel', '', null, 'design'],
      ['criador_imagens', 'Criador de Imagens', 'criacao', 'trabalhando', 'Arte do Lodge 239', null, 'ilustracao'],
      ['copywriter', 'Copywriter', 'conteudo', 'trabalhando', 'Legenda na fila', null, 'redacao'],
      ['social_media', 'Social Media', 'conteudo', 'disponivel', '', null, 'social'],
      ['email_marketing', 'E-mail Marketing', 'conteudo', 'disponivel', 'Rascunho do Brevo espera aprovação', null, 'redacao'],
      ['analista_tendencias', 'Analista de Tendências', 'reuniao', 'trabalhando', 'Feriados de dezembro'],
      ['moviemaker', 'Moviemaker', 'video', 'dormindo', '', null, 'video'],
      ['editor_video', 'Editor de Vídeo', 'video', 'trabalhando', 'Renderizando o Reels 9:16', null, 'edicao'],
      ['sonoplasta', 'Sonoplasta', 'video', 'dormindo', '', null, 'som'],
      ['gestor_trafego', 'Gestor de Tráfego', 'performance', 'trabalhando', 'Campanha de dezembro', null, 'graficos'],
      ['analista_metricas', 'Analista de Métricas', 'performance', 'trabalhando', 'Relatório semanal', null, 'metricas']],
    paredes: [['quadro', 'esq', 1.0, 3.2, 50, 90], ['janela', 'esq', 5.4, 8.6, 42, 102], ['relogio', 'esq', 9.6, 9.6, 92, 92],
      ['tv', 'esq', 10.6, 13.2, 44, 92], ['prateleira', 'dir', 0.8, 3.6, 74, 74], ['moodboard', 'dir', 5.6, 10.4, 42, 96],
      ['arandela', 'dir', 11.2, 11.2, 90, 90], ['elevador', 'dir', 12.2, 13.4, 0, 0, '1']],
    moveis: [['tapete', 12.25, 0.15, 1.1, 0.8, 0x264653], ['planta', 0, 0, 1], ['planta', 4, 0], ['mesaReuniao', 6.5, 5.5],
      ['cadeirasFrente', 6.5, 6.9], ['cafeteira', 10, 4], ['bebedouro', 13, 4], ['sofa', 11, 5, 0x6d597a], ['mesinha', 11.5, 6.1],
      ['poltrona', 13, 6.5, 0xe76f51], ['planta', 13, 8], ['planta', 13, 13]] },
  { id: 'comercial', nome: '2º andar', sub: 'Comercial', grade: 12, chao: 'madeira', corChao: 0x6b5a48, parede: 0x1f3b36,
    setores: [
      { id: 'hospedagem', nome: 'Hospedagem', area: [0, 0, 6, 5], cor: 0xe9c46a, estacao: 'mesa', mesas: [[1, 1], [3, 1], [1, 3]] },
      { id: 'corporativo', nome: 'Corporativo', area: [6, 0, 4, 5], cor: 0x2a9d8f, estacao: 'executiva', mesas: [[7, 1], [9, 1], [7, 3]] },
      { id: 'reuniao', nome: 'Reunião', area: [0, 6, 6, 6], cor: 0x8ecae6, estacao: 'nenhuma', mesas: [[1.7, 7.35], [3.7, 7.35]] },
      { id: 'lounge', nome: 'Lounge', area: [7, 6, 5, 6], cor: 0xd4af37 }],
    agentes: [['prospectador', 'Prospectador', 'corporativo', 'trabalhando', 'Prévia de 20 leads corporativos', null, 'executiva'],
      ['estrategista', 'Estrategista', 'reuniao', 'trabalhando', 'Matriz BCG da Casa Vero']],
    paredes: [['quadro', 'esq', 1.0, 3.4, 50, 90], ['janela', 'esq', 4.6, 8.4, 42, 102], ['relogio', 'esq', 9.6, 9.6, 92, 92],
      ['tv', 'dir', 1.0, 4.0, 44, 92], ['prateleira', 'dir', 5.0, 8.6, 74, 74], ['arandela', 'dir', 9.4, 9.4, 90, 90], ['elevador', 'dir', 10.2, 11.4, 0, 0, '2']],
    moveis: [['tapete', 10.2, 0.12, 1.2, 0.6, 0x00361b], ['planta', 0, 0, 1], ['planta', 5, 0], ['mesaReuniao', 1.5, 7.5],
      ['cadeirasFrente', 1.5, 8.9], ['planta', 5, 11], ['cafeteira', 8, 6], ['sofa', 8, 8, 0x00361b], ['mesinha', 8.5, 9.1],
      ['poltrona', 11, 9, 0xd9a15b], ['planta', 11, 11, 1]] },
  { id: 'cobertura', nome: 'Cobertura', sub: 'Cérebro', grade: 12, chao: 'marmore', corChao: 0x2b2d42, parede: 0x1f2235,
    setores: [
      { id: 'reuniao', nome: 'Conselho', area: [1, 1, 8, 4], cor: 0x8ecae6, estacao: 'nenhuma', mesas: [[2.2, 1.45], [4.2, 1.45], [5.2, 1.45], [7.2, 1.45]] },
      { id: 'laboratorio', nome: 'Laboratório', area: [0, 6, 6, 6], cor: 0xff8fab }],
    agentes: [['estagiario_1', 'Estagiário 1', 'reuniao', 'trabalhando', 'Levando a ficha do Lodge 64'],
      ['estagiario_2', 'Estagiário 2', 'reuniao', 'disponivel', ''], ['estagiario_3', 'Estagiário 3', 'reuniao', 'trabalhando', ''],
      ['estagiario_4', 'Estagiário 4', 'reuniao', 'dormindo', '']],
    paredes: [['janela', 'esq', 0.5, 5.6, 26, 108], ['formulas', 'esq', 6.2, 8.8, 44, 108], ['mapa', 'esq', 9.2, 11.7, 62, 108],
      ['janela', 'dir', 0.5, 9.4, 26, 108], ['elevador', 'dir', 10.2, 11.4, 0, 0, 'C']],
    moveis: [['planta', 0, 0, 1], ['mesaReuniao', 2, 1.6], ['mesaReuniao', 5, 1.6], ['cadeirasFrente', 2, 3], ['cadeirasFrente', 5, 3],
      ['bar', 0, 2.5], ['bancadaLab', 0, 6.4], ['tanque', 1, 6, 0x63e6be, 1], ['monitoresCerebro', 2, 6], ['tanque', 4, 6, 0xc77dff],
      ['cerebro', 3, 9], ['poltrona', 9, 4, 0x7f5539], ['mesinha', 10, 4], ['poltrona', 10, 5, 0x7f5539], ['abajur', 11, 3], ['planta', 6, 11, 1]] },
];

// ---------- Motor ----------
const canvas = document.getElementById('cena3d');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
const cena3d = new THREE.Scene();
cena3d.background = new THREE.Color(0xcfe3ea);
cena3d.fog = new THREE.Fog(0xcfe3ea, 90, 190);
const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 500);
cena3d.add(new THREE.HemisphereLight(0xfff7e6, 0x6f8f5a, 0.85));
const sol = new THREE.DirectionalLight(0xfff1d6, 1.7);
sol.position.set(-30, 48, 26);
sol.castShadow = true;
sol.shadow.mapSize.set(2048, 2048);
Object.assign(sol.shadow.camera, { left: -32, right: 32, top: 32, bottom: -32, near: 1, far: 130 });
sol.shadow.bias = -0.0004;
sol.shadow.normalBias = 0.02;
cena3d.add(sol);

const cacheMat = new Map();
function mat(cor, extra = null) {
  const chave = extra ? null : cor;
  if (chave !== null && cacheMat.has(chave)) return cacheMat.get(chave);
  const m = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.8, metalness: 0, ...(extra || {}) });
  if (chave !== null) cacheMat.set(chave, m);
  return m;
}
const brilho = (cor, intensidade = 0.8) => mat(cor, { emissive: cor, emissiveIntensity: intensidade, roughness: 0.4 });
function malha(geo, material, x = 0, y = 0, z = 0, pai = null, sombra = true) {
  const m = new THREE.Mesh(geo, material);
  m.position.set(x, y, z);
  m.castShadow = sombra;
  m.receiveShadow = true;
  if (pai) pai.add(m);
  return m;
}
const caixa = (l, a, p, material, x, y, z, pai, sombra) => malha(new THREE.BoxGeometry(l, a, p), material, x, y, z, pai, sombra);
const cilindro = (r1, r2, a, material, x, y, z, pai, lados = 16) => malha(new THREE.CylinderGeometry(r1, r2, a, lados), material, x, y, z, pai);
const esfera = (r, material, x, y, z, pai, l = 16, h = 12) => malha(new THREE.SphereGeometry(r, l, h), material, x, y, z, pai);

// Texturas desenhadas em canvas (sem arquivos externos).
function textura(l, a, desenhar, repetir = null) {
  const c = document.createElement('canvas');
  c.width = l; c.height = a;
  desenhar(c.getContext('2d'), l, a);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  if (repetir) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repetir); }
  return t;
}
const hex = (n) => `#${n.toString(16).padStart(6, '0')}`;
function tom(cor, f) {
  const c = new THREE.Color(cor);
  return c.multiplyScalar(f).getHex();
}
let semente = 7;
const acaso = () => ((semente = (semente * 16807) % 2147483647) / 2147483647);
const PISOS = {
  madeira: (cor) => textura(512, 512, (g, l, a) => {
    for (let y = 0; y < a; y += 32) for (let x = -(y % 96); x < l; x += 192) {
      g.fillStyle = hex(tom(cor, 0.88 + acaso() * 0.24));
      g.fillRect(x, y, 192, 32);
      g.strokeStyle = 'rgba(0,0,0,0.18)';
      g.strokeRect(x + 0.5, y + 0.5, 192, 32);
      g.strokeStyle = 'rgba(0,0,0,0.05)';
      for (let k = 0; k < 3; k++) { g.beginPath(); g.moveTo(x, y + 8 + k * 8 + acaso() * 3); g.lineTo(x + 192, y + 8 + k * 8 + acaso() * 3); g.stroke(); }
    }
  }, [3, 2]),
  concreto: (cor) => textura(256, 256, (g, l, a) => {
    g.fillStyle = hex(cor); g.fillRect(0, 0, l, a);
    for (let k = 0; k < 2600; k++) { g.fillStyle = `rgba(${acaso() > 0.5 ? '255,255,255' : '0,0,0'},${acaso() * 0.08})`; g.fillRect(acaso() * l, acaso() * a, 2, 2); }
    g.strokeStyle = 'rgba(0,0,0,0.25)'; g.strokeRect(0.5, 0.5, l - 1, a - 1);
  }, [4, 3]),
  marmore: (cor) => textura(512, 512, (g, l, a) => {
    g.fillStyle = hex(cor); g.fillRect(0, 0, l, a);
    g.strokeStyle = 'rgba(212,175,55,0.35)'; g.lineWidth = 1.5;
    for (let k = 0; k < 14; k++) {
      g.beginPath(); let x = acaso() * l, y = 0; g.moveTo(x, y);
      while (y < a) { x += (acaso() - 0.5) * 60; y += 20 + acaso() * 30; g.lineTo(x, y); }
      g.stroke();
    }
    g.strokeStyle = 'rgba(255,255,255,0.08)'; g.lineWidth = 2;
    for (let x = 0; x <= l; x += 128) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, a); g.stroke(); g.beginPath(); g.moveTo(0, x); g.lineTo(l, x); g.stroke(); }
  }, [2, 1.5]),
};
// Telas dos monitores
const TELAS = {
  codigo: textura(128, 80, (g) => { g.fillStyle = '#14202b'; g.fillRect(0, 0, 128, 80); ['#57c98a', '#8ecae6', '#d9a15b', '#c77dff'].forEach((c, i) => { for (let k = 0; k < 4; k++) { g.fillStyle = c; g.fillRect(8 + (k % 2) * 10, 8 + (i * 4 + k) * 4, 30 + acaso() * 60, 2); } }); }),
  grafico: textura(128, 80, (g) => { g.fillStyle = '#10232a'; g.fillRect(0, 0, 128, 80); g.fillStyle = '#2a9d8f'; for (let k = 0; k < 8; k++) { const h = 10 + acaso() * 50; g.fillRect(10 + k * 14, 70 - h, 9, h); } g.strokeStyle = '#d9a15b'; g.lineWidth = 2; g.beginPath(); for (let k = 0; k < 9; k++) g.lineTo(8 + k * 14, 50 - acaso() * 35); g.stroke(); }),
  arte: textura(128, 80, (g) => { const gr = g.createLinearGradient(0, 0, 128, 80); gr.addColorStop(0, '#f4a261'); gr.addColorStop(1, '#00361b'); g.fillStyle = gr; g.fillRect(0, 0, 128, 80); g.fillStyle = '#f5efe3'; g.fillRect(14, 50, 60, 6); g.fillRect(14, 60, 40, 4); g.beginPath(); g.arc(96, 28, 14, 0, 7); g.fill(); }),
  video: textura(128, 80, (g) => { g.fillStyle = '#1b1b22'; g.fillRect(0, 0, 128, 80); g.fillStyle = '#4d7c8a'; g.fillRect(6, 6, 74, 42); ['#e76f51', '#2a9d8f', '#d9a15b', '#8ecae6'].forEach((c, i) => { g.fillStyle = c; g.fillRect(6 + i * 28, 56 + (i % 2) * 8, 24, 6); }); g.fillStyle = '#e0645a'; g.fillRect(40, 52, 2, 26); }),
  onda: textura(128, 80, (g) => { g.fillStyle = '#16161d'; g.fillRect(0, 0, 128, 80); g.strokeStyle = '#ff8fab'; g.lineWidth = 2; g.beginPath(); for (let x = 0; x < 128; x += 2) g.lineTo(x, 40 + Math.sin(x / 5) * (8 + acaso() * 18)); g.stroke(); }),
  social: textura(128, 80, (g) => { g.fillStyle = '#fafafa'; g.fillRect(0, 0, 128, 80); for (let k = 0; k < 6; k++) { g.fillStyle = ['#e76f51', '#2a9d8f', '#d9a15b', '#c77dff', '#8ecae6', '#ff006e'][k]; g.fillRect(8 + (k % 3) * 38, 8 + Math.floor(k / 3) * 36, 34, 32); } }),
  cerebro: textura(128, 80, (g) => { g.fillStyle = '#071a24'; g.fillRect(0, 0, 128, 80); ['#66d9e8', '#ff8fab', '#63e6be'].forEach((c, i) => { g.strokeStyle = c; g.lineWidth = 1.5; g.beginPath(); for (let x = 0; x < 128; x += 2) g.lineTo(x, 16 + i * 24 + Math.sin(x / (3 + i)) * (4 + acaso() * 6)); g.stroke(); }); }),
  mapa: textura(128, 80, (g) => { g.fillStyle = '#0c1430'; g.fillRect(0, 0, 128, 80); g.strokeStyle = 'rgba(123,156,255,0.7)'; for (let k = 0; k < 24; k++) { g.beginPath(); g.moveTo(64, 40); g.lineTo(acaso() * 128, acaso() * 80); g.stroke(); } g.fillStyle = '#9fb8ff'; for (let k = 0; k < 24; k++) g.fillRect(acaso() * 128, acaso() * 80, 3, 3); }),
};
const telaMat = new Map();
const matTela = (nome) => telaMat.get(nome) || telaMat.set(nome, new THREE.MeshStandardMaterial({ map: TELAS[nome], emissive: 0xffffff, emissiveMap: TELAS[nome], emissiveIntensity: 0.55, roughness: 0.3 })).get(nome);

// ---------- Entorno ----------
const gramaTex = textura(256, 256, (g, l, a) => { g.fillStyle = '#86b964'; g.fillRect(0, 0, l, a); for (let k = 0; k < 3000; k++) { g.fillStyle = `rgba(${acaso() > 0.5 ? '40,90,30' : '190,220,140'},${acaso() * 0.18})`; g.fillRect(acaso() * l, acaso() * a, 2, 3); } }, [40, 40]);
const chao = malha(new THREE.PlaneGeometry(260, 260), new THREE.MeshStandardMaterial({ map: gramaTex, roughness: 1 }), 0, 0, 0, cena3d, false);
chao.rotation.x = -Math.PI / 2;
caixa(260, 0.05, 7, mat(0x45494c), 0, 0.03, 17, cena3d, false);
for (let x = -120; x < 120; x += 6) caixa(2.4, 0.06, 0.22, mat(0xf2efe6), x, 0.07, 17, cena3d, false);
caixa(260, 0.14, 2.4, mat(0xd9d3c4), 0, 0.07, 12.3, cena3d, false);
const pisoExt = textura(256, 256, (g, l, a) => { g.fillStyle = '#e6dfd0'; g.fillRect(0, 0, l, a); g.strokeStyle = 'rgba(0,0,0,0.09)'; for (let k = 0; k <= l; k += 32) { g.beginPath(); g.moveTo(k, 0); g.lineTo(k, a); g.stroke(); g.beginPath(); g.moveTo(0, k); g.lineTo(l, k); g.stroke(); } }, [7, 5]);
caixa(30, 0.1, 22, new THREE.MeshStandardMaterial({ map: pisoExt, roughness: 0.9 }), 1, 0.05, 0, cena3d, false);
caixa(4, 0.12, 4.2, mat(0xe6dfd0), 0, 0.06, 13.4, cena3d, false); // acesso da calçada
const piscina = caixa(9, 0.1, 4.5, mat(0x3fa9d6, { roughness: 0.08, metalness: 0.15, emissive: 0x1d6f95, emissiveIntensity: 0.15 }), 21, 0.12, -2, cena3d, false);
caixa(10.4, 0.12, 5.9, mat(0xf0ebe0), 21, 0.06, -2, cena3d, false);
for (let i = 0; i < 4; i++) {
  const e = caixa(0.8, 0.12, 1.9, mat(CREME), 17.4 + i * 2.4, 0.32, 2.4, cena3d);
  e.rotation.x = -0.1;
  cilindro(0.04, 0.04, 2.2, mat(0x8a7a66), 17.4 + i * 2.4 + 0.9, 1.1, 2.4, cena3d, 6);
  const guarda = malha(new THREE.ConeGeometry(1, 0.4, 8), mat(i % 2 ? CARAMELO : CREME), 17.4 + i * 2.4 + 0.9, 2.2, 2.4, cena3d);
  guarda.castShadow = true;
}
function arvore(x, z, e = 1) {
  cilindro(0.16 * e, 0.24 * e, 1.8 * e, mat(0x7a5536), x, 0.9 * e, z, cena3d, 7);
  [[0, 2.5, 0, 1.25], [0.5, 2.1, 0.3, 0.9], [-0.5, 2.2, -0.2, 0.95], [0.1, 3.1, -0.1, 0.85]].forEach(([dx, dy, dz, r], k) =>
    malha(new THREE.IcosahedronGeometry(r * e, 1), mat(k % 2 ? 0x4f8f45 : 0x5d9e4f, { flatShading: true, roughness: 1 }), x + dx * e, dy * e, z + dz * e, cena3d));
}
function palmeira(x, z) {
  for (let k = 0; k < 6; k++) cilindro(0.17 - k * 0.012, 0.19 - k * 0.012, 0.9, mat(0x9b7653), x + k * 0.06, 0.45 + k * 0.85, z, cena3d, 7);
  for (let k = 0; k < 7; k++) {
    const folha = caixa(0.35, 0.04, 2.6, mat(0x4c8a3a), 0, 0, 0, null);
    folha.position.set(x + 0.36, 5.3, z);
    folha.rotation.set(0.5, (k / 7) * Math.PI * 2, 0);
    folha.translateZ(1.1);
    cena3d.add(folha);
  }
}
[[-17, -8, 1.2], [-20, 1, 1], [-16, 7, 0.9], [-25, -12, 1.4], [8, -15, 1], [-6, -16, 1.2], [32, -14, 1.3], [-31, 5, 1.1], [30, 6, 1]].forEach(([x, z, e]) => arvore(x, z, e));
[[15, -6], [27, -6], [15.5, 3.8], [12.5, 9.5], [-12, 9.5]].forEach(([x, z]) => palmeira(x, z));
for (let x = -110; x < 110; x += 12) arvore(x, 22, 0.8);
for (let x = -42; x <= 42; x += 12) {
  cilindro(0.06, 0.08, 3.4, mat(0x2b2b2b), x, 1.7, 13.2, cena3d, 6);
  caixa(0.9, 0.08, 0.22, mat(0x2b2b2b), x + 0.35, 3.4, 13.2, cena3d);
  caixa(0.4, 0.05, 0.16, brilho(0xfff1c1, 0.4), x + 0.6, 3.34, 13.2, cena3d);
}
[[-9, 9.6], [-6, 9.6], [6, 9.6], [9, 9.6]].forEach(([x, z]) => { // floreiras da entrada
  caixa(2.2, 0.6, 1, mat(0xd8d0c0), x, 0.3, z, cena3d);
  for (let k = 0; k < 4; k++) esfera(0.32, mat(k % 2 ? 0x5d9e4f : 0x6fae55, { flatShading: true }), x - 0.75 + k * 0.5, 0.8, z, cena3d, 7, 5);
});
const carros = [];
[[0xd9a15b, -30, 15.4, 1], [0xf5efe3, 10, 15.4, 1], [0x2f4858, 40, 18.6, -1], [0x00361b, -5, 18.6, -1], [0x9d0208, 70, 18.6, -1]].forEach(([cor, x, z, sentido]) => {
  const carro = new THREE.Group();
  caixa(3.8, 0.7, 1.75, mat(cor, { roughness: 0.35, metalness: 0.35 }), 0, 0.62, 0, carro);
  caixa(2.1, 0.62, 1.55, mat(0x26343c, { roughness: 0.15, metalness: 0.5 }), -0.2, 1.24, 0, carro);
  [[-1.2, 0.85], [1.2, 0.85], [-1.2, -0.85], [1.2, -0.85]].forEach(([dx, dz]) => {
    const roda = cilindro(0.34, 0.34, 0.24, mat(0x1c1c1c), dx, 0.34, dz, carro, 14);
    roda.rotation.x = Math.PI / 2;
  });
  caixa(0.06, 0.18, 0.4, brilho(0xfff6d5, 0.6), 1.92, 0.7, 0.55, carro);
  caixa(0.06, 0.18, 0.4, brilho(0xfff6d5, 0.6), 1.92, 0.7, -0.55, carro);
  carro.position.set(x, 0, z);
  carro.rotation.y = sentido > 0 ? 0 : Math.PI;
  carro.userData.sentido = sentido;
  cena3d.add(carro);
  carros.push(carro);
});
