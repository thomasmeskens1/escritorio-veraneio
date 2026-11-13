// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
// ---------- Prédio ----------
const grupos = [];
const vidroMat = new THREE.MeshPhysicalMaterial({ color: 0xb5dbe8, roughness: 0.04, metalness: 0.1, transparent: true, opacity: 0.26 });
const caixilho = mat(0xf7f5ef);
const nomesSetores = [];
const posReuniao = [];
const lugaresReuniao = {}, centrosReuniao = {};
const coord = (andar, x, y) => [-LARG / 2 + (x * LARG) / andar.grade, -FUNDO / 2 + (y * FUNDO) / andar.grade];

ANDARES_3D.forEach((andar, n) => {
  const g = new THREE.Group();
  g.position.y = n * ALTURA;
  g.userData = { base: n * ALTURA, alvo: n * ALTURA, andar };
  cena3d.add(g);
  grupos.push(g);
  semente = 11 + n * 7;
  // laje, piso com textura, teto e luminárias
  caixa(LARG + 0.6, 0.3, FUNDO + 0.6, mat(0xefebe3), 0, 0.15, 0, g);
  const p = new THREE.Group();
  p.position.y = 0.31;
  g.add(p);
  p.userData.assentos = [];
  const baixo = new THREE.Group(); // móveis desenhados com a laje embutida na altura
  baixo.position.y = -0.31;
  p.add(baixo);
  caixa(LARG - 0.1, 0.02, FUNDO - 0.1, new THREE.MeshStandardMaterial({ map: PISOS[andar.chao](andar.corChao), roughness: andar.chao === 'marmore' ? 0.35 : 0.85 }), 0, 0.31, 0, g, false);
  for (let x = -6; x <= 6; x += 4) for (let z = -3; z <= 3; z += 3) {
    cilindro(0.01, 0.01, 0.4, mat(0x333333), x, ALTURA - 0.2, z, g, 4);
    malha(new THREE.CylinderGeometry(0.14, 0.24, 0.16, 14, 1, true), brilho(0xfff1c1, 0.45), x, ALTURA - 0.45, z, g, false);
  }
  // paredes do fundo e da direita (núcleo), na cor do andar
  caixa(LARG, ALTURA - 0.3, 0.2, mat(andar.parede), 0, ALTURA / 2 + 0.15, -FUNDO / 2 + 0.05, g);
  caixa(0.2, ALTURA - 0.3, FUNDO, mat(andar.parede), LARG / 2 - 0.05, ALTURA / 2 + 0.15, 0, g);
  caixa(LARG, 0.12, 0.04, mat(tom(andar.parede, 0.7)), 0, 0.37, -FUNDO / 2 + 0.17, g); // rodapé
  // setores: piso demarcado e nome
  andar.setores.forEach((s) => {
    const [x0, z0] = coord(andar, s.area[0], s.area[1]), [x1, z1] = coord(andar, s.area[0] + s.area[2], s.area[1] + s.area[3]);
    const zona = caixa(x1 - x0 - 0.2, 0.01, z1 - z0 - 0.2, new THREE.MeshStandardMaterial({ color: s.cor, transparent: true, opacity: 0.22, roughness: 1 }), (x0 + x1) / 2, 0.015, (z0 + z1) / 2, p, false);
    zona.receiveShadow = true;
    const setor3d = { andar, nome: s.nome, pos: new THREE.Vector3((x0 + x1) / 2, n * ALTURA + 0.34, z1 - 0.3), grupo: g, zona, cor: s.cor };
    zona.userData.setor = setor3d;
    nomesSetores.push(setor3d);
  });
  andar.moveis.forEach(([tipo, x, y, a, b, c]) => {
    if (tipo === 'cadeirasFrente' && andar.id === 'marketing') return;
    if (tipo === 'tapete') { const [cx, cz] = coord(andar, x + a / 2, y + b / 2); MOVEIS.tapete(p, cx, cz, (a * LARG) / andar.grade, (b * FUNDO) / andar.grade, c); return; }
    const centro = tipo === 'mesaReuniao' ? coord(andar, x + 1.5, y + 0.55) : tipo === 'cadeirasFrente' ? coord(andar, x + 1.5, y + 0.3) : coord(andar, x + 0.5, y + 0.5);
    MOVEIS[tipo]?.(ALTOS.has(tipo) ? baixo : p, centro[0], centro[1], tipo === 'cerebro' ? andar : a, b, c);
    if (tipo === 'cadeirasFrente') for (let k = 0; k < 3; k++) (lugaresReuniao[andar.id] ||= []).push({ x: centro[0] - 1 + k, z: centro[1], rot: Math.PI, cadeira: true });
    if (tipo === 'mesaReuniao' && andar.id === 'marketing') {
      for (let k = 0; k < 12; k++) {
        const atras = k < 5, frente = k >= 5 && k < 10;
        const px = atras ? centro[0] - 1.3 + k * 0.65 : frente ? centro[0] - 1.3 + (k - 5) * 0.65 : centro[0] + (k === 10 ? -2.05 : 2.05);
        const pz = atras ? centro[1] - 0.95 : frente ? centro[1] + 0.95 : centro[1];
        const rot = atras ? 0 : frente ? Math.PI : (k === 10 ? Math.PI / 2 : -Math.PI / 2);
        posReuniao.push({ x: px, z: pz, rot });
        (lugaresReuniao[andar.id] ||= []).push({ x: px, z: pz, rot, cadeira: true, mesa: atras });
        cadeira(p, px, pz, rot, 0x2b2d42);
        if (atras) p.userData.assentos.push({ x: px, z: pz });
        reuniaoCentro.set(centro[0], 0, centro[1]);
        centrosReuniao[andar.id] = [centro[0], centro[1]];
      }
    } else if (tipo === 'mesaReuniao') {
      for (let k = 0; k < 4; k++) {
        cadeira(p, centro[0] - 1.1 + k * 0.73, centro[1] - 0.95, 0, 0x2b2d42);
        p.userData.assentos.push({ x: centro[0] - 1.1 + k * 0.73, z: centro[1] - 0.95 });
        (lugaresReuniao[andar.id] ||= []).push({ x: centro[0] - 1.1 + k * 0.73, z: centro[1] - 0.95, rot: 0, cadeira: true, mesa: true });
      }
      const [cx0, cz0] = centrosReuniao[andar.id] || centro; // duas mesas (Cobertura): o meio entre elas
      centrosReuniao[andar.id] = centrosReuniao[andar.id] ? [(cx0 + centro[0]) / 2, (cz0 + centro[1]) / 2] : [centro[0], centro[1]];
    }
  });
  andar.paredes.forEach((item) => itemParede(p, andar, item));
  // agentes: mesa do setor na ordem do 2D; Térreo com posição fixa; reunião nas cadeiras do fundo
  const livres = Object.fromEntries(andar.setores.map((s) => [s.id, [...(s.mesas || [])]]));
  andar.agentes.forEach(([id, nome, setor, status, fala, fixo, tipoEstacao]) => {
    const setorDados = andar.setores.find((s) => s.id === setor);
    const lugar = fixo || livres[setor]?.shift();
    if (!lugar) return;
    const [x, z] = coord(andar, lugar[0] + 0.5, lugar[1] + 0.5);
    const a = avatar(id, nome, status, fala, andar);
    const naReuniao = setorDados?.estacao === 'nenhuma';
    if (naReuniao) {
      const assentos = p.userData.assentos;
      assentos.sort((m, o) => Math.abs(m.x - x) - Math.abs(o.x - x));
      const lugarMesa = assentos.shift() || { x, z };
      a.raiz.position.set(lugarMesa.x, 0, lugarMesa.z);
      a.naMesa = true;
    } else { estacao(p, tipoEstacao || setorDados?.estacao, x, z); a.raiz.position.set(x, 0, z - 0.12); }
    if (tipoEstacao === 'balcao' || tipoEstacao === 'pulpito') pose(a, 'em pe');
    p.add(a.raiz);
    a.casa = { x: a.raiz.position.x, z: a.raiz.position.z, rot: 0, sentado: a.sentado };
  });
  g.userData.livres = livres;
  g.userData.piso = p;
  g.userData.placas = {};
  // mesas vagas (sempre uma por setor com estação, como no 2D)
  andar.setores.filter((s) => s.estacao && s.estacao !== 'nenhuma' && livres[s.id]?.length).forEach((s) => {
    const [x, z] = coord(andar, livres[s.id][0][0] + 0.5, livres[s.id][0][1] + 0.5);
    estacao(p, s.estacao === 'design' ? 'mesa' : s.estacao, x, z);
    const placa = malha(new THREE.PlaneGeometry(0.5, 0.18), new THREE.MeshBasicMaterial({ map: textura(128, 48, (c) => { c.fillStyle = '#f5efe3'; c.fillRect(0, 0, 128, 48); c.fillStyle = '#00361b'; c.font = 'bold 26px Georgia'; c.textAlign = 'center'; c.fillText('Vaga', 64, 34); }) }), x, 0.95, z + 0.95, p, false);
    placa.rotation.x = -0.4;
    g.userData.placas[s.id] = placa;
  });
  // fachada: pilares, vidro, montantes e faixa de laje
  [[-LARG / 2, -FUNDO / 2], [LARG / 2, -FUNDO / 2], [-LARG / 2, FUNDO / 2], [LARG / 2, FUNDO / 2]].forEach(([x, z]) => caixa(0.4, ALTURA, 0.4, caixilho, x, ALTURA / 2, z, g));
  const vidros = [caixa(LARG, ALTURA - 0.3, 0.05, vidroMat, 0, ALTURA / 2 + 0.15, FUNDO / 2, g, false), caixa(0.05, ALTURA - 0.3, FUNDO, vidroMat, -LARG / 2, ALTURA / 2 + 0.15, 0, g, false)];
  const montantes = [];
  for (let x = -LARG / 2 + 2; x < LARG / 2; x += 2) montantes.push(caixa(0.08, ALTURA - 0.3, 0.1, caixilho, x, ALTURA / 2 + 0.15, FUNDO / 2, g));
  for (let z = -FUNDO / 2 + 2; z < FUNDO / 2; z += 2) montantes.push(caixa(0.1, ALTURA - 0.3, 0.08, caixilho, -LARG / 2, ALTURA / 2 + 0.15, z, g));
  montantes.push(caixa(LARG, 0.1, 0.1, caixilho, 0, 1.1, FUNDO / 2, g), caixa(0.1, 0.1, FUNDO, caixilho, -LARG / 2, 1.1, 0, g));
  g.userData.vidros = [...vidros, ...montantes];
  if (andar.id === 'terreo') { // marquise e portas da entrada
    g.userData.vidros.push(caixa(5, 0.18, 2.2, mat(VERDE), 0, ALTURA - 0.45, FUNDO / 2 + 1.1, g));
    caixa(2.2, 2.3, 0.08, mat(0x88b8c8, { transparent: true, opacity: 0.5, roughness: 0.05 }), 0, 1.45, FUNDO / 2 + 0.02, g, false);
  }
});
const telhado = new THREE.Group();
telhado.position.y = ANDARES_3D.length * ALTURA;
telhado.userData = { base: ANDARES_3D.length * ALTURA, alvo: ANDARES_3D.length * ALTURA };
cena3d.add(telhado);
caixa(LARG + 0.6, 0.35, FUNDO + 0.6, mat(0xefebe3), 0, 0.17, 0, telhado);
caixa(LARG + 0.6, 0.9, 0.08, vidroMat, 0, 0.8, FUNDO / 2 + 0.25, telhado, false);
caixa(0.08, 0.9, FUNDO + 0.6, vidroMat, -LARG / 2 - 0.25, 0.8, 0, telhado, false);
for (let x = -6; x <= 6; x += 1.2) caixa(0.15, 0.15, 6, mat(0x9b7653), x, 2.6, -2, telhado);
[[-6.5, -4.6], [6.5, -4.6], [-6.5, 0.6], [6.5, 0.6]].forEach(([x, z]) => caixa(0.2, 2.6, 0.2, mat(0x9b7653), x, 1.3, z, telhado));
MOVEIS.sofa(telhado, -3, -2, 0x00361b);
MOVEIS.sofa(telhado, 3, -2, 0x00361b);
MOVEIS.mesinha(telhado, 0, -1.6);
planta(telhado, -7, 4.5, true); planta(telhado, 7, 4.5, true);
caixa(4.6, 1.6, 0.3, mat(VERDE), 0, 1.15, FUNDO / 2 + 0.05, telhado);
malha(new THREE.PlaneGeometry(4.3, 1.35), new THREE.MeshBasicMaterial({ map: textura(512, 160, (c) => { c.fillStyle = '#00361B'; c.fillRect(0, 0, 512, 160); c.fillStyle = '#D9A15B'; c.font = 'italic 700 64px Georgia, serif'; c.textAlign = 'center'; c.fillText('Veraneio', 256, 100); }) }), 0, 1.15, FUNDO / 2 + 0.21, telhado, false);
