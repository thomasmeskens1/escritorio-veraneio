// Conexão WebSocket com o backend.

const CODIGO_TOKEN_INVALIDO = 4401;
const ATRASO_RECONEXAO = 2000;

let socket = null;
let timerReconexao = null;

function conectado() {
  return socket?.readyState === WebSocket.OPEN;
}

function enviar(dados) {
  if (!conectado()) return false;
  socket.send(JSON.stringify(dados));
  return true;
}

function atualizarConexao() {
  atualizarPilula(conectado());
  atualizarChat();
}

function tratarMensagem(msg) {
  switch (msg.tipo) {
    case 'estado':
      aplicarEstado(msg.andares);
      atualizarContadores(msg.andares);
      renderizarEquipe(); // tela Equipe aberta: status ao vivo
      break;
    case 'resposta_agente':
      receberResposta(msg);
      break;
    case 'tarefa_adiada':
      receberAdiada(msg);
      break;
    case 'aviso':
      receberAviso(msg);
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

  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({ tipo: 'auth', token: sessao.token }));
    if (chatAberto) ws.send(JSON.stringify({ tipo: 'presenca', interagiu: true, chat: chatAtual() })); // reconectou
    atualizarConexao();
    recarregarHistoricos();
  });

  ws.addEventListener('message', (e) => {
    try {
      tratarMensagem(JSON.parse(e.data));
    } catch (erro) {
      console.warn('Mensagem inválida do servidor:', erro);
    }
  });

  ws.addEventListener('close', (e) => {
    if (socket !== ws) return; // fechamento feito por desconectar()
    socket = null;
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
  const ws = socket;
  socket = null;
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
