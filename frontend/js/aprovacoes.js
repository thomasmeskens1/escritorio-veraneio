// Uma fila só de aprovações (Onda 2 de novembro: construtor-12, designer-20, estrategista-04, construtor-01).
// Na aba "Para aprovar" da Caixa de entrada, junto dos formulários e produções: propostas de agente, pedidos de obra,
// persona do Corporativo, decisões de estudo e folhas de aprovação (GET /api/aprovacoes). Cada item vence em 7 dias;
// vencido só fica destacado: nada some e nada é aprovado sozinho. Um item por vez, sem "aprovar tudo".

let dadosAprovacoes = [];
const textosAbertos = new Set(); // 'tipo/id' com o texto (persona, obra) aberto
const camposAbertos = new Set(); // 'tipo/id' com o campo "Decisão do Thomas" aberto
const decidindo = new Set();
let avisoAprovacao = null; // { chave, texto, erro }

const chaveAprovacao = (item) => `${item.tipo}/${item.id}`;
const nAprovarCaixa = () => dadosCaixa.aprovar.length + dadosAprovacoes.length;

async function atualizarAprovacoes() {
  if (!sessao) return;
  try {
    const dados = await chamarCaixa('/api/aprovacoes');
    dadosAprovacoes = Array.isArray(dados.itens) ? dados.itens : [];
  } catch {
    // mantém o que já estava
  }
}

function limparAprovacoes() {
  dadosAprovacoes = [];
  textosAbertos.clear();
  camposAbertos.clear();
  avisoAprovacao = null;
}

function prazoAprovacao(item) {
  if (item.vencido) return `Venceu: parado há ${plural(item.dias, 'dia', 'dias')}`;
  const restam = Math.max(0, 7 - (item.dias || 0));
  return restam ? `Vence em ${plural(restam, 'dia', 'dias')}` : 'Vence hoje';
}

function abrirChatAprovacao(item, preencher) {
  if (!item.chat) return;
  fecharFormularioPopup();
  if (andarAtual !== item.chat.andar && cena) renderizarAndar(item.chat.andar);
  abrirAgente(item.chat.andar, item.chat.agente);
  if (preencher && !modalInput.disabled) {
    modalInput.value = preencher;
    ajustarAlturaInput();
    modalInput.focus();
  }
}

async function decidirAprovacao(item, acao, texto = '') {
  const k = chaveAprovacao(item);
  if (decidindo.has(k)) return;
  decidindo.add(k);
  renderizarCaixa();
  try {
    const resposta = await fetch(`/api/aprovacoes/${encodeURIComponent(item.tipo)}/${encodeURIComponent(item.id)}/${acao}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto }),
    });
    if (resposta.status === 401) return encerrarSessao('Sessão expirada. Entre novamente.');
    const dados = await resposta.json().catch(() => ({}));
    avisoAprovacao = resposta.ok ? { chave: k, texto: dados.mensagem || 'Feito.', erro: false }
      : { chave: k, texto: dados.detail || 'Não foi possível decidir agora.', erro: true };
  } catch {
    avisoAprovacao = { chave: k, texto: 'Servidor indisponível. Tente de novo.', erro: true };
  } finally {
    decidindo.delete(k);
    camposAbertos.delete(k);
  }
  await atualizarCaixa();
  renderizarCaixa();
}

function botaoAprovacao(rotulo, classe, aoClicar) {
  const botao = novoEl('button', classe, rotulo);
  botao.type = 'button';
  botao.addEventListener('click', aoClicar);
  return botao;
}

function criarItemAprovacao(item) {
  const k = chaveAprovacao(item);
  const li = novoEl('li', `aprovacao-item${item.vencido ? ' vencido' : ''}${item.informativo ? ' informativo' : ''}`);
  const topo = novoEl('span', 'caixa-item-topo');
  topo.append(novoEl('strong', null, item.titulo), novoEl('time', null, quandoCaixa(item.criado_em)));
  li.append(topo, novoEl('span', 'caixa-motivo', item.informativo ? 'Para acompanhar (a decisão não é sua)' : prazoAprovacao(item)));
  if (item.resumo) li.append(novoEl('span', 'caixa-resumo', item.resumo));
  if (item.texto && textosAbertos.has(k)) li.append(novoEl('pre', 'aprovacao-texto', item.texto));

  const acoes = novoEl('div', 'aprovacao-acoes');
  const ocupado = decidindo.has(k);
  if (item.texto) {
    acoes.append(botaoAprovacao(textosAbertos.has(k) ? 'Esconder o texto' : 'Ler o texto', 'botao-secundario', () => {
      if (textosAbertos.has(k)) textosAbertos.delete(k); else textosAbertos.add(k);
      renderizarCaixa();
    }));
  }
  if (item.tipo === 'obra' && item.texto && navigator.clipboard) {
    acoes.append(botaoAprovacao('Copiar para o Claude Code', 'botao-secundario', () => {
      navigator.clipboard.writeText(item.texto).then(() => {
        avisoAprovacao = { chave: k, texto: 'Texto copiado.', erro: false };
        renderizarCaixa();
      }).catch(() => {});
    }));
  }
  (item.acoes || []).forEach((a) => {
    let aoClicar;
    if (a.preencher) aoClicar = () => abrirChatAprovacao(item, a.preencher);
    else if (a.acao === 'abrir') aoClicar = () => abrirChatAprovacao(item);
    else if (a.campo) aoClicar = () => { camposAbertos.add(k); renderizarCaixa(); };
    else aoClicar = () => { if (window.confirm(`${a.rotulo}: ${item.titulo}?`)) decidirAprovacao(item, a.acao); };
    const botao = botaoAprovacao(ocupado ? 'Aguarde...' : a.rotulo, 'botao-secundario', aoClicar);
    botao.disabled = ocupado;
    acoes.append(botao);
  });
  if (item.chat && !(item.acoes || []).some((a) => a.acao === 'abrir' || a.preencher)) {
    acoes.append(botaoAprovacao('Abrir o chat', 'botao-secundario', () => abrirChatAprovacao(item)));
  }
  li.append(acoes);

  const campo = (item.acoes || []).find((a) => a.campo);
  if (campo && camposAbertos.has(k)) {
    const caixaTexto = novoEl('textarea', 'form-entrada');
    caixaTexto.rows = 2;
    caixaTexto.placeholder = 'Ex.: Opção B, revisar em 60 dias';
    caixaTexto.setAttribute('aria-label', campo.campo);
    const confirmar = botaoAprovacao('Registrar', 'botao-secundario', () => {
      const texto = caixaTexto.value.trim();
      if (texto) decidirAprovacao(item, campo.acao, texto);
    });
    const bloco = novoEl('div', 'aprovacao-campo');
    bloco.append(novoEl('small', null, campo.campo), caixaTexto, confirmar);
    li.append(bloco);
  }
  if (avisoAprovacao?.chave === k) {
    li.append(novoEl('p', `perfil-treino-resultado${avisoAprovacao.erro ? ' erro' : ''}`, avisoAprovacao.texto));
  }
  return li;
}

// Lista da fila para a aba "Para aprovar" (null quando não há nada).
function criarListaAprovacoes() {
  if (!dadosAprovacoes.length && !avisoAprovacao) return null;
  const lista = novoEl('ul', 'caixa-lista aprovacoes-lista');
  dadosAprovacoes.forEach((item) => lista.append(criarItemAprovacao(item)));
  if (avisoAprovacao && !dadosAprovacoes.some((i) => chaveAprovacao(i) === avisoAprovacao.chave)) {
    lista.append(novoEl('p', `perfil-treino-resultado${avisoAprovacao.erro ? ' erro' : ''}`, avisoAprovacao.texto));
  }
  return lista;
}
