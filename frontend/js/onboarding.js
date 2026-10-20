// Onboarding da Recepcionista: tour guiado pelo sistema, todo no navegador (sem modelo de IA, sem tokens).
// Ela "anda" de um ponto a outro (balão com o rosto dela), troca de andar pelo elevador e aponta agentes e
// partes da interface. Navegação: Próximo/Voltar, setas do teclado e Esc para sair.

const PASSOS_ONBOARDING = [
  { andar: 'terreo', alvo: { agente: 'recepcionista' }, titulo: 'Olá! Eu sou a Recepcionista',
    texto: 'Vou te mostrar rapidinho como o Escritório Veraneio funciona. Use “Próximo” ou as setas do teclado; Esc encerra o tour.' },
  { alvo: '#elevador', titulo: 'O elevador',
    texto: 'Cada andar é um time. Clique aqui para trocar de andar. Andares com cadeado são restritos à diretoria.' },
  { alvo: '.contadores', titulo: 'Quem está fazendo o quê',
    texto: 'Aqui você acompanha quantos agentes estão disponíveis, trabalhando, em construção ou pausados.' },
  { andar: 'terreo', alvo: { agente: 'professor' }, titulo: 'Térreo: a escola',
    texto: 'Aqui ficamos eu e o Professor. Ele ensina a escrever bons pedidos (briefings), com exemplos práticos.' },
  { andar: 'marketing', alvo: { agente: 'gestor' }, titulo: 'Marketing: o time criativo',
    texto: 'Setores de Gestão, Criação, Conteúdo, Vídeo e Performance. O Gestor coordena projetos grandes: divide em etapas e distribui para a equipe.' },
  { andar: 'marketing', alvo: { agente: 'copywriter' }, titulo: 'Como pedir uma tarefa',
    texto: 'Clique em qualquer agente: abre a ficha dele e a conversa. Descreva o que precisa e envie. A resposta chega no chat, mesmo se você sair do sistema.' },
  { andar: 'marketing', alvo: { agente: 'criador_imagens' }, titulo: 'Imagens e vídeos',
    texto: 'O Criador de Imagens e o Editor de Vídeo entregam artes em PNG e vídeos em MP4, salvos na pasta do Drive. Mesas com “Vaga” são lugares para novos agentes.' },
  { andar: 'porao', alvo: { agente: 'construtor' }, titulo: 'Porão: o Construtor',
    texto: 'Precisa de um especialista que ainda não existe? Descreva a função ao Construtor e ele cria um agente novo, com mesa própria.' },
  { andar: 'porao', alvo: { agente: 'despachante' }, titulo: 'O Despachante',
    texto: 'Clique nele para ver a fila de tarefas: o que está rodando, o que aguarda e o que já foi concluído.' },
  { andar: 'cobertura', alvo: { agente: 'cerebro' }, titulo: 'Cobertura: o Cérebro',
    texto: 'A memória da Casa Veraneio: lodges, preços, serviços e o que o time aprende. Todos os agentes consultam o Cérebro, e os estagiários levam as respostas até as mesas.' },
  { alvo: '#abrir-registro', titulo: 'Registro de atividade',
    texto: 'Tudo o que acontece fica registrado aqui: pedidos, respostas, falhas e trocas de modelo.' },
  { andar: 'terreo', titulo: 'Duas dicas rápidas',
    texto: 'Anexos: use o clipe do chat para enviar imagens e PDFs (até 15 MB). Rotinas: escreva, por exemplo, “todos os dias às 8h, resuma as métricas” para agendar uma tarefa.' },
  { andar: 'terreo', alvo: { agente: 'recepcionista' }, titulo: 'Pronto!',
    texto: 'Esse foi o tour. Se ficar alguma dúvida, é só falar comigo no chat. Bom trabalho!' },
];

const MARGEM_ALVO = 8;
const ALTURA_AGENTE = 104; // boneco + nome acima da cabeça (px, zoom 1)

let onboarding = null; // { passos, indice, raiz, foco, balao }

// Rosto da Recepcionista (cabelo longo castanho, blazer verde, crachá), em SVG.
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

function iniciarOnboarding() {
  if (onboarding) return;
  if (typeof fecharChat === 'function') fecharChat();
  if (typeof fecharPainel === 'function') fecharPainel();
  if (typeof fecharRegistro === 'function') fecharRegistro();
  const passos = PASSOS_ONBOARDING.filter((p) => !p.andar || podeAcessar(p.andar));

  const raiz = novoEl('div', 'onboarding');
  const bloqueio = novoEl('div', 'onboarding-bloqueio'); // impede cliques no escritório durante o tour
  const foco = novoEl('div', 'onboarding-foco');
  const balao = novoEl('section', 'onboarding-balao');
  balao.setAttribute('role', 'dialog');
  balao.setAttribute('aria-modal', 'true');
  balao.setAttribute('aria-labelledby', 'onboarding-titulo');
  balao.innerHTML = `
    <div class="onboarding-guia">${ROSTO_RECEPCIONISTA}<span>Recepcionista</span></div>
    <h3 id="onboarding-titulo"></h3>
    <p class="onboarding-texto" aria-live="polite"></p>
    <div class="onboarding-acoes">
      <span class="onboarding-progresso"></span>
      <button type="button" class="botao-secundario" data-acao="sair">Sair</button>
      <button type="button" class="botao-secundario" data-acao="voltar">Voltar</button>
      <button type="button" class="botao-primario" data-acao="proximo">Próximo</button>
    </div>`;
  balao.addEventListener('click', (e) => {
    const acao = e.target.closest('button')?.dataset.acao;
    if (acao === 'sair') encerrarOnboarding();
    else if (acao === 'voltar') irParaPasso(onboarding.indice - 1);
    else if (acao === 'proximo') irParaPasso(onboarding.indice + 1);
  });
  raiz.append(bloqueio, foco, balao);
  document.body.append(raiz);

  onboarding = { passos, indice: -1, raiz, foco, balao };
  document.addEventListener('keydown', teclaOnboarding);
  window.addEventListener('resize', reposicionarOnboarding);
  irParaPasso(0);
}

function encerrarOnboarding() {
  if (!onboarding) return;
  onboarding.raiz.remove();
  onboarding = null;
  document.removeEventListener('keydown', teclaOnboarding);
  window.removeEventListener('resize', reposicionarOnboarding);
  if (podeAcessar('terreo')) renderizarAndar('terreo');
}

function teclaOnboarding(e) {
  if (!onboarding) return;
  if (e.key === 'Escape') encerrarOnboarding();
  else if (e.key === 'ArrowRight') irParaPasso(onboarding.indice + 1);
  else if (e.key === 'ArrowLeft') irParaPasso(onboarding.indice - 1);
  else return;
  e.preventDefault();
}

function irParaPasso(indice) {
  if (!onboarding) return;
  if (indice >= onboarding.passos.length) return encerrarOnboarding();
  if (indice < 0) return;
  onboarding.indice = indice;
  const passo = onboarding.passos[indice];
  const ultimo = indice === onboarding.passos.length - 1;
  const { balao } = onboarding;
  balao.querySelector('#onboarding-titulo').textContent = passo.titulo;
  balao.querySelector('.onboarding-texto').textContent = passo.texto;
  balao.querySelector('.onboarding-progresso').textContent = `${indice + 1} de ${onboarding.passos.length}`;
  balao.querySelector('[data-acao="voltar"]').disabled = indice === 0;
  balao.querySelector('[data-acao="proximo"]').textContent = ultimo ? 'Concluir' : 'Próximo';

  const trocaAndar = passo.andar && passo.andar !== andarAtual;
  if (trocaAndar) renderizarAndar(passo.andar); // ela "pega o elevador"
  // Espera a câmera do novo andar assentar antes de medir onde está o agente.
  setTimeout(reposicionarOnboarding, trocaAndar ? 160 : 0);
  balao.querySelector('[data-acao="proximo"]').focus({ preventScroll: true });
}

// Retângulo (na tela) do alvo do passo: seletor da interface ou agente no canvas. null = centro da tela.
function retanguloAlvo(alvo) {
  if (!alvo) return null;
  if (typeof alvo === 'string') {
    const el = document.querySelector(alvo);
    const r = el?.getBoundingClientRect();
    return r && r.width ? { x: r.left, y: r.top, w: r.width, h: r.height } : null;
  }
  const pos = posicoesAndar[alvo.agente];
  if (!cena || !pos) return null;
  const cam = cena.cameras.main;
  const canvas = cena.game.canvas.getBoundingClientRect();
  const pes = isoParaTela(pos.x + AGENTE_NO_TILE, pos.y + AGENTE_NO_TILE);
  const elevacao = dadosAgente(andarAtual, alvo.agente).visual === 'cerebro' ? ELEVACAO_PEDESTAL : 0;
  const x = canvas.left + (pes.x - cam.worldView.x) * cam.zoom;
  const y = canvas.top + (pes.y - elevacao - cam.worldView.y) * cam.zoom;
  const largura = 96 * cam.zoom, altura = ALTURA_AGENTE * cam.zoom;
  return { x: x - largura / 2, y: y - altura, w: largura, h: altura + 8 * cam.zoom };
}

function reposicionarOnboarding() {
  if (!onboarding) return;
  const { foco, balao, passos, indice } = onboarding;
  const r = retanguloAlvo(passos[indice].alvo);
  foco.classList.toggle('sem-alvo', !r);
  if (r) {
    Object.assign(foco.style, { left: `${r.x - MARGEM_ALVO}px`, top: `${r.y - MARGEM_ALVO}px`,
      width: `${r.w + MARGEM_ALVO * 2}px`, height: `${r.h + MARGEM_ALVO * 2}px` });
  }
  // Balão ao lado do alvo (direita, esquerda, abaixo ou acima), sempre dentro da tela.
  const b = balao.getBoundingClientRect();
  const vw = window.innerWidth, vh = window.innerHeight, m = 16;
  let x = (vw - b.width) / 2, y = (vh - b.height) / 2;
  if (r) {
    const opcoes = [
      [r.x + r.w + MARGEM_ALVO + m, r.y + r.h / 2 - b.height / 2],
      [r.x - MARGEM_ALVO - m - b.width, r.y + r.h / 2 - b.height / 2],
      [r.x + r.w / 2 - b.width / 2, r.y + r.h + MARGEM_ALVO + m],
      [r.x + r.w / 2 - b.width / 2, r.y - MARGEM_ALVO - m - b.height],
    ];
    const cabe = ([px, py]) => px >= m && py >= m && px + b.width <= vw - m && py + b.height <= vh - m;
    [x, y] = opcoes.find(cabe) || opcoes[2];
  }
  balao.style.left = `${Math.min(Math.max(m, x), vw - b.width - m)}px`;
  balao.style.top = `${Math.min(Math.max(m, y), vh - b.height - m)}px`;
  balao.classList.remove('andando');
  void balao.offsetWidth; // reinicia a animação de "passos"
  balao.classList.add('andando');
}
