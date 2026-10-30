// Registro de insatisfações (Thomas, 30/10/2026; só o master): cada 👎 ou mensagem negativa respondida no pop-up de
// js/avaliacao.js, com o pedido e a resposta do agente, para analisar junto com a equipe. "Marcar como analisada"
// guarda uma nota do que foi feito.

const botaoInsatisfacoes = document.getElementById('abrir-insatisfacoes');
const contadorInsatisfacoes = document.getElementById('insatisfacoes-contador');
const INTERVALO_INSATISFACOES = 120000;
let dadosInsatisfacoes = { itens: [], novas: 0 };
let filtroInsatisfacoes = 'nova';
let timerInsatisfacoes = null;

async function chamarInsatisfacoes(caminho, corpo) {
  const resposta = await fetch(caminho, corpo ? {
    method: 'POST', headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  } : { headers: { Authorization: `Bearer ${sessao.token}` } });
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
  return resposta.json();
}

function mostrarContadorInsatisfacoes(novas) {
  contadorInsatisfacoes.hidden = !novas;
  contadorInsatisfacoes.textContent = novas > 99 ? '99+' : String(novas);
  botaoInsatisfacoes.title = `Insatisfações: ${novas} nova(s) para analisar`;
}

async function atualizarInsatisfacoes() {
  if (!sessao?.master) return;
  try {
    dadosInsatisfacoes = await chamarInsatisfacoes('/api/insatisfacoes');
  } catch {
    return;
  }
  mostrarContadorInsatisfacoes(dadosInsatisfacoes.novas);
  if (popupFormulario?.querySelector('.janela-insatisfacoes')) renderizarInsatisfacoes();
}

function iniciarInsatisfacoes() {
  clearInterval(timerInsatisfacoes);
  botaoInsatisfacoes.hidden = !sessao?.master;
  if (!sessao?.master) return;
  atualizarInsatisfacoes();
  timerInsatisfacoes = setInterval(atualizarInsatisfacoes, INTERVALO_INSATISFACOES);
}

function limparInsatisfacoes() {
  clearInterval(timerInsatisfacoes);
  dadosInsatisfacoes = { itens: [], novas: 0 };
  botaoInsatisfacoes.hidden = true;
  contadorInsatisfacoes.hidden = true;
}

function quandoInsatisfacao(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
}

function detalhesInsatisfacao(rotulo, texto) {
  const det = novoEl('details');
  det.append(novoEl('summary', null, rotulo), novoEl('p', null, texto || '(vazio)'));
  return det;
}

function criarItemInsatisfacao(item) {
  const li = novoEl('li', `insatisfacao-item${item.status === 'analisada' ? ' analisada' : ''}`);
  const topo = novoEl('div', 'insatisfacao-topo');
  const origem = item.origem === 'mensagem' ? 'mensagem no chat' : '👎';
  topo.append(novoEl('strong', null, `${item.usuario_nome} → ${item.agente_nome} · pedido #${item.tarefa_id}`),
    novoEl('span', null, `${item.categoria_nome} · ${origem} · ${quandoInsatisfacao(item.em)}`));
  li.append(topo);
  if (item.motivo) li.append(novoEl('p', 'insatisfacao-motivo', item.motivo));
  if (item.mensagem && item.mensagem !== item.motivo) li.append(detalhesInsatisfacao('Mensagem que a pessoa escreveu', item.mensagem));
  li.append(detalhesInsatisfacao('Pedido', item.pedido), detalhesInsatisfacao('Resposta do agente', textoNatural(extrairFormulario(item.resposta || '').texto)));

  if (item.status === 'analisada') {
    const nota = item.nota ? `Análise: ${item.nota}` : 'Analisada.';
    li.append(novoEl('p', 'rotinas-nota', `${nota} (${quandoInsatisfacao(item.analisada_em)})`));
    const reabrir = novoEl('button', 'botao-secundario', 'Reabrir');
    reabrir.type = 'button';
    reabrir.addEventListener('click', async () => {
      reabrir.disabled = true;
      await chamarInsatisfacoes(`/api/insatisfacoes/${item.id}/reabrir`, {}).catch(() => {});
      atualizarInsatisfacoes();
    });
    li.append(reabrir);
    return li;
  }
  const form = novoEl('form', 'insatisfacao-acoes');
  const nota = novoEl('input', 'insatisfacao-texto');
  nota.type = 'text';
  nota.maxLength = 2000;
  nota.placeholder = 'O que concluímos ou corrigimos (opcional)';
  const marcar = novoEl('button', 'botao-primario', 'Marcar como analisada');
  marcar.type = 'submit';
  form.append(nota, marcar);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    marcar.disabled = true;
    try {
      await chamarInsatisfacoes(`/api/insatisfacoes/${item.id}/analisar`, { nota: nota.value.trim() });
    } catch {
      marcar.disabled = false;
      return;
    }
    atualizarInsatisfacoes();
  });
  li.append(form);
  return li;
}

function renderizarInsatisfacoes() {
  const janela = popupFormulario?.querySelector('.janela-insatisfacoes');
  if (!janela) return;
  const contagem = { nova: 0, analisada: 0 };
  dadosInsatisfacoes.itens.forEach((i) => { contagem[i.status] = (contagem[i.status] || 0) + 1; });
  janela.querySelectorAll('.caixa-aba').forEach((b) => {
    const ativa = b.dataset.aba === filtroInsatisfacoes;
    b.classList.toggle('ativa', ativa);
    b.setAttribute('aria-selected', String(ativa));
    const n = b.dataset.aba === 'todas' ? dadosInsatisfacoes.itens.length : contagem[b.dataset.aba];
    b.querySelector('.caixa-aba-n').textContent = n ? ` (${n})` : '';
  });
  const corpo = janela.querySelector('.caixa-corpo');
  const itens = dadosInsatisfacoes.itens.filter((i) => filtroInsatisfacoes === 'todas' || i.status === filtroInsatisfacoes);
  if (!itens.length) {
    corpo.replaceChildren(novoEl('p', 'rotinas-nota', filtroInsatisfacoes === 'nova'
      ? 'Nenhuma insatisfação nova. Quando alguém der 👎 ou reclamar no chat e explicar o motivo, aparece aqui.'
      : 'Nada por aqui.'));
    return;
  }
  const lista = novoEl('ul', 'insatisfacoes-lista');
  itens.forEach((i) => lista.append(criarItemInsatisfacao(i)));
  corpo.replaceChildren(lista);
}

function abrirInsatisfacoes() {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-insatisfacoes');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, 'Insatisfações'), novoEl('p', null, 'Reações negativas da equipe, com o motivo, o pedido e a resposta'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);
  const abas = novoEl('div', 'caixa-abas');
  abas.setAttribute('role', 'tablist');
  [['nova', 'Novas'], ['analisada', 'Analisadas'], ['todas', 'Todas']].forEach(([chaveAba, rotulo]) => {
    const aba = novoEl('button', 'caixa-aba');
    aba.type = 'button';
    aba.dataset.aba = chaveAba;
    aba.setAttribute('role', 'tab');
    aba.append(document.createTextNode(rotulo), novoEl('span', 'caixa-aba-n'));
    aba.addEventListener('click', () => { filtroInsatisfacoes = chaveAba; renderizarInsatisfacoes(); });
    abas.append(aba);
  });
  janela.append(barra, abas, novoEl('div', 'formulario-corpo caixa-corpo'));
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  renderizarInsatisfacoes();
  atualizarInsatisfacoes();
  fechar.focus();
}

botaoInsatisfacoes.addEventListener('click', abrirInsatisfacoes);
