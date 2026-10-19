// Modal de conversa com os agentes.

const ROTULOS_STATUS = { dormindo: 'Dormindo', disponivel: 'Disponível', trabalhando: 'Trabalhando' };

const historicos = {}; // 'andar/agente' -> [{ autor, texto, tipo }]
const pendentes = new Set(); // agentes com tarefa enviada aguardando resposta
let chatAberto = null; // { andar, agente }

const modal = document.getElementById('modal');
const modalHistorico = document.getElementById('modal-historico');
const modalInput = document.getElementById('modal-input');
const modalEnviar = document.getElementById('modal-enviar');

const chave = (andar, agente) => `${andar}/${agente}`;

function criarMensagem({ autor, texto, tipo }) {
  const div = document.createElement('div');
  div.className = `msg msg-${tipo}`;
  const nome = document.createElement('span');
  nome.className = 'msg-autor';
  nome.textContent = autor;
  div.append(nome, document.createTextNode(texto));
  return div;
}

function rolarParaFim() {
  modalHistorico.scrollTop = modalHistorico.scrollHeight;
}

// Guarda no histórico do agente e mostra na tela se o modal dele estiver aberto.
function adicionarMensagem(andar, agente, mensagem) {
  const k = chave(andar, agente);
  (historicos[k] ||= []).push(mensagem);
  if (chatAberto && chave(chatAberto.andar, chatAberto.agente) === k) {
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

  document.getElementById('modal-nome').textContent = dados.nome;
  document.getElementById('modal-funcao').textContent = dados.funcao || ANDARES[andar].nome;
  const status = document.getElementById('modal-status');
  status.className = `status status-${dados.status}`;
  status.title = ROTULOS_STATUS[dados.status];

  document.getElementById('modal-pensando').hidden = !ocupado;
  modalInput.disabled = ocupado || !online;
  modalEnviar.disabled = ocupado || !online;
  modalInput.placeholder = online ? 'Descreva a tarefa...' : 'Sem conexão com o servidor...';
}

function abrirChat(andar, agente) {
  chatAberto = { andar, agente };
  modalHistorico.replaceChildren(...(historicos[chave(andar, agente)] || []).map(criarMensagem));
  modal.classList.add('aberto');
  atualizarChat();
  rolarParaFim();
  if (!modalInput.disabled) modalInput.focus();
}

function fecharChat() {
  chatAberto = null;
  modal.classList.remove('aberto');
}

function limparChat() {
  Object.keys(historicos).forEach((k) => delete historicos[k]);
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

function receberResposta({ andar, agente, texto, modelo }) {
  pendentes.delete(chave(andar, agente));
  const nome = dadosAgente(andar, agente).nome;
  const autor = modelo ? `${nome} · ${modelo}` : nome; // mostra qual modelo respondeu
  adicionarMensagem(andar, agente, { autor, texto, tipo: 'agente' });
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
