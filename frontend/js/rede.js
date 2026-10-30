// Conexão WebSocket com o backend.

const CODIGO_TOKEN_INVALIDO = 4401;
const ATRASO_RECONEXAO = 2000;
// Vigia (Thomas, 30/10/2026): pelo túnel da Cloudflare a conexão pode ficar "aberta mas muda" (nada chega). Só é
// AO VIVO depois que o servidor responde; sem resposta em PRAZO_RESPOSTA, reconecta sozinha ("RECONECTANDO").
const PRAZO_RESPOSTA = 10000;
const INTERVALO_PING = 30000;

let socket = null;
let timerReconexao = null;
let confirmado = false; // o servidor já respondeu nesta conexão
let timerVigia = null;

function conectado() {
  return socket?.readyState === WebSocket.OPEN;
}

function enviar(dados) {
  if (!conectado()) return false;
  socket.send(JSON.stringify(dados));
  return true;
}

function atualizarConexao() {
  atualizarPilula(conectado() && confirmado ? 'online' : (sessao ? 'reconectando' : 'fechado'));
  atualizarChat();
}

// Espera alguma mensagem do servidor; se não vier no prazo, derruba a conexão muda e abre outra.
function vigiar(ws) {
  clearTimeout(timerVigia);
  timerVigia = setTimeout(() => {
    if (socket !== ws) return;
    console.warn('Conexão sem resposta do servidor; reconectando.');
    socket = null;
    confirmado = false;
    liberarPendentes();
    atualizarConexao();
    try { ws.close(4000, 'sem resposta'); } catch { /* já fechada */ }
    if (sessao) timerReconexao = setTimeout(conectar, ATRASO_RECONEXAO);
  }, PRAZO_RESPOSTA);
}

setInterval(() => {
  if (conectado() && confirmado && enviar({ tipo: 'ping' })) vigiar(socket);
}, INTERVALO_PING);

function tratarMensagem(msg) {
  switch (msg.tipo) {
    case 'pong':
      break;
    case 'recebido': // o servidor recebeu a mensagem do chat (js/chat.js)
      confirmarEnvio(msg.id_envio);
      break;
    case 'estado':
      aplicarEstado(msg.andares);
      atualizarContadores(msg.andares);
      renderizarEquipe(); // tela Equipe aberta: status ao vivo
      break;
    case 'resposta_agente':
      receberResposta(msg);
      caixaMudou(); // caixa de entrada (js/caixa.js)
      break;
    case 'tarefa_adiada':
      receberAdiada(msg);
      caixaMudou();
      break;
    case 'aviso':
      receberAviso(msg);
      caixaMudou(); // pode ser uma decisão de produção esperando você
      break;
    case 'correcao_nova': // ratinho do Cérebro (js/aviso_cerebro.js)
      mostrarAvisoCerebro(msg.total, msg.ultima);
      break;
    case 'erro':
      receberErro(msg);
      break;
    case 'limpar_chat':
      limparConversas(msg);
      break;
  }
}

function conectar() {
  if (!sessao || socket) return;
  const protocolo = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocolo}://${location.host}/ws`);
  socket = ws;
  confirmado = false;
  vigiar(ws); // abertura + primeira resposta (o estado do escritório) dentro do prazo
  atualizarConexao();

  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({ tipo: 'auth', token: sessao.token }));
    if (chatAberto) ws.send(JSON.stringify({ tipo: 'presenca', interagiu: true, chat: chatAtual() })); // reconectou
    atualizarConexao();
    recarregarHistoricos();
  });

  ws.addEventListener('message', (e) => {
    if (socket !== ws) return; // conexão já trocada pela vigia
    clearTimeout(timerVigia);
    if (!confirmado) {
      confirmado = true;
      atualizarConexao();
    }
    try {
      tratarMensagem(JSON.parse(e.data));
    } catch (erro) {
      console.warn('Mensagem inválida do servidor:', erro);
    }
  });

  ws.addEventListener('close', (e) => {
    if (socket !== ws) return; // fechamento feito por desconectar() ou pela vigia
    socket = null;
    confirmado = false;
    clearTimeout(timerVigia);
    liberarPendentes();
    atualizarConexao();
    if (e.code === CODIGO_TOKEN_INVALIDO) {
      encerrarSessao('Sessão expirada. Entre novamente.');
    } else if (sessao) {
      timerReconexao = setTimeout(conectar, ATRASO_RECONEXAO);
    }
  });
}

function desconectar() {
  clearTimeout(timerReconexao);
  clearTimeout(timerVigia);
  const ws = socket;
  socket = null;
  confirmado = false;
  if (ws) ws.close(1000);
  atualizarConexao();
}

// Presença (status ativo/ausente no painel de usuários): a cada minuto, avisa o servidor se a pessoa mexeu no
// escritório desde o último aviso, com a aba visível. Sem interação por 5 min o servidor mostra "ausente".
const INTERVALO_PRESENCA = 60000;
let interagiuDesdeAviso = true;
['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'].forEach((evento) => {
  document.addEventListener(evento, () => { interagiuDesdeAviso = true; }, { passive: true });
});
const chatAtual = () => (chatAberto ? `${chatAberto.andar}/${chatAberto.agente}` : '');
setInterval(() => {
  enviar({ tipo: 'presenca', interagiu: interagiuDesdeAviso && document.visibilityState === 'visible', chat: chatAtual() });
  interagiuDesdeAviso = false;
}, INTERVALO_PRESENCA);

// Abriu ou fechou um chat: os outros usuários veem "Em uso: <você>" no agente na hora.
function avisarChatAberto() {
  interagiuDesdeAviso = true;
  enviar({ tipo: 'presenca', interagiu: true, chat: chatAtual() });
}
