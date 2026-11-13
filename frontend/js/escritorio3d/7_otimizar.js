// Escritório 3D, Fase 5 da migração (desempenho, 13/11/2026): o prédio tem ~2.500 peças, e desenhar cada uma
// separadamente custava ~22 ms de processador por quadro. Aqui, uma vez só, as peças PARADAS de cada andar
// (paredes, piso, móveis, decoração) são juntadas numa malha por material. O desenho não muda: mesma geometria,
// mesmos materiais e sombras.
// Fica de fora tudo o que se move, é clicável ou muda de visibilidade/material sozinho: avatares, LEDs, bolhas,
// peças flutuantes, ondas, carros, vidros, placas "Vaga", zonas dos setores, transparentes e qualquer peça com
// dados próprios (userData).

function juntarPecasParadas() {
  const moveis = new Set();
  const marcar = (o) => o?.traverse?.((x) => moveis.add(x));
  avatares.forEach((a) => marcar(a.raiz));
  leds.forEach(({ led }) => marcar(led));
  bolhas.forEach(({ b }) => marcar(b));
  flutuantes.forEach(marcar);
  ondas.forEach(({ onda }) => marcar(onda));
  carros.forEach(marcar);
  grupos.forEach((g) => {
    (g.userData.vidros || []).forEach(marcar);
    Object.values(g.userData.placas || {}).forEach(marcar);
  });

  const podeJuntar = (m) => {
    if (!m.isMesh || m.isInstancedMesh || moveis.has(m) || !m.visible || m.renderOrder) return false;
    if (Object.keys(m.userData).length || Array.isArray(m.material) || m.material.transparent) return false;
    for (let p = m.parent; p && !p.isScene && !grupos.includes(p) && p !== telhado; p = p.parent) {
      if (moveis.has(p) || !p.visible) return false;
    }
    return true;
  };

  // Cada raiz (andar, telhado ou o terreno) recebe uma malha por material e por tipo de sombra.
  const raizes = [...grupos, telhado, cena3d];
  let antes = 0, depois = 0;
  raizes.forEach((raiz) => {
    raiz.updateMatrixWorld(true);
    const inversa = new THREE.Matrix4().copy(raiz.matrixWorld).invert();
    const lotes = new Map();
    raiz.traverse((m) => {
      if (m === raiz || !podeJuntar(m)) return;
      let r = m.parent; // a peça pertence à raiz mais próxima
      while (r && !raizes.includes(r)) r = r.parent;
      if (r !== raiz) return;
      const g = m.geometry;
      const chave = [m.material.uuid, m.castShadow, m.receiveShadow, Object.keys(g.attributes).sort().join()].join('|');
      if (!lotes.has(chave)) lotes.set(chave, []);
      lotes.get(chave).push(m);
    });
    lotes.forEach((pecas) => {
      if (pecas.length < 2) return;
      const geo = juntarGeometrias(pecas.map((m) => {
        const copia = m.geometry.clone();
        copia.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inversa, m.matrixWorld));
        return copia;
      }));
      if (!geo) return;
      const unida = new THREE.Mesh(geo, pecas[0].material);
      unida.castShadow = pecas[0].castShadow;
      unida.receiveShadow = pecas[0].receiveShadow;
      raiz.add(unida);
      pecas.forEach((m) => m.parent.remove(m));
      antes += pecas.length;
      depois += 1;
    });
  });
  return { antes, depois };
}

// Junta geometrias (mesmos atributos) numa só, com índice.
function juntarGeometrias(lista) {
  const nomes = Object.keys(lista[0].attributes);
  const total = lista.reduce((s, g) => s + g.attributes.position.count, 0);
  const totalIndices = lista.reduce((s, g) => s + (g.index ? g.index.count : g.attributes.position.count), 0);
  const saida = new THREE.BufferGeometry();
  for (const nome of nomes) {
    const base = lista[0].attributes[nome];
    if (base.isInterleavedBufferAttribute) return null;
    const dados = new Float32Array(total * base.itemSize);
    let pos = 0;
    for (const g of lista) {
      const a = g.attributes[nome];
      if (!a || a.itemSize !== base.itemSize) return null;
      dados.set(a.array.length === a.count * a.itemSize ? a.array : Array.from(a.array).slice(0, a.count * a.itemSize), pos);
      pos += a.count * a.itemSize;
    }
    saida.setAttribute(nome, new THREE.BufferAttribute(dados, base.itemSize, base.normalized));
  }
  const indices = total > 65535 ? new Uint32Array(totalIndices) : new Uint16Array(totalIndices);
  let i = 0, deslocamento = 0;
  for (const g of lista) {
    const n = g.attributes.position.count;
    if (g.index) for (let k = 0; k < g.index.count; k++) indices[i++] = g.index.getX(k) + deslocamento;
    else for (let k = 0; k < n; k++) indices[i++] = k + deslocamento;
    deslocamento += n;
  }
  saida.setIndex(new THREE.BufferAttribute(indices, 1));
  saida.computeBoundingSphere();
  saida.computeBoundingBox();
  return saida;
}

// Nos bonecos, cada articulação (corpo, cabeça, braços, pernas, joelhos) gira inteira: as peças presas a uma
// mesma articulação viram uma malha por material. Ficam de fora o marcador de status, o cérebro que pulsa e
// qualquer peça animada sozinha. Cada malha unida guarda o agente (clique e destaque continuam iguais).
function juntarBoneco(a) {
  const fora = new Set([a.marcador, a.cerebroMalha].filter(Boolean));
  const animadas = new Set();
  leds.forEach(({ led }) => led.traverse((x) => animadas.add(x)));
  bolhas.forEach(({ b }) => animadas.add(b));
  flutuantes.forEach((f) => f.traverse((x) => animadas.add(x)));
  ondas.forEach(({ onda }) => onda.traverse((x) => animadas.add(x)));
  let antes = 0, depois = 0;
  a.raiz.traverse((articulacao) => {
    if (articulacao.isMesh || animadas.has(articulacao)) return;
    const lotes = new Map();
    articulacao.children.forEach((m) => {
      if (!m.isMesh || m.children.length || fora.has(m) || animadas.has(m) || !m.visible || m.renderOrder) return;
      if (Array.isArray(m.material) || m.material.transparent) return;
      if (Object.keys(m.userData).some((k) => k !== 'agente')) return;
      const chave = [m.material.uuid, m.castShadow, m.receiveShadow, Object.keys(m.geometry.attributes).sort().join()].join('|');
      if (!lotes.has(chave)) lotes.set(chave, []);
      lotes.get(chave).push(m);
    });
    lotes.forEach((pecas) => {
      if (pecas.length < 2) return;
      const geo = juntarGeometrias(pecas.map((m) => { m.updateMatrix(); return m.geometry.clone().applyMatrix4(m.matrix); }));
      if (!geo) return;
      const unida = new THREE.Mesh(geo, pecas[0].material);
      unida.castShadow = pecas[0].castShadow;
      unida.receiveShadow = pecas[0].receiveShadow;
      unida.userData.agente = a;
      articulacao.add(unida);
      pecas.forEach((m) => articulacao.remove(m));
      antes += pecas.length;
      depois += 1;
    });
  });
  return { antes, depois };
}

window.E3D.otimizacao = juntarPecasParadas();
window.E3D.juntarBoneco = juntarBoneco;
avatares.forEach((a) => {
  const r = juntarBoneco(a);
  window.E3D.otimizacao.antes += r.antes;
  window.E3D.otimizacao.depois += r.depois;
});

// Sombras: o sol é fixo, então o mapa de sombra só muda quando algo se move (carros, quem caminha, andares
// deslizando). Recalculá-lo em quadros alternados (30 vezes por segundo a 60 qps) é imperceptível e corta pela
// metade o custo da sombra, que é o maior do quadro.
{
  renderer.shadowMap.autoUpdate = false;
  renderer.shadowMap.needsUpdate = true;
  let quadroSombra = 0;
  const antesDoQuadro = window.E3D.aCadaQuadro;
  window.E3D.aCadaQuadro = function (agora, dt) {
    antesDoQuadro.call(this, agora, dt);
    quadroSombra = (quadroSombra + 1) % 2;
    if (quadroSombra === 0) renderer.shadowMap.needsUpdate = true;
  };
}
