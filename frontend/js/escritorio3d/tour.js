// Tour da Recepcionista no prédio 3D (migração do visual, Fase 4, Thomas 13/11/2026).
// Os passos, os textos, a caixa de diálogo, os destaques e as teclas são os do 2D (js/onboarding.js), sem mudança.
// Aqui só se troca a parte que dependia do motor Phaser: a Recepcionista anda de verdade pelo prédio 3D (pelo
// elevador) até ficar ao lado de cada agente, e a câmera vai junto com ela.
// Ajustes do Thomas (13/11/2026): a câmera acompanha a caminhada; no tour ela anda mais rápido e o elevador é
// mais curto; no passo do "!" vermelho, o agente mostra o "!" de exemplo enquanto ela explica.
// Carregado depois da cena (estado.js, SCRIPTS_3D); as funções abaixo substituem as homônimas do onboarding.js.

const TOUR_AO_LADO = new THREE.Vector3(0.75, 0, 0.35); // mesmo lugar ao lado do agente usado nas visitas
const TOUR_ESPERA_CAMERA = reduzir ? 0 : 700;
const TOUR_RITMO = 0.55;                    // caminhada 45% mais rápida (o mesmo RITMO_TOUR do 2D)
const TOUR_ELEVADOR_MS = reduzir ? 10 : 600; // as visitas dos estagiários levam 1,4 s no elevador
const TOUR_RAIO = 12;                       // distância da câmera: a mesma de quando se clica num agente

function guiaDoTour() {
  return window.E3D.avatares.find((a) => a.id === 'recepcionista' && a.andar.id === 'terreo') || null;
}

// O avatar do agente do passo, no andar do passo.
function agenteDoTour(andar, agente) {
  return window.E3D.avatares.find((a) => a.id === agente && a.andar.id === andar) || null;
}

function criarGuia() {
  const avatar = guiaDoTour();
  onboarding.guia = avatar ? { avatar, saiu: false, seguir: false, token: 0, noElevador: false, depois: null } : null;
  return onboarding.guia;
}

// Fim do tour: ela volta para a mesa dela no Térreo (se estiver no elevador, assim que sair dele).
function removerGuia() {
  const guia = onboarding?.guia;
  if (!guia) return;
  onboarding.guia = null;
  guia.seguir = false;
  guia.token += 1;
  const a = guia.avatar;
  if (!guia.saiu) return;
  const voltar = () => {
    const nCasa = ANDARES_3D.findIndex((x) => x.id === a.andar.id);
    levar(a, nCasa, new THREE.Vector3(a.casa.x, 0, a.casa.z), a.casa.rot || 0, a.casa.sentado);
  };
  if (guia.noElevador) guia.depois = voltar;
  else voltar();
}

function ocultarRecepcionistaDaMesa() {} // no 3D ela mesma sai da mesa (não há uma cópia)

// A câmera se aproxima dela (o mesmo enquadramento de quando se clica num agente).
function focarCamera() {
  const guia = onboarding?.guia;
  if (guia) window.E3D.irParaAgente(guia.avatar);
}

function seguirGuia() {}

// Caminhada do tour, mais rápida que a das visitas.
function andarNoTour(a, destino, rot, aoChegar) {
  window.E3D.andarAte(a, destino, rot, aoChegar, false);
  if (a.caminho) a.caminho.ms = Math.max(300, a.caminho.ms * TOUR_RITMO);
}

// Leva a guia até um ponto, trocando de andar pelo elevador se preciso. Um pedido novo (outro passo) cancela o
// anterior; se ela estiver dentro do elevador, o pedido novo espera a porta abrir.
function moverGuia(guia, nDestino, ponto, rot, aoChegar) {
  const a = guia.avatar;
  if (guia.noElevador) { guia.depois = () => moverGuia(guia, nDestino, ponto, rot, aoChegar); guia.token += 1; return; }
  const token = (guia.token += 1);
  const valendo = (f) => () => { if (guia.token === token) f(); };
  const nAgora = window.E3D.grupos.indexOf(a.raiz.parent?.parent);
  guia.seguir = true;
  if (nAgora === nDestino || nAgora < 0) { andarNoTour(a, ponto, rot, valendo(aoChegar)); return; }

  andarNoTour(a, window.E3D.pontoDoElevador(ANDARES_3D[nAgora]), Math.PI / 2, valendo(() => {
    guia.noElevador = true;
    a.raiz.visible = false;
    // A câmera vai para o andar de destino enquanto ela está no elevador e a espera na porta.
    renderizarAndar(ANDARES_3D[nDestino].id);
    const porta = window.E3D.pontoDoElevador(ANDARES_3D[nDestino]);
    irPara({ alvo: new THREE.Vector3(porta.x, nDestino * ALTURA + 1.2, porta.z), raio: TOUR_RAIO, azimute: orbita.azimute, polar: 1.0 }, TOUR_ELEVADOR_MS + 200);
    setTimeout(() => {
      pisos[nDestino].add(a.raiz);
      a.raiz.position.copy(porta);
      a.raiz.visible = true;
      guia.noElevador = false;
      const depois = guia.depois;
      guia.depois = null;
      if (depois) { depois(); return; }
      if (guia.token === token) andarNoTour(a, ponto, rot, valendo(aoChegar));
    }, TOUR_ELEVADOR_MS);
  }));
}

// Leva a Recepcionista até o agente do passo; ao chegar, a câmera se aproxima e ela fala.
function levarGuia(andar, agente, aoChegar) {
  const geracao = onboarding.geracao;
  const vivo = () => onboarding && geracao === onboarding.geracao;
  const guia = onboarding.guia || criarGuia();
  if (!guia) { if (andar !== andarAtual) renderizarAndar(andar); aoChegar(); return; } // sem o avatar dela: fala sem andar

  const a = guia.avatar;
  const n = ANDARES_3D.findIndex((x) => x.id === andar);
  const chegar = () => {
    if (!vivo()) return;
    guia.seguir = false;
    focarCamera();
    mostrarExemploDoPasso(andar, agente);
    setTimeout(() => { if (vivo()) aoChegar(); }, TOUR_ESPERA_CAMERA);
  };
  if (agente === 'recepcionista' && !guia.saiu) { // primeiro passo: ela ainda está na mesa
    if (andar !== andarAtual) renderizarAndar(andar);
    chegar();
    return;
  }
  // Mesmo andar: a câmera já vai para perto dela e a acompanha.
  const nAgora = window.E3D.grupos.indexOf(a.raiz.parent?.parent);
  if (nAgora === n && !guia.noElevador) {
    if (andar !== andarAtual) renderizarAndar(andar);
    window.E3D.irParaAgente(a);
  }

  const alvo = agente === 'recepcionista' ? null : agenteDoTour(andar, agente);
  const ponto = alvo ? alvo.raiz.position.clone().add(TOUR_AO_LADO) : new THREE.Vector3(a.casa.x + 0.75, 0, a.casa.z + 0.35);
  guia.saiu = true;
  moverGuia(guia, n, ponto, -Math.PI / 2 - 0.3, chegar);
}

// ---------- "!" de exemplo: no passo que explica o "!" vermelho, o agente mostra um enquanto ela fala ----------
let exemploPendente = null; // { a, antes, indice }

function mostrarExemploDoPasso(andar, agente) {
  const passo = onboarding?.passos[onboarding.indice];
  if (!passo?.texto.includes('“!”')) return;
  const a = agenteDoTour(andar, agente);
  if (!a || exemploPendente) return;
  exemploPendente = { a, antes: !!a.pendente, indice: onboarding.indice };
  window.E3D.definirPendente(a, true);
}

function tirarExemplo() {
  if (!exemploPendente) return;
  const { a, antes } = exemploPendente;
  exemploPendente = null;
  // devolve o estado real (pode ter mudado durante o passo)
  window.E3D.definirPendente(a, antes || pendenciasAgentes.has(`${a.andar.id}/${a.id}`));
}

// ---------- A câmera acompanha a guia enquanto ela caminha ----------
const quadroAntesDoTour = window.E3D.aCadaQuadro;
const posGuia = new THREE.Vector3();
window.E3D.aCadaQuadro = function (agora, dt) {
  quadroAntesDoTour.call(this, agora, dt);
  if (exemploPendente && (!onboarding || onboarding.indice !== exemploPendente.indice)) tirarExemplo();
  const guia = onboarding?.guia;
  if (!guia?.seguir || !guia.avatar.raiz.visible || transicao) return;
  guia.avatar.raiz.getWorldPosition(posGuia);
  posGuia.y += 1.2;
  const k = reduzir ? 1 : Math.min(1, dt * 4);
  orbita.alvo.lerp(posGuia, k);
  orbita.raio += (TOUR_RAIO - orbita.raio) * k;
  orbita.polar += (1.0 - orbita.polar) * k;
};
