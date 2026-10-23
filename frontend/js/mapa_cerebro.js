// Mapa do Cérebro (diretoria): o conhecimento ativo como uma árvore radial em SVG, sem biblioteca.
// Centro = Cérebro; anéis = empresa → fonte → grupo → documento. Cada setor ocupa o ângulo proporcional ao número
// de documentos (o círculo se deforma conforme a densidade); o raio de cada ponto cresce com o nº de trechos.
// Passar o mouse num ponto acende a linha da raiz até ele e mostra a trilha. Roda do mouse = zoom; arrastar = mover.

const CORES_EMPRESA = { casa_veraneio: '#f4a261', cv_corporativo: '#4dabf7', casa_vero: '#69db7c', '*': '#adb5bd' };
const NS_SVG = 'http://www.w3.org/2000/svg';
const RAIO_ANEL = 150; // distância entre os anéis (unidades do SVG)
const janelaMapa = document.getElementById('mapa-cerebro');
const areaMapa = document.getElementById('mapa-area');
const dicaMapa = document.getElementById('mapa-dica');
let mapaAberto = false;

function svg(tag, atributos = {}) {
  const el = document.createElementNS(NS_SVG, tag);
  Object.entries(atributos).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

async function abrirMapa() {
  if (!sessao || sessao.role !== 'diretoria') return;
  mapaAberto = true;
  janelaMapa.classList.add('aberto');
  areaMapa.replaceChildren(novoEl('p', 'painel-aviso', 'Montando o mapa...'));
  try {
    const resposta = await fetch('/api/cerebro/mapa', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (!resposta.ok) throw new Error(resposta.status);
    desenharMapa(await resposta.json());
  } catch {
    areaMapa.replaceChildren(novoEl('p', 'painel-aviso', 'Não foi possível carregar o mapa do Cérebro.'));
  }
}

function fecharMapa() {
  mapaAberto = false;
  janelaMapa.classList.remove('aberto');
  dicaMapa.hidden = true;
}

// Folhas por nó (peso do ângulo), profundidade e pai: prepara a árvore para o desenho.
function prepararArvore(no, pai = null, profundidade = 0, empresa = null) {
  no.pai = pai;
  no.profundidade = profundidade;
  no.empresa = no.empresa || empresa;
  (no.filhos || []).forEach((f) => prepararArvore(f, no, profundidade + 1, no.empresa));
  no.folhas = no.filhos?.length ? no.filhos.reduce((soma, f) => soma + f.folhas, 0) : 1;
  return no;
}

// Ângulo de cada nó: o setor do pai dividido pelos filhos na proporção das folhas. Na raiz, cada empresa tem um
// mínimo de FATIA_MINIMA do círculo (senão a empresa com mais dados esmaga as outras e os rótulos se sobrepõem).
const FATIA_MINIMA = 0.14;

function posicionar(no, inicio, fim) {
  no.angulo = (inicio + fim) / 2;
  no.raio = no.profundidade * RAIO_ANEL;
  no.x = Math.cos(no.angulo) * no.raio;
  no.y = Math.sin(no.angulo) * no.raio;
  const filhos = no.filhos || [];
  const pesos = filhos.map((f) => (no.profundidade === 0 ? Math.max(f.folhas, no.folhas * FATIA_MINIMA) : f.folhas));
  const total = pesos.reduce((s, p) => s + p, 0) || 1;
  let atual = inicio;
  filhos.forEach((f, i) => {
    const fatia = ((fim - inicio) * pesos[i]) / total;
    posicionar(f, atual, atual + fatia);
    atual += fatia;
  });
}

function trilha(no) {
  const nos = [];
  for (let n = no; n; n = n.pai) nos.unshift(n);
  return nos;
}

function desenharMapa(raiz) {
  prepararArvore(raiz);
  posicionar(raiz, -Math.PI / 2, (3 * Math.PI) / 2);
  const todos = [];
  (function coletar(n) { todos.push(n); (n.filhos || []).forEach(coletar); })(raiz);
  const profundidadeMax = Math.max(...todos.map((n) => n.profundidade));
  const limite = profundidadeMax * RAIO_ANEL + 60;
  const desenho = svg('svg', { viewBox: `${-limite} ${-limite} ${limite * 2} ${limite * 2}`, class: 'mapa-svg',
    role: 'img', 'aria-label': 'Mapa do conhecimento do Cérebro' });
  const camadaLinhas = svg('g');
  const camadaPontos = svg('g');
  desenho.append(camadaLinhas, camadaPontos);

  // anéis de referência
  for (let p = 1; p <= profundidadeMax; p += 1) {
    camadaLinhas.append(svg('circle', { cx: 0, cy: 0, r: p * RAIO_ANEL, class: 'mapa-anel' }));
  }
  const maxTrechos = Math.max(1, ...todos.filter((n) => n.profundidade > 0).map((n) => n.trechos || 1));
  todos.forEach((no) => {
    const cor = CORES_EMPRESA[no.empresa] || '#f8f9fa';
    if (no.pai) {
      // curva suave: sai do pai na direção radial do filho
      const meio = (no.pai.raio + no.raio) / 2;
      const cx = Math.cos(no.angulo) * meio;
      const cy = Math.sin(no.angulo) * meio;
      no.linha = svg('path', { d: `M${no.pai.x},${no.pai.y} Q${cx},${cy} ${no.x},${no.y}`, class: 'mapa-linha', stroke: cor });
      camadaLinhas.append(no.linha);
    }
    const raio = no.profundidade === 0 ? 18 : 2 + 10 * Math.sqrt((no.trechos || 1) / maxTrechos);
    no.ponto = svg('circle', { cx: no.x, cy: no.y, r: raio.toFixed(1), fill: cor, class: `mapa-ponto nivel-${no.profundidade}` });
    no.ponto.addEventListener('mouseenter', (e) => destacar(no, e, true));
    no.ponto.addEventListener('mousemove', (e) => moverDica(e));
    no.ponto.addEventListener('mouseleave', () => destacar(no, null, false));
    camadaPontos.append(no.ponto);
    if (no.profundidade <= 2) { // rótulos só nos anéis internos (empresas e fontes)
      const rotulo = svg('text', { x: no.x, y: no.y - raio - 6, class: `mapa-rotulo nivel-${no.profundidade}` });
      rotulo.textContent = no.nome;
      camadaPontos.append(rotulo);
    }
  });

  const documentos = todos.filter((n) => !n.filhos?.length && n.profundidade > 0).length;
  const resumo = novoEl('div', 'mapa-resumo');
  resumo.append(novoEl('span', null, `${raiz.trechos.toLocaleString('pt-BR')} trechos · ${documentos.toLocaleString('pt-BR')} documentos · `
    + `densidade média ${(raiz.trechos / Math.max(1, documentos)).toFixed(1)} trechos por documento`));
  (raiz.filhos || []).forEach((empresa) => {
    const item = novoEl('span', 'mapa-legenda');
    const bolinha = novoEl('i');
    bolinha.style.background = CORES_EMPRESA[empresa.empresa] || '#f8f9fa';
    item.append(bolinha, `${empresa.nome}: ${empresa.trechos.toLocaleString('pt-BR')}`);
    resumo.append(item);
  });
  areaMapa.replaceChildren(resumo, desenho);
  ativarZoom(desenho, limite);
}

function destacar(no, evento, ligar) {
  janelaMapa.classList.toggle('mapa-focando', ligar);
  trilha(no).forEach((n) => {
    n.linha?.classList.toggle('ativa', ligar);
    n.ponto.classList.toggle('ativo', ligar);
  });
  if (!ligar) {
    dicaMapa.hidden = true;
    return;
  }
  const caminho = trilha(no).map((n) => n.nome).join(' › ');
  const filhos = no.filhos?.length ? ` · ${no.filhos.length} ramificação(ões)` : '';
  dicaMapa.textContent = `${caminho}\n${(no.trechos || 0).toLocaleString('pt-BR')} trecho(s)${filhos}`;
  dicaMapa.hidden = false;
  moverDica(evento);
}

function moverDica(evento) {
  if (!evento || dicaMapa.hidden) return;
  const caixa = janelaMapa.querySelector('.janela').getBoundingClientRect();
  dicaMapa.style.left = `${Math.min(evento.clientX - caixa.left + 14, caixa.width - 320)}px`;
  dicaMapa.style.top = `${evento.clientY - caixa.top + 14}px`;
}

// Zoom na roda do mouse (em torno do cursor) e arrastar para mover, mexendo no viewBox.
function ativarZoom(desenho, limite) {
  let caixa = { x: -limite, y: -limite, w: limite * 2, h: limite * 2 };
  const aplicar = () => desenho.setAttribute('viewBox', `${caixa.x} ${caixa.y} ${caixa.w} ${caixa.h}`);
  desenho.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = desenho.getBoundingClientRect();
    const px = caixa.x + ((e.clientX - r.left) / r.width) * caixa.w;
    const py = caixa.y + ((e.clientY - r.top) / r.height) * caixa.h;
    const fator = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const largura = Math.min(limite * 4, Math.max(limite / 8, caixa.w * fator));
    caixa = { x: px - ((px - caixa.x) * largura) / caixa.w, y: py - ((py - caixa.y) * largura) / caixa.h, w: largura, h: largura };
    aplicar();
  }, { passive: false });
  let arrasto = null;
  desenho.addEventListener('pointerdown', (e) => { arrasto = { x: e.clientX, y: e.clientY, caixa: { ...caixa } }; });
  window.addEventListener('pointerup', () => { arrasto = null; });
  desenho.addEventListener('pointermove', (e) => {
    if (!arrasto) return;
    const r = desenho.getBoundingClientRect();
    caixa = { ...arrasto.caixa, x: arrasto.caixa.x - ((e.clientX - arrasto.x) / r.width) * caixa.w,
      y: arrasto.caixa.y - ((e.clientY - arrasto.y) / r.height) * caixa.h };
    aplicar();
  });
}

function configurarMapa() {
  document.getElementById('abrir-mapa').hidden = sessao?.role !== 'diretoria';
}

document.getElementById('abrir-mapa').addEventListener('click', abrirMapa);
document.getElementById('mapa-fechar').addEventListener('click', fecharMapa);
janelaMapa.addEventListener('click', (e) => { if (e.target === janelaMapa) fecharMapa(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && mapaAberto) fecharMapa(); });
