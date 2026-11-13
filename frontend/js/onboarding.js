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
  { ui: '#abrir-triagem', titulo: 'Não sabe com quem falar?',
    texto: 'Não sabe qual agente procurar? Clique em “Não sei com quem falar”, escreva o que precisa e eu levo o pedido ao agente certo. Atalho: barra de espaço duas vezes dentro de um andar.' },
  { ui: '.contadores', titulo: 'Quem está fazendo o quê',
    texto: 'Aqui em cima você acompanha quantos agentes estão disponíveis, trabalhando, em construção ou pausados.' },
  { ui: '#abrir-caixa', titulo: 'Caixa de entrada',
    texto: 'Aqui chega o que espera você (“Para aprovar”: formulários e decisões de produção) e o que ficou pronto (“Concluídos”). Pode fechar o escritório enquanto um agente trabalha: a resposta volta ao chat e aparece aqui, sem precisar enviar de novo.' },
  { andar: 'terreo', agente: 'professor', titulo: 'Térreo: a escola',
    texto: 'Este é o Professor. Ele ensina a escrever bons pedidos (briefings), com exemplos práticos.' },
  { andar: 'marketing', agente: 'gestor', titulo: 'Marketing: o time criativo',
    texto: 'Aqui ficam Gestão, Criação, Conteúdo, Vídeo e Performance. Peça pronta (post, carrossel, reels, apresentação) é com o Gestor: comece com “Peça final:” e ele monta o plano e aciona a equipe. Só ideias? Comece com “Planejamento:”. Na pauta da semana, o botão “Produzir a semana” manda produzir as peças do Monday.' },
  { andar: 'marketing', agente: 'copywriter', titulo: 'Como pedir uma tarefa',
    texto: 'Clique em qualquer agente para abrir a ficha e a conversa. Cada conversa trabalha para uma empresa (Casa Veraneio, Corporativo ou Casa Vero), escolhida no seletor do topo ou citada no próprio pedido. O botão de envio mostra para qual empresa vai (“Enviar para Corporativo”).' },
  { andar: 'marketing', agente: 'copywriter', chat: true, titulo: 'A conversa continua de onde parou',
    texto: 'Ao abrir um agente, você vê a última interação. O painel “Andamento” mostra cada passo do trabalho. Se o agente precisar de uma informação sua, abre um formulário em pop-up. Embaixo da resposta do Copywriter há ajustes rápidos (“Mais curto”, “3 variações”...), “Levar para uma Peça final” e o 👍/👎, que ensina o time.' },
  { andar: 'marketing', agente: 'social_media', titulo: 'O “!” vermelho',
    texto: 'Agente com um “!” vermelho no nome está esperando você: um formulário sem resposta ou uma decisão antes de produzir. Abra o chat dele e responda.' },
  { andar: 'marketing', agente: 'criador_imagens', titulo: 'Imagens, vídeos e apresentações',
    texto: 'O Criador de Imagens e o Editor de Vídeo produzem as peças finais, salvas no Drive. Na entrega, “Visualizar” abre a pasta, “Pedir ajuste” gera uma nova versão e “Desdobrar 4:5 e 9:16” cria os outros formatos da arte. O Sonoplasta cuida do som: todo vídeo sai sem som e com som. Mesas com “Vaga” esperam novos agentes.' },
  { andar: 'marketing', agente: 'analista_tendencias', titulo: 'Tendências e datas',
    texto: 'Na mesa de reunião fica a Analista de Tendências: ela calcula as datas que importam (Carnaval, feriadões, Réveillon), estuda o mercado e as notícias e diz o que preparar antes do momento.' },
  { andar: 'comercial', agente: 'prospectador', titulo: '2º andar: Comercial',
    texto: 'O Prospectador encontra empresas para o Corporativo e mostra uma prévia; só com a sua aprovação os leads entram no Monday.' },
  { andar: 'comercial', agente: 'estrategista', titulo: 'O Estrategista',
    texto: 'Na mesa de reunião, o Estrategista posiciona as três empresas na Matriz BCG, faz SWOT e estudos de concorrência, sempre com a fonte e o grau de confiança.' },
  { andar: 'porao', agente: 'construtor', titulo: 'Porão: o Construtor',
    texto: 'Precisa de um especialista que ainda não existe? Descreva a função ao Construtor e ele cria um agente novo, com mesa própria.' },
  { andar: 'porao', agente: 'despachante', titulo: 'O Despachante',
    texto: 'Clique no Despachante para ver a fila de tarefas: o que está rodando, o que aguarda e o que já foi concluído.' },
  { andar: 'cobertura', agente: 'cerebro', titulo: 'Cobertura: o Cérebro',
    texto: 'Esta é a memória das três empresas: imóveis, preços, serviços, regras e o que o time aprende, sem misturar uma empresa com a outra. Todos consultam o Cérebro, e os estagiários levam as respostas até as mesas.' },
  { ui: '#abrir-registro', titulo: 'Registro de atividade',
    texto: 'Tudo o que acontece fica registrado aqui: pedidos, respostas, falhas e trocas de modelo.' },
  { andar: 'terreo', agente: 'recepcionista', titulo: 'Duas dicas e até logo!',
    texto: 'Use o clipe do chat para enviar imagens e PDFs (até 15 MB). Para uma tarefa repetir sozinha, use o botão “Agendar tarefa” na ficha do agente. Qualquer dúvida, é só falar comigo ou com o Professor!' },
];

const MS_POR_LETRA = 22;

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
  irParaPasso(0);
}

function encerrarOnboarding() {
  if (!onboarding) return;
  clearInterval(onboarding.timerTexto);
  if (chatAberto && typeof fecharChat === 'function') fecharChat();
  removerGuia();
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
  caixa.classList.toggle('no-topo', !!passo.chat); // não cobre a conversa demonstrada
  if (!passo.chat && chatAberto && typeof fecharChat === 'function') fecharChat();
  mostrarFoco(null);
  escreverTexto('');

  const falar = () => {
    if (!onboarding || geracao !== onboarding.geracao) return; // o usuário já pulou para outro passo
    caixa.classList.remove('caminhando');
    if (passo.chat) {
      abrirChat(passo.andar, passo.agente);
      modalInput.blur(); // Enter continua avançando o tutorial (não envia rascunho ao agente)
      mostrarFoco('.janela-agente .historico');
      setTimeout(reposicionarFoco, 450); // a janela termina de abrir
    } else mostrarFoco(passo.ui || null);
    escreverTexto(passo.texto);
  };
  if (!passo.agente) return falar();
  levarGuia(passo.andar, passo.agente, falar);
}

// ---------- A Recepcionista andando ----------
// No prédio 3D, a caminhada, o elevador e a câmera ficam em js/escritorio3d/tour.js (criarGuia, removerGuia,
// levarGuia, focarCamera), carregado com a cena.

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

document.getElementById('iniciar-onboarding').addEventListener('click', iniciarOnboarding);
