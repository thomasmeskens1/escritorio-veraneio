// Registro de atividade: últimos pedidos, com linha do tempo de cada um (acordeão).

const INTERVALO_REGISTRO = 5000;
const LIMITE_REGISTRO = 50;

const ROTULOS_EVENTO = {
  recebida: 'Recebida',
  tentativa: 'Tentativa',
  falha_modelo: 'Falha do modelo',
  consulta_cerebro: 'Consulta ao Cérebro',
  agente_criado: 'Agente criado',
  etapa_iniciada: 'Etapa iniciada',
  etapa_salva: 'Etapa salva',
  adiada: 'Adiada',
  concluida: 'Concluída',
  falhou: 'Falhou',
};

const janelaRegistro = document.getElementById('registro');
const registroConteudo = document.getElementById('registro-conteudo');
const registroAtualizado = document.getElementById('registro-atualizado');

let registroAberto = false;
let timerRegistro = null;
let carregandoRegistro = false;
let assinaturaRegistro = '';
const registrosExpandidos = new Set(); // tarefa_id abertos (sobrevivem às atualizações)

// ---------- Formatação ----------
function dataValida(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d : null;
}

const horaMinuto = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const ehHoje = (d) => d.toDateString() === new Date().toDateString();

function criarHora(iso, comSegundos = false) {
  const d = dataValida(iso);
  const el = novoEl('time', null, d ? (comSegundos ? d.toLocaleTimeString('pt-BR') : horaMinuto(d)) : '—');
  if (d) {
    el.dateTime = d.toISOString();
    el.title = d.toLocaleString('pt-BR');
    if (!comSegundos && !ehHoje(d)) el.append(novoEl('small', null, d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })));
  }
  return el;
}

// Nome do agente: lista do item > estado atual > id.
function nomeAgenteRegistro(id, item) {
  const doItem = (item.agentes || []).find((a) => a.id === id);
  if (doItem?.nome) return doItem.nome;
  for (const nivel of Object.keys(estadoAgentes || {})) {
    if (estadoAgentes[nivel]?.[id]?.nome) return estadoAgentes[nivel][id].nome;
  }
  return id || '—';
}

// ---------- Abertura ----------
function abrirRegistro() {
  if (!sessao) return;
  registroAberto = true;
  janelaRegistro.classList.add('aberto');
  if (!registroConteudo.childElementCount) registroConteudo.append(novoEl('p', 'painel-aviso', 'Carregando registro...'));
  carregarRegistro();
  clearInterval(timerRegistro);
  timerRegistro = setInterval(carregarRegistro, INTERVALO_REGISTRO);
  document.getElementById('registro-fechar').focus();
}

function fecharRegistro() {
  const estavaAberto = registroAberto;
  registroAberto = false;
  clearInterval(timerRegistro);
  timerRegistro = null;
  janelaRegistro.classList.remove('aberto');
  if (estavaAberto) document.getElementById('abrir-registro').focus();
}

// Ao sair: nada do usuário anterior fica na tela.
function limparRegistro() {
  fecharRegistro();
  registroConteudo.replaceChildren();
  registroAtualizado.textContent = '';
  assinaturaRegistro = '';
  registrosExpandidos.clear();
}

// ---------- Dados ----------
async function carregarRegistro() {
  if (!registroAberto || carregandoRegistro || !sessao) return;
  carregandoRegistro = true;
  try {
    const resposta = await fetch(`/api/registro?limite=${LIMITE_REGISTRO}`, {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    if (resposta.status === 401) {
      fecharRegistro();
      encerrarSessao('Sessão expirada. Entre novamente.');
      return;
    }
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    const dados = await resposta.json();
    if (!registroAberto) return;
    const itens = Array.isArray(dados.itens) ? dados.itens : [];
    const nova = JSON.stringify(itens);
    if (nova !== assinaturaRegistro || !registroConteudo.querySelector('.registro-lista, .tarefas-vazio')) {
      assinaturaRegistro = nova;
      renderizarRegistro(itens);
    }
    registroAtualizado.textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (erro) {
    console.warn('Falha ao carregar registro:', erro);
    if (!registroAberto) return;
    registroAtualizado.textContent = 'Sem conexão — tentando novamente...';
    if (!registroConteudo.querySelector('.registro-lista')) {
      registroConteudo.replaceChildren(novoEl('p', 'painel-aviso', 'Não foi possível carregar o registro.'));
    }
  } finally {
    carregandoRegistro = false;
  }
}

// ---------- Renderização ----------
function renderizarRegistro(itens) {
  if (!itens.length) {
    const vazio = novoEl('div', 'tarefas-vazio');
    vazio.append(novoEl('strong', null, 'Nenhuma atividade registrada ainda.'), novoEl('span', null, 'Os pedidos enviados aos agentes aparecem aqui.'));
    registroConteudo.replaceChildren(vazio);
    return;
  }
  const cabecalho = novoEl('div', 'registro-cabecalho');
  cabecalho.setAttribute('aria-hidden', 'true');
  ['Quando', 'Usuário', 'Agentes', 'Tarefa', 'Modelo', ''].forEach((t) => cabecalho.append(novoEl('span', null, t)));
  const lista = novoEl('ul', 'registro-lista');
  itens.forEach((item) => lista.append(criarItemRegistro(item)));
  registroConteudo.replaceChildren(cabecalho, lista);
}

function criarItemRegistro(item) {
  const id = String(item.tarefa_id);
  const aberto = registrosExpandidos.has(id);
  const li = novoEl('li', `registro-item registro-${item.status || 'desconhecido'}`);

  const linha = novoEl('button', 'registro-linha');
  linha.type = 'button';
  linha.setAttribute('aria-expanded', String(aberto));
  linha.setAttribute('aria-controls', `registro-detalhe-${id}`);

  const agentes = novoEl('span', 'reg-agentes');
  (item.agentes || []).forEach((a) => agentes.append(novoEl('span', 'chip-agente', a.nome || a.id)));
  if (!agentes.childElementCount) agentes.append(novoEl('span', 'reg-vazio', '—'));

  const modelo = novoEl('span', 'reg-modelo', abreviarModelo(item.modelo) || '—');
  if (item.modelo) modelo.title = item.modelo;
  else modelo.classList.add('reg-vazio');

  const quando = criarHora(item.em);
  quando.classList.add('reg-hora');
  const usuario = novoEl('span', 'reg-usuario', item.usuario_nome || item.usuario || '—');
  if (item.usuario) usuario.title = item.usuario;

  linha.append(quando, usuario, agentes, novoEl('span', 'reg-resumo', item.resumo || '(sem resumo)'), modelo, novoEl('span', 'seta'));

  const detalhe = criarDetalheRegistro(item);
  detalhe.id = `registro-detalhe-${id}`;
  detalhe.hidden = !aberto;
  li.classList.toggle('aberto', aberto);

  linha.addEventListener('click', () => {
    const abrir = detalhe.hidden;
    detalhe.hidden = !abrir;
    li.classList.toggle('aberto', abrir);
    linha.setAttribute('aria-expanded', String(abrir));
    if (abrir) registrosExpandidos.add(id);
    else registrosExpandidos.delete(id);
  });

  li.append(linha, detalhe);
  return li;
}

function fato(rotulo, valor) {
  const div = novoEl('div');
  const dd = novoEl('dd');
  if (valor instanceof Node) dd.append(valor);
  else dd.textContent = valor;
  div.append(novoEl('dt', null, rotulo), dd);
  return div;
}

function criarDetalheRegistro(item) {
  const caixa = novoEl('div', 'registro-detalhe');
  const fatos = novoEl('dl', 'reg-fatos');
  fatos.append(
    fato('Dificuldade', item.dificuldade ? seloDificuldade(item.dificuldade) : '—'),
    fato('Status', novoEl('span', `estado estado-${item.status}`, ROTULOS_TAREFA[item.status] || item.status || '—')),
    fato('Tempo total', formatarTempo(item.tempo_segundos)),
  );
  if (item.custo_usd > 0) fatos.append(fato('Custo', moedaUsd(item.custo_usd, 4)));
  if (item.modelo) fatos.append(fato('Modelo', novoEl('span', 'reg-modelo-completo', item.modelo)));
  caixa.append(fatos);

  const eventos = Array.isArray(item.eventos) ? item.eventos : [];
  caixa.append(novoEl('h4', null, 'Linha do tempo'));
  if (!eventos.length) {
    caixa.append(novoEl('p', 'aprendizado-nota', 'Sem eventos registrados.'));
    return caixa;
  }
  const linhaTempo = novoEl('ol', 'linha-tempo');
  eventos.forEach((ev) => {
    const li = novoEl('li', `evento evento-${ev.tipo}`);
    const topo = novoEl('div', 'evento-topo');
    topo.append(criarHora(ev.em, true), novoEl('strong', null, ROTULOS_EVENTO[ev.tipo] || ev.tipo || '—'));
    if (ev.agente) topo.append(novoEl('span', 'chip-agente', nomeAgenteRegistro(ev.agente, item)));
    if (ev.modelo) {
      const m = novoEl('span', 'reg-modelo', abreviarModelo(ev.modelo));
      m.title = ev.modelo;
      topo.append(m);
    }
    li.append(topo);
    if (ev.detalhe) li.append(novoEl('p', 'evento-detalhe', ev.detalhe));
    linhaTempo.append(li);
  });
  caixa.append(linhaTempo);
  return caixa;
}

document.getElementById('registro-fechar').addEventListener('click', fecharRegistro);
janelaRegistro.addEventListener('click', (e) => {
  if (e.target === janelaRegistro) fecharRegistro();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && registroAberto) fecharRegistro();
});
