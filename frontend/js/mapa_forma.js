// Forma do Mapa do Cérebro: a silhueta (dois hemisférios com dobras), as regiões de cada empresa e a simulação
// de forças que acomoda os pontos. O desenho e a interação ficam em js/mapa_cerebro.js.

// Hemisfério (unidades do SVG): meia largura, meia altura e o vão da fissura entre os dois.
const MEIA_LARGURA = 500;
const MEIA_ALTURA = 250;
const ACHATAMENTO = 2.2; // o lado de dentro (junto à fissura) é mais reto: cada hemisfério tem forma de D
const FISSURA = 14;
const MOLA = [0, 0, 300, 95, 30]; // comprimento base da ligação ao pai, por profundidade (cresce com os irmãos)
const RAIO_POR_NIVEL = [13, 12, 7, 4.5]; // pontos com ramificações; documentos crescem com os trechos
const VOLTAS = 260; // passos da simulação de forças
const CELULA = 40; // grade da detecção de colisão

// Gerador pseudoaleatório com semente: o mesmo conhecimento dá sempre o mesmo desenho.
function sorteio(semente) {
  return () => {
    semente = (semente + 0x6d2b79f5) | 0;
    let t = Math.imul(semente ^ (semente >>> 15), 1 | semente);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- Silhueta: hemisférios com dobras ----------
// Borda do hemisfério (1 = elipse) por ângulo: senos de várias frequências fazem os giros.
function dobras(angulo, lado) {
  return 1 + 0.018 * Math.sin(13 * angulo + lado) + 0.01 * Math.sin(29 * angulo + 2 * lado) + 0.05 * Math.cos(angulo)
    + 0.03 * Math.cos(2 * angulo);
}

function centroHemisferio(lado) {
  return lado * (FISSURA / 2 + MEIA_ALTURA / ACHATAMENTO);
}

// (x, y) ↔ coordenadas normalizadas do hemisfério (u, v); o lado de dentro é achatado.
function normalizar(x, y, lado) {
  const v = (y - centroHemisferio(lado)) / MEIA_ALTURA;
  return [x / MEIA_LARGURA, v * lado < 0 ? v * ACHATAMENTO : v];
}

function desnormalizar(u, v, lado) {
  return [u * MEIA_LARGURA, centroHemisferio(lado) + (v * lado < 0 ? v / ACHATAMENTO : v) * MEIA_ALTURA];
}

// Traça o contorno (escala 1 = borda); `mostrar` corta trechos, para os giros internos ficarem abertos.
function contorno(lado, escala = 1, onda = 0, mostrar = () => true) {
  let d = '';
  let desenhando = false;
  for (let k = 0; k <= 180; k += 1) {
    const angulo = (k / 180) * 2 * Math.PI;
    if (!mostrar(angulo)) {
      desenhando = false;
      continue;
    }
    const r = escala * dobras(angulo, lado) * (1 + onda * Math.sin(17 * angulo + escala * 13 + lado));
    const [x, y] = desnormalizar(r * Math.cos(angulo), r * Math.sin(angulo), lado);
    d += `${desenhando ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    desenhando = true;
  }
  return d;
}

// Mantém o ponto dentro do hemisfério e da faixa da sua empresa, com uma folga da borda.
function conter(no) {
  const { lado, faixa } = no.regiao;
  no.x = Math.max(faixa[0] * MEIA_LARGURA + no.folga, Math.min(faixa[1] * MEIA_LARGURA - no.folga, no.x));
  const [u, v] = normalizar(no.x, no.y, lado);
  const limite = dobras(Math.atan2(v, u), lado) * 0.9;
  const distancia = Math.hypot(u, v);
  if (distancia > limite) [no.x, no.y] = desnormalizar((u * limite) / distancia, (v * limite) / distancia, lado);
}

// ---------- Árvore e acomodação ----------
function prepararArvore(no, pai = null, profundidade = 0, empresa = null) {
  no.pai = pai;
  no.profundidade = profundidade;
  no.empresa = no.empresa || empresa;
  no.regiao = profundidade === 1 ? no : pai?.regiao;
  (no.filhos || []).forEach((f) => prepararArvore(f, no, profundidade + 1, no.empresa));
  no.folhas = no.filhos?.length ? no.filhos.reduce((soma, f) => soma + f.folhas, 0) : 1;
  return no;
}

// Regiões: a empresa com mais documentos fica com o hemisfério de cima; as outras dividem o de baixo, cada uma
// numa faixa vertical proporcional à raiz do nº de documentos (as pequenas não somem). Nenhum ponto sai da faixa
// da sua empresa: os dados de uma nunca aparecem misturados aos de outra.
function definirRegioes(empresas) {
  const [maior, ...resto] = [...empresas].sort((a, b) => b.folhas - a.folhas);
  if (maior) Object.assign(maior, { lado: -1, faixa: [-1, 1], ancora: [0, centroHemisferio(-1)] });
  const pesos = resto.map((e) => Math.sqrt(e.folhas));
  const total = pesos.reduce((s, p) => s + p, 0) || 1;
  let inicio = -0.85;
  resto.forEach((e, i) => {
    const largura = (1.7 * pesos[i]) / total;
    Object.assign(e, { lado: 1, faixa: [inicio, inicio + largura],
      ancora: [(inicio + largura / 2) * MEIA_LARGURA, centroHemisferio(1)] });
    inicio += largura;
  });
  empresas.forEach((e) => { e.alcance = ((e.faixa[1] - e.faixa[0]) / 2) * MEIA_LARGURA; });
}

// Simulação de forças por posição: cada ponto puxado para a região da empresa, mola até o pai, colisão com os
// vizinhos e a silhueta como limite. Determinística (semente fixa).
function acomodar(todos) {
  const acaso = sorteio(20261023);
  todos.forEach((no) => {
    if (no.profundidade === 0) [no.x, no.y] = [0, 0];
    else if (no.profundidade === 1) [no.x, no.y] = no.ancora;
    else {
      const angulo = acaso() * 2 * Math.PI;
      const distancia = no.mola * (0.5 + acaso());
      no.x = no.pai.x + Math.cos(angulo) * distancia;
      no.y = no.pai.y + Math.sin(angulo) * distancia;
    }
  });
  const moveis = todos.filter((n) => n.profundidade >= 1);
  for (let volta = 0; volta < VOLTAS; volta += 1) {
    const forca = 1 - volta / VOLTAS;
    moveis.forEach((no) => {
      const [ax, ay] = no.regiao.ancora;
      const puxao = no.profundidade === 1 ? 0.2 : 0.003 * forca;
      no.x += (ax - no.x) * puxao;
      no.y += (ay - no.y) * puxao;
      if (no.profundidade < 2) return;
      const dx = no.x - no.pai.x;
      const dy = no.y - no.pai.y;
      const ajuste = ((Math.hypot(dx, dy) || 1) - no.mola) / (Math.hypot(dx, dy) || 1) * 0.5;
      no.x -= dx * ajuste * 0.75;
      no.y -= dy * ajuste * 0.75;
      if (no.pai.profundidade >= 2) {
        no.pai.x += dx * ajuste * 0.25;
        no.pai.y += dy * ajuste * 0.25;
      }
    });
    separar(moveis, acaso);
    separar(moveis, acaso);
    moveis.forEach(conter);
  }
}

// Colisão: pontos mais próximos que a soma das folgas se afastam (grade para não comparar todos com todos).
function separar(nos, acaso) {
  const grade = new Map();
  const chave = (gx, gy) => gx * 100003 + gy;
  nos.forEach((no) => {
    const k = chave(Math.floor(no.x / CELULA), Math.floor(no.y / CELULA));
    if (!grade.has(k)) grade.set(k, []);
    grade.get(k).push(no);
  });
  nos.forEach((a) => {
    const gx = Math.floor(a.x / CELULA);
    const gy = Math.floor(a.y / CELULA);
    for (let i = -1; i <= 1; i += 1) {
      for (let j = -1; j <= 1; j += 1) {
        (grade.get(chave(gx + i, gy + j)) || []).forEach((b) => {
          if (b.indice <= a.indice) return;
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let d = Math.hypot(dx, dy);
          const minimo = a.folga + b.folga;
          if (d >= minimo) return;
          if (d < 0.01) {
            dx = acaso() - 0.5;
            dy = acaso() - 0.5;
            d = Math.hypot(dx, dy);
          }
          const empurrao = ((minimo - d) / d) * 0.5;
          a.x -= dx * empurrao;
          a.y -= dy * empurrao;
          b.x += dx * empurrao;
          b.y += dy * empurrao;
        });
      }
    }
  });
}

// Ligação levemente torta (como um axônio), da posição do pai até o ponto.
function curva(no, acaso) {
  const { x: x1, y: y1 } = no.pai;
  const { x: x2, y: y2 } = no;
  const curvatura = (acaso() - 0.5) * 0.6;
  const cx = (x1 + x2) / 2 - (y2 - y1) * curvatura;
  const cy = (y1 + y2) / 2 + (x2 - x1) * curvatura;
  return `M${x1.toFixed(1)},${y1.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
}
