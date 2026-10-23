// Mapa do Cérebro (diretoria): o conhecimento ativo desenhado como um cérebro, em SVG, sem biblioteca.
// Dois hemisférios: a empresa com mais documentos ocupa o de cima, as outras dividem o de baixo, cada uma na sua
// região. Os pontos (fonte → grupo → documento) se acomodam por uma pequena simulação de forças — molas nas
// ligações, colisão entre pontos e a silhueta do cérebro como limite —, o que dá o aspecto orgânico; o raio de
// cada documento cresce com o nº de trechos. Passar o mouse acende a trilha da raiz até o ponto, com impulsos
// correndo por ela; sinapses aleatórias mantêm o cérebro "vivo". Roda do mouse = zoom; arrastar = mover.
// O movimento é feito em JavaScript (não depende das animações do sistema estarem ligadas). A forma e a
// acomodação dos pontos ficam em js/mapa_forma.js.

// Neon (visual cyberpunk): cada empresa com a sua cor; o brilho vem do filtro #neon do SVG.
const CORES_EMPRESA = { casa_veraneio: '#ff9f1c', cv_corporativo: '#00e5ff', casa_vero: '#39ff14', '*': '#d16bff' };
const NS_SVG = 'http://www.w3.org/2000/svg';
const RAIO_TOQUE = 16; // px de tolerância do mouse em volta de um ponto
const VELOCIDADE = 0.45; // unidades do SVG por ms, dos impulsos na trilha
const janelaMapa = document.getElementById('mapa-cerebro');
const areaMapa = document.getElementById('mapa-area');
const dicaMapa = document.getElementById('mapa-dica');
const movimentoReduzido = matchMedia('(prefers-reduced-motion: reduce)');
let mapaAberto = false;
let mapa = null; // estado do desenho aberto

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
  if (mapa) cancelAnimationFrame(mapa.quadro);
  mapa = null;
}

function trilha(no) {
  const nos = [];
  for (let n = no; n; n = n.pai) nos.unshift(n);
  return nos;
}

// ---------- Desenho ----------
function desenharMapa(raiz) {
  if (mapa) cancelAnimationFrame(mapa.quadro);
  prepararArvore(raiz);
  definirRegioes(raiz.filhos || []);
  const todos = [];
  (function coletar(n) { n.indice = todos.length; todos.push(n); (n.filhos || []).forEach(coletar); })(raiz);
  const folhas = todos.filter((n) => !n.filhos?.length && n.profundidade > 0);
  const maxTrechos = Math.max(1, ...folhas.map((n) => n.trechos || 1));
  const variacao = sorteio(11);
  todos.forEach((no) => {
    no.raio = no.filhos?.length ? RAIO_POR_NIVEL[Math.min(no.profundidade, 3)] : 2 + 4 * Math.sqrt((no.trechos || 1) / maxTrechos);
    no.folga = no.raio + 4;
    const base = MOLA[Math.min(no.profundidade, MOLA.length - 1)];
    // cada ligação com um comprimento um pouco diferente: os grupos viram nuvens, não anéis
    no.mola = (no.profundidade === 2 ? Math.min(base, no.regiao.alcance * 0.55) : base)
      * (0.6 + 0.2 * Math.sqrt(no.pai?.filhos.length || 1)) * (0.45 + variacao());
    no.cor = CORES_EMPRESA[no.empresa] || '#f8f9fa';
  });
  acomodar(todos);

  const meiaAltura = FISSURA / 2 + MEIA_ALTURA / ACHATAMENTO + MEIA_ALTURA * 1.11 + 80;
  const meiaLargura = MEIA_LARGURA * 1.11 + 50;
  const caixa = { x: -meiaLargura, y: -meiaAltura, w: meiaLargura * 2, h: meiaAltura * 2 };
  const desenho = svg('svg', { viewBox: `${caixa.x} ${caixa.y} ${caixa.w} ${caixa.h}`, class: 'mapa-svg',
    role: 'img', 'aria-label': 'Mapa do conhecimento do Cérebro' });
  const defs = svg('defs');
  // Brilho neon: o desenho desfocado por baixo do original.
  const filtro = svg('filter', { id: 'neon', x: '-50%', y: '-50%', width: '200%', height: '200%' });
  filtro.append(svg('feGaussianBlur', { stdDeviation: '3', result: 'desfoque' }));
  const juntar = svg('feMerge');
  juntar.append(svg('feMergeNode', { in: 'desfoque' }), svg('feMergeNode', { in: 'desfoque' }), svg('feMergeNode', { in: 'SourceGraphic' }));
  filtro.append(juntar);
  const massa = svg('radialGradient', { id: 'mapa-massa' });
  massa.append(svg('stop', { offset: '0%', 'stop-color': '#2a1145' }), svg('stop', { offset: '100%', 'stop-color': '#0d0716' }));
  defs.append(filtro, massa);

  // Sem filtro na silhueta (seria redesenhada a cada quadro da animação): o halo é um traço largo e translúcido.
  const camadaCerebro = svg('g');
  [-1, 1].forEach((lado) => {
    camadaCerebro.append(svg('path', { d: `${contorno(lado)}Z`, class: 'mapa-halo' }),
      svg('path', { d: `${contorno(lado)}Z`, class: 'mapa-hemisferio' }));
    [0.86, 0.72, 0.58, 0.44, 0.3, 0.16].forEach((escala) => camadaCerebro.append(svg('path', {
      d: contorno(lado, escala, 0.06, (a) => Math.sin(4 * a + escala * 11 + lado) > -0.45), class: 'mapa-giro' })));
  });
  const camadaLinhas = svg('g');
  const camadaPontos = svg('g');
  const camadaBrilho = svg('g');
  const camadaFaiscas = svg('g');
  const camadaRotulos = svg('g');
  const rotulosTrilha = svg('g');
  desenho.append(defs, camadaCerebro, camadaLinhas, camadaPontos, camadaBrilho, camadaFaiscas, camadaRotulos, rotulosTrilha);

  const acaso = sorteio(7);
  todos.forEach((no) => {
    if (no.pai) {
      no.linha = svg('path', { d: curva(no, acaso), class: `mapa-linha nivel-${no.profundidade}`, stroke: no.cor });
      camadaLinhas.append(no.linha);
    }
    const destaque = no.profundidade <= 1;
    no.ponto = svg('circle', { cx: no.x.toFixed(1), cy: no.y.toFixed(1), r: no.raio.toFixed(1),
      class: `mapa-ponto nivel-${no.profundidade}`, fill: destaque ? '#07080d' : no.cor, stroke: no.cor });
    (destaque ? camadaBrilho : camadaPontos).append(no.ponto);
  });
  areaMapa.replaceChildren(desenho);
  rotularEmpresas(raiz.filhos || [], camadaRotulos);

  const resumo = novoEl('div', 'mapa-resumo');
  resumo.append(novoEl('span', null, `${raiz.trechos.toLocaleString('pt-BR')} trechos · ${folhas.length.toLocaleString('pt-BR')} documentos · `
    + `densidade média ${(raiz.trechos / Math.max(1, folhas.length)).toFixed(1)} trechos por documento`));
  (raiz.filhos || []).forEach((empresa) => {
    const item = novoEl('span', 'mapa-legenda');
    const bolinha = novoEl('i');
    bolinha.style.background = empresa.cor;
    item.append(bolinha, `${empresa.nome}: ${empresa.trechos.toLocaleString('pt-BR')}`);
    resumo.append(item);
  });
  desenho.before(resumo);

  const faiscasTrilha = [0, 1, 2].map(() => svg('circle', { r: 3.5, class: 'mapa-faisca', display: 'none' }));
  // a faísca brilha por um traço largo e translúcido (stroke) em volta do núcleo branco
  camadaFaiscas.append(...faiscasTrilha);
  mapa = { raiz, todos, folhas, desenho, camadaFaiscas, rotulosTrilha, faiscasTrilha, focado: null, inicioFoco: 0,
    sinapses: [], ultimaSinapse: 0, arrasto: null, quadro: 0 };
  ativarInteracao(desenho, caixa);
  mapa.quadro = requestAnimationFrame(animar);
}

// Nome de cada empresa do lado de fora da silhueta, junto à sua região (assim não cobre pontos; os demais nomes
// aparecem no hover); nomes longos quebram em duas linhas e, se dois rótulos se encostam, o de fora se afasta.
function rotularEmpresas(empresas, camada) {
  const caixas = [];
  empresas.forEach((empresa) => {
    const [x, y] = empresa.ancora;
    const borda = y + empresa.lado * (MEIA_ALTURA * 1.12 + (empresa.lado > 0 ? 24 : 34));
    const rotulo = svg('text', { x: x.toFixed(1), y: borda.toFixed(1),
      class: 'mapa-rotulo nivel-1', fill: empresa.cor });
    const palavras = empresa.nome.split(' ');
    const meio = palavras.length > 2 ? Math.ceil(palavras.length / 2) : palavras.length;
    [palavras.slice(0, meio), palavras.slice(meio)].filter((l) => l.length).forEach((linha, i) => {
      const parte = svg('tspan', { x: x.toFixed(1), dy: i ? '1.15em' : '0' });
      parte.textContent = linha.join(' ');
      rotulo.append(parte);
    });
    camada.append(rotulo);
    let caixa = rotulo.getBBox();
    while (caixas.some((c) => caixa.x < c.x + c.width && c.x < caixa.x + caixa.width && caixa.y < c.y + c.height
        && c.y < caixa.y + caixa.height)) {
      rotulo.setAttribute('y', (Number(rotulo.getAttribute('y')) + 12 * empresa.lado).toFixed(1));
      caixa = rotulo.getBBox();
    }
    caixas.push(caixa);
  });
}

// ---------- Hover: trilha acesa ----------
function noSobOMouse(evento) {
  const ctm = mapa.desenho.getScreenCTM();
  if (!ctm) return null;
  const p = new DOMPoint(evento.clientX, evento.clientY).matrixTransform(ctm.inverse());
  const tolerancia = RAIO_TOQUE / ctm.a;
  let melhor = null;
  let menor = Infinity;
  mapa.todos.forEach((no) => {
    const d = Math.hypot(no.x - p.x, no.y - p.y) - no.raio;
    if (d < tolerancia && d < menor) {
      melhor = no;
      menor = d;
    }
  });
  return melhor;
}

function rotuloTrilha(no) {
  const direita = no.x < MEIA_LARGURA * 0.4;
  const texto = svg('text', { x: (no.x + (direita ? 1 : -1) * (no.raio + 8)).toFixed(1), y: (no.y + 4).toFixed(1),
    class: 'mapa-rotulo mapa-rotulo-trilha', 'text-anchor': direita ? 'start' : 'end' });
  texto.textContent = no.nome.length > 52 ? `${no.nome.slice(0, 51)}…` : no.nome;
  mapa.rotulosTrilha.append(texto);
}

function focar(no, evento) {
  if (no === mapa.focado) {
    moverDica(evento);
    return;
  }
  if (mapa.focado) {
    trilha(mapa.focado).forEach((n) => {
      n.linha?.classList.remove('ativa');
      n.ponto.classList.remove('ativo');
      n.ponto.setAttribute('r', n.raio.toFixed(1));
    });
  }
  mapa.rotulosTrilha.replaceChildren();
  mapa.faiscasTrilha.forEach((f) => f.setAttribute('display', 'none'));
  mapa.focado = no;
  mapa.desenho.classList.toggle('mapa-focando', Boolean(no));
  mapa.desenho.style.cursor = no ? 'pointer' : '';
  if (!no) {
    dicaMapa.hidden = true;
    return;
  }
  const nos = trilha(no);
  mapa.inicioFoco = performance.now();
  nos.forEach((n) => {
    n.linha?.classList.add('ativa');
    n.ponto.classList.add('ativo');
  });
  mapa.faiscasTrilha.forEach((f) => f.setAttribute('stroke', no.cor));
  // Rótulos: o ponto sob o mouse e a fonte da trilha, se não ficarem um em cima do outro.
  if (no.profundidade >= 2) rotuloTrilha(no);
  const fonte = nos[2];
  if (fonte && fonte !== no && Math.hypot(fonte.x - no.x, fonte.y - no.y) > 40) rotuloTrilha(fonte);
  const filhos = no.filhos?.length ? ` · ${no.filhos.length} ramificação(ões)` : '';
  dicaMapa.textContent = `${nos.map((n) => n.nome).join(' › ')}\n${(no.trechos || 0).toLocaleString('pt-BR')} trecho(s)${filhos}`;
  dicaMapa.hidden = false;
  moverDica(evento);
}

function moverDica(evento) {
  if (!evento || dicaMapa.hidden) return;
  const caixa = janelaMapa.querySelector('.janela').getBoundingClientRect();
  dicaMapa.style.left = `${Math.min(evento.clientX - caixa.left + 14, caixa.width - 320)}px`;
  dicaMapa.style.top = `${evento.clientY - caixa.top + 14}px`;
}

// ---------- Movimento ----------
// Posição de quem percorre uma sequência de ligações, a `s` unidades do começo.
function pontoNaTrilha(linhas, s) {
  let i = 0;
  linhas.forEach((l) => { l.comprimento ??= l.getTotalLength(); });
  while (i < linhas.length - 1 && s > linhas[i].comprimento) {
    s -= linhas[i].comprimento;
    i += 1;
  }
  return linhas[i].getPointAtLength(Math.max(0, Math.min(s, linhas[i].comprimento)));
}

function animar(agora) {
  if (!mapa || !mapaAberto) return;
  if (mapa.focado) {
    // a trilha pulsa da raiz até a ponta e três impulsos correm por ela
    const nos = trilha(mapa.focado);
    const tempo = agora - mapa.inicioFoco;
    nos.forEach((n, i) => n.ponto.setAttribute('r', (n.raio + Math.min(n.raio, 5) * (0.6 + 0.5 * Math.sin(tempo / 140 - i))).toFixed(2)));
    const linhas = nos.slice(1).map((n) => n.linha);
    if (linhas.length) {
      pontoNaTrilha(linhas, 0);
      const total = linhas.reduce((s, l) => s + l.comprimento, 0);
      mapa.faiscasTrilha.forEach((faisca, j) => {
        const p = pontoNaTrilha(linhas, (tempo * VELOCIDADE + (j * total) / 3) % total);
        faisca.setAttribute('cx', p.x.toFixed(1));
        faisca.setAttribute('cy', p.y.toFixed(1));
        faisca.removeAttribute('display');
      });
    }
  } else {
    mapa.raiz.ponto.setAttribute('r', (mapa.raiz.raio * (1 + 0.15 * Math.sin(agora / 400))).toFixed(2));
  }
  animarSinapses(agora);
  mapa.quadro = requestAnimationFrame(animar);
}

// Sinapses: de tempos em tempos um impulso corre entre a raiz e um documento qualquer.
function animarSinapses(agora) {
  if (!movimentoReduzido.matches && !mapa.focado && mapa.folhas.length && agora - mapa.ultimaSinapse > 350
      && mapa.sinapses.length < 8) {
    const folha = mapa.folhas[Math.floor(Math.random() * mapa.folhas.length)];
    const linhas = trilha(folha).slice(1).map((n) => n.linha);
    pontoNaTrilha(linhas, 0);
    const faisca = svg('circle', { r: 2.4, class: 'mapa-sinapse', fill: folha.cor, stroke: folha.cor });
    mapa.camadaFaiscas.append(faisca);
    mapa.sinapses.push({ linhas, faisca, inicio: agora, ida: Math.random() < 0.5,
      total: linhas.reduce((s, l) => s + l.comprimento, 0) });
    mapa.ultimaSinapse = agora;
  }
  mapa.sinapses = mapa.sinapses.filter((s) => {
    const t = ((agora - s.inicio) * VELOCIDADE * 0.6) / s.total;
    if (t >= 1 || mapa.focado) {
      s.faisca.remove();
      return false;
    }
    const p = pontoNaTrilha(s.linhas, s.total * (s.ida ? t : 1 - t));
    s.faisca.setAttribute('cx', p.x.toFixed(1));
    s.faisca.setAttribute('cy', p.y.toFixed(1));
    s.faisca.setAttribute('opacity', Math.sin(Math.PI * t).toFixed(2));
    return true;
  });
}

// ---------- Zoom, arrasto e hover ----------
// Roda do mouse = zoom em torno do cursor; arrastar = mover (mexendo no viewBox); sem arrasto, o hover acende.
function ativarInteracao(desenho, inicial) {
  let caixa = { ...inicial };
  const aplicar = () => desenho.setAttribute('viewBox', `${caixa.x} ${caixa.y} ${caixa.w} ${caixa.h}`);
  const noSvg = (e) => new DOMPoint(e.clientX, e.clientY).matrixTransform(desenho.getScreenCTM().inverse());
  desenho.addEventListener('wheel', (e) => {
    e.preventDefault();
    const p = noSvg(e);
    const fator = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const largura = Math.min(inicial.w * 2, Math.max(inicial.w / 10, caixa.w * fator));
    const altura = (largura * inicial.h) / inicial.w;
    caixa = { x: p.x - ((p.x - caixa.x) * largura) / caixa.w, y: p.y - ((p.y - caixa.y) * altura) / caixa.h, w: largura, h: altura };
    aplicar();
  }, { passive: false });
  desenho.addEventListener('pointerdown', (e) => {
    mapa.arrasto = { x: e.clientX, y: e.clientY, caixa: { ...caixa }, escala: desenho.getScreenCTM().a, moveu: false };
  });
  desenho.addEventListener('pointermove', (e) => {
    const arrasto = mapa?.arrasto;
    if (arrasto) {
      arrasto.moveu ||= Math.hypot(e.clientX - arrasto.x, e.clientY - arrasto.y) > 3;
      if (arrasto.moveu) {
        focar(null);
        caixa = { ...arrasto.caixa, x: arrasto.caixa.x - (e.clientX - arrasto.x) / arrasto.escala,
          y: arrasto.caixa.y - (e.clientY - arrasto.y) / arrasto.escala };
        aplicar();
        return;
      }
    }
    focar(noSobOMouse(e), e);
  });
  desenho.addEventListener('pointerleave', () => { if (!mapa?.arrasto) focar(null); });
}

function configurarMapa() {
  document.getElementById('abrir-mapa').hidden = sessao?.role !== 'diretoria';
}

document.getElementById('abrir-mapa').addEventListener('click', abrirMapa);
document.getElementById('mapa-fechar').addEventListener('click', fecharMapa);
janelaMapa.addEventListener('click', (e) => { if (e.target === janelaMapa) fecharMapa(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && mapaAberto) fecharMapa(); });
window.addEventListener('pointerup', () => { if (mapa) mapa.arrasto = null; });
