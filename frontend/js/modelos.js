// Tela "Modelos de IA" (diretoria): uso das LLMs no período — resumo, cada modelo, cada agente, falhas recentes,
// plano Max e chamadas por dia. Dados de /api/modelos/uso; atualiza a cada 30 s enquanto aberta.

const INTERVALO_MODELOS = 30000;
const PERIODOS_MODELOS = [[1, 'Hoje'], [7, '7 dias'], [30, '30 dias']];
const ROTULOS_STATUS_MODELO = { ativo: 'Ativo', pausa: 'Em pausa', afastado: 'Afastado' };
const janelaModelos = document.getElementById('modelos');
const modelosConteudo = document.getElementById('modelos-conteudo');
let modelosAbertos = false;
let periodoModelos = 7;
let timerModelos = null;

function abrirModelos() {
  if (!sessao || sessao.role !== 'diretoria') return;
  modelosAbertos = true;
  janelaModelos.classList.add('aberto');
  if (!modelosConteudo.childElementCount) modelosConteudo.append(novoEl('p', 'painel-aviso', 'Carregando...'));
  carregarModelos();
  clearInterval(timerModelos);
  timerModelos = setInterval(carregarModelos, INTERVALO_MODELOS);
  document.getElementById('modelos-fechar').focus();
}

function fecharModelos() {
  if (!modelosAbertos) return;
  modelosAbertos = false;
  clearInterval(timerModelos);
  janelaModelos.classList.remove('aberto');
}

function limparModelos() {
  fecharModelos();
  modelosConteudo.replaceChildren();
}

// O ícone da barra só aparece para a diretoria.
function configurarModelos() {
  document.getElementById('abrir-modelos').hidden = sessao?.role !== 'diretoria';
}

async function carregarModelos() {
  if (!modelosAbertos || !sessao) return;
  try {
    const resposta = await fetch(`/api/modelos/uso?dias=${periodoModelos}`, {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    if (!resposta.ok) throw new Error(resposta.status);
    renderizarModelos(await resposta.json());
  } catch {
    modelosConteudo.replaceChildren(novoEl('p', 'painel-aviso', 'Não foi possível carregar o uso dos modelos.'));
  }
}

// ---------- Formatação ----------
const nomeModelo = (m) => (m === 'claude-code/max' ? 'Claude Code (Max)' : String(m || '').split('/').pop().replace(':free', ' (grátis)'));
const segundosLegiveis = (s) => (s == null ? '—' : s >= 90 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`);
const dolarModelos = (v) => `US$ ${Number(v || 0).toFixed(2)}`;
const porcentoModelos = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);

function cartaoModelos(valor, rotulo, classe = '') {
  const el = novoEl('div', `modelos-cartao ${classe}`);
  el.append(novoEl('strong', null, String(valor)), novoEl('span', null, rotulo));
  return el;
}

function secaoModelos(titulo, ...filhos) {
  const el = novoEl('section', 'modelos-secao');
  el.append(novoEl('h3', null, titulo), ...filhos.filter(Boolean));
  return el;
}

function tabelaModelos(cabecalhos, linhas) {
  const t = novoEl('table', 'modelos-tabela');
  const cab = novoEl('tr');
  cabecalhos.forEach((c) => cab.append(novoEl('th', null, c)));
  t.append(cab, ...linhas);
  return t;
}

function celulaModelos(conteudo) {
  const td = novoEl('td');
  td.append(conteudo);
  return td;
}

// ---------- Renderização ----------
function renderizarModelos(dados) {
  const filtros = novoEl('div', 'equipe-filtros modelos-periodos');
  PERIODOS_MODELOS.forEach(([dias, rotulo]) => {
    const b = novoEl('button', 'equipe-filtro', rotulo);
    b.type = 'button';
    b.setAttribute('aria-selected', String(dias === periodoModelos));
    b.addEventListener('click', () => { periodoModelos = dias; carregarModelos(); });
    filtros.append(b);
  });
  document.getElementById('modelos-resumo').textContent =
    `Últimos ${dados.dias === 1 ? 'dia' : `${dados.dias} dias`} · atualiza a cada 30 s`;
  modelosConteudo.replaceChildren(filtros, criarResumoModelos(dados.resumo), criarGraficoDias(dados.por_dia),
    criarTabelaModelos(dados.modelos), criarMax(dados.max), criarAgentes(dados.agentes),
    criarFalhasRecentes(dados.falhas_recentes));
}

function criarResumoModelos(r) {
  const grade = novoEl('div', 'modelos-resumo');
  grade.append(
    cartaoModelos(r.chamadas, 'Chamadas'),
    cartaoModelos(porcentoModelos(r.taxa_sucesso), 'Sucesso', 'modelos-ok'),
    cartaoModelos(r.falhas, 'Falhas', r.falhas ? 'modelos-ruim' : ''),
    cartaoModelos(dolarModelos(r.custo_periodo_usd), 'Custo da API no período'),
    cartaoModelos(`${dolarModelos(r.custo_mes_usd)} / ${dolarModelos(r.credito_utilizavel_usd)}`, 'API no mês / orçamento'),
  );
  return grade;
}

function criarGraficoDias(serie = []) {
  const maior = Math.max(1, ...serie.map((d) => d.sucessos + d.falhas));
  const grafico = novoEl('div', 'modelos-grafico');
  grafico.setAttribute('role', 'img');
  grafico.setAttribute('aria-label', 'Chamadas por dia: sucessos e falhas');
  serie.forEach((d) => {
    const coluna = novoEl('div', 'modelos-coluna');
    const dia = new Date(`${d.dia}T12:00:00Z`);
    coluna.title = `${dia.toLocaleDateString('pt-BR')}: ${d.sucessos} sucesso(s), ${d.falhas} falha(s)`;
    const pilha = novoEl('div', 'modelos-pilha');
    const falha = novoEl('i', 'modelos-barra-falha');
    falha.style.height = `${(d.falhas / maior) * 100}%`;
    const ok = novoEl('i', 'modelos-barra-ok');
    ok.style.height = `${(d.sucessos / maior) * 100}%`;
    pilha.append(falha, ok);
    coluna.append(pilha, novoEl('small', null, dia.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })));
    grafico.append(coluna);
  });
  const legenda = novoEl('p', 'modelos-legenda');
  legenda.append(novoEl('i', 'modelos-ponto-ok'), ' sucessos  ', novoEl('i', 'modelos-ponto-falha'), ' falhas');
  return secaoModelos('Chamadas por dia', grafico, legenda);
}

function criarTabelaModelos(modelos = []) {
  if (!modelos.length) return secaoModelos('Modelos', novoEl('p', 'painel-aviso', 'Nenhuma chamada no período.'));
  const linhas = modelos.map((m) => {
    const tr = novoEl('tr', m.taxa_falha >= 0.5 ? 'modelos-linha-ruim' : m.taxa_falha >= 0.2 ? 'modelos-linha-atencao' : null);
    const status = novoEl('span', `modelos-status status-modelo-${m.status}`, ROTULOS_STATUS_MODELO[m.status] || m.status);
    if (m.volta_em) status.title = `${m.motivo} · volta em ${new Date(m.volta_em).toLocaleString('pt-BR')}`;
    tr.append(novoEl('td', null, nomeModelo(m.modelo)), celulaModelos(status), novoEl('td', null, String(m.tentativas)),
      novoEl('td', null, String(m.sucessos)), novoEl('td', null, String(m.falhas)), novoEl('td', null, porcentoModelos(m.taxa_falha)),
      novoEl('td', null, segundosLegiveis(m.tempo_medio_s)), novoEl('td', null, m.custo_usd ? dolarModelos(m.custo_usd) : '—'));
    return tr;
  });
  return secaoModelos('Modelos', tabelaModelos(['Modelo', 'Status', 'Chamadas', 'Sucessos', 'Falhas', 'Taxa de falha', 'Tempo médio', 'Custo'], linhas));
}

function criarMax(max) {
  if (!max) return null;
  const grade = novoEl('div', 'modelos-resumo');
  grade.append(
    cartaoModelos(max.textos.total, `Textos pelo Max · ${segundosLegiveis(max.textos.tempo_medio_s)} em média`),
    cartaoModelos(max.producoes.total, `Produções (PNG/MP4) · ${segundosLegiveis(max.producoes.tempo_medio_s)} em média`),
    cartaoModelos(max.textos.falhas + max.producoes.falhas, 'Falhas no Max', max.textos.falhas + max.producoes.falhas ? 'modelos-ruim' : ''),
  );
  return secaoModelos('Plano Max (Claude Code)', grade);
}

function criarAgentes(agentes = []) {
  if (!agentes.length) return null;
  const linhas = agentes.map((a) => {
    const principais = a.modelos.slice(0, 3).map((m) => `${nomeModelo(m.modelo)} (${m.tentativas}${m.falhas ? `, ${m.falhas} falha${m.falhas > 1 ? 's' : ''}` : ''})`).join(' · ');
    const tr = novoEl('tr');
    tr.append(novoEl('td', null, a.nome), novoEl('td', null, String(a.tentativas)), novoEl('td', null, String(a.falhas)),
      novoEl('td', null, a.custo_usd ? dolarModelos(a.custo_usd) : '—'), novoEl('td', 'modelos-texto', principais));
    return tr;
  });
  return secaoModelos('Uso por agente', tabelaModelos(['Agente', 'Chamadas', 'Falhas', 'Custo API', 'Modelos mais usados'], linhas));
}

function criarFalhasRecentes(falhas = []) {
  if (!falhas.length) return secaoModelos('Falhas recentes', novoEl('p', 'painel-aviso', 'Nenhuma falha no período. 🎉'));
  const linhas = falhas.map((f) => {
    const tr = novoEl('tr');
    tr.title = f.detalhe;
    tr.append(novoEl('td', null, new Date(f.em).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })),
      novoEl('td', null, nomeModelo(f.modelo)), novoEl('td', null, f.agente), novoEl('td', 'modelos-texto', f.motivo));
    return tr;
  });
  return secaoModelos('Falhas recentes', tabelaModelos(['Quando', 'Modelo', 'Agente', 'Motivo'], linhas));
}

document.getElementById('abrir-modelos').addEventListener('click', abrirModelos);
document.getElementById('modelos-fechar').addEventListener('click', fecharModelos);
janelaModelos.addEventListener('click', (e) => { if (e.target === janelaModelos) fecharModelos(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modelosAbertos) fecharModelos(); });
