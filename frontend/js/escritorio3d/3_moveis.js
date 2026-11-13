// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
// ---------- Móveis e estações ----------
function cadeira(pai, x, z, rot = 0, cor = 0x2b2d42, escritorio = true) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.y = rot;
  pai.add(g);
  caixa(0.5, 0.08, 0.48, mat(cor), 0, 0.46, 0, g);
  caixa(0.5, 0.55, 0.07, mat(cor), 0, 0.78, -0.24, g);
  if (escritorio) { cilindro(0.04, 0.04, 0.38, mat(0x555555), 0, 0.23, 0, g, 8); cilindro(0.26, 0.26, 0.04, mat(0x333333), 0, 0.04, 0, g, 5); }
  else [[-0.2, -0.2], [0.2, -0.2], [-0.2, 0.2], [0.2, 0.2]].forEach(([dx, dz]) => caixa(0.04, 0.44, 0.04, mat(0x5c4a3a), dx, 0.22, dz, g));
  return g;
}
function monitor(pai, x, z, tela = 'codigo', larg = 0.7, alto = 0.42, rot = Math.PI) {
  const g = new THREE.Group();
  g.position.set(x, 0.78, z);
  g.rotation.y = rot;
  pai.add(g);
  caixa(larg, alto, 0.04, mat(0x1b1f23), 0, 0.33, 0, g);
  const t = malha(new THREE.PlaneGeometry(larg - 0.06, alto - 0.06), matTela(tela), 0, 0.33, 0.022, g, false);
  caixa(0.06, 0.16, 0.06, mat(0x3b3b3b), 0, 0.08, -0.03, g);
  caixa(0.24, 0.02, 0.16, mat(0x3b3b3b), 0, 0.01, -0.02, g);
  return t;
}
const mesaTampo = (pai, x, z, l = 1.3, p = 0.66, cor = 0xc89b6d) => {
  caixa(l, 0.05, p, mat(cor, { roughness: 0.6 }), x, 0.76, z, pai);
  [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sz]) => caixa(0.05, 0.74, 0.05, mat(0x3b3b3b), x + sx * (l / 2 - 0.06), 0.37, z + sz * (p / 2 - 0.06), pai));
};
// Estação: agente em (x, z) olhando para a frente do prédio (+z); mesa à frente dele, cadeira atrás.
function estacao(pai, tipo, x, z) {
  const zm = z + 0.6;
  const extras = {
    executiva: () => { mesaTampo(pai, x, zm, 1.6, 0.75, 0x5c3d2e); monitor(pai, x - 0.25, zm + 0.18, 'grafico'); caixa(0.34, 0.02, 0.24, mat(0xb0b0b0, { metalness: 0.6, roughness: 0.3 }), x + 0.45, 0.8, zm, pai); planta(pai, x + 0.62, zm + 0.2, false, 0.35); },
    design: () => { mesaTampo(pai, x, zm, 1.4, 0.7, 0xf0ebe0); monitor(pai, x, zm + 0.2, 'arte', 0.8, 0.48); caixa(0.32, 0.015, 0.22, mat(0x222222), x + 0.45, 0.79, zm - 0.05, pai); luminaria(pai, x - 0.55, zm + 0.15); },
    ilustracao: () => { mesaTampo(pai, x, zm, 1.4, 0.7, 0xf0ebe0); monitor(pai, x - 0.15, zm + 0.2, 'arte'); const prancheta = caixa(0.45, 0.02, 0.32, mat(0x1b1b1b), x + 0.4, 0.84, zm - 0.02, pai); prancheta.rotation.x = -0.4; },
    redacao: () => { mesaTampo(pai, x, zm); monitor(pai, x, zm + 0.2, 'codigo'); caixa(0.22, 0.05, 0.3, mat(0xffffff), x + 0.45, 0.81, zm, pai); cilindro(0.04, 0.035, 0.09, mat(0xe76f51), x - 0.45, 0.83, zm - 0.05, pai, 10); },
    social: () => { mesaTampo(pai, x, zm); monitor(pai, x - 0.15, zm + 0.2, 'social'); cilindro(0.01, 0.01, 0.5, mat(0x333333), x + 0.5, 1.03, zm + 0.1, pai, 6); malha(new THREE.TorusGeometry(0.12, 0.018, 8, 20), brilho(0xfff6e0, 0.9), x + 0.5, 1.3, zm + 0.1, pai); },
    video: () => { mesaTampo(pai, x, zm); monitor(pai, x, zm + 0.2, 'video'); const tripe = new THREE.Group(); tripe.position.set(x + 0.85, 0, zm - 0.3); pai.add(tripe); [0, 2.1, 4.2].forEach((a) => { const perna = cilindro(0.012, 0.012, 1.3, mat(0x222222), Math.sin(a) * 0.15, 0.62, Math.cos(a) * 0.15, tripe, 6); perna.rotation.set(Math.cos(a) * 0.2, 0, -Math.sin(a) * 0.2); }); caixa(0.2, 0.14, 0.12, mat(0x222222), 0, 1.3, 0, tripe); },
    edicao: () => { mesaTampo(pai, x, zm, 1.5, 0.7, 0x2b2b2b); monitor(pai, x - 0.36, zm + 0.2, 'video', 0.62); monitor(pai, x + 0.36, zm + 0.2, 'video', 0.62); },
    som: () => { mesaTampo(pai, x, zm, 1.5, 0.7, 0x2b2b2b); monitor(pai, x, zm + 0.22, 'onda'); caixa(0.5, 0.05, 0.25, mat(0x333333), x, 0.81, zm - 0.06, pai); [-1, 1].forEach((s) => caixa(0.18, 0.3, 0.18, mat(0x1b1b1b), x + s * 0.62, 0.93, zm + 0.15, pai)); },
    graficos: () => { mesaTampo(pai, x, zm); monitor(pai, x - 0.3, zm + 0.2, 'grafico', 0.6); monitor(pai, x + 0.3, zm + 0.2, 'grafico', 0.6); },
    metricas: () => { mesaTampo(pai, x, zm); monitor(pai, x, zm + 0.2, 'grafico', 0.8, 0.48); caixa(0.2, 0.05, 0.28, mat(0xffffff), x + 0.5, 0.81, zm, pai); },
    bancada: () => { mesaTampo(pai, x, zm, 1.6, 0.8, 0xa0703c); caixa(0.3, 0.12, 0.2, mat(0xc92a2a), x - 0.5, 0.85, zm, pai); caixa(0.4, 0.06, 0.08, mat(0x868e96, { metalness: 0.7, roughness: 0.3 }), x + 0.2, 0.82, zm + 0.1, pai); monitor(pai, x + 0.45, zm + 0.22, 'codigo', 0.5, 0.32); },
    central: () => { mesaTampo(pai, x, zm, 1.8, 0.8, 0x343a40); [-0.6, 0, 0.6].forEach((dx, k) => monitor(pai, x + dx, zm + 0.22 - Math.abs(dx) * 0.15, k === 1 ? 'mapa' : 'codigo', 0.56, 0.38, Math.PI - dx * 0.4)); },
    mesa: () => { mesaTampo(pai, x, zm); monitor(pai, x, zm + 0.2, 'codigo'); },
    balcao: () => { caixa(2.2, 1.05, 0.55, mat(CREME), x, 0.52, zm + 0.1, pai); caixa(2.3, 0.05, 0.65, mat(0x5c3d2e), x, 1.07, zm + 0.1, pai); caixa(1.1, 0.25, 0.02, mat(VERDE), x, 0.62, zm + 0.38, pai); monitor(pai, x - 0.4, zm, 'codigo', 0.5, 0.34); cilindro(0.06, 0.08, 0.06, mat(0xd4af37, { metalness: 0.8, roughness: 0.2 }), x + 0.6, 1.12, zm + 0.1, pai, 12); },
    pulpito: () => { caixa(0.7, 1.05, 0.45, mat(0x7f5539), x, 0.52, zm, pai); const topo = caixa(0.8, 0.05, 0.5, mat(0x5c3d2e), x, 1.08, zm, pai); topo.rotation.x = 0.2; },
  };
  (extras[tipo] || extras.mesa)();
  if (!['balcao', 'pulpito'].includes(tipo)) cadeira(pai, x, z - 0.12, 0, tipo === 'executiva' ? 0x1b1b1b : 0x2b2d42);
}
function luminaria(pai, x, z) {
  cilindro(0.07, 0.07, 0.02, mat(0x222222), x, 0.79, z, pai, 10);
  const haste = cilindro(0.012, 0.012, 0.45, mat(0x222222), x, 1.0, z, pai, 6);
  haste.rotation.z = 0.25;
  malha(new THREE.ConeGeometry(0.09, 0.12, 12, 1, true), brilho(0xfff1c1, 0.6), x + 0.06, 1.2, z, pai);
}
function planta(pai, x, z, alta = false, escala = 1) {
  const e = escala * (alta ? 1.35 : 1);
  cilindro(0.2 * e, 0.15 * e, 0.36 * e, mat(0xc87f56), x, 0.18 * e, z, pai, 12);
  for (let k = 0; k < (alta ? 9 : 6); k++) {
    const a = (k / (alta ? 9 : 6)) * Math.PI * 2;
    const folha = malha(new THREE.ConeGeometry(0.1 * e, 0.7 * e, 5), mat(k % 2 ? 0x3f7d3a : 0x56994b, { flatShading: true }), x + Math.cos(a) * 0.08 * e, 0.62 * e + (alta ? (k % 3) * 0.2 : 0), z + Math.sin(a) * 0.08 * e, pai);
    folha.rotation.set(Math.sin(a) * 0.5, 0, -Math.cos(a) * 0.5);
  }
}
const leds = [];
const bolhas = [], flutuantes = [], pulsantes = [];
const cerebros = [];
const reuniaoCentro = new THREE.Vector3();
const ALTOS = new Set(['rack', 'caixas', 'tambores', 'estante', 'poltrona', 'sofa', 'mesinha', 'abajur', 'cafeteira', 'bebedouro', 'bar']);
const MOVEIS = {
  tapete: (pai, x, z, l, p, cor) => {
    const t = textura(128, 128, (g) => { g.fillStyle = hex(cor); g.fillRect(0, 0, 128, 128); g.strokeStyle = hex(tom(cor, 1.5)); g.lineWidth = 6; g.strokeRect(10, 10, 108, 108); g.lineWidth = 2; g.strokeRect(20, 20, 88, 88); });
    caixa(l, 0.02, p, new THREE.MeshStandardMaterial({ map: t, roughness: 1 }), x, 0.02, z, pai, false);
  },
  planta: (pai, x, z, alta) => planta(pai, x, z, !!alta),
  rack: (pai, x, z) => {
    caixa(0.7, 2.1, 0.8, mat(0x22272b, { roughness: 0.5, metalness: 0.4 }), x, 1.36, z, pai);
    for (let k = 0; k < 8; k++) {
      const led = caixa(0.05, 0.03, 0.02, mat(k % 3 ? 0x69db7c : 0x4dabf7, { emissive: k % 3 ? 0x69db7c : 0x4dabf7, emissiveIntensity: 1 }), x - 0.22 + (k % 2) * 0.1, 0.6 + k * 0.2, z + 0.41, pai, false);
      leds.push({ led, fase: acaso() * 6 });
    }
  },
  caixas: (pai, x, z, pilha) => { caixa(0.6, 0.45, 0.5, mat(0xc8a26b), x, 0.53, z, pai); caixa(0.5, 0.4, 0.45, mat(0xb98f5a), x + 0.05, 0.96, z, pai); if (!pilha) caixa(0.55, 0.4, 0.45, mat(0xd2ad78), x + 0.55, 0.5, z + 0.1, pai); },
  tambores: (pai, x, z) => { cilindro(0.28, 0.28, 0.85, mat(0x1971c2, { roughness: 0.5 }), x, 0.73, z, pai); cilindro(0.28, 0.28, 0.85, mat(0xc92a2a, { roughness: 0.5 }), x + 0.62, 0.73, z + 0.1, pai); },
  prototipo: (pai, x, z) => {
    mesaTampo(pai, x, z, 1.4, 0.8, 0xa0703c);
    caixa(0.36, 0.4, 0.28, mat(0xadb5bd, { metalness: 0.6, roughness: 0.35 }), x, 1.0, z, pai);
    caixa(0.28, 0.22, 0.24, mat(0xced4da, { metalness: 0.6, roughness: 0.35 }), x, 1.33, z, pai);
    [-1, 1].forEach((s) => esfera(0.035, brilho(0x4dabf7, 1), x + s * 0.07, 1.35, z + 0.125, pai, 8, 6));
    cilindro(0.01, 0.01, 0.2, mat(0x333333), x, 1.54, z, pai, 6);
    esfera(0.03, brilho(0xe0645a, 1), x, 1.65, z, pai, 8, 6);
  },
  estante: (pai, x, z) => {
    caixa(0.35, 2, 1.4, mat(0x7f5539), x, 1.32, z, pai);
    for (let p = 0; p < 4; p++) for (let k = 0; k < 7; k++) {
      const cor = [0xc92a2a, 0x1971c2, 0xd4af37, 0x2a9d8f, 0x6d597a, 0xf4a261][(p * 7 + k) % 6];
      caixa(0.22, 0.32 + acaso() * 0.08, 0.13, mat(cor), x + 0.12, 0.62 + p * 0.45, z - 0.5 + k * 0.16, pai);
    }
  },
  poltrona: (pai, x, z, cor) => { caixa(0.8, 0.4, 0.75, mat(cor), x, 0.52, z, pai); caixa(0.8, 0.55, 0.18, mat(cor), x, 0.85, z - 0.3, pai); [-1, 1].forEach((s) => caixa(0.14, 0.25, 0.72, mat(tom(cor, 0.85)), x + s * 0.4, 0.82, z, pai)); },
  sofa: (pai, x, z, cor) => { caixa(1.9, 0.4, 0.8, mat(cor), x, 0.52, z, pai); caixa(1.9, 0.55, 0.2, mat(cor), x, 0.85, z - 0.32, pai); [-1, 1].forEach((s) => caixa(0.18, 0.3, 0.8, mat(tom(cor, 0.85)), x + s * 0.92, 0.82, z, pai)); [-0.5, 0.5].forEach((dx) => caixa(0.8, 0.1, 0.62, mat(tom(cor, 1.15)), x + dx, 0.77, z + 0.04, pai)); },
  mesinha: (pai, x, z) => { cilindro(0.38, 0.38, 0.05, mat(0x5c3d2e, { roughness: 0.5 }), x, 0.62, z, pai, 20); cilindro(0.05, 0.05, 0.3, mat(0x333333), x, 0.46, z, pai, 8); cilindro(0.06, 0.05, 0.1, mat(0xffffff), x + 0.1, 0.7, z, pai, 10); },
  abajur: (pai, x, z) => { cilindro(0.16, 0.18, 0.05, mat(0x333333), x, 0.34, z, pai, 12); cilindro(0.02, 0.02, 1.4, mat(0x333333), x, 1.05, z, pai, 6); malha(new THREE.CylinderGeometry(0.18, 0.28, 0.32, 16, 1, true), brilho(0xfff1c1, 0.5), x, 1.8, z, pai); },
  cafeteira: (pai, x, z) => { caixa(1.6, 0.95, 0.6, mat(0xf0ebe0), x + 0.3, 0.8, z, pai); caixa(1.7, 0.05, 0.65, mat(0x2b2b2b), x + 0.3, 1.29, z, pai); caixa(0.32, 0.42, 0.32, mat(0x333333, { metalness: 0.5, roughness: 0.3 }), x, 1.52, z - 0.05, pai); for (let k = 0; k < 3; k++) cilindro(0.04, 0.035, 0.08, mat([0xe76f51, 0xffffff, 0x2a9d8f][k]), x + 0.4 + k * 0.12, 1.36, z + 0.1, pai, 10); },
  bebedouro: (pai, x, z) => { caixa(0.4, 1, 0.4, mat(0xe9ecef), x, 0.82, z, pai); cilindro(0.17, 0.17, 0.45, mat(0x8ecae6, { transparent: true, opacity: 0.7, roughness: 0.1 }), x, 1.55, z, pai, 14); },
  carteira: (pai, x, z) => { mesaTampo(pai, x, z + 0.15, 0.9, 0.5, 0xc89b6d); cadeira(pai, x, z - 0.35, 0, 0x457b9d, false); caixa(0.25, 0.02, 0.3, mat(0xffffff), x, 0.79, z + 0.15, pai); },
  mesaReuniao: (pai, x, z) => {
    caixa(3.3, 0.07, 1.25, mat(0x6b4a33, { roughness: 0.45 }), x, 0.78, z, pai);
    [-1.3, 1.3].forEach((dx) => caixa(0.12, 0.72, 0.9, mat(0x2b2b2b), x + dx, 0.38, z, pai));
    caixa(0.5, 0.05, 0.2, mat(0x1b1b1b), x, 0.83, z, pai);
  },
  cadeirasFrente: (pai, x, z) => { for (let k = 0; k < 3; k++) cadeira(pai, x - 1 + k, z, Math.PI, 0x2b2d42); },
  bar: (pai, x, z) => { caixa(0.6, 1.05, 1.8, mat(0x3d2b1f), x, 0.85, z, pai); caixa(0.7, 0.05, 1.9, mat(0xd4af37, { metalness: 0.7, roughness: 0.25 }), x, 1.39, z, pai); for (let k = 0; k < 5; k++) cilindro(0.04, 0.05, 0.28, mat([0x2a9d8f, 0x9d0208, 0xd9a15b, 0x6d597a, 0x1b4332][k], { roughness: 0.2 }), x, 1.55, z - 0.7 + k * 0.35, pai, 10); },
  // Bancada encostada na parede: tubos de ensaio, frascos e microscópio (laboratorio.js).
  bancadaLab: (pai, x, z) => {
    caixa(0.9, 0.9, 2.6, mat(0xe9ecef), x, 0.45, z, pai);
    caixa(0.95, 0.05, 2.65, mat(0x2b2d42), x, 0.92, z, pai);
    caixa(0.2, 0.08, 0.7, mat(0x7f5539), x, 0.99, z - 0.8, pai);
    for (let k = 0; k < 5; k++) cilindro(0.025, 0.025, 0.24, mat([0x63e6be, 0xff8fab, 0xc77dff, 0xffd43b, 0x66d9e8][k], { transparent: true, opacity: 0.85, emissive: [0x63e6be, 0xff8fab, 0xc77dff, 0xffd43b, 0x66d9e8][k], emissiveIntensity: 0.5 }), x, 1.1, z - 1.08 + k * 0.14, pai, 8);
    [[0.1, -0.1, 0x63e6be], [-0.15, 0.2, 0xff8fab], [0.15, 0.45, 0xc77dff]].forEach(([dx, dz, cor]) => {
      malha(new THREE.ConeGeometry(0.11, 0.22, 14), mat(cor, { transparent: true, opacity: 0.7, emissive: cor, emissiveIntensity: 0.35, roughness: 0.1 }), x + dx, 1.06, z + dz, pai);
      cilindro(0.03, 0.03, 0.12, mat(0xdff3ff, { transparent: true, opacity: 0.6 }), x + dx, 1.22, z + dz, pai, 8);
    });
    caixa(0.2, 0.03, 0.24, mat(0x2b2b2b), x, 0.96, z + 0.95, pai);
    cilindro(0.025, 0.025, 0.36, mat(0x2b2b2b), x - 0.06, 1.12, z + 0.95, pai, 8).rotation.z = 0.3;
    cilindro(0.04, 0.035, 0.24, mat(0xdee2e6, { metalness: 0.6, roughness: 0.3 }), x + 0.02, 1.3, z + 0.95, pai, 12).rotation.z = -0.5;
  },
  // Tanque de vidro com líquido, bolhas e, num deles, um cérebro reserva flutuando.
  tanque: (pai, x, z, cor, reserva) => {
    cilindro(0.42, 0.42, 0.14, mat(0x2b2b2b, { metalness: 0.6 }), x, 0.07, z, pai, 24);
    cilindro(0.38, 0.38, 1.85, mat(0xdff3ff, { transparent: true, opacity: 0.25, roughness: 0.05 }), x, 1.06, z, pai, 24);
    cilindro(0.34, 0.34, 1.35, mat(cor, { transparent: true, opacity: 0.45, emissive: cor, emissiveIntensity: 0.55, roughness: 0.1 }), x, 0.82, z, pai, 24).castShadow = false;
    cilindro(0.42, 0.42, 0.14, mat(0x2b2b2b, { metalness: 0.6 }), x, 2.02, z, pai, 24);
    for (let k = 0; k < 7; k++) bolhas.push({ b: esfera(0.025 + acaso() * 0.02, mat(0xffffff, { transparent: true, opacity: 0.7 }), x + (acaso() - 0.5) * 0.4, 0.3, z + (acaso() - 0.5) * 0.4, pai, 6, 4), fase: acaso() });
    if (reserva) flutuantes.push(malha(cerebroDobrado(0.2, 3), mat(ROSA_CEREBRO, { roughness: 0.5 }), x, 0.95, z, pai));
  },
  // Mesa com três monitores de ondas cerebrais (o do meio pulsa).
  monitoresCerebro: (pai, x, z) => {
    mesaTampo(pai, x + 1.05, z + 0.1, 3.4, 0.7, 0x2b2d42);
    for (let k = 0; k < 3; k++) {
      caixa(0.95, 0.58, 0.05, mat(0x111111), x + k * 1.05, 1.18, z - 0.12, pai);
      const tela = new THREE.MeshStandardMaterial({ map: TELAS.cerebro, emissive: 0xffffff, emissiveMap: TELAS.cerebro, emissiveIntensity: 0.6 });
      malha(new THREE.PlaneGeometry(0.89, 0.52), tela, x + k * 1.05, 1.18, z - 0.09, pai, false);
      if (k === 1) pulsantes.push(tela);
    }
  },
  // Pedestal iluminado: coluna de luz ciano, luzes na lateral e meia-argola de vidro na frente.
  cerebro: (pai, x, z, andar) => {
    cilindro(0.9, 1, 0.16, mat(0x343a40), x, 0.08, z, pai, 32);
    cilindro(0.74, 0.8, 0.44, mat(0x495057, { metalness: 0.4, roughness: 0.4 }), x, 0.38, z, pai, 32);
    malha(new THREE.TorusGeometry(0.77, 0.03, 8, 48), brilho(CIANO, 0.9), x, 0.6, z, pai).rotation.x = Math.PI / 2;
    [-0.6, 0, 0.6].forEach((a) => esfera(0.045, brilho(CIANO, 1.2), x + Math.sin(a) * 0.81, 0.38, z + Math.cos(a) * 0.81, pai, 8, 6));
    malha(new THREE.CylinderGeometry(0.68, 0.78, 2.8, 32, 1, true), new THREE.MeshBasicMaterial({ color: CIANO, transparent: true, opacity: 0.09, side: THREE.DoubleSide, depthWrite: false }), x, 2.0, z, pai, false);
    malha(new THREE.CylinderGeometry(0.82, 0.82, 0.8, 32, 1, true, -Math.PI / 2, Math.PI), new THREE.MeshPhysicalMaterial({ color: 0xdff3ff, transparent: true, opacity: 0.22, roughness: 0.05, side: THREE.DoubleSide, depthWrite: false }), x, 1.0, z, pai, false);
    ratoCerebro(pai, x, z, andar);
  },
};
// Janela da Cobertura: a cidade à noite, como no 2D (skyline com janelas acesas).
const CIDADE_NOITE = textura(256, 160, (c) => { const gr = c.createLinearGradient(0, 0, 0, 160); gr.addColorStop(0, '#0f1b3d'); gr.addColorStop(1, '#23365f'); c.fillStyle = gr; c.fillRect(0, 0, 256, 160); c.fillStyle = 'rgba(255,255,255,0.8)'; for (let k = 0; k < 40; k++) c.fillRect(acaso() * 256, acaso() * 70, 1.5, 1.5); c.fillStyle = '#f5efe3'; c.beginPath(); c.arc(210, 30, 12, 0, 7); c.fill(); for (let x = 0; x < 256; x += 22) { const h = 40 + acaso() * 70; c.fillStyle = '#0b1226'; c.fillRect(x, 160 - h, 20, h); c.fillStyle = 'rgba(255,214,120,0.85)'; for (let y = 160 - h + 6; y < 156; y += 9) for (let j = 0; j < 3; j++) if (acaso() > 0.45) c.fillRect(x + 3 + j * 6, y, 3, 4); } });
// Itens de parede: 'esq' = parede do fundo (ao longo de x), 'dir' = parede da direita (ao longo de z).
function itemParede(pai, andar, [tipo, lado, t0, t1, z0, z1, letra]) {
  const g = new THREE.Group();
  const passo = lado === 'esq' ? LARG / andar.grade : FUNDO / andar.grade;
  const meio = ((t0 + t1) / 2) * passo, larg = Math.max(0.3, (t1 - t0) * passo);
  if (lado === 'esq') { g.position.set(-LARG / 2 + meio, 0, -FUNDO / 2 + 0.16); }
  else { g.position.set(LARG / 2 - 0.16, 0, -FUNDO / 2 + meio); g.rotation.y = -Math.PI / 2; }
  pai.add(g);
  const y0 = (z0 / PAREDE_PX) * (ALTURA - 0.4), y1 = (z1 / PAREDE_PX) * (ALTURA - 0.4), alto = Math.max(0.2, y1 - y0), ym = (y0 + y1) / 2;
  const quadroTex = (fundo, cores) => textura(128, 96, (c) => { c.fillStyle = fundo; c.fillRect(0, 0, 128, 96); cores.forEach((cor, k) => { c.fillStyle = cor; c.fillRect(10 + k * 38, 14 + (k % 2) * 20, 30, 50 - (k % 2) * 16); }); });
  const quadro = (tex, moldura = 0x2b2b2b) => { caixa(larg + 0.08, alto + 0.08, 0.04, mat(moldura), 0, ym, 0, g); malha(new THREE.PlaneGeometry(larg, alto), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 }), 0, ym, 0.025, g, false); };
  ({
    quadro: () => quadro(quadroTex('#fff1e6', ['#d4af37', '#7b2cbf', '#e9c46a'])),
    janela: () => { caixa(larg + 0.1, alto + 0.1, 0.05, mat(andar.id === 'cobertura' ? 0x2b2b2b : 0xf7f5ef), 0, ym, 0, g); malha(new THREE.PlaneGeometry(larg, alto), new THREE.MeshStandardMaterial({ map: andar.id === 'cobertura' ? CIDADE_NOITE : textura(128, 96, (c) => { const gr = c.createLinearGradient(0, 0, 0, 96); gr.addColorStop(0, '#8ec5e8'); gr.addColorStop(1, '#d7ecf5'); c.fillStyle = gr; c.fillRect(0, 0, 128, 96); c.fillStyle = 'rgba(255,255,255,0.8)'; c.beginPath(); c.ellipse(40, 30, 22, 8, 0, 0, 7); c.fill(); c.fillStyle = '#5d9e4f'; c.fillRect(0, 80, 128, 16); }), emissive: 0xffffff, emissiveIntensity: 0.25 }), 0, ym, 0.03, g, false); caixa(0.05, alto, 0.06, mat(0xf7f5ef), 0, ym, 0.03, g); },
    relogio: () => { cilindro(0.22, 0.22, 0.05, mat(0xffffff), 0, ym, 0, g, 24).rotation.x = Math.PI / 2; malha(new THREE.TorusGeometry(0.22, 0.025, 8, 24), mat(0x2b2b2b), 0, ym, 0.02, g); caixa(0.02, 0.15, 0.01, mat(0x111111), 0, ym + 0.06, 0.04, g); caixa(0.11, 0.02, 0.01, mat(0x111111), 0.05, ym, 0.04, g); },
    tv: () => { caixa(larg, alto, 0.06, mat(0x111111), 0, ym, 0, g); malha(new THREE.PlaneGeometry(larg - 0.08, alto - 0.08), matTela('grafico'), 0, ym, 0.035, g, false); },
    prateleira: () => { caixa(larg, 0.05, 0.3, mat(0x7f5539), 0, ym, 0.1, g); for (let k = 0; k < Math.floor(larg / 0.3); k++) caixa(0.16, 0.22 + (k % 2) * 0.1, 0.18, mat([0xd4af37, 0xe9c46a, 0xf8f9fa, 0x2a9d8f][k % 4]), -larg / 2 + 0.2 + k * 0.3, ym + 0.15, 0.1, g); },
    moodboard: () => { caixa(larg, alto, 0.04, mat(0xc8a26b, { roughness: 1 }), 0, ym, 0, g); for (let k = 0; k < 14; k++) caixa(0.22, 0.16, 0.01, mat([0xffffff, 0xff8fab, 0xc77dff, 0xe9c46a, 0x8ecae6][k % 5]), -larg / 2 + 0.25 + (k % 7) * (larg - 0.5) / 6, ym - alto / 4 + Math.floor(k / 7) * alto / 2, 0.03, g).rotation.z = (acaso() - 0.5) * 0.3; },
    arandela: () => { caixa(0.12, 0.2, 0.08, mat(0x2b2b2b), 0, ym, 0.04, g); malha(new THREE.ConeGeometry(0.12, 0.18, 12, 1, true), brilho(0xfff1c1, 0.8), 0, ym + 0.14, 0.1, g); },
    lousa: () => quadro(textura(256, 160, (c) => { c.fillStyle = '#244b3c'; c.fillRect(0, 0, 256, 160); c.fillStyle = 'rgba(255,255,255,0.85)'; c.font = '28px Georgia'; c.fillText('Bem-vindos!', 40, 60); c.font = '16px Georgia'; c.fillText('Briefing = objetivo + público + prazo', 18, 104); }), 0x7f5539),
    canos: () => { const cano = cilindro(0.07, 0.07, lado === 'esq' ? LARG - 0.4 : FUNDO - 0.4, mat(0x868e96, { metalness: 0.6, roughness: 0.4 }), 0, ALTURA - 0.75, 0.05, g, 10); cano.rotation.z = Math.PI / 2; g.position.x = lado === 'esq' ? 0 : g.position.x; },
    ferramentas: () => { caixa(larg, alto, 0.03, mat(0xc8a26b, { roughness: 1 }), 0, ym, 0, g); for (let k = 0; k < 6; k++) caixa(0.05, 0.3, 0.03, mat([0xc92a2a, 0x868e96, 0xffc300][k % 3]), -larg / 2 + 0.2 + k * (larg - 0.4) / 5, ym, 0.03, g); },
    painel: () => { caixa(larg, alto, 0.12, mat(0x868e96, { metalness: 0.5, roughness: 0.4 }), 0, ym, 0.04, g); caixa(0.05, 0.05, 0.02, brilho(0xe0645a, 1), larg / 4, ym + alto / 3, 0.11, g); },
    formulas: () => quadro(textura(256, 200, (c) => { c.fillStyle = '#22352c'; c.fillRect(0, 0, 256, 200); c.fillStyle = 'rgba(255,255,255,0.88)'; c.font = 'italic 19px Georgia'; ['cos(q, d) = q·d / |q||d|', 'top-k = 8 trechos', 'Plano: dominar o mercado', 'de hospedagem até 2027 ✓'].forEach((t, k) => { c.save(); c.translate(16, 40 + k * 44); c.rotate(-0.03); c.fillText(t, 0, 0); c.restore(); }); }), 0x7f5539),
    mapa: () => quadro(textura(256, 180, (c) => { c.fillStyle = '#f0dbc3'; c.fillRect(0, 0, 256, 180); const pontos = [['P', 30, 30], ['T', 30, 75], ['1', 30, 120], ['2', 75, 160], ['C', 128, 22], ['Veraneio', 215, 40], ['Corp', 222, 95], ['Vero', 205, 150]]; c.strokeStyle = '#c0392b'; c.lineWidth = 1.5; pontos.forEach(([, x, y]) => { c.beginPath(); c.moveTo(128, 92); c.lineTo(x, y); c.stroke(); }); pontos.forEach(([n, x, y], k) => { c.fillStyle = k < 5 ? '#00361b' : '#d9a15b'; if (k < 5) c.fillRect(x - 10, y - 10, 20, 20); else { c.beginPath(); c.moveTo(x - 12, y); c.lineTo(x, y - 12); c.lineTo(x + 12, y); c.fill(); c.fillRect(x - 9, y, 18, 12); } c.fillStyle = k < 5 ? '#f5efe3' : '#00361b'; c.font = 'bold 12px Georgia'; c.textAlign = 'center'; c.fillText(n, x, k < 5 ? y + 4 : y + 26); }); c.fillStyle = '#f7a8c0'; c.beginPath(); c.ellipse(128, 92, 24, 18, 0, 0, 7); c.fill(); c.strokeStyle = '#d0607f'; c.beginPath(); c.moveTo(128, 76); c.lineTo(128, 108); c.stroke(); }), 0x7f5539),
    elevador: () => {
      caixa(larg + 0.3, ALTURA - 0.4, 0.12, mat(0x9aa5ae, { metalness: 0.6, roughness: 0.3 }), 0, (ALTURA - 0.4) / 2, 0, g);
      [-1, 1].forEach((s) => caixa(larg / 2 - 0.04, 2.1, 0.04, mat(0xc9d1d8, { metalness: 0.8, roughness: 0.2 }), s * larg / 4, 1.05, 0.07, g));
      malha(new THREE.PlaneGeometry(0.36, 0.28), new THREE.MeshBasicMaterial({ map: textura(64, 48, (c) => { c.fillStyle = '#111'; c.fillRect(0, 0, 64, 48); c.fillStyle = '#d9a15b'; c.font = 'bold 34px Georgia'; c.textAlign = 'center'; c.fillText(letra, 32, 38); }) }), 0, 2.35, 0.08, g, false);
    },
  })[tipo]?.();
}
