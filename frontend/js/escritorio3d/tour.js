// Tour da Recepcionista no prédio 3D (migração do visual, Fase 4, Thomas 13/11/2026).
// Os passos, os textos, a caixa de diálogo, os destaques e as teclas são os do 2D (js/onboarding.js), sem mudança.
// Aqui só se troca a parte que dependia do motor Phaser: a Recepcionista anda de verdade pelo prédio 3D (pelo
// elevador, como os estagiários) até ficar ao lado de cada agente, e a câmera se aproxima dela quando chega.
// Carregado depois da cena (estado.js, SCRIPTS_3D); as funções abaixo substituem as homônimas do onboarding.js.

const TOUR_AO_LADO = new THREE.Vector3(0.75, 0, 0.35); // mesmo lugar ao lado do agente usado nas visitas
const TOUR_ESPERA_CAMERA = reduzir ? 0 : 1150;

function guiaDoTour() {
  return window.E3D.avatares.find((a) => a.id === 'recepcionista' && a.andar.id === 'terreo') || null;
}

// O avatar do agente do passo, no andar do passo.
function agenteDoTour(andar, agente) {
  return window.E3D.avatares.find((a) => a.id === agente && a.andar.id === andar) || null;
}

function criarGuia() {
  const avatar = guiaDoTour();
  onboarding.guia = avatar ? { avatar, saiu: false } : null;
  return onboarding.guia;
}

// Fim do tour: ela volta para a mesa dela no Térreo.
function removerGuia() {
  const guia = onboarding?.guia;
  if (!guia) return;
  onboarding.guia = null;
  const a = guia.avatar;
  if (!guia.saiu) return;
  const nCasa = ANDARES_3D.findIndex((x) => x.id === a.andar.id);
  levar(a, nCasa, new THREE.Vector3(a.casa.x, 0, a.casa.z), a.casa.rot || 0, a.casa.sentado);
}

function ocultarRecepcionistaDaMesa() {} // no 3D ela mesma sai da mesa (não há uma cópia)

// A câmera se aproxima dela (o mesmo enquadramento de quando se clica num agente).
function focarCamera() {
  const guia = onboarding?.guia;
  if (guia) window.E3D.irParaAgente(guia.avatar);
}

function seguirGuia() {}

// Leva a Recepcionista até o agente do passo; ao chegar, a câmera se aproxima e ela fala.
function levarGuia(andar, agente, aoChegar) {
  const geracao = onboarding.geracao;
  const vivo = () => onboarding && geracao === onboarding.geracao;
  const guia = onboarding.guia || criarGuia();
  if (andar !== andarAtual) renderizarAndar(andar);
  if (!guia) { aoChegar(); return; } // sem o avatar dela: fala sem andar

  const a = guia.avatar;
  const n = ANDARES_3D.findIndex((x) => x.id === andar);
  const chegar = () => {
    if (!vivo()) return;
    focarCamera();
    setTimeout(() => { if (vivo()) aoChegar(); }, TOUR_ESPERA_CAMERA);
  };
  if (agente === 'recepcionista' && !guia.saiu) { chegar(); return; } // primeiro passo: ela ainda está na mesa

  const alvo = agente === 'recepcionista' ? null : agenteDoTour(andar, agente);
  const ponto = alvo ? alvo.raiz.position.clone().add(TOUR_AO_LADO) : new THREE.Vector3(a.casa.x + 0.75, 0, a.casa.z + 0.35);
  guia.saiu = true;
  levar(a, n, ponto, -Math.PI / 2 - 0.3, false, chegar);
}
