// Popup do agente: conversa (a ficha de informações fica em js/perfil.js).

const ROTULOS_STATUS = { dormindo: 'Pausado', disponivel: 'Disponível', trabalhando: 'Trabalhando', construindo: 'Em construção' };

const historicos = {}; // 'andar/agente' -> [{ autor, texto, tipo, meta?, tarefa_id? }]
const pendentes = new Set(); // agentes com tarefa enviada aguardando resposta
const rascunhos = {}; // 'andar/agente' -> texto digitado e não enviado
const historicoCarregado = new Set(); // agentes cujo histórico salvo já veio do servidor
const carregandoHistorico = new Set(); // agentes com a busca do histórico em curso
const assinaturas = {}; // 'andar/agente' -> Set de mensagens com tarefa já exibidas (evita repetir)
let geracaoHistorico = 0; // muda ao sair: buscas antigas são descartadas
let chatAberto = null; // { andar, agente }

const modal = document.getElementById('modal');
const modalHistorico = document.getElementById('modal-historico');
const modalInput = document.getElementById('modal-input');
const modalEnviar = document.getElementById('modal-enviar');

const chave = (andar, agente) => `${andar}/${agente}`;

function criarMensagem({ autor, texto, tipo, meta }) {
  const div = document.createElement('div');
  div.className = `msg msg-${tipo}`;
  const nome = document.createElement('span');
  nome.className = 'msg-autor';
  nome.textContent = autor;
  div.append(nome, document.createTextNode(texto));
  if (meta) {
    const linha = document.createElement('span');
    linha.className = 'msg-meta';
    linha.textContent = meta;
    div.append(linha);
  }
  return div;
}

const chatEstaAberto = (andar, agente) =>
  !!chatAberto && chave(chatAberto.andar, chatAberto.agente) === chave(andar, agente);

function rolarParaFim() {
  modalHistorico.scrollTop = modalHistorico.scrollHeight;
}

// Mesma tarefa + mesmo tipo + mesmo texto = mesma mensagem (ao vivo x histórico salvo).
const assinaturaMensagem = (m) => (m.tarefa_id != null ? `${m.tipo}|${m.tarefa_id}|${m.texto}` : null);

// Registra a assinatura; false se a mensagem já foi exibida.
function marcarVista(k, mensagem) {
  const a = assinaturaMensagem(mensagem);
  if (!a) return true;
  const vistas = (assinaturas[k] ||= new Set());
  if (vistas.has(a)) return false;
  vistas.add(a);
  return true;
}

// Guarda no histórico do agente e mostra na tela se o modal dele estiver aberto.
function adicionarMensagem(andar, agente, mensagem) {
  const k = chave(andar, agente);
  if (!marcarVista(k, mensagem)) return;
  (historicos[k] ||= []).push(mensagem);
  if (chatEstaAberto(andar, agente)) {
    modalHistorico.append(criarMensagem(mensagem));
    rolarParaFim();
  }
}

// Atualiza cabeçalho, indicador "pensando" e bloqueio de envio.
function atualizarChat() {
  if (!chatAberto) return;
  const { andar, agente } = chatAberto;
  const dados = dadosAgente(andar, agente);
  const ocupado = dados.status === 'trabalhando' || pendentes.has(chave(andar, agente));
  const online = conectado();
  const restrito = producaoRestrita(andar, agente);
  const carregando = carregandoHistorico.has(chave(andar, agente));

  document.getElementById('modal-nome').textContent = dados.nome;
  document.getElementById('modal-funcao').textContent = dados.funcao || ANDARES[andar].nome;
  const status = document.getElementById('modal-status');
  status.className = `status status-${dados.status}`;
  status.title = ROTULOS_STATUS[dados.status];

  document.getElementById('modal-pensando').hidden = !ocupado;
  // Envio espera o histórico chegar, para a pergunta nova não se repetir ao mesclar.
  const bloqueado = ocupado || !online || restrito || carregando;
  modalInput.disabled = bloqueado;
  modalEnviar.disabled = bloqueado;
  if (restrito) modalInput.placeholder = 'Envio indisponível para esta conta';
  else if (!online) modalInput.placeholder = 'Sem conexão com o servidor...';
  else modalInput.placeholder = carregando ? 'Carregando histórico…' : 'Descreva a tarefa...';
}

// Redesenha a conversa do agente aberto (com o aviso de carregamento, se for o caso).
function renderizarHistorico(andar, agente) {
  const k = chave(andar, agente);
  modalHistorico.replaceChildren(...(historicos[k] || []).map(criarMensagem));
  if (carregandoHistorico.has(k)) {
    const aviso = document.createElement('p');
    aviso.className = 'msg-carregando';
    aviso.textContent = 'Carregando histórico…';
    modalHistorico.prepend(aviso);
  }
  rolarParaFim();
}

function abrirChat(andar, agente) {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = { andar, agente };
  modalInput.value = rascunhos[chave(andar, agente)] || '';
  carregarHistorico(andar, agente);
  renderizarHistorico(andar, agente);
  modal.classList.add('aberto');
  carregarPerfil(andar, agente);
  atualizarChat();
  if (!modalInput.disabled) modalInput.focus();
}

// Mensagem do agente no formato das respostas ao vivo (modelo na linha de metadados).
function mensagemDoAgente(andar, agente, dados) {
  const nome = dadosAgente(andar, agente).nome;
  const meta = metadadosResposta(dados);
  const autor = !meta && dados.modelo ? `${nome} · ${dados.modelo}` : nome;
  return { autor, texto: dados.texto, tipo: 'agente', meta, tarefa_id: dados.tarefa_id };
}

function converterDoServidor(andar, agente, m) {
  if (m.autor === 'voce') return { autor: 'Você', texto: m.texto, tipo: 'voce', tarefa_id: m.tarefa_id };
  if (m.autor === 'agente') return mensagemDoAgente(andar, agente, { ...m.meta, texto: m.texto, tarefa_id: m.tarefa_id });
  return { autor: 'sistema', texto: m.texto, tipo: 'sistema', tarefa_id: m.tarefa_id };
}

// Busca a conversa salva (uma vez por sessão da página) e a coloca antes das mensagens ao vivo.
async function carregarHistorico(andar, agente) {
  const k = chave(andar, agente);
  if (!sessao || historicoCarregado.has(k) || carregandoHistorico.has(k)) return;
  const geracao = geracaoHistorico;
  carregandoHistorico.add(k);
  let dados = null;
  let status = 0;
  try {
    const resposta = await fetch(`/api/historico/${encodeURIComponent(andar)}/${encodeURIComponent(agente)}`, {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    status = resposta.status;
    if (resposta.ok) dados = await resposta.json();
  } catch (erro) {
    console.warn('Falha ao carregar o histórico:', erro);
  }
  if (geracao !== geracaoHistorico) return; // saiu da conta enquanto buscava
  carregandoHistorico.delete(k);
  if (status === 401) {
    encerrarSessao('Sessão expirada. Entre novamente.');
    return;
  }

  const aberto = chatEstaAberto(andar, agente);
  if (dados) {
    historicoCarregado.add(k);
    // Mensagem ao vivo que também está no histórico fica na posição cronológica dele.
    const salvas = (dados.mensagens || []).map((m) => converterDoServidor(andar, agente, m));
    const noHistorico = new Set(salvas.map(assinaturaMensagem).filter(Boolean));
    const aoVivo = (historicos[k] || []).filter((m) => !noHistorico.has(assinaturaMensagem(m)));
    salvas.forEach((m) => marcarVista(k, m));
    historicos[k] = [...salvas, ...aoVivo];
    if (dados.pendentes?.length && dadosAgente(andar, agente).status === 'trabalhando') pendentes.add(k);
  }
  if (aberto) {
    renderizarHistorico(andar, agente);
    // Erro fica só na tela: na próxima abertura tenta de novo.
    if (!dados) modalHistorico.prepend(criarMensagem({ autor: 'sistema', texto: 'Não foi possível carregar o histórico.', tipo: 'sistema' }));
    atualizarChat();
  }
}

function fecharChat() {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = null;
  modal.classList.remove('aberto');
}

function limparChat() {
  Object.keys(historicos).forEach((k) => delete historicos[k]);
  Object.keys(rascunhos).forEach((k) => delete rascunhos[k]);
  Object.keys(assinaturas).forEach((k) => delete assinaturas[k]);
  historicoCarregado.clear();
  carregandoHistorico.clear();
  geracaoHistorico += 1;
  modalInput.value = '';
  pendentes.clear();
}

function enviarTarefa(evento) {
  evento.preventDefault();
  const texto = modalInput.value.trim();
  if (!chatAberto || !texto || modalEnviar.disabled) return;

  const { andar, agente } = chatAberto;
  if (!enviar({ tipo: 'mensagem', andar, agente, texto })) return;

  modalInput.value = '';
  pendentes.add(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'Você', texto, tipo: 'voce' });
  atualizarChat();
}

// Resposta pode vir com extras (dificuldade, tempo, adiada); o modelo vai na linha de metadados.
function receberResposta(msg) {
  const { andar, agente, texto } = msg;
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, mensagemDoAgente(andar, agente, msg));
  if (chatEstaAberto(andar, agente)) carregarPerfil(andar, agente); // atualiza o contador de tarefas
  else mostrarToast(andar, agente, texto);
  atualizarChat();
  avisarPainel();
}

// Tarefa estourou o tempo/falhou localmente e foi para a fila do Claude.
function receberAdiada({ andar, agente, texto, tarefa_id }) {
  if (!andar || !agente) return;
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema', tarefa_id });
  atualizarChat();
  avisarPainel();
}

function receberErro({ andar, agente, texto, tarefa_id }) {
  if (!andar || !agente) {
    console.warn('Erro do servidor:', texto);
    return;
  }
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema', tarefa_id });
  if (!chatAberto) console.warn(`Erro (${andar}/${agente}):`, texto);
  atualizarChat();
}

// Conexão caiu: tarefas pendentes não terão resposta nesta conexão.
function liberarPendentes() {
  pendentes.clear();
  atualizarChat();
}

document.getElementById('modal-form').addEventListener('submit', enviarTarefa);
document.getElementById('modal-fechar').addEventListener('click', fecharChat);
modal.addEventListener('click', (e) => {
  if (e.target === modal) fecharChat();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatAberto) fecharChat();
});
