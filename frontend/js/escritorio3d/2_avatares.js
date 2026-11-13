// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
// ---------- Avatares: corpo articulado e visual único por agente ----------
const avatares = [];
function avatar(id, nome, status, fala, andar) {
  const [pele, cabelo, corCabelo, roupa, corRoupa, corCalca, acessorio] = AP[id];
  const mPele = mat(new THREE.Color(pele).getHex()), mCabelo = mat(new THREE.Color(corCabelo).getHex(), { roughness: 0.9 });
  const mRoupa = mat(new THREE.Color(corRoupa).getHex()), mCalca = mat(new THREE.Color(corCalca).getHex());
  const corpo = new THREE.Group();
  const raiz = new THREE.Group();
  raiz.add(corpo);
  // tronco e roupa
  const tronco = caixa(0.46, 0.5, 0.28, roupa === 'avental' ? mat(0xffffff) : mRoupa, 0, 0.8, 0, corpo);
  if (roupa === 'blazer') {
    caixa(0.14, 0.34, 0.02, mat(0xf8f9fa), 0, 0.88, 0.145, corpo);
    [-1, 1].forEach((s) => { const lapela = caixa(0.09, 0.3, 0.025, mat(tom(new THREE.Color(corRoupa).getHex(), 0.75)), s * 0.09, 0.9, 0.15, corpo); lapela.rotation.z = s * 0.35; });
  }
  if (roupa === 'camisa') [-1, 1].forEach((s) => { const gola = caixa(0.12, 0.05, 0.05, mat(tom(new THREE.Color(corRoupa).getHex(), 1.15)), s * 0.07, 1.03, 0.12, corpo); gola.rotation.z = s * 0.4; });
  if (roupa === 'moletom') {
    malha(new THREE.TorusGeometry(0.15, 0.06, 8, 16, Math.PI), mRoupa, 0, 1.04, -0.08, corpo).rotation.x = Math.PI / 2 + 0.3;
    caixa(0.26, 0.12, 0.02, mat(tom(new THREE.Color(corRoupa).getHex(), 0.8)), 0, 0.66, 0.145, corpo);
  }
  if (roupa === 'macacao') [-1, 1].forEach((s) => caixa(0.06, 0.3, 0.02, mat(tom(new THREE.Color(corRoupa).getHex(), 0.75)), s * 0.12, 0.9, 0.145, corpo));
  if (roupa === 'avental') caixa(0.48, 0.32, 0.3, mat(0xffffff), 0, 0.5, 0, corpo);
  tronco.userData.tronco = true;
  // pescoço e cabeça
  cilindro(0.07, 0.07, 0.08, mPele, 0, 1.08, 0, corpo, 10);
  const cabeca = new THREE.Group();
  cabeca.position.set(0, 1.32, 0);
  corpo.add(cabeca);
  esfera(0.25, mPele, 0, 0, 0, cabeca, 24, 18);
  [-1, 1].forEach((s) => {
    esfera(0.034, mat(0x1b1b1b), s * 0.085, 0.02, 0.228, cabeca, 10, 8);
    esfera(0.012, mat(0xffffff), s * 0.085 + 0.012, 0.035, 0.258, cabeca, 6, 4);
    esfera(0.04, mPele, s * 0.245, -0.01, 0, cabeca, 8, 6); // orelhas
  });
  malha(new THREE.TorusGeometry(0.05, 0.011, 6, 14, Math.PI), mat(0x8a3b2b), 0, -0.085, 0.228, cabeca).rotation.z = Math.PI;
  esfera(0.03, mat(tom(new THREE.Color(pele).getHex(), 0.92)), 0, -0.02, 0.25, cabeca, 8, 6);
  // cabelos (avatar_partes.js: curto, longo, coque, careca, cacheado, moicano)
  const touca = (r = 0.265, abertura = 0.52) => {
    const t = malha(new THREE.SphereGeometry(r, 24, 14, 0, Math.PI * 2, 0, Math.PI * abertura), mCabelo, 0, 0.02, -0.02, cabeca);
    t.rotation.x = -0.25;
    return t;
  };
  if (cabelo === 'curto') touca();
  if (cabelo === 'longo') { touca(0.27, 0.55); caixa(0.5, 0.56, 0.14, mCabelo, 0, -0.2, -0.16, cabeca); [-1, 1].forEach((s) => caixa(0.08, 0.4, 0.14, mCabelo, s * 0.24, -0.16, 0.02, cabeca)); }
  if (cabelo === 'coque') { touca(0.265, 0.5); esfera(0.11, mCabelo, 0, 0.24, -0.12, cabeca, 12, 10); }
  if (cabelo === 'cacheado') for (let k = 0; k < 22; k++) {
    const a = (k / 22) * Math.PI * 2, nivel = k % 3;
    esfera(0.085, mCabelo, Math.cos(a) * (0.22 - nivel * 0.05), 0.1 + nivel * 0.07, Math.sin(a) * (0.22 - nivel * 0.05) - 0.03, cabeca, 8, 6);
  }
  if (cabelo === 'cacheado') esfera(0.12, mCabelo, 0, 0.25, -0.02, cabeca, 10, 8);
  if (cabelo === 'moicano') { caixa(0.08, 0.14, 0.46, mCabelo, 0, 0.25, -0.03, cabeca); touca(0.256, 0.42).material = mat(tom(new THREE.Color(corCabelo).getHex(), 0.5)); }
  if (cabelo === 'careca') esfera(0.06, mat(0xffffff, { transparent: true, opacity: 0.25 }), -0.08, 0.2, 0.1, cabeca, 8, 6);
  // acessórios
  if (acessorio === 'oculos') {
    [-1, 1].forEach((s) => malha(new THREE.TorusGeometry(0.06, 0.012, 6, 18), mat(0x222222), s * 0.088, 0.025, 0.245, cabeca));
    caixa(0.06, 0.012, 0.012, mat(0x222222), 0, 0.03, 0.25, cabeca);
  }
  if (acessorio === 'fone') {
    malha(new THREE.TorusGeometry(0.275, 0.022, 8, 24, Math.PI), mat(0x222222), 0, 0.02, 0, cabeca);
    [-1, 1].forEach((s) => { const concha = cilindro(0.075, 0.075, 0.06, mat(0x333333), s * 0.27, 0, 0, cabeca, 14); concha.rotation.z = Math.PI / 2; });
  }
  if (acessorio === 'bone') {
    malha(new THREE.SphereGeometry(0.27, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat(0xe63946), 0, 0.04, 0, cabeca);
    caixa(0.3, 0.025, 0.2, mat(0xe63946), 0, 0.05, 0.28, cabeca);
  }
  if (acessorio === 'capacete') {
    malha(new THREE.SphereGeometry(0.29, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat(0xffc300, { roughness: 0.4 }), 0, 0.05, 0, cabeca);
    cilindro(0.34, 0.34, 0.03, mat(0xffc300, { roughness: 0.4 }), 0, 0.05, 0.02, cabeca, 20);
  }
  if (acessorio === 'lapis') { const lapis = cilindro(0.015, 0.015, 0.26, mat(0xffc300), 0.25, 0.08, 0.02, cabeca, 6); lapis.rotation.x = Math.PI / 2; }
  if (acessorio === 'cracha') { caixa(0.1, 0.13, 0.012, mat(0xf8f9fa), 0.11, 0.78, 0.146, corpo); caixa(0.07, 0.025, 0.013, mat(CARAMELO), 0.11, 0.82, 0.148, corpo); }
  if (acessorio === 'gravata') { caixa(0.06, 0.04, 0.02, mat(0x9d0208), 0, 0.99, 0.15, corpo); const g = caixa(0.07, 0.3, 0.018, mat(0x9d0208), 0, 0.82, 0.152, corpo); g.scale.set(1, 1, 1); }
  if (acessorio === 'camera') { caixa(0.16, 0.11, 0.08, mat(0x222222), 0, 0.72, 0.19, corpo); cilindro(0.04, 0.04, 0.06, mat(0x111111), 0, 0.72, 0.25, corpo, 12).rotation.x = Math.PI / 2; }
  // braços e pernas com articulação (ombro/quadril e joelho)
  const bracos = [-1, 1].map((s) => {
    const ombro = new THREE.Group();
    ombro.position.set(s * 0.3, 0.98, 0);
    corpo.add(ombro);
    const manga = roupa === 'camiseta' ? mPele : (roupa === 'avental' ? mat(0xffffff) : mRoupa);
    if (roupa === 'camiseta') malha(new THREE.CapsuleGeometry(0.075, 0.08, 4, 10), mRoupa, 0, -0.07, 0, ombro);
    malha(new THREE.CapsuleGeometry(0.068, 0.24, 4, 10), manga, 0, -0.18, 0, ombro);
    esfera(0.065, mPele, 0, -0.36, 0, ombro, 10, 8);
    return ombro;
  });
  const pernas = [-1, 1].map((s) => {
    const quadril = new THREE.Group();
    quadril.position.set(s * 0.11, 0.56, 0);
    corpo.add(quadril);
    const mPerna = roupa === 'macacao' ? mRoupa : mCalca;
    malha(new THREE.CapsuleGeometry(0.09, 0.14, 4, 10), mPerna, 0, -0.12, 0, quadril);
    const joelho = new THREE.Group();
    joelho.position.y = -0.26;
    quadril.add(joelho);
    malha(new THREE.CapsuleGeometry(0.085, 0.12, 4, 10), mPerna, 0, -0.1, 0, joelho);
    caixa(0.15, 0.08, 0.24, mat(0x2b2b2b), 0, -0.25, 0.04, joelho);
    return { quadril, joelho };
  });
  // marcador de status flutuando sobre a cabeça
  const marcador = malha(new THREE.OctahedronGeometry(0.1, 0), new THREE.MeshStandardMaterial({ color: STATUS[status], emissive: STATUS[status], emissiveIntensity: 0.55, roughness: 0.3 }), 0, 1.95, 0, raiz, false);
  marcador.visible = false; // o status aparece pelos indicadores do 2D (digitando, zzz, martelo)
  marcador.scale.set(0.8, 1.4, 0.8);
  const dados = { id, nome, status, fala, andar, raiz, corpo, cabeca, bracos, pernas, marcador, fase: avatares.length * 0.9, sentado: false };
  raiz.traverse((m) => { m.userData.agente = dados; });
  avatares.push(dados);
  pose(dados, 'sentado');
  return dados;
}
function pose(a, tipo) {
  a.sentado = tipo === 'sentado';
  a.corpo.position.y = 0;
  a.pernas.forEach(({ quadril, joelho }) => { quadril.rotation.x = a.sentado ? -Math.PI / 2 : 0; joelho.rotation.x = a.sentado ? Math.PI / 2 : 0; });
  a.bracos.forEach((b) => { b.rotation.x = a.sentado ? -1.05 : 0; b.rotation.z = 0; });
}

// ---------- O Cérebro (cerebro.js do 2D): ratinho de laboratório gênio com o cérebro rosa à mostra ----------
const ROSA = 0xf4a6b4, ROSA_CEREBRO = 0xf7a8c0, PELO = 0xe9ecef, CIANO = 0x66d9e8;
function cerebroDobrado(r, detalhe = 4) {
  const geo = new THREE.IcosahedronGeometry(r, detalhe);
  const pos = geo.attributes.position, p3 = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    const n = p3.fromBufferAttribute(pos, i).normalize();
    const dobra = Math.sin(n.x * 17 + Math.sin(n.y * 9) * 2.2) * Math.sin(n.z * 15 + n.y * 7) * 0.07;
    const fissura = Math.exp(-Math.pow(n.x * 10, 2)) * 0.13 * Math.max(0, n.y + 0.3); // sulco entre os hemisférios
    n.multiplyScalar(r * (1 + dobra - fissura));
    pos.setXYZ(i, n.x, n.y, n.z);
  }
  geo.computeVertexNormals();
  return geo;
}
const ondas = [];
function ratoCerebro(pai, x, z, andar) {
  const raiz = new THREE.Group();
  raiz.position.set(x, 0.6, z);
  pai.add(raiz);
  const corpo = new THREE.Group();
  corpo.scale.setScalar(1.3);
  raiz.add(corpo);
  const pelo = mat(PELO, { roughness: 0.95 }), rosa = mat(ROSA, { roughness: 0.7 });
  esfera(0.3, pelo, 0, 0.42, 0, corpo, 20, 16).scale.set(1, 1.2, 0.9);
  esfera(0.2, mat(0xf8f9fa), 0, 0.4, 0.14, corpo, 16, 12).scale.set(1, 1.3, 0.6);
  [-1, 1].forEach((s) => esfera(0.09, rosa, s * 0.12, 0.05, 0.1, corpo, 10, 8).scale.set(1, 0.5, 1.6)); // pés
  [-1, 1].forEach((s) => esfera(0.065, rosa, s * 0.05, 0.56, 0.27, corpo, 10, 8)); // patinhas unidas, tramando algo
  const rabo = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0.22, -0.24), new THREE.Vector3(0.1, 0.08, -0.5), new THREE.Vector3(0.38, 0.14, -0.56), new THREE.Vector3(0.44, 0.42, -0.42)]);
  malha(new THREE.TubeGeometry(rabo, 24, 0.026, 6, false), rosa, 0, 0, 0, corpo);
  const cabeca = new THREE.Group();
  cabeca.position.set(0, 0.98, 0);
  corpo.add(cabeca);
  esfera(0.36, pelo, 0, 0, 0, cabeca, 24, 18).scale.set(1.12, 0.9, 1);
  esfera(0.16, pelo, 0, -0.11, 0.3, cabeca, 16, 12).scale.set(1, 0.8, 1.2);
  esfera(0.045, rosa, 0, -0.08, 0.49, cabeca, 10, 8);
  [-1, 1].forEach((s) => {
    esfera(0.21, pelo, s * 0.38, 0.2, -0.03, cabeca, 16, 12).scale.set(1, 1, 0.3); // orelhas grandes
    esfera(0.15, rosa, s * 0.38, 0.2, 0.03, cabeca, 14, 10).scale.set(1, 1, 0.2);
    esfera(0.072, mat(0xffffff), s * 0.13, 0.02, 0.29, cabeca, 12, 10);
    esfera(0.036, mat(0x1b1b1b), s * 0.13, 0.0, 0.35, cabeca, 10, 8);
    const palpebra = malha(new THREE.SphereGeometry(0.078, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), pelo, s * 0.13, 0.02, 0.29, cabeca);
    palpebra.rotation.x = 0.55; // pálpebra pesada: olhar de quem tem um plano
    caixa(0.13, 0.026, 0.03, mat(0x9aa0a6), s * 0.13, 0.13, 0.33, cabeca).rotation.z = s * -0.38; // sobrancelha em V
    for (let k = -1; k <= 1; k++) cilindro(0.004, 0.004, 0.3, mat(0x868e96), s * 0.22, -0.11 + k * 0.03, 0.4, cabeca, 4).rotation.z = Math.PI / 2 + k * 0.15 * s;
  });
  malha(new THREE.TorusGeometry(0.06, 0.01, 6, 12, Math.PI * 0.7), mat(0x8a3b2b), 0.05, -0.2, 0.42, cabeca).rotation.z = Math.PI + 0.35;
  const cerebro = malha(cerebroDobrado(0.3), mat(ROSA_CEREBRO, { roughness: 0.55, emissive: 0xd0607f, emissiveIntensity: 0.15 }), 0, 0.27, -0.03, cabeca);
  cerebro.scale.set(1.18, 0.8, 1.05);
  for (let k = 0; k < 3; k++) { // ondas que saem do cérebro quando ele trabalha
    const onda = malha(new THREE.TorusGeometry(0.42, 0.012, 6, 40), new THREE.MeshBasicMaterial({ color: CIANO, transparent: true, opacity: 0 }), 0, 0.35, -0.03, cabeca, false);
    onda.rotation.x = Math.PI / 2;
    ondas.push({ onda, fase: k / 3 });
  }
  const marcador = malha(new THREE.OctahedronGeometry(0.1, 0), new THREE.MeshStandardMaterial({ color: STATUS.trabalhando, emissive: STATUS.trabalhando, emissiveIntensity: 0.55 }), 0, 2.3, 0, raiz, false);
  marcador.visible = false;
  marcador.scale.set(0.8, 1.4, 0.8);
  const dados = { id: 'cerebro', nome: 'Cérebro', status: 'trabalhando', fala: '15.155 trechos das 3 empresas, cada uma separada', andar, raiz, corpo, cabeca, bracos: [], pernas: [], marcador, fase: 3.3, sentado: false, cerebroMalha: cerebro, alturaMarcador: 2.3 };
  raiz.traverse((m) => { m.userData.agente = dados; });
  avatares.push(dados);
  dados.casa = { x, z, rot: 0, sentado: false };
}
