// Ratinho do Cérebro (Thomas, 29/10/2026): aparece no canto inferior direito, animado, quando há correções ou
// elogios esperando aprovação. Só para a Diretoria e o master. O clique leva à Cobertura com a ficha do Cérebro
// aberta. Avisos: em tempo real ("correcao_nova", correcoes.avisar_diretoria) e ao entrar, se houver pendências.

const RATO_CEREBRO = `
<svg class="rato" viewBox="0 0 120 110" aria-hidden="true">
  <path class="rato-rabo" d="M86 88 C 108 92, 116 74, 104 66 C 96 61, 92 70, 99 72" fill="none" stroke="#f4a6b4"
    stroke-width="4" stroke-linecap="round"/>
  <ellipse cx="62" cy="84" rx="28" ry="20" fill="#e9ecef"/>
  <ellipse cx="62" cy="90" rx="17" ry="11" fill="#f8f9fa"/>
  <g class="rato-orelha rato-orelha-e"><circle cx="34" cy="34" r="15" fill="#c5ccd3"/><circle cx="34" cy="34" r="9.5"
    fill="#f4a6b4"/></g>
  <g class="rato-orelha rato-orelha-d"><circle cx="88" cy="34" r="15" fill="#c5ccd3"/><circle cx="88" cy="34" r="9.5"
    fill="#f4a6b4"/></g>
  <ellipse cx="61" cy="52" rx="27" ry="24" fill="#e9ecef"/>
  <g class="rato-cerebro">
    <ellipse cx="61" cy="33" rx="19" ry="12" fill="#f7a8c0"/>
    <path d="M47 33 C 51 26, 55 38, 59 30 M61 26 C 64 34, 69 26, 73 33 M52 38 C 57 35, 64 40, 70 37"
      fill="none" stroke="#d0607f" stroke-width="1.6" stroke-linecap="round"/>
  </g>
  <g class="rato-olhos">
    <circle cx="51" cy="54" r="5.5" fill="#ffffff"/><circle cx="71" cy="54" r="5.5" fill="#ffffff"/>
    <circle cx="52" cy="55" r="2.8" fill="#1b1e24"/><circle cx="72" cy="55" r="2.8" fill="#1b1e24"/>
  </g>
  <circle cx="61" cy="65" r="3.4" fill="#ff8fab"/>
  <path d="M40 64 L28 61 M40 67 L27 68 M82 64 L94 61 M82 67 L95 68" stroke="#868e96" stroke-width="1.2"
    stroke-linecap="round"/>
</svg>`;

let avisoCerebro = null;
let avisoCerebroVisto = false; // o aviso de pendências ao entrar sai uma vez por sessão

const veAvisoCerebro = () => !!sessao && (sessao.role === 'diretoria' || sessao.master);

function mostrarAvisoCerebro(total, ultima = '') {
  if (!veAvisoCerebro() || !total) return;
  fecharAvisoCerebro(true);
  const aviso = novoEl('button', 'aviso-cerebro');
  aviso.type = 'button';
  aviso.setAttribute('aria-label', 'Abrir o Cérebro para aprovar correções e elogios');
  aviso.innerHTML = RATO_CEREBRO;
  const texto = novoEl('span', 'aviso-cerebro-texto');
  const novidade = ultima === 'elogio' ? 'Novo elogio para aprovar' : ultima === 'correcao' ? 'Nova correção para aprovar'
    : 'Correções e elogios esperando você';
  texto.append(novoEl('strong', null, novidade),
    novoEl('small', null, `${total} para revisar no Cérebro · clique para abrir`));
  const fechar = novoEl('span', 'aviso-cerebro-fechar', '×');
  fechar.setAttribute('role', 'button');
  fechar.title = 'Dispensar';
  fechar.addEventListener('click', (e) => {
    e.stopPropagation();
    fecharAvisoCerebro();
  });
  aviso.append(texto, novoEl('span', 'aviso-cerebro-selo', String(total)), fechar);
  aviso.addEventListener('click', () => {
    fecharAvisoCerebro();
    if (typeof podeAcessar === 'function' && !podeAcessar('cobertura')) return;
    renderizarAndar('cobertura');
    abrirAgente('cobertura', 'cerebro'); // ficha do Cérebro aberta, com a lista de correções e elogios
  });
  document.getElementById('toasts').append(aviso);
  avisoCerebro = aviso;
}

function fecharAvisoCerebro(imediato = false) {
  const aviso = avisoCerebro;
  avisoCerebro = null;
  if (!aviso?.isConnected) return;
  if (imediato) return aviso.remove();
  aviso.classList.add('saindo');
  setTimeout(() => aviso.remove(), 350);
}

// Ao entrar: se já houver pendências, o ratinho aparece uma vez.
async function verificarAvisoCerebro() {
  if (!veAvisoCerebro() || avisoCerebroVisto) return;
  avisoCerebroVisto = true;
  try {
    const resposta = await fetch('/api/correcoes', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (!resposta.ok) return;
    const dados = await resposta.json();
    mostrarAvisoCerebro(dados.observacoes?.length || 0);
  } catch {
    // sem conexão: tenta na próxima entrada
  }
}

function limparAvisoCerebro() {
  fecharAvisoCerebro(true);
  avisoCerebroVisto = false;
}
