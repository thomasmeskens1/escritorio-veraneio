// Escritório 3D (Fase 1 da migração, Thomas 13/11/2026): cena do protótipo aprovado, dividida em módulos que
// compartilham o escopo global (carregados em ordem por js/escritorio3d/estado.js). Só visual: dados e regras
// vêm do sistema (estado.js liga a cena ao estado do servidor).
// ---------- Câmera ----------
const VISTA_GERAL = { alvo: new THREE.Vector3(0, 7.5, 0), raio: 82, azimute: -0.62, polar: 1.04 };
const orbita = { alvo: VISTA_GERAL.alvo.clone(), raio: VISTA_GERAL.raio, azimute: VISTA_GERAL.azimute, polar: VISTA_GERAL.polar };
let transicao = null;
function aplicarCamera() {
  const { alvo, raio, azimute, polar } = orbita;
  camera.position.set(alvo.x + raio * Math.sin(polar) * Math.sin(azimute), alvo.y + raio * Math.cos(polar), alvo.z + raio * Math.sin(polar) * Math.cos(azimute));
  camera.lookAt(alvo);
}
const suave = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
function irPara(destino, ms = 1200) {
  let azimute = destino.azimute; // gira pelo caminho mais curto
  while (azimute - orbita.azimute > Math.PI) azimute -= Math.PI * 2;
  while (azimute - orbita.azimute < -Math.PI) azimute += Math.PI * 2;
  transicao = { de: { alvo: orbita.alvo.clone(), raio: orbita.raio, azimute: orbita.azimute, polar: orbita.polar }, para: { ...destino, azimute }, inicio: performance.now(), ms: reduzir ? 1 : ms };
}
let arrastando = null;
canvas.addEventListener('pointerdown', (e) => { arrastando = { x: e.clientX, y: e.clientY, moveu: false }; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', (e) => {
  if (!arrastando) return;
  const dx = e.clientX - arrastando.x, dy = e.clientY - arrastando.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) arrastando.moveu = true;
  orbita.azimute -= dx * 0.005;
  orbita.polar = Math.min(1.42, Math.max(0.3, orbita.polar - dy * 0.004));
  arrastando.x = e.clientX; arrastando.y = e.clientY;
  transicao = null;
});
canvas.addEventListener('pointerup', (e) => { if (arrastando && !arrastando.moveu) clicar(e); arrastando = null; });
canvas.addEventListener('wheel', (e) => { e.preventDefault(); orbita.raio = Math.min(130, Math.max(5, orbita.raio * (1 + Math.sign(e.deltaY) * 0.08))); transicao = null; }, { passive: false });

// ---------- Andares e reunião ----------
let andarFoco = null, emReuniao = false, setorEmDestaque = null;
const botoesAndar = [];
document.querySelectorAll('#elevador .andar').forEach((b) => botoesAndar.push([b.dataset.andar, b]));
const btPredio = document.getElementById('vista-predio'), btReuniao = document.getElementById('vista-reuniao'), btGirar = document.getElementById('girar');
const totalAgentes = avatares.length;
function marcar(id) {
  botoesAndar.forEach(([a, b]) => { b.setAttribute('aria-pressed', String(a === id)); b.classList.toggle('ativo', a === id); });
  btPredio.setAttribute('aria-pressed', String(id === null));
  btReuniao.setAttribute('aria-pressed', String(id === 'reuniao'));
}
function escrever(titulo) { const el = document.getElementById('andar-atual'); if (el) el.textContent = titulo; }
const textoGeral = `5 andares e ${totalAgentes} agentes, contando o Cérebro e os estagiários. Escolha um andar no elevador para abrir o pavimento, como numa maquete.`;
function focarAndar(id, reuniao = false) {
  if (!reuniao && reuniaoAtual) encerrarReuniao();
  const n = ANDARES_3D.findIndex((a) => a.id === id);
  andarFoco = id;
  grupos.forEach((g, i) => {
    g.userData.alvo = id === null || i <= n ? g.userData.base : g.userData.base + 45;
    g.userData.vidros.forEach((v) => { v.visible = id === null || i !== n; });
  });
  telhado.userData.alvo = id === null ? telhado.userData.base : telhado.userData.base + 45;
  marcar(reuniao ? 'reuniao' : id);
  if (id === null) { irPara(VISTA_GERAL); escrever('Vista geral', textoGeral); return; }
  const andar = ANDARES_3D[n];
  if (reuniao) {
    const [cx, cz] = centroDaReuniao(id);
    irPara({ alvo: new THREE.Vector3(cx, n * ALTURA + 1.2, cz), raio: 12, azimute: -Math.PI / 2 - 0.25, polar: 1.1 }, 1700);
    escrever(reuniaoAtual?.titulo || 'Sala de reunião', reuniaoAtual?.texto || '');
    return;
  }
  irPara({ alvo: new THREE.Vector3(0, n * ALTURA + 0.6, 0), raio: 38, azimute: -0.5, polar: 0.86 });
  const ativos = andar.agentes.filter((a) => a[3] === 'trabalhando').length;
  escrever(ANDARES[andar.id]?.nome || andar.nome, `${andar.agentes.length} ${andar.agentes.length === 1 ? 'agente' : 'agentes'}, ${ativos} trabalhando agora. Clique num agente para ver o que ele está fazendo.`);
}
btPredio.addEventListener('click', () => focarAndar(null));
btReuniao.addEventListener('click', () => {
  if (reuniaoAtual) { const onde = andarFoco; encerrarReuniao(); focarAndar(onde); return; }
  iniciarReuniao(andarFoco);
});
let girando = false;
btGirar.addEventListener('click', () => { girando = !girando; btGirar.setAttribute('aria-pressed', String(girando)); });
// ---------- Reunião ----------
// Com um andar aberto: a equipe daquele andar vai à mesa de reunião do próprio andar (Térreo e Porão, sem mesa, em
// roda e de pé). Sem andar: os gestores de cada andar sobem pelo elevador e se reúnem na Cobertura, com o Cérebro.
const LIDERES = ['recepcionista', 'gestor', 'estrategista', 'despachante'];
const RODA = { terreo: [4.2, 2.4], porao: [6.5, 5.2] }; // centro da roda (tiles do 2D) nos andares sem mesa
let reuniaoAtual = null;
function centroDaReuniao(andarId) {
  if (centrosReuniao[andarId]) return centrosReuniao[andarId];
  const andar = ANDARES_3D.find((x) => x.id === andarId);
  return coord(andar, ...(RODA[andarId] || [andar.grade / 2, andar.grade / 2]));
}
function lugaresLivres(andarId, quantos) {
  const lugares = (lugaresReuniao[andarId] || []).filter((l) => !avatares.some((a) => a.naMesa && a.andar.id === andarId
    && Math.abs(a.casa.x - l.x) < 0.1 && Math.abs(a.casa.z - l.z) < 0.1));
  lugares.sort((m, o) => (o.rot === Math.PI) - (m.rot === Math.PI)); // primeiro o lado de frente para quem já está à mesa
  if (lugares.length >= quantos) return lugares;
  const [cx, cz] = centroDaReuniao(andarId); // sem cadeiras suficientes: em roda, de pé, olhando para o centro
  for (let k = lugares.length; k < quantos; k++) {
    const ang = (k / quantos) * Math.PI * 2;
    lugares.push({ x: cx + Math.cos(ang) * 1.4, z: cz + Math.sin(ang) * 1.4, rot: Math.atan2(-Math.cos(ang), -Math.sin(ang)), cadeira: false });
  }
  return lugares;
}
function sentarNoLugar(a, lugar, atraso = 0) {
  setTimeout(() => andarAte(a, new THREE.Vector3(lugar.x, 0, lugar.z), lugar.rot, null, lugar.cadeira), reduzir ? 0 : atraso);
}
function iniciarReuniao(andarId) {
  const local = andarId || 'cobertura';
  const andar = ANDARES_3D.find((x) => x.id === local);
  const participantes = andarId
    ? avatares.filter((a) => a.andar.id === andarId && a.id !== 'cerebro' && !a.visitando)
    : avatares.filter((a) => LIDERES.includes(a.id) && !a.visitando);
  const nomes = participantes.map((a) => a.nome);
  reuniaoAtual = {
    andarId: local, gestores: !andarId, participantes,
    titulo: andarId ? `Reunião · ${andar.sub}` : 'Reunião dos gestores · Cobertura',
    texto: andarId
      ? `${nomes.join(', ')} na mesa do ${andar.nome}.`
      : `${nomes.join(', ')} sobem para a Cobertura e se reúnem com o Cérebro.`,
  };
  emReuniao = true;
  focarAndar(local, true);
  const movem = participantes.filter((a) => !(a.naMesa && a.andar.id === local));
  const lugares = lugaresLivres(local, movem.length);
  const nLocal = ANDARES_3D.findIndex((x) => x.id === local);
  movem.forEach((a, k) => {
    const lugar = lugares[k];
    const nAgora = grupos.indexOf(a.raiz.parent?.parent);
    if (nAgora === nLocal) { a.emViagem = false; a.lugarPendente = null; sentarNoLugar(a, lugar, k * 120); return; }
    if (a.emViagem) { a.lugarPendente = { lugar, n: nLocal }; return; } // ainda no elevador: vai direto ao chegar
    // Gestor de outro andar: vai ao elevador do próprio andar, sobe e senta na Cobertura
    const nCasa = ANDARES_3D.findIndex((x) => x.id === a.andar.id);
    a.emViagem = true;
    setTimeout(() => andarAte(a, pontoDoElevador(ANDARES_3D[nCasa]), Math.PI / 2, () => trocarDeAndar(a, nLocal, () => {
      a.emViagem = false;
      if (reuniaoAtual?.participantes.includes(a)) sentarNoLugar(a, lugar);
    })), reduzir ? 0 : k * 250);
  });
}
function encerrarReuniao() {
  const atual = reuniaoAtual;
  reuniaoAtual = null;
  emReuniao = false;
  if (!atual) return;
  atual.participantes.forEach((a, k) => {
    const casa = new THREE.Vector3(a.casa.x, 0, a.casa.z);
    const nCasa = ANDARES_3D.findIndex((x) => x.id === a.andar.id);
    const nAgora = grupos.indexOf(a.raiz.parent?.parent);
    a.emViagem = true;
    const voltarParaMesa = () => {
      // Uma reunião nova neste mesmo andar já levou o agente para a mesa: não volta para a própria mesa.
      if (reuniaoAtual?.participantes.includes(a) && !a.lugarPendente && grupos.indexOf(a.raiz.parent?.parent) === ANDARES_3D.findIndex((x) => x.id === reuniaoAtual.andarId)) return;
      const pendente = a.lugarPendente;
      a.lugarPendente = null;
      if (pendente && reuniaoAtual?.participantes.includes(a)) { // outra reunião começou durante a volta
        a.emViagem = false;
        if (pendente.n === nCasa) { sentarNoLugar(a, pendente.lugar); return; }
        andarAte(a, pontoDoElevador(ANDARES_3D[nCasa]), Math.PI / 2, () => trocarDeAndar(a, pendente.n, () => sentarNoLugar(a, pendente.lugar)));
        return;
      }
      andarAte(a, casa, a.casa.rot || 0, () => { a.emViagem = false; }, a.casa.sentado);
    };
    if (nAgora === nCasa) { setTimeout(voltarParaMesa, reduzir ? 0 : k * 100); return; }
    // Desce pelo elevador e volta para a própria mesa
    setTimeout(() => andarAte(a, pontoDoElevador(ANDARES_3D[nAgora]), Math.PI / 2, () => trocarDeAndar(a, nCasa, voltarParaMesa)), reduzir ? 0 : k * 150);
  });
}
