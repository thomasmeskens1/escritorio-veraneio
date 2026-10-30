// Caixa de entrada (Thomas, 30/10/2026; ideia do pizza-bot): "Para aprovar" (formulários e produções esperando
// você) e "Concluídos" (pedidos prontos que você ainda não abriu). Clicar abre o chat do pedido e marca como lido.

const botaoCaixa = document.getElementById('abrir-caixa');
const contadorCaixa = document.getElementById('caixa-contador');
const INTERVALO_CAIXA = 60000;
let dadosCaixa = { aprovar: [], concluidos: [] };
let abaCaixa = 'aprovar';
let timerCaixa = null;
let atrasoCaixa = null;

async function chamarCaixa(caminho, corpo) {
  const resposta = await fetch(caminho, corpo ? {
    method: 'POST', headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  } : { headers: { Authorization: `Bearer ${sessao.token}` } });
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
  return resposta.json();
}

async function atualizarCaixa() {
  if (!sessao) return;
  try {
    dadosCaixa = await chamarCaixa('/api/caixa');
  } catch {
    return; // mantém o que já estava na tela
  }
  const total = dadosCaixa.aprovar.length + dadosCaixa.concluidos.length;
  contadorCaixa.hidden = !total;
  contadorCaixa.textContent = total > 99 ? '99+' : String(total);
  contadorCaixa.classList.toggle('urgente', dadosCaixa.aprovar.length > 0);
  botaoCaixa.title = `Caixa de entrada: ${dadosCaixa.aprovar.length} para aprovar, ${dadosCaixa.concluidos.length} concluídos`;
  if (popupFormulario?.querySelector('.janela-caixa')) renderizarCaixa();
}

// Respostas chegando pelo WebSocket: atualiza em seguida (agrupado, sem uma chamada por mensagem).
function caixaMudou() {
  clearTimeout(atrasoCaixa);
  atrasoCaixa = setTimeout(atualizarCaixa, 1500);
}

function iniciarCaixa() {
  clearInterval(timerCaixa);
  atualizarCaixa();
  timerCaixa = setInterval(atualizarCaixa, INTERVALO_CAIXA);
}

function quandoCaixa(iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return '';
  const hoje = d.toDateString() === new Date().toDateString();
  return hoje ? d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function abrirItemCaixa(item, marcar) {
  fecharFormularioPopup();
  if (marcar) {
    chamarCaixa('/api/caixa/lidos', { ids: [item.tarefa_id] }).then(caixaMudou).catch(() => {});
  }
  if (andarAtual !== item.andar && cena) renderizarAndar(item.andar);
  abrirAgente(item.andar, item.agente);
}

// Abriu o chat por outro caminho: os concluídos daquele chat também contam como lidos.
function caixaChatAberto(andar, agente) {
  const ids = dadosCaixa.concluidos.filter((c) => c.andar === andar && c.agente === agente).map((c) => c.tarefa_id);
  if (ids.length && sessao) chamarCaixa('/api/caixa/lidos', { ids }).then(caixaMudou).catch(() => {});
}

function renderizarCaixa() {
  const janela = popupFormulario?.querySelector('.janela-caixa');
  if (!janela) return;
  const corpo = janela.querySelector('.caixa-corpo');
  janela.querySelectorAll('.caixa-aba').forEach((b) => {
    const ativa = b.dataset.aba === abaCaixa;
    b.classList.toggle('ativa', ativa);
    b.setAttribute('aria-selected', String(ativa));
    const n = dadosCaixa[b.dataset.aba].length;
    b.querySelector('.caixa-aba-n').textContent = n ? ` (${n})` : '';
  });
  const itens = dadosCaixa[abaCaixa];
  const lista = novoEl('ul', 'caixa-lista');
  if (!itens.length) {
    corpo.replaceChildren(novoEl('p', 'rotinas-nota', abaCaixa === 'aprovar'
      ? 'Nada esperando você. Quando um agente pedir um formulário ou uma decisão de produção, aparece aqui.'
      : 'Nenhum pedido novo concluído nos últimos 7 dias.'));
    return;
  }
  itens.forEach((item) => {
    const li = novoEl('li');
    const linha = novoEl('button', `caixa-item${item.status === 'falhou' ? ' falhou' : ''}`);
    linha.type = 'button';
    const topo = novoEl('span', 'caixa-item-topo');
    const quem = item.por ? `${item.agente_nome} · por ${item.por}` : item.agente_nome;
    topo.append(novoEl('strong', null, quem), novoEl('time', null, quandoCaixa(item.em)));
    linha.append(topo);
    if (item.motivo) linha.append(novoEl('span', 'caixa-motivo', item.motivo));
    if (item.status === 'falhou') linha.append(novoEl('span', 'caixa-motivo', 'Não foi concluído: veja o motivo no chat'));
    linha.append(novoEl('span', 'caixa-resumo', item.resumo || '(sem texto)'));
    linha.addEventListener('click', () => abrirItemCaixa(item, abaCaixa === 'concluidos'));
    li.append(linha);
    lista.append(li);
  });
  const partes = [lista];
  if (abaCaixa === 'concluidos') {
    const todos = novoEl('button', 'botao-secundario caixa-todos', 'Marcar todos como lidos');
    todos.type = 'button';
    todos.addEventListener('click', async () => {
      todos.disabled = true;
      await chamarCaixa('/api/caixa/lidos', { todos: true }).catch(() => {});
      atualizarCaixa();
    });
    partes.unshift(todos);
  }
  corpo.replaceChildren(...partes);
}

function abrirCaixa() {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-caixa');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, 'Caixa de entrada'), novoEl('p', null, 'O que espera você e o que ficou pronto'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);
  const abas = novoEl('div', 'caixa-abas');
  abas.setAttribute('role', 'tablist');
  [['aprovar', 'Para aprovar'], ['concluidos', 'Concluídos']].forEach(([chaveAba, rotulo]) => {
    const aba = novoEl('button', 'caixa-aba');
    aba.type = 'button';
    aba.dataset.aba = chaveAba;
    aba.setAttribute('role', 'tab');
    aba.append(document.createTextNode(rotulo), novoEl('span', 'caixa-aba-n'));
    aba.addEventListener('click', () => { abaCaixa = chaveAba; renderizarCaixa(); });
    abas.append(aba);
  });
  janela.append(barra, abas, novoEl('div', 'formulario-corpo caixa-corpo'));
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  abaCaixa = dadosCaixa.aprovar.length || !dadosCaixa.concluidos.length ? 'aprovar' : 'concluidos';
  renderizarCaixa();
  atualizarCaixa();
  fechar.focus();
}

// Ao sair: nada do usuário anterior fica na tela.
function limparCaixa() {
  clearInterval(timerCaixa);
  clearTimeout(atrasoCaixa);
  dadosCaixa = { aprovar: [], concluidos: [] };
  contadorCaixa.hidden = true;
}

botaoCaixa.addEventListener('click', abrirCaixa);
