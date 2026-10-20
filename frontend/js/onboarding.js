// Onboarding da Recepcionista, no estilo tutorial de jogo, todo no navegador (sem IA, sem tokens).
// Ela levanta da mesa e anda pelo escritório (pega o elevador entre andares, para ao lado de cada agente);
// a câmera a acompanha e as falas aparecem numa caixa de diálogo com o rosto dela, digitadas letra a letra.
// Partes da interface (elevador, contadores, registro) ganham um destaque enquanto ela explica.
// Controles: Próximo/Voltar, Enter/espaço/setas e Esc para sair.

const PASSOS_ONBOARDING = [
  { andar: 'terreo', agente: 'recepcionista', titulo: 'Boas-vindas',
    texto: 'Olá! Eu sou a Recepcionista. Vou te mostrar rapidinho como o Escritório Veraneio funciona. Vem comigo!' },
  { ui: '#elevador', titulo: 'O elevador',
    texto: 'Cada andar é um time. Use o elevador para trocar de andar. Andares com cadeado são restritos à diretoria.' },
  { ui: '.contadores', titulo: 'Quem está fazendo o quê',
    texto: 'Aqui em cima você acompanha quantos agentes estão disponíveis, trabalhando, em construção ou pausados.' },
  { andar: 'terreo', agente: 'professor', titulo: 'Térreo: a escola',
    texto: 'Este é o Professor. Ele ensina a escrever bons pedidos (briefings), com exemplos práticos.' },
  { andar: 'marketing', agente: 'gestor', titulo: 'Marketing: o time criativo',
    texto: 'Aqui ficam Gestão, Criação, Conteúdo, Vídeo e Performance. O Gestor coordena projetos grandes: divide em etapas e distribui para a equipe.' },
  { andar: 'marketing', agente: 'copywriter', titulo: 'Como pedir uma tarefa',
    texto: 'Clique em qualquer agente para abrir a ficha e a conversa. Descreva o que precisa e envie: a resposta chega no chat, mesmo se você sair.' },
  { andar: 'marketing', agente: 'criador_imagens', titulo: 'Imagens e vídeos',
    texto: 'O Criador de Imagens e o Editor de Vídeo entregam artes em PNG e vídeos em MP4, salvos no Drive. Mesas com “Vaga” esperam novos agentes.' },
  { andar: 'porao', agente: 'construtor', titulo: 'Porão: o Construtor',
    texto: 'Precisa de um especialista que ainda não existe? Descreva a função ao Construtor e ele cria um agente novo, com mesa própria.' },
  { andar: 'porao', agente: 'despachante', titulo: 'O Despachante',
    texto: 'Clique no Despachante para ver a fila de tarefas: o que está rodando, o que aguarda e o que já foi concluído.' },
  { andar: 'cobertura', agente: 'cerebro', titulo: 'Cobertura: o Cérebro',
    texto: 'Esta é a memória da Casa Veraneio: lodges, preços, serviços e o que o time aprende. Todos consultam o Cérebro, e os estagiários levam as respostas até as mesas.' },
  { ui: '#abrir-registro', titulo: 'Registro de atividade',
    texto: 'Tudo o que acontece fica registrado aqui: pedidos, respostas, falhas e trocas de modelo.' },
  { andar: 'terreo', agente: 'recepcionista', titulo: 'Duas dicas e até logo!',
    texto: 'Use o clipe do chat para enviar imagens e PDFs (até 15 MB) e escreva “todos os dias às 8h…” para agendar rotinas. Qualquer dúvida, é só falar comigo no chat!' },
];

const ZOOM_TOUR = 1.7;         // aproximação da câmera sobre ela (x enquadramento do andar)
const MS_POR_LETRA = 22;
const SEGUIR_ACIMA = 40;       // a câmera mira o corpo, não os pés (px)

let onboarding = null; // { passos, indice, geracao, raiz, foco, caixa, guia, timerTexto, completo }

const ROSTO_RECEPCIONISTA = `
<svg viewBox="0 0 48 48" aria-hidden="true">
  <path d="M11 22c0-9 6-15 13-15s13 6 13 15v14H11z" fill="#b5651d"/>
  <path d="M8 48c1-8 7-12 16-12s15 4 16 12z" fill="#2a9d8f"/>
  <rect x="27" y="40" width="6" height="5" rx="1" fill="#f8f9fa"/>
  <circle cx="24" cy="22" r="10" fill="#ffdbac"/>
  <path d="M14 21c1-7 5-10 10-10s9 3 10 10c-4-1-8-4-10-7-2 3-6 6-10 7z" fill="#b5651d"/>
  <circle cx="20.5" cy="23" r="1.3" fill="#343a40"/><circle cx="27.5" cy="23" r="1.3" fill="#343a40"/>
  <path d="M21 27.5c1.6 1.4 4.4 1.4 6 0" stroke="#c0392b" stroke-width="1.4" fill="none" stroke-linecap="round"/>
</svg>`;

// ---------- Início e fim ----------

function iniciarOnboarding() {
  if (onboarding || !cena) return;
  if (typeof fecharChat === 'function') fecharChat();
  if (typeof fecharPainel === 'function') fecharPainel();
  if (typeof fecharRegistro === 'function') fecharRegistro();

  const raiz = novoEl('div', 'onboarding');
  const foco = novoEl('div', 'onboarding-foco sem-alvo');
  const caixa = novoEl('section', 'onboarding-caixa');
  caixa.setAttribute('role', 'dialog');
  caixa.setAttribute('aria-modal', 'true');
  caixa.setAttribute('aria-labelledby', 'onboarding-titulo');
  caixa.innerHTML = `
    <div class="onboarding-retrato">${ROSTO_RECEPCIONISTA}</div>
    <div class="onboarding-fala">
      <p class="onboarding-nome">Recepcionista <span id="onboarding-titulo"></span></p>
      <p class="onboarding-texto" aria-live="polite"></p>
      <span class="onboarding-seta" aria-hidden="true">▼</span>
    </div>
    <div class="onboarding-acoes">
      <span class="onboarding-progresso"></span>
      <button type="button" class="botao-secundario" data-acao="sair">Pular tutorial</button>
      <button type="button" class="botao-secundario" data-acao="voltar">Voltar</button>
      <button type="button" class="botao-primario" data-acao="proximo">Próximo</button>
    </div>`;
  caixa.addEventListener('click', (e) => {
    const acao = e.target.closest('button')?.dataset.acao;
    if (acao === 'sair') encerrarOnboarding();
    else if (acao === 'voltar') irParaPasso(onboarding.indice - 1);
    else if (acao === 'proximo' || e.target.closest('.onboarding-fala')) avancar();
  });
  raiz.append(novoEl('div', 'onboarding-bloqueio'), foco, caixa);
  document.body.append(raiz);

  onboarding = {
    passos: PASSOS_ONBOARDING.filter((p) => !p.andar || podeAcessar(p.andar)),
    indice: -1, geracao: 0, raiz, foco, caixa, guia: null, timerTexto: null, completo: true,
  };
  document.addEventListener('keydown', teclaOnboarding);
  window.addEventListener('resize', reposicionarFoco);
  cena.events.on('update', seguirGuia);
  irParaPasso(0);
}

function encerrarOnboarding() {
  if (!onboarding) return;
  clearInterval(onboarding.timerTexto);
  removerGuia();
  cena?.events.off('update', seguirGuia);
  cena?.cameras.main.stopFollow();
  cena?.cameras.main.zoomEffect.reset(); // interrompe uma aproximação em andamento
  onboarding.raiz.remove();
  onboarding = null;
  document.removeEventListener('keydown', teclaOnboarding);
  window.removeEventListener('resize', reposicionarFoco);
  if (cena && podeAcessar('terreo')) renderizarAndar('terreo'); // reenquadra e devolve a Recepcionista à mesa
}

function teclaOnboarding(e) {
  if (!onboarding) return;
  if (e.key === 'Escape') encerrarOnboarding();
  else if (['Enter', ' ', 'ArrowRight'].includes(e.key)) avancar();
  else if (e.key === 'ArrowLeft') irParaPasso(onboarding.indice - 1);
  else return;
  e.preventDefault();
}

// Primeiro completa a fala que está sendo digitada; depois vai ao próximo passo.
function avancar() {
  if (!onboarding.completo) return completarTexto();
  irParaPasso(onboarding.indice + 1);
}

// ---------- Passos ----------

function irParaPasso(indice) {
  if (!onboarding) return;
  if (indice >= onboarding.passos.length) return encerrarOnboarding();
  if (indice < 0) return;
  onboarding.indice = indice;
  const geracao = ++onboarding.geracao;
  const passo = onboarding.passos[indice];
  const { caixa } = onboarding;
  caixa.querySelector('.onboarding-progresso').textContent = `${indice + 1} de ${onboarding.passos.length}`;
  caixa.querySelector('[data-acao="voltar"]').disabled = indice === 0;
  caixa.querySelector('[data-acao="proximo"]').textContent = indice === onboarding.passos.length - 1 ? 'Concluir' : 'Próximo';
  caixa.querySelector('#onboarding-titulo').textContent = `· ${passo.titulo}`;
  caixa.classList.add('caminhando');
  mostrarFoco(null);
  escreverTexto('');

  const falar = () => {
    if (!onboarding || geracao !== onboarding.geracao) return; // o usuário já pulou para outro passo
    caixa.classList.remove('caminhando');
    mostrarFoco(passo.ui || null);
    escreverTexto(passo.texto);
  };
  if (!passo.agente) return falar();
  levarGuia(passo.andar, passo.agente, falar);
}

// ---------- A Recepcionista andando ----------

// Lugar dela ao lado do agente do passo; no caso dela mesma, a própria mesa.
function destinoAoLadoDe(agente) {
  const pos = posicoesAndar[agente];
  if (!pos) return { x: GRADE - 1.8, y: 1.45, sentido: -1 };
  if (agente === 'recepcionista') return { x: pos.x + AGENTE_NO_TILE, y: pos.y + AGENTE_NO_TILE, sentido: 1 };
  return lugarAoLado(agente, pos);
}

function criarGuia(inicio) {
  const dados = dadosAgente('terreo', 'recepcionista');
  const pes = isoParaTela(inicio.x, inicio.y);
  const avatar = criarBoneco(cena, pes.x, pes.y, { ...dados, status: 'disponivel', escalaRotulo: 1,
    rotuloAcima: ROTULO_VISITA }); // nome acima, sem cobrir o do agente ao lado
  onboarding.guia = { avatar, g: { x: inicio.x, y: inicio.y }, tweens: [], alvo: { x: pes.x, y: pes.y - SEGUIR_ACIMA } };
  ocultarRecepcionistaDaMesa();
  focarCamera();
  return onboarding.guia;
}

function removerGuia() {
  const guia = onboarding?.guia;
  if (!guia) return;
  pararCaminhada(guia);
  guia.avatar.objetos.forEach((o) => o.active && o.destroy());
  onboarding.guia = null;
}

// No Térreo, a Recepcionista "de verdade" sai da mesa enquanto a guia anda.
function ocultarRecepcionistaDaMesa() {
  if (andarAtual === 'terreo') avatares.recepcionista?.objetos.forEach((o) => o.setVisible(false));
}

function focarCamera() {
  const cam = cena.cameras.main;
  cam.startFollow(onboarding.guia.alvo, false, 0.09, 0.09);
  cam.zoomTo(Math.min(2.2, enquadrarCamera() * ZOOM_TOUR), 700);
}

// A câmera segue um ponto acima dos pés dela, atualizado a cada quadro.
function seguirGuia() {
  const guia = onboarding?.guia;
  if (!guia) return;
  const pes = isoParaTela(guia.g.x, guia.g.y);
  guia.alvo.x = pes.x;
  guia.alvo.y = pes.y - SEGUIR_ACIMA;
}

// Leva a guia até o agente: no mesmo andar, caminha; em outro, sai pelo elevador e entra no andar novo.
function levarGuia(andar, agente, aoChegar) {
  const geracao = onboarding.geracao;
  const vivo = () => onboarding && geracao === onboarding.geracao;
  const chegar = (destino) => {
    if (!vivo()) return;
    onboarding.guia.avatar.virar(destino.sentido);
    aoChegar();
  };
  const entrarNoAndar = () => {
    if (!vivo()) return;
    removerGuia();
    if (andar !== andarAtual) renderizarAndar(andar);
    const destino = destinoAoLadoDe(agente);
    const veioDoElevador = agente !== 'recepcionista' || onboarding.indice > 0;
    const guia = criarGuia(veioDoElevador ? portaElevador() : destino);
    if (!veioDoElevador) return chegar(destino);
    guia.avatar.definirAlfa(0);
    cena.tweens.add({ targets: guia.avatar.objetos, alpha: 1, duration: 300 });
    caminhar(guia, [saidaElevador(), destino], () => chegar(destino));
  };

  const guia = onboarding.guia;
  if (!guia || andar !== andarAtual) {
    if (!guia) return entrarNoAndar();
    // Sai pelo elevador do andar atual antes de aparecer no próximo.
    return caminhar(guia, [saidaElevador(), portaElevador()], () => {
      if (!vivo()) return;
      cena.tweens.add({ targets: guia.avatar.objetos, alpha: 0, duration: 250, onComplete: entrarNoAndar });
    });
  }
  const destino = destinoAoLadoDe(agente);
  focarCamera();
  caminhar(guia, [destino], () => chegar(destino));
}

// ---------- Fala (caixa de diálogo) ----------

function escreverTexto(texto) {
  const { caixa } = onboarding;
  const alvo = caixa.querySelector('.onboarding-texto');
  clearInterval(onboarding.timerTexto);
  alvo.textContent = '';
  onboarding.texto = texto;
  onboarding.completo = !texto;
  caixa.classList.toggle('completo', onboarding.completo && !!texto);
  if (!texto) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return completarTexto();
  let n = 0;
  onboarding.timerTexto = setInterval(() => {
    n += 1;
    alvo.textContent = texto.slice(0, n);
    if (n >= texto.length) completarTexto();
  }, MS_POR_LETRA);
}

function completarTexto() {
  clearInterval(onboarding.timerTexto);
  onboarding.caixa.querySelector('.onboarding-texto').textContent = onboarding.texto || '';
  onboarding.completo = true;
  onboarding.caixa.classList.add('completo');
}

// ---------- Destaque de partes da interface ----------

function mostrarFoco(seletor) {
  const { foco } = onboarding;
  foco.dataset.seletor = seletor || '';
  reposicionarFoco();
}

function reposicionarFoco() {
  if (!onboarding) return;
  const { foco } = onboarding;
  const r = foco.dataset.seletor ? document.querySelector(foco.dataset.seletor)?.getBoundingClientRect() : null;
  foco.classList.toggle('sem-alvo', !r?.width);
  if (!r?.width) return;
  const m = 8;
  Object.assign(foco.style, { left: `${r.left - m}px`, top: `${r.top - m}px`,
    width: `${r.width + m * 2}px`, height: `${r.height + m * 2}px` });
}
