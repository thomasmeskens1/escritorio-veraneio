// Popup do agente: conversa (a ficha de informações fica em js/perfil.js).

const ROTULOS_STATUS = { dormindo: 'Pausado', disponivel: 'Disponível', trabalhando: 'Trabalhando', construindo: 'Em construção' };

const historicos = {}; // 'andar/agente' -> [{ autor, texto, tipo, meta? }]
const pendentes = new Set(); // agentes com tarefa enviada aguardando resposta
const rascunhos = {}; // 'andar/agente' -> texto digitado e não enviado
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

// Guarda no histórico do agente e mostra na tela se o modal dele estiver aberto.
function adicionarMensagem(andar, agente, mensagem) {
  const k = chave(andar, agente);
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

  document.getElementById('modal-nome').textContent = dados.nome;
  document.getElementById('modal-funcao').textContent = dados.funcao || ANDARES[andar].nome;
  const status = document.getElementById('modal-status');
  status.className = `status status-${dados.status}`;
  status.title = ROTULOS_STATUS[dados.status];

  document.getElementById('modal-pensando').hidden = !ocupado;
  modalInput.disabled = ocupado || !online || restrito;
  modalEnviar.disabled = ocupado || !online || restrito;
  if (restrito) modalInput.placeholder = 'Envio indisponível para esta conta';
  else modalInput.placeholder = online ? 'Descreva a tarefa...' : 'Sem conexão com o servidor...';
}

function abrirChat(andar, agente) {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = { andar, agente };
  modalInput.value = rascunhos[chave(andar, agente)] || '';
  modalHistorico.replaceChildren(...(historicos[chave(andar, agente)] || []).map(criarMensagem));
  modal.classList.add('aberto');
  carregarPerfil(andar, agente);
  atualizarChat();
  rolarParaFim();
  if (!modalInput.disabled) modalInput.focus();
}

function fecharChat() {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = null;
  modal.classList.remove('aberto');
}

function limparChat() {
  Object.keys(historicos).forEach((k) => delete historicos[k]);
  Object.keys(rascunhos).forEach((k) => delete rascunhos[k]);
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
  const { andar, agente, texto, modelo } = msg;
  pendentes.delete(chave(andar, agente));
  const nome = dadosAgente(andar, agente).nome;
  const meta = metadadosResposta(msg);
  const autor = !meta && modelo ? `${nome} · ${modelo}` : nome;
  adicionarMensagem(andar, agente, { autor, texto, tipo: 'agente', meta });
  if (chatEstaAberto(andar, agente)) carregarPerfil(andar, agente); // atualiza o contador de tarefas
  else mostrarToast(andar, agente, texto);
  atualizarChat();
  avisarPainel();
}

// Tarefa estourou o tempo/falhou localmente e foi para a fila do Claude.
function receberAdiada({ andar, agente, texto }) {
  if (!andar || !agente) return;
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema' });
  atualizarChat();
  avisarPainel();
}

// Aviso do servidor ligado a um agente (ex.: agente criado, agendamento criado): mensagem de sistema
// no chat dele e toast se o chat não estiver aberto.
function receberAviso({ andar, agente, texto, titulo }) {
  if (!andar || !agente) {
    console.info('Aviso do servidor:', texto);
    return;
  }
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema' });
  if (!chatEstaAberto(andar, agente)) mostrarToast(andar, agente, texto, titulo || 'Aviso');
  atualizarChat();
}

function receberErro({ andar, agente, texto }) {
  if (!andar || !agente) {
    console.warn('Erro do servidor:', texto);
    return;
  }
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema' });
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
