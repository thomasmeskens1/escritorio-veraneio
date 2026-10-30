// Barra superior: contadores de agentes por status, status do servidor e relógio.

const STATUS_CONTADOS = ['disponivel', 'trabalhando', 'construindo', 'dormindo'];

// Soma os agentes de todos os andares visíveis no último `estado`.
function atualizarContadores(andares) {
  const totais = Object.fromEntries(STATUS_CONTADOS.map((s) => [s, 0]));
  Object.entries(andares || {}).forEach(([nivel, agentes]) => {
    if (!agentes || typeof agentes !== 'object' || !podeAcessar(nivel)) return;
    Object.values(agentes).forEach((a) => {
      if (a && a.status in totais) totais[a.status] += 1;
    });
  });
  STATUS_CONTADOS.forEach((s) => {
    document.getElementById(`contador-${s}`).textContent = totais[s];
  });
}

// Pílula "AO VIVO" (WebSocket aberto) / "FECHADO".
// 'online' | 'reconectando' (sessão ativa, conexão caindo ou sem resposta: js/rede.js tenta de novo) | 'fechado'.
function atualizarPilula(estado) {
  const pilula = document.getElementById('conexao');
  pilula.classList.toggle('online', estado === 'online');
  pilula.classList.toggle('reconectando', estado === 'reconectando');
  pilula.textContent = { online: 'AO VIVO', reconectando: 'RECONECTANDO' }[estado] || 'FECHADO';
  pilula.title = { online: 'Servidor conectado', reconectando: 'Sem resposta do servidor; reconectando sozinho' }[estado]
    || 'Servidor desconectado';
}

function atualizarRelogio() {
  const agora = new Date();
  const relogio = document.getElementById('relogio');
  const texto = agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (relogio.textContent !== texto) {
    relogio.textContent = texto;
    relogio.dateTime = agora.toISOString();
  }
}

// O Phaser escuta mousedown/touch na window: sem isto, clicar num botão de popup
// ou da barra também "clica" no agente desenhado atrás dele.
['#topo', '#elevador', '.modal', '#toasts'].forEach((seletor) => {
  document.querySelectorAll(seletor).forEach((el) => {
    ['mousedown', 'mouseup', 'touchstart', 'touchend', 'pointerdown'].forEach((tipo) =>
      el.addEventListener(tipo, (e) => e.stopPropagation()),
    );
  });
});

atualizarRelogio();
setInterval(atualizarRelogio, 1000);
document.getElementById('abrir-registro').addEventListener('click', () => abrirRegistro());
