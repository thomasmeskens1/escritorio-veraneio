// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
// ---------- Clique e etiquetas ----------
const raio = new THREE.Raycaster(), ponteiro = new THREE.Vector2();
function clicar(e) {
  ponteiro.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  const achado = raio.intersectObjects(cena3d.children, true).find((h) => h.object.userData.agente);
  if (achado) mostrarAgente(achado.object.userData.agente);
}
function mostrarAgente(a) { if (!a.id.startsWith('estagiario')) clicarAgente(a.casaAndar || a.andar.id, a.id); }
const camada = document.getElementById('etiquetas');
avatares.forEach((a) => {
  const el = document.createElement('button');
  el.type = 'button'; el.className = 'etiqueta'; el.hidden = true;
  el.innerHTML = `<i class="ponto" style="background:${hex(STATUS[a.status])}"></i>${a.nome}${a.fala ? ` <span class="balao-fala">· ${a.fala}</span>` : ''}`;
  el.addEventListener('click', () => mostrarAgente(a));
  camada.append(el);
  a.etiqueta = el;
});
nomesSetores.forEach((s) => { const el = document.createElement('div'); el.className = 'setor-nome'; el.textContent = s.nome; el.hidden = true; camada.append(el); s.el = el; });
const v = new THREE.Vector3();
function projetar(el, pos) {
  v.copy(pos).project(camera);
  el.style.left = `${(v.x * 0.5 + 0.5) * innerWidth}px`;
  el.style.top = `${(-v.y * 0.5 + 0.5) * innerHeight}px`;
  return v.z < 1;
}
function atualizarEtiquetas() {
  const perto = orbita.raio < 50;
  avatares.forEach((a) => {
    const mostrar = perto && !a.caminho && a.raiz.visible && a.raiz.parent?.parent?.userData?.andar?.id === andarFoco; // no andar onde está (visitas e tour, como no 2D)
    a.etiqueta.hidden = !mostrar;
    if (mostrar) { a.marcador.getWorldPosition(v); v.y += 0.2; a.etiqueta.hidden = !projetar(a.etiqueta, v.clone()); }
  });
  nomesSetores.forEach((s) => {
    const mostrar = perto && !emReuniao && andarFoco === s.andar.id;
    s.el.hidden = !mostrar;
    s.el.classList.toggle('destaque', s === setorEmDestaque);
    if (mostrar) s.el.hidden = !projetar(s.el, s.pos);
  });
}

function ajustar() { renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }
addEventListener('resize', ajustar);
ajustar();
escrever('Vista geral', textoGeral);

let antes = performance.now();
function quadro(agora) {
  const dt = Math.min(0.05, (agora - antes) / 1000);
  antes = agora;
  if (transicao) {
    const t = Math.min(1, (agora - transicao.inicio) / transicao.ms), k = suave(t), { de, para } = transicao;
    orbita.alvo.lerpVectors(de.alvo, para.alvo, k);
    orbita.raio = de.raio + (para.raio - de.raio) * k;
    orbita.azimute = de.azimute + (para.azimute - de.azimute) * k;
    orbita.polar = de.polar + (para.polar - de.polar) * k;
    if (t >= 1) transicao = null;
  } else if (girando) orbita.azimute += dt * 0.12;
  aplicarCamera();
  [...grupos, telhado].forEach((g) => {
    g.position.y += (g.userData.alvo - g.position.y) * Math.min(1, dt * (reduzir ? 60 : 5));
    g.visible = g.position.y < g.userData.base + 30;
  });
  avatares.forEach((a) => {
    const c = a.caminho;
    if (c && agora >= c.inicio) {
      const t = Math.min(1, (agora - c.inicio) / c.ms);
      a.raiz.position.lerpVectors(c.de, c.para, suave(t));
      if (t < 1) {
        a.raiz.rotation.y = Math.atan2(c.para.x - c.de.x, c.para.z - c.de.z);
        const passo = Math.sin(agora / 110 + a.fase) * 0.6;
        a.pernas[0].quadril.rotation.x = passo; a.pernas[1].quadril.rotation.x = -passo;
        a.bracos[0].rotation.x = -passo * 0.8; a.bracos[1].rotation.x = passo * 0.8;
      } else {
        a.caminho = null;
        a.raiz.rotation.y = c.rot;
        pose(a, c.sentar ? 'sentado' : 'em pe');
        c.aoChegar?.();
      }
    } else if (!c && !reduzir && !a.visitando) {
      if (a.status === 'trabalhando' && a.sentado) a.bracos.forEach((b, i) => { b.rotation.x = -1.05 + Math.sin(agora / 140 + i * 2 + a.fase) * 0.06; });
      if (a.status !== 'dormindo') a.cabeca.rotation.y = Math.sin(agora / 1300 + a.fase) * (a.status === 'disponivel' ? 0.4 : 0.15);
      else a.cabeca.rotation.x = 0.25;
    }
    a.marcador.rotation.y += dt * 1.6;
    a.marcador.position.y = (a.alturaMarcador || 1.95) + Math.sin(agora / 500 + a.fase) * 0.05;
    if (a.cerebroMalha && !reduzir) a.cerebroMalha.material.emissiveIntensity = 0.15 + (Math.sin(agora / 400) + 1) * 0.12;
  });
  if (!reduzir) {
    ondas.forEach(({ onda, fase }) => { const t = (agora / 1800 + fase) % 1; onda.scale.setScalar(1 + t * 1.6); onda.material.opacity = 0.6 * (1 - t); });
    bolhas.forEach(({ b, fase }) => { const t = (agora / 2200 + fase) % 1; b.position.y = 0.3 + t * 1.25; b.material.opacity = 0.75 * (1 - t); });
    flutuantes.forEach((f) => { f.position.y = 0.95 + Math.sin(agora / 900) * 0.12; f.rotation.y += dt * 0.4; });
    pulsantes.forEach((m) => { m.emissiveIntensity = 0.45 + (Math.sin(agora / 300) + 1) * 0.3; });
  }
  leds.forEach(({ led, fase }) => { led.material.emissiveIntensity = Math.sin(agora / 300 + fase) > 0.2 ? 1.2 : 0.15; });
  carros.forEach((c) => { c.position.x += c.userData.sentido * dt * 6; if (c.position.x > 120) c.position.x = -120; if (c.position.x < -120) c.position.x = 120; });
  window.E3D?.aCadaQuadro?.(agora, dt);
  renderer.render(cena3d, camera);
  atualizarEtiquetas();
  requestAnimationFrame(quadro);
}
requestAnimationFrame(quadro);
// ---------- Indicadores de status do 2D (avatar.js): digitando, zzz, martelo e o "!" de pendência ----------
function sprite(desenhar, escala = 0.42, l = 128, a = 96) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: textura(l, a, desenhar), transparent: true }));
  s.scale.set(escala * (l / a), escala, 1);
  s.renderOrder = 10;
  return s;
}
const balaoPontos = (aceso) => (c) => {
  c.fillStyle = '#ffffff'; c.strokeStyle = 'rgba(0,0,0,0.25)'; c.lineWidth = 3;
  c.beginPath(); c.roundRect(6, 8, 116, 62, 26); c.fill(); c.stroke();
  c.beginPath(); c.moveTo(40, 68); c.lineTo(30, 90); c.lineTo(58, 68); c.fill();
  [36, 64, 92].forEach((x, i) => { c.fillStyle = i === aceso ? '#f4a261' : '#adb5bd'; c.beginPath(); c.arc(x, 39, 9, 0, 7); c.fill(); });
};
const TEX_PONTOS = [0, 1, 2].map((i) => textura(128, 96, balaoPontos(i)));
const desenharZ = (c) => { c.fillStyle = '#ced4da'; c.font = 'bold 72px Georgia'; c.textAlign = 'center'; c.strokeStyle = 'rgba(0,0,0,0.35)'; c.lineWidth = 4; c.strokeText('z', 64, 72); c.fillText('z', 64, 72); };
const desenharMartelo = (c) => { c.translate(64, 48); c.rotate(-0.5); c.fillStyle = '#8d5524'; c.fillRect(-6, -8, 12, 52); c.fillStyle = '#868e96'; c.fillRect(-28, -30, 56, 24); c.fillStyle = '#adb5bd'; c.fillRect(-28, -30, 56, 8); };
const desenharAlerta = (c) => { c.fillStyle = '#e03131'; c.beginPath(); c.arc(64, 48, 40, 0, 7); c.fill(); c.strokeStyle = '#ffffff'; c.lineWidth = 6; c.stroke(); c.fillStyle = '#ffffff'; c.font = 'bold 60px system-ui, sans-serif'; c.textAlign = 'center'; c.fillText('!', 64, 70); };
function criarIndicadores(a) {
  const alto = a.alturaMarcador ? a.alturaMarcador + 0.1 : 2.0;
  const pontos = sprite(balaoPontos(0), 0.38);
  pontos.position.set(0.32, alto, 0);
  const zs = [0, 1].map((k) => { const z = sprite(desenharZ, 0.3); z.position.set(0.25, alto, 0); z.userData.fase = k * 0.5; return z; });
  const martelo = sprite(desenharMartelo, 0.42);
  martelo.position.set(0.35, alto - 0.1, 0);
  const alerta = sprite(desenharAlerta, 0.34);
  alerta.position.set(-0.3, alto + 0.05, 0);
  [pontos, ...zs, martelo, alerta].forEach((s) => a.raiz.add(s));
  a.ind = { pontos, zs, martelo, alerta, alto };
  aplicarIndicadores(a);
}
function aplicarIndicadores(a) {
  const { pontos, zs, martelo, alerta } = a.ind;
  pontos.visible = a.status === 'trabalhando';
  zs.forEach((z) => { z.visible = a.status === 'dormindo'; });
  martelo.visible = a.status === 'construindo';
  alerta.visible = !!a.pendente;
}
function animarIndicadores(agora) {
  avatares.forEach((a) => {
    if (!a.ind) return;
    const { pontos, zs, martelo, alto } = a.ind;
    if (pontos.visible) pontos.material.map = TEX_PONTOS[Math.floor(agora / 260) % 3];
    zs.forEach((z) => {
      if (!z.visible) return;
      const t = ((agora / 2200) + z.userData.fase) % 1;
      z.position.y = alto + t * 0.6;
      z.position.x = 0.25 + t * 0.2;
      z.material.opacity = 1 - t;
    });
    if (martelo.visible) martelo.material.rotation = Math.sin(agora / 160) * 0.5;
  });
}

// ---------- Destaque de setor no hover (destaque_setor.js): o piso do setor fica sólido e o nome sobe ----------
const raioHover = new THREE.Raycaster(), ponteiroHover = new THREE.Vector2();
let agenteSobMouse = null;
function destacar(setor) {
  if (setor === setorEmDestaque) return;
  if (setorEmDestaque) {
    setorEmDestaque.zona.material.opacity = 0.22;
    setorEmDestaque.zona.position.y = 0.015;
    setorEmDestaque.zona.material.emissiveIntensity = 0;
  }
  setorEmDestaque = setor;
  if (setor) {
    setor.zona.material.opacity = 0.78;
    setor.zona.position.y = 0.03;
    setor.zona.material.emissive.setHex(setor.cor);
    setor.zona.material.emissiveIntensity = 0.25;
  }
}
canvas.addEventListener('pointermove', (e) => {
  if (arrastando?.moveu) return;
  ponteiroHover.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raioHover.setFromCamera(ponteiroHover, camera);
  const achados = raioHover.intersectObjects(cena3d.children, true);
  const agente = achados.find((h) => h.object.userData.agente && h.object.visible)?.object.userData.agente || null;
  if (agente !== agenteSobMouse) {
    agenteSobMouse?.etiqueta?.classList.remove('hover');
    agente?.etiqueta?.classList.add('hover');
    agenteSobMouse = agente;
  }
  canvas.style.cursor = agente ? 'pointer' : '';
  const focado = ANDARES_3D.find((x) => x.id === andarFoco);
  const zona = focado && !emReuniao ? achados.find((h) => h.object.userData.setor?.andar === focado) : null;
  destacar(zona ? zona.object.userData.setor : null);
});
canvas.addEventListener('pointerleave', () => destacar(null));

// ---------- Visitas (visitas.js): um estagiário leva a resposta do Cérebro até a mesa de quem consultou ----------
const pisos = grupos.map((g) => g.children.find((c) => c.userData.assentos));
function pontoDoElevador(andar) {
  const item = andar.paredes.find((p) => p[0] === 'elevador');
  const meio = (item[2] + item[3]) / 2;
  return new THREE.Vector3(LARG / 2 - 0.9, 0, -FUNDO / 2 + (meio * FUNDO) / andar.grade);
}
function andarAte(a, destino, rot, aoChegar, sentar = false) {
  pose(a, 'em pe');
  const distancia = a.raiz.position.distanceTo(destino);
  a.caminho = { de: a.raiz.position.clone(), para: destino.clone(), rot, sentar, inicio: performance.now(), ms: reduzir ? 1 : Math.max(500, distancia * 420), aoChegar };
}
function trocarDeAndar(a, nAndar, aoSair) {
  a.raiz.visible = false;
  setTimeout(() => {
    pisos[nAndar].add(a.raiz);
    a.raiz.position.copy(pontoDoElevador(ANDARES_3D[nAndar]));
    a.raiz.visible = true;
    aoSair();
  }, reduzir ? 10 : 1400);
}
function visitar(estagiario, alvo) {
  if (!estagiario || !alvo || estagiario.visitando || estagiario.caminho) return;
  const nCasa = ANDARES_3D.findIndex((x) => x.id === estagiario.andar.id);
  const nAlvo = ANDARES_3D.findIndex((x) => x.id === alvo.andar.id);
  const falaAntes = estagiario.fala;
  estagiario.visitando = alvo;
  window.UI?.aoVisita?.(estagiario, alvo, true);
  andarAte(estagiario, pontoDoElevador(ANDARES_3D[nCasa]), Math.PI / 2, () => trocarDeAndar(estagiario, nAlvo, () => {
    const ao = alvo.raiz.position.clone().add(new THREE.Vector3(0.75, 0, 0.35));
    estagiario.fala = `Levando a resposta do Cérebro ao ${alvo.nome}`;
    andarAte(estagiario, ao, -Math.PI / 2 - 0.3, () => setTimeout(() => {
      andarAte(estagiario, pontoDoElevador(ANDARES_3D[nAlvo]), Math.PI / 2, () => trocarDeAndar(estagiario, nCasa, () => {
        const casa = new THREE.Vector3(estagiario.casa.x, 0, estagiario.casa.z);
        andarAte(estagiario, casa, 0, () => {
          estagiario.visitando = null;
          estagiario.fala = falaAntes;
          window.UI?.aoVisita?.(estagiario, alvo, false);
        }, true);
      }));
    }, reduzir ? 10 : 6000));
  }));
}
let proximaVisita = performance.now() + 9000;
function talvezVisitar(agora) {
  if (agora < proximaVisita || reuniaoAtual) return;
  proximaVisita = agora + 32000;
  const livres = avatares.filter((a) => a.id.startsWith('estagiario') && a.status !== 'dormindo' && !a.visitando && !a.caminho);
  const atendidos = avatares.filter((a) => !a.id.startsWith('estagiario') && a.id !== 'cerebro' && a.andar.id !== 'cobertura' && !a.caminho);
  if (!livres.length || !atendidos.length) return;
  visitar(livres[Math.floor(Math.random() * livres.length)], atendidos[Math.floor(Math.random() * atendidos.length)]);
}

// ---------- API para a interface (interface.js) ----------
function irParaAgente(a) {
  const nAgora = a.raiz.parent?.parent ? grupos.indexOf(a.raiz.parent.parent) : -1;
  const andarAgora = nAgora >= 0 ? ANDARES_3D[nAgora] : a.andar;
  if (andarFoco !== andarAgora.id) focarAndar(andarAgora.id);
  const pos = new THREE.Vector3();
  a.raiz.getWorldPosition(pos);
  irPara({ alvo: new THREE.Vector3(pos.x, nAgora * ALTURA + 1.2, pos.z), raio: 12, azimute: orbita.azimute, polar: 1.0 }, 1100);
}
function definirStatus(a, status) {
  a.status = status;
  a.marcador.material.color.setHex(STATUS[status]);
  a.marcador.material.emissive.setHex(STATUS[status]);
  a.etiqueta.querySelector('.ponto').style.background = hex(STATUS[status]);
  if (a.ind) aplicarIndicadores(a);
}
function definirPendente(a, pendente) {
  a.pendente = pendente;
  a.etiqueta.classList.toggle('pendente', pendente);
  if (a.ind) aplicarIndicadores(a);
}
avatares.forEach(criarIndicadores);
window.E3D = {
  ANDARES_3D, AP, avatares, STATUS, NOME_STATUS, hex,
  focarAndar, irParaAgente, definirStatus, definirPendente, visitar, grupos, telhado,
  andarAte, trocarDeAndar, pontoDoElevador, avatar, criarIndicadores, coord, pose,
  iniciarReuniao, encerrarReuniao, mostrarAgente,
  andarFoco: () => andarFoco,
  emReuniao: () => !!reuniaoAtual,
  aCadaQuadro(agora) {
    animarIndicadores(agora);
  },
};
