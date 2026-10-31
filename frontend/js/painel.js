// Painel de tarefas do Despachante e notificações (toasts) de respostas.

const INTERVALO_PAINEL = 10000;
const MAX_TOASTS = 3;
const DURACAO_TOAST = 6000;

const ROTULOS_TAREFA = { executando: 'Executando', concluida: 'Concluída', adiada: 'Adiada', falhou: 'Falhou' };
const ROTULOS_DIFICULDADE = { simples: 'simples', media: 'média', complexa: 'complexa' };

const painel = document.getElementById('painel');
const painelConteudo = document.getElementById('painel-conteudo');
const painelAtualizado = document.getElementById('painel-atualizado');
const toasts = document.getElementById('toasts');

let painelAberto = false;
let timerPainel = null;
let carregandoPainel = false;

// ---------- Formatação ----------
const moedaUsd = (valor, casas = 2) =>
  new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: casas,
  }).format(valor || 0);

function formatarTempo(segundos) {
  if (segundos == null || Number.isNaN(Number(segundos))) return '—';
  const s = Number(segundos);
  if (s < 10) return `${s.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`;
  const total = Math.round(s);
  if (total < 60) return `${total} s`;
  const h = Math.floor(total / 3600);
  const min = Math.floor((total % 3600) / 60);
  if (h) return min ? `${h} h ${min} min` : `${h} h`;
  const resto = total % 60;
  return resto ? `${min} min ${resto} s` : `${min} min`;
}

// "openrouter/nvidia/modelo:free" -> "modelo:free"
const abreviarModelo = (modelo) => (modelo ? String(modelo).split('/').pop() : '');

function formatarQuando(iso) {
  const data = iso ? new Date(iso) : null;
  if (!data || Number.isNaN(data.getTime())) return '—';
  const seg = (Date.now() - data.getTime()) / 1000;
  if (seg < 60) return 'agora';
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)} h`;
  return data.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// Linha de metadados de uma resposta: "simples · 12 s · modelo".
function metadadosResposta({ dificuldade, tempo_segundos, modelo, adiada }) {
  const partes = [];
  if (dificuldade) partes.push(ROTULOS_DIFICULDADE[dificuldade] || dificuldade);
  if (tempo_segundos != null) partes.push(formatarTempo(tempo_segundos));
  if (modelo) partes.push(abreviarModelo(modelo));
  if (adiada) partes.push('processada pela fila do Claude');
  return partes.join(' · ');
}

// Cria elemento com classe e texto (sempre via textContent).
function novoEl(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto != null) e.textContent = texto;
  return e;
}

// ---------- Abertura ----------
// sistema -> painel de tarefas; estagiario -> nada (não interativos); ia (inclusive o
// Cérebro) -> popup do agente com chat.
function abrirAgente(andar, id) {
  const { tipo } = dadosAgente(andar, id);
  if (tipo === 'estagiario') return;
  if (tipo === 'sistema') {
    abrirPainel();
  } else {
    fecharPainel();
    abrirChat(andar, id);
  }
}

function abrirPainel() {
  if (typeof fecharChat === 'function') fecharChat();
  painelAberto = true;
  painel.classList.add('aberto');
  if (!painelConteudo.childElementCount) painelConteudo.append(novoEl('p', 'painel-aviso', 'Carregando tarefas...'));
  carregarTarefas();
  clearInterval(timerPainel);
  timerPainel = setInterval(carregarTarefas, INTERVALO_PAINEL);
  document.getElementById('painel-fechar').focus();
}

function fecharPainel() {
  painelAberto = false;
  clearInterval(timerPainel);
  timerPainel = null;
  painel.classList.remove('aberto');
}

// ---------- Dados ----------
async function carregarTarefas() {
  if (!painelAberto || carregandoPainel || !sessao) return;
  carregandoPainel = true;
  try {
    const resposta = await fetch('/api/tarefas', {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    if (resposta.status === 401) {
      fecharPainel();
      encerrarSessao('Sessão expirada. Entre novamente.');
      return;
    }
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    const dados = await resposta.json();
    if (!painelAberto) return;
    dados.resumo = { ...(dados.resumo || {}), uso_max: await carregarUsoMax() };
    renderizarPainel(dados);
    painelAtualizado.textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR')}`;
  } catch (erro) {
    console.warn('Falha ao carregar tarefas:', erro);
    if (painelAberto) painelAtualizado.textContent = 'Sem conexão — tentando novamente...';
    if (painelAberto && !painelConteudo.querySelector('.resumo')) {
      painelConteudo.replaceChildren(novoEl('p', 'painel-aviso', 'Não foi possível carregar as tarefas.'));
    }
  } finally {
    carregandoPainel = false;
  }
}

// ---------- Renderização ----------
function renderizarPainel({ resumo = {}, tarefas = [] }) {
  const blocos = [
    criarAvisos(resumo.avisos), criarResumo(resumo), criarCredito(resumo.anthropic), criarModelosFora(resumo.modelos_fora),
    criarSaudeModelos(resumo.modelos_7d), criarUsoMax(resumo.uso_max), criarAprendizado(resumo.aprendizado),
    criarListaTarefas(tarefas),
  ];
  painelConteudo.replaceChildren(...blocos.filter(Boolean));
}

// Medição do Max (despachante-07): consumo dos últimos 7 dias por tipo, agente e empresa. Só a Diretoria
// (decisão 11); atualiza a cada minuto, não a cada 10 s.
const INTERVALO_USO_MAX = 60000;
let usoMax = null;
let usoMaxEm = 0;

async function carregarUsoMax() {
  if (sessao?.role !== 'diretoria') return null;
  if (Date.now() - usoMaxEm < INTERVALO_USO_MAX) return usoMax;
  usoMaxEm = Date.now();
  try {
    const resposta = await fetch('/api/producao/uso-max', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.ok) usoMax = await resposta.json();
  } catch (erro) {
    console.warn('Falha ao carregar o uso do Max:', erro);
  }
  return usoMax;
}

const ROTULOS_TIPO_MAX = { texto: 'Texto', anexo: 'Anexo', prospeccao: 'Prospecção', producao: 'Produção' };
const numeroCurto = (n) => new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(n || 0);

function criarUsoMax(uso) {
  if (!uso || !uso.total || !uso.total.trabalhos) return null;
  const caixa = novoEl('section', 'credito');
  caixa.append(novoEl('h3', null, `Uso do Max (${uso.dias} dias)`));
  const { total } = uso;
  caixa.append(novoEl('p', 'credito-legenda',
    `${total.trabalhos} trabalho(s) · ${formatarTempo(total.duracao_s)} · ${numeroCurto(total.tokens)} tokens · `
    + `${numeroCurto(total.chars)} caracteres · ${total.rodadas} rodada(s)`));
  [['Por tipo', uso.por_tipo, (c) => ROTULOS_TIPO_MAX[c.chave] || c.nome],
    ['Por agente', uso.por_agente, (c) => c.nome], ['Por empresa', uso.por_empresa, (c) => c.nome]]
    .forEach(([titulo, linhas = [], rotulo]) => {
      if (!linhas.length) return;
      const tabela = novoEl('table', 'saude-modelos');
      const cabecalho = novoEl('tr');
      [titulo, 'Trabalhos', 'Tempo', 'Tokens', 'Caracteres', 'Rodadas'].forEach((t) => cabecalho.append(novoEl('th', null, t)));
      tabela.append(cabecalho);
      linhas.slice(0, 8).forEach((c) => {
        const linha = novoEl('tr', c.falhas ? 'saude-atencao' : null);
        [rotulo(c), `${c.trabalhos}${c.falhas ? ` (${c.falhas} falha)` : ''}`, formatarTempo(c.duracao_s),
          numeroCurto(c.tokens), numeroCurto(c.chars), c.rodadas].forEach((v) => linha.append(novoEl('td', null, String(v))));
        tabela.append(linha);
      });
      caixa.append(tabela);
    });
  caixa.append(novoEl('p', 'credito-legenda', 'Tokens e rodadas vêm do Claude Code (trabalhador novo); o plano Max não '
    + 'informa o limite exato da janela de 5 h.'));
  return caixa;
}

// Modelos fora da rota: pausa curta (cota, limite, lentidão) ou AFASTADOS por falha recorrente (7 dias).
// Avisos de operação para a Diretoria (ex.: backup diário atrasado).
function criarAvisos(avisos = []) {
  if (!avisos.length) return null;
  const caixa = novoEl('section', 'credito');
  caixa.append(novoEl('h3', null, '⚠ Atenção'));
  avisos.forEach((texto) => caixa.append(novoEl('p', 'credito-legenda modelo-afastado', texto)));
  return caixa;
}

function criarModelosFora(modelos = []) {
  if (!modelos.length) return null;
  const caixa = novoEl('section', 'credito');
  caixa.append(novoEl('h3', null, 'Modelos fora da rota'));
  modelos.forEach(({ modelo, motivo, volta_em: volta, afastado, falhas_24h: falhas }) => {
    const quando = new Date(volta).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const linha = novoEl('p', `credito-legenda${afastado ? ' modelo-afastado' : ''}`,
      `${afastado ? '⚠ ' : ''}${abreviarModelo(modelo)} · ${motivo} · ${falhas} falha(s) em 24 h · volta em ${quando} `);
    if (sessao?.role === 'diretoria') {  // devolver à rota agora (revisão de 30/10/2026)
      const devolver = novoEl('button', 'botao-secundario painel-detalhes', 'Devolver à rota');
      devolver.type = 'button';
      devolver.addEventListener('click', async () => {
        devolver.disabled = true;
        await fetch('/api/modelos/devolver', {
          method: 'POST', headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ modelo }),
        }).catch(() => {});
        carregarPainel();
      });
      linha.append(devolver);
    }
    caixa.append(linha);
  });
  return caixa;
}

// Saúde de cada modelo nos últimos 7 dias: ajuda a decidir se um modelo deve sair da lista de vez.
function criarSaudeModelos(modelos = []) {
  if (!modelos.length) return null;
  const caixa = novoEl('section', 'credito');
  const titulo = novoEl('h3', null, 'Saúde dos modelos (7 dias) ');
  if (sessao?.role === 'diretoria') {
    const detalhes = novoEl('button', 'botao-secundario painel-detalhes', 'Ver tudo');
    detalhes.type = 'button';
    detalhes.addEventListener('click', () => { fecharPainel(); abrirModelos(); });
    titulo.append(detalhes);
  }
  caixa.append(titulo);
  const tabela = novoEl('table', 'saude-modelos');
  const cabecalho = novoEl('tr');
  ['Modelo', 'Tentativas', 'Falhas', 'Taxa de falha', 'Tempo médio'].forEach((t) => cabecalho.append(novoEl('th', null, t)));
  tabela.append(cabecalho);
  modelos.forEach(({ modelo, tentativas, falhas, taxa_falha: taxa, tempo_medio_s: tempo }) => {
    const linha = novoEl('tr', taxa >= 0.5 ? 'saude-ruim' : taxa >= 0.2 ? 'saude-atencao' : null);
    [abreviarModelo(modelo), tentativas, falhas, `${Math.round(taxa * 100)}%`, tempo != null ? `${tempo} s` : '—']
      .forEach((v) => linha.append(novoEl('td', null, String(v))));
    tabela.append(linha);
  });
  caixa.append(tabela);
  return caixa;
}

function criarResumo(resumo) {
  const grade = novoEl('div', 'resumo');
  const porStatus = resumo.por_status || {};
  Object.entries(ROTULOS_TAREFA).forEach(([status, rotulo]) => {
    const cartao = novoEl('div', `resumo-cartao resumo-${status}`);
    cartao.append(novoEl('strong', null, porStatus[status] ?? 0), novoEl('span', null, rotulo));
    grade.append(cartao);
  });
  const fila = novoEl('div', 'resumo-cartao resumo-fila');
  fila.append(novoEl('strong', null, resumo.fila_anthropic ?? 0), novoEl('span', null, 'Na fila'));
  grade.append(fila);
  return grade;
}

function criarCredito(anthropic) {
  const caixa = novoEl('section', 'credito');
  caixa.append(novoEl('h3', null, 'Crédito Anthropic (mês)'));
  if (!anthropic) {
    caixa.append(novoEl('p', 'credito-legenda', 'Sem dados de consumo.'));
    return caixa;
  }
  const { gasto_mes_usd: gasto = 0, credito_mensal_usd: credito = 0, liberado_ate_hoje_usd: liberado = 0 } = anthropic;
  const pct = (v) => (credito > 0 ? Math.min(100, Math.max(0, (v / credito) * 100)) : 0);

  const valores = novoEl('p', 'credito-valores');
  valores.append(novoEl('strong', null, moedaUsd(gasto, 4)), document.createTextNode(` de ${moedaUsd(credito)}`));

  const barra = novoEl('div', 'credito-barra');
  barra.setAttribute('role', 'progressbar');
  barra.setAttribute('aria-label', 'Crédito Anthropic usado no mês');
  barra.setAttribute('aria-valuemin', '0');
  barra.setAttribute('aria-valuemax', String(credito));
  barra.setAttribute('aria-valuenow', String(gasto));
  const uso = novoEl('div', 'credito-uso');
  uso.style.width = `${pct(gasto)}%`;
  if (anthropic.pausado || gasto >= liberado) uso.classList.add('no-limite');
  const marcador = novoEl('div', 'credito-marcador');
  marcador.style.left = `${pct(liberado)}%`;
  marcador.title = `Liberado até hoje: ${moedaUsd(liberado)}`;
  barra.append(uso, marcador);

  const legenda = novoEl('p', 'credito-legenda');
  legenda.append(novoEl('i', 'credito-ponto', ''), document.createTextNode(`Liberado até hoje (ritmo diário): ${moedaUsd(liberado)}`));
  caixa.append(valores, barra, legenda);

  if (anthropic.pausado) {
    caixa.append(novoEl('p', 'credito-pausado', 'Ritmo diário do Claude atingido — a fila segue com os modelos gratuitos e o local'));
  }
  return caixa;
}

function criarListaTarefas(tarefas) {
  const secao = novoEl('section', 'tarefas');
  secao.append(novoEl('h3', null, 'Tarefas recentes'));
  if (!tarefas.length) {
    const vazio = novoEl('div', 'tarefas-vazio');
    vazio.append(novoEl('strong', null, 'Nenhuma tarefa por aqui ainda.'), novoEl('span', null, 'Envie uma tarefa a um agente e ela aparece nesta fila.'));
    secao.append(vazio);
    return secao;
  }

  const tabela = novoEl('table', 'tabela-tarefas');
  const cabecalho = novoEl('tr');
  ['Agente', 'Tarefa', 'Dificuldade', 'Status', 'Modelo', 'Tempo', 'Custo', 'Quando'].forEach((t) =>
    cabecalho.append(novoEl('th', null, t)),
  );
  const thead = novoEl('thead');
  thead.append(cabecalho);
  const tbody = novoEl('tbody');
  tarefas.forEach((t) => tbody.append(criarLinhaTarefa(t)));
  tabela.append(thead, tbody);
  secao.append(tabela);
  return secao;
}

function celula(rotulo, classe, conteudo) {
  const td = novoEl('td', classe);
  td.dataset.rotulo = rotulo;
  if (conteudo instanceof Node) td.append(conteudo);
  else td.textContent = conteudo ?? '';
  return td;
}

function criarLinhaTarefa(t) {
  const tr = novoEl('tr');

  const agente = novoEl('div');
  agente.append(novoEl('strong', null, t.agente_nome || t.agente || '—'));
  if (ANDARES[t.andar]) agente.append(novoEl('small', null, ANDARES[t.andar].nome));

  const texto = novoEl('div');
  texto.append(novoEl('span', 'tarefa-texto', t.texto || ''));
  if (t.motivo) texto.append(novoEl('small', 'tarefa-motivo', t.motivo));

  const dif = t.dificuldade
    ? novoEl('span', `selo selo-${t.dificuldade}`, ROTULOS_DIFICULDADE[t.dificuldade] || t.dificuldade)
    : '—';
  const status = novoEl('span', `estado estado-${t.status}`, ROTULOS_TAREFA[t.status] || t.status);
  const modelo = novoEl('span', 'tarefa-modelo', abreviarModelo(t.modelo) || '—');
  if (t.modelo) modelo.title = t.modelo;
  const quando = novoEl('time', null, formatarQuando(t.criada_em));
  if (t.criada_em) {
    quando.dateTime = t.criada_em;
    quando.title = new Date(t.criada_em).toLocaleString('pt-BR');
  }

  tr.append(
    celula('Agente', 'col-agente', agente),
    celula('Tarefa', 'col-texto', texto),
    celula('Dificuldade', null, dif),
    celula('Status', null, status),
    celula('Modelo', t.modelo ? null : 'vazia', modelo),
    celula('Tempo', t.tempo_segundos != null ? null : 'vazia', t.tempo_segundos != null ? formatarTempo(t.tempo_segundos) : '—'),
    celula('Custo', t.custo_usd > 0 ? null : 'vazia', t.custo_usd > 0 ? moedaUsd(t.custo_usd, 4) : '—'),
    celula('Quando', null, quando),
  );
  return tr;
}

// ---------- Toasts ----------
// `titulo` é opcional (padrão: "Nova resposta de <agente>").
function mostrarToast(andar, agente, texto, titulo) {
  const nome = dadosAgente(andar, agente).nome;
  const toast = novoEl('button', 'toast');
  toast.type = 'button';
  toast.append(novoEl('strong', null, titulo || `Nova resposta de ${nome}`));
  if (texto) toast.append(novoEl('span', null, texto.length > 80 ? `${texto.slice(0, 80)}…` : texto));
  toast.addEventListener('click', () => {
    removerToast(toast);
    abrirAgente(andar, agente);
  });
  toasts.append(toast);
  while (toasts.childElementCount > MAX_TOASTS) toasts.firstElementChild.remove();
  setTimeout(() => removerToast(toast), DURACAO_TOAST);
}

function removerToast(toast) {
  if (!toast.isConnected) return;
  toast.classList.add('saindo');
  setTimeout(() => toast.remove(), 200);
}

function limparToasts() {
  toasts.replaceChildren();
}

// Uma tarefa mudou: atualiza o painel se estiver visível.
function avisarPainel() {
  if (painelAberto) carregarTarefas();
}

document.getElementById('painel-fechar').addEventListener('click', fecharPainel);
painel.addEventListener('click', (e) => {
  if (e.target === painel) fecharPainel();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && painelAberto) fecharPainel();
});
