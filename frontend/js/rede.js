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
      atualizarCabecalhoDiretora();
      break;
    case 'resposta_agente':
      receberResposta(msg);
      break;
    case 'tarefa_adiada':
      receberAdiada(msg);
      break;
    case 'erro':
      receberErro(msg);
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
    atualizarConexao();
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
