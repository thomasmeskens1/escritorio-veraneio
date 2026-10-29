// Ficha do agente (descrição, exemplo, tarefas, aprendizado, rotinas, treino) e, no popup
// do Cérebro, a seção "Conhecimento" (GET /api/cerebro/estatisticas).

const AVISO_PRODUCAO = 'A produção de imagens e vídeos é exclusiva da conta do Thomas. Fale com ele para solicitar.';

const perfis = {}; // 'andar/agente' -> resposta de GET /api/agentes/{andar}/{id}
const errosPerfil = {}; // 'andar/agente' -> mensagem de erro do último carregamento
let perfilExpandido = !window.matchMedia('(max-width: 640px)').matches;
let resultadoTreino = null; // { chave, texto, erro }
let treinando = false;
const rotinas = {}; // 'andar/agente' -> lista de GET /api/agendamentos (só as ativas)
const errosRotinas = {};
const cancelandoRotinas = new Set(); // ids com DELETE em andamento
const DICA_ROTINA = 'Nenhuma rotina. Para agendar, use o botão "Agendar tarefa" abaixo.';

const modalPerfil = document.getElementById('modal-perfil');
const modalRestrito = document.getElementById('modal-restrito');

// ---------- API ----------
class ErroApi extends Error {}

async function buscarAgente(andar, id) {
  const resposta = await fetch(`/api/agentes/${encodeURIComponent(andar)}/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${sessao.token}` },
  });
  if (resposta.status === 401) {
    encerrarSessao('Sessão expirada. Entre novamente.');
    return null;
  }
  if (resposta.status === 404) throw new ErroApi('Agente não encontrado.');
  if (!resposta.ok) throw new ErroApi('Não foi possível carregar as informações do agente.');
  return resposta.json();
}

const producaoRestrita = (andar, agente) => !!perfis[chave(andar, agente)]?.producao_restrita;

function limparPerfis() {
  Object.keys(perfis).forEach((k) => delete perfis[k]);
  Object.keys(errosPerfil).forEach((k) => delete errosPerfil[k]);
  Object.keys(rotinas).forEach((k) => delete rotinas[k]);
  Object.keys(errosRotinas).forEach((k) => delete errosRotinas[k]);
  Object.assign(conhecimento, { dados: null, erro: '', oculto: false });
  resultadoTreino = null;
}

// ---------- Ficha no popup do agente ----------
async function carregarPerfil(andar, agente) {
  const k = chave(andar, agente);
  delete errosPerfil[k];
  renderizarPerfil();
  carregarRotinas(andar, agente);
  if (ehCerebro(andar, agente)) {
    carregarConhecimento(andar, agente);
    carregarCorrecoes(andar, agente); // correções do Thomas para virar regra (js/correcoes.js)
  }
  try {
    const dados = await buscarAgente(andar, agente);
    if (!dados) return;
    perfis[k] = dados;
  } catch (erro) {
    if (!(erro instanceof ErroApi)) console.warn('Falha ao carregar agente:', erro);
    errosPerfil[k] = erro instanceof ErroApi ? erro.message : 'Servidor indisponível.';
  }
  if (chatEstaAberto(andar, agente)) {
    renderizarPerfil();
    atualizarChat();
  }
}

function renderizarPerfil() {
  if (!chatAberto) return;
  const k = chave(chatAberto.andar, chatAberto.agente);
  const dados = perfis[k];
  modalRestrito.hidden = !dados?.producao_restrita;
  modalRestrito.textContent = AVISO_PRODUCAO;
  // Cérebro: janela larga e sem chat (só a ficha, em duas colunas).
  const janelaAgente = modalPerfil.closest('.janela-agente');
  janelaAgente?.classList.toggle('janela-larga', ehCerebro(chatAberto.andar, chatAberto.agente));
  janelaAgente?.classList.toggle('sem-chat', ehCerebro(chatAberto.andar, chatAberto.agente));

  if (!dados) {
    const texto = errosPerfil[k] || 'Carregando informações...';
    modalPerfil.replaceChildren(novoEl('p', `perfil-carregando${errosPerfil[k] ? ' erro' : ''}`, texto));
    return;
  }

  const corpo = novoEl('div', 'perfil-corpo');
  corpo.id = 'perfil-corpo';
  const cerebroAberto = ehCerebro(chatAberto.andar, chatAberto.agente);
  corpo.hidden = !perfilExpandido && !cerebroAberto; // o Cérebro não tem chat: a ficha fica sempre aberta
  const ajustes = dados.aprendizado?.ajustes;
  if (cerebroAberto) {
    // Cérebro (Thomas, 29/10/2026): sem chat, ficha em duas colunas. Esquerda: descrição, números, correções;
    // direita: Conhecimento, Rotinas agendadas logo abaixo e o campo de ensinar. "Educação das empresas" saiu
    // (as entrevistas das três empresas estão completas).
    const esquerda = novoEl('div', 'perfil-coluna');
    const direita = novoEl('div', 'perfil-coluna');
    if (dados.descricao) esquerda.append(novoEl('p', 'perfil-descricao', dados.descricao));
    esquerda.append(criarFatos(dados));
    if (!correcoes.oculto) esquerda.append(criarCorrecoes());
    if (Array.isArray(ajustes) && ajustes.length) esquerda.append(criarAjustesAgente(ajustes));
    if (dados.tipo === 'ia' || dados.pode_treinar) esquerda.append(criarTreino(k, dados));
    if (!conhecimento.oculto) direita.append(criarConhecimento());
    if (dados.tipo === 'ia') direita.append(criarRotinas(chatAberto.andar, chatAberto.agente));
    corpo.classList.add('perfil-colunas');
    corpo.append(esquerda, direita);
  } else {
    if (dados.descricao) corpo.append(novoEl('p', 'perfil-descricao', dados.descricao));
    if (dados.exemplo) corpo.append(criarExemplo(dados.exemplo));
    corpo.append(criarFatos(dados));
    if (dados.tipo === 'ia') corpo.append(criarRotinas(chatAberto.andar, chatAberto.agente));
    if (Array.isArray(ajustes) && ajustes.length) corpo.append(criarAjustesAgente(ajustes));
    if (dados.tipo === 'ia' || dados.pode_treinar) corpo.append(criarTreino(k, dados));
  }

  modalPerfil.replaceChildren(...(cerebroAberto ? [] : [criarAlternador(dados)]), corpo);
}

function criarAlternador(dados) {
  const botao = novoEl('button', 'perfil-alternar');
  botao.type = 'button';
  botao.setAttribute('aria-expanded', String(perfilExpandido));
  botao.setAttribute('aria-controls', 'perfil-corpo');
  const resumo = [`${dados.tarefas_concluidas ?? 0} resolvidas`];
  const proximo = dados.aprendizado?.proximo_treino_em;
  if (proximo != null) resumo.push(`próximo aprendizado em ${proximo}`);
  const nRotinas = rotinas[chave(chatAberto.andar, chatAberto.agente)]?.length;
  if (nRotinas) resumo.push(plural(nRotinas, 'rotina', 'rotinas'));
  botao.append(
    novoEl('span', 'perfil-alternar-titulo', 'Sobre o agente'),
    novoEl('small', 'perfil-alternar-resumo', resumo.join(' · ')),
    novoEl('span', 'seta'),
  );
  botao.addEventListener('click', () => {
    perfilExpandido = !perfilExpandido;
    renderizarPerfil();
    modalPerfil.querySelector('.perfil-alternar')?.focus();
  });
  return botao;
}

// Clicar no exemplo preenche o campo da tarefa.
function criarExemplo(exemplo) {
  const botao = novoEl('button', 'perfil-exemplo');
  botao.type = 'button';
  botao.title = 'Usar este exemplo';
  botao.append(novoEl('small', null, 'Exemplo de pedido'), novoEl('span', null, `“${exemplo}”`));
  botao.addEventListener('click', () => {
    if (modalInput.disabled) return;
    modalInput.value = exemplo;
    ajustarAlturaInput();
    modalInput.focus();
  });
  return botao;
}

function criarFatos(dados) {
  const lista = novoEl('ul', 'perfil-fatos');
  const resolvidas = novoEl('li');
  resolvidas.append(document.createTextNode('Tarefas resolvidas: '), novoEl('strong', null, dados.tarefas_concluidas ?? 0));
  if (dados.tarefas_total != null) resolvidas.append(document.createTextNode(` de ${dados.tarefas_total}`));
  lista.append(resolvidas);

  const ap = dados.aprendizado || {};
  const proximo = novoEl('li');
  if (ap.proximo_treino_em != null) {
    const n = ap.proximo_treino_em;
    proximo.append(document.createTextNode(n === 1 ? 'Falta ' : 'Faltam '), novoEl('strong', null, n),
      document.createTextNode(` ${n === 1 ? 'tarefa' : 'tarefas'} para o próximo aprendizado`));
  } else {
    proximo.textContent = 'Todos os aprendizados programados já foram feitos';
  }
  if (ap.modelo_ativo != null) {
    proximo.append(novoEl('span', `selo-modelo ${ap.modelo_ativo ? 'ativo' : 'inativo'}`, ap.modelo_ativo ? 'Modelo ativo' : 'Regras fixas'));
  }
  lista.append(proximo);
  return lista;
}

function criarAjustesAgente(ajustes) {
  const bloco = novoEl('div', 'perfil-ajustes');
  bloco.append(novoEl('h4', null, 'Ajustes automáticos'));
  const lista = novoEl('ul');
  ajustes.forEach((a) => {
    const item = novoEl('li');
    const linha = novoEl('div', 'ajuste-linha');
    linha.append(seloDificuldade(a.de), novoEl('span', 'ajuste-seta', '→'), seloDificuldade(a.para));
    item.append(linha);
    if (a.motivo) item.append(novoEl('small', null, a.motivo));
    lista.append(item);
  });
  bloco.append(lista);
  return bloco;
}

// "Agendar tarefa" (todo agente de IA) e "Treinar agora" (diretoria), lado a lado.
function criarTreino(k, dados) {
  const bloco = novoEl('div', 'perfil-treino');
  if (dados.tipo === 'ia') {
    const agendar = novoEl('button', 'botao-secundario', 'Agendar tarefa');
    agendar.type = 'button';
    agendar.addEventListener('click', abrirAgendamento);
    bloco.append(agendar);
  }
  if (!dados.pode_treinar) return bloco;
  const botao = novoEl('button', 'botao-secundario', treinando ? 'Treinando...' : 'Treinar agora');
  botao.type = 'button';
  botao.disabled = treinando;
  botao.addEventListener('click', treinarAgora);
  bloco.append(botao);
  if (resultadoTreino?.chave === k) {
    const resultado = novoEl('p', `perfil-treino-resultado${resultadoTreino.erro ? ' erro' : ''}`, resultadoTreino.texto);
    resultado.setAttribute('role', 'status');
    bloco.append(resultado);
    if (resultadoTreino.relatorio) {
      const ver = novoEl('button', 'botao-secundario', 'Ver relatório');
      ver.type = 'button';
      ver.addEventListener('click', () => abrirRelatorioTreino(resultadoTreino.relatorio));
      bloco.append(ver);
    }
  }
  return bloco;
}

function textoTreino({ mensagem, modelo }) {
  const partes = [mensagem || 'Treino concluído.'];
  if (modelo) {
    partes.push(`${plural(modelo.amostras ?? 0, 'amostra', 'amostras')} · acurácia ${porcento(modelo.acuracia)} `
      + `(regras ${porcento(modelo.acuracia_regras)}) · ${modelo.ativo ? 'modelo ativo' : 'regras fixas mantidas'}`);
  }
  return partes.join('\n');
}

async function treinarAgora() {
  if (!chatAberto || treinando || !sessao) return;
  const { andar, agente } = chatAberto;
  const k = chave(andar, agente);
  treinando = true;
  renderizarPerfil();
  try {
    const resposta = await fetch('/api/aprendizado/treinar', {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    if (resposta.status === 401) {
      encerrarSessao('Sessão expirada. Entre novamente.');
      return;
    }
    const dados = await resposta.json().catch(() => ({}));
    if (resposta.status === 403) resultadoTreino = { chave: k, erro: true, texto: 'Apenas a diretoria pode treinar.' };
    else if (!resposta.ok) resultadoTreino = { chave: k, erro: true, texto: dados.mensagem || 'Não foi possível treinar agora.' };
    else {
      resultadoTreino = { chave: k, erro: false, texto: textoTreino(dados), relatorio: dados.relatorio };
      if (dados.relatorio) abrirRelatorioTreino(dados.relatorio); // o que foi aprendido e por quê
    }
  } catch {
    resultadoTreino = { chave: k, erro: true, texto: 'Servidor indisponível. Tente novamente.' };
  } finally {
    treinando = false;
  }
  if (chatEstaAberto(andar, agente)) carregarPerfil(andar, agente); // números novos após o treino
}

// ---------- Rotinas agendadas ----------
async function carregarRotinas(andar, agente) {
  if (!sessao) return;
  const k = chave(andar, agente);
  try {
    const params = new URLSearchParams({ andar, agente });
    const resposta = await fetch(`/api/agendamentos?${params}`, { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.status === 401) return encerrarSessao('Sessão expirada. Entre novamente.');
    if (!resposta.ok) throw new ErroApi('Não foi possível carregar as rotinas.');
    const dados = await resposta.json();
    rotinas[k] = Array.isArray(dados.agendamentos) ? dados.agendamentos : [];
    delete errosRotinas[k];
  } catch (erro) {
    errosRotinas[k] = erro instanceof ErroApi ? erro.message : 'Servidor indisponível.';
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

// Chamada quando chega um aviso "Rotina agendada" (ou após cancelar).
function atualizarRotinas(andar, agente) {
  if (chatEstaAberto(andar, agente)) carregarRotinas(andar, agente);
  else delete rotinas[chave(andar, agente)]; // recarrega ao abrir
}

function formatarProxima(iso) {
  if (!iso) return 'sem próxima execução';
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return '—';
  const fuso = { timeZone: 'America/Sao_Paulo' };
  const dia = data.toLocaleDateString('pt-BR', { ...fuso, day: '2-digit', month: '2-digit' });
  const hora = data.toLocaleTimeString('pt-BR', { ...fuso, hour: '2-digit', minute: '2-digit' });
  return `próxima: ${dia} às ${hora}`;
}

function criarRotinas(andar, agente) {
  const k = chave(andar, agente);
  const bloco = novoEl('div', 'perfil-rotinas');
  bloco.append(novoEl('h4', null, 'Rotinas agendadas'));
  const lista = rotinas[k];
  if (!lista) {
    bloco.append(novoEl('p', `rotinas-nota${errosRotinas[k] ? ' erro' : ''}`, errosRotinas[k] || 'Carregando...'));
    return bloco;
  }
  if (!lista.length) {
    bloco.append(novoEl('p', 'rotinas-nota', DICA_ROTINA));
    return bloco;
  }
  const ul = novoEl('ul');
  lista.forEach((r) => {
    const item = novoEl('li');
    const info = novoEl('div', 'rotina-info');
    info.append(novoEl('strong', null, r.descricao), novoEl('span', 'rotina-tarefa', `“${r.tarefa}”`));
    const meta = [formatarProxima(r.proxima_execucao)];
    if (r.execucoes) meta.push(`${plural(r.execucoes, 'execução', 'execuções')}`);
    if (sessao?.role === 'diretoria') meta.push(`por ${r.usuario}`);
    info.append(novoEl('small', null, meta.join(' · ')));
    const cancelando = cancelandoRotinas.has(r.id);
    const botao = novoEl('button', 'botao-secundario rotina-cancelar', cancelando ? 'Cancelando...' : 'Cancelar');
    botao.type = 'button';
    botao.disabled = cancelando;
    botao.setAttribute('aria-label', `Cancelar a rotina: ${r.descricao}`);
    botao.addEventListener('click', () => cancelarRotina(andar, agente, r.id));
    item.append(info, botao);
    ul.append(item);
  });
  bloco.append(ul);
  if (errosRotinas[k]) bloco.append(novoEl('p', 'rotinas-nota erro', errosRotinas[k]));
  return bloco;
}

// O ÚNICO jeito de agendar (Thomas, 29/10/2026): mensagem no chat nunca vira rotina. O formulário aparece na
// conversa; a empresa é a do seletor do topo do chat.
const FREQUENCIAS_ROTINA = ['Uma vez', 'Todos os dias', 'De segunda a sexta', 'Fins de semana', 'Toda semana',
  'Todo mês', 'A cada X horas'];

function abrirAgendamento() {
  if (!chatAberto || !sessao) return;
  const { andar, agente } = chatAberto;
  abrirFormularioPopup({
    titulo: 'Agendar tarefa', botao: 'Agendar',
    campos: [
      { nome: 'tarefa', rotulo: 'O que o agente deve fazer', tipo: 'texto_longo', obrigatorio: true },
      { nome: 'frequencia', rotulo: 'Frequência', tipo: 'opcoes', obrigatorio: true, opcoes: FREQUENCIAS_ROTINA },
      { nome: 'horario', rotulo: 'Horário (menos em "A cada X horas")', tipo: 'hora' },
      { nome: 'data', rotulo: 'Data (só em "Uma vez")', tipo: 'data' },
      { nome: 'dia_semana', rotulo: 'Dia da semana (só em "Toda semana")', tipo: 'opcoes',
        opcoes: ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'] },
      { nome: 'dia_mes', rotulo: 'Dia do mês (só em "Todo mês")', tipo: 'numero' },
      { nome: 'intervalo_horas', rotulo: 'De quantas em quantas horas (só em "A cada X horas")', tipo: 'numero' },
    ],
  }, (respostas) => agendarTarefa(andar, agente, respostas), `${dadosAgente(andar, agente).nome} vai executar no horário`);
}

async function agendarTarefa(andar, agente, respostas) {
  const corpo = {
    andar, agente, tarefa: respostas.tarefa, frequencia: respostas.frequencia, horario: respostas.horario,
    data: respostas.data, dia_semana: respostas.dia_semana, dia_mes: Number(respostas.dia_mes) || 0,
    intervalo_horas: Number(respostas.intervalo_horas) || 0, empresa: empresaDaConversa(andar, agente),
  };
  let texto;
  try {
    const resposta = await fetch('/api/agendamentos', {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
    });
    if (resposta.status === 401) return encerrarSessao('Sessão expirada. Entre novamente.');
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      const detalhe = Array.isArray(dados.detail) ? 'Confira os campos do formulário.' : dados.detail;
      texto = `Não agendei: ${detalhe || 'tente de novo'}. Clique em "Agendar tarefa" para corrigir.`;
    } else {
      texto = `Rotina agendada: ${dados.descricao} (${formatarProxima(dados.proxima_execucao)}).`;
      carregarRotinas(andar, agente);
    }
  } catch {
    texto = 'Servidor indisponível. Tente agendar de novo.';
  }
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema' });
}

async function cancelarRotina(andar, agente, id) {
  if (!sessao || cancelandoRotinas.has(id)) return;
  cancelandoRotinas.add(id);
  renderizarPerfil();
  let erro = '';
  try {
    const resposta = await fetch(`/api/agendamentos/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    if (resposta.status === 401) return encerrarSessao('Sessão expirada. Entre novamente.');
    if (resposta.status === 403) erro = 'Só quem criou a rotina (ou a diretoria) pode cancelá-la.';
    else if (!resposta.ok && resposta.status !== 404) erro = 'Não foi possível cancelar a rotina.';
  } catch {
    erro = 'Servidor indisponível.';
  } finally {
    cancelandoRotinas.delete(id);
  }
  await carregarRotinas(andar, agente);
  if (erro) {
    errosRotinas[chave(andar, agente)] = erro;
    if (chatEstaAberto(andar, agente)) renderizarPerfil();
  }
}

// ---------- Conhecimento do Cérebro ----------
const FONTES_CONHECIMENTO = { oficial: 'Oficial', ensinado: 'Ensinado', site: 'Site', drive: 'Drive', rede: 'Redes', dados: 'Painel', tarefa: 'Tarefas' };
const EMPRESAS_CONHECIMENTO = [['casa_veraneio', 'Veraneio'], ['cv_corporativo', 'Corporativo'], ['casa_vero', 'Vero'], ['*', 'Comum']];
const conhecimento = { dados: null, erro: '', oculto: false }; // estatísticas do RAG central

const ehCerebro = (andar, agente) => dadosAgente(andar, agente).visual === 'cerebro';
const numero = (n) => (Number(n) || 0).toLocaleString('pt-BR');

async function carregarConhecimento(andar, agente) {
  if (!sessao) return;
  try {
    const resposta = await fetch('/api/cerebro/estatisticas', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.status === 401) return encerrarSessao('Sessão expirada. Entre novamente.');
    if (resposta.status === 403 || resposta.status === 404) {
      Object.assign(conhecimento, { dados: null, erro: '', oculto: true });
    } else if (!resposta.ok) {
      Object.assign(conhecimento, { erro: 'Não foi possível carregar o conhecimento.', oculto: false });
    } else {
      Object.assign(conhecimento, { dados: await resposta.json(), erro: '', oculto: false });
    }
  } catch {
    Object.assign(conhecimento, { erro: 'Servidor indisponível.', oculto: false });
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

function criarConhecimento() {
  const bloco = novoEl('div', 'perfil-conhecimento');
  bloco.append(novoEl('h4', null, 'Conhecimento'));
  const d = conhecimento.dados;
  if (!d) {
    bloco.append(novoEl('p', `rotinas-nota${conhecimento.erro ? ' erro' : ''}`, conhecimento.erro || 'Carregando...'));
    return bloco;
  }
  const numeros = novoEl('div', 'conhecimento-numeros');
  [[d.total, 'itens'], [d.consultas_hoje, 'consultas hoje'], [d.consultas_total, 'consultas no total']].forEach(([n, rotulo]) => {
    const cartao = novoEl('div', 'conhecimento-cartao');
    cartao.append(novoEl('strong', null, numero(n)), novoEl('span', null, rotulo));
    numeros.append(cartao);
  });
  bloco.append(numeros);

  // Uma linha por empresa (os dados nunca se misturam); o detalhe por fonte aparece ao passar o mouse.
  const porEmpresa = d.por_empresa && typeof d.por_empresa === 'object' ? d.por_empresa : {};
  const maior = Math.max(1, ...EMPRESAS_CONHECIMENTO.map(([e]) => Number(porEmpresa[e]?.total) || 0));
  const lista = novoEl('ul', 'conhecimento-fontes');
  EMPRESAS_CONHECIMENTO.forEach(([empresa, rotulo]) => {
    const n = Number(porEmpresa[empresa]?.total) || 0;
    const item = novoEl('li', `empresa-${empresa === '*' ? 'comum' : empresa}`);
    const detalhe = Object.entries(porEmpresa[empresa]?.por_fonte || {})
      .map(([fonte, qtd]) => `${FONTES_CONHECIMENTO[fonte] || fonte}: ${numero(qtd)}`).join(' · ');
    item.title = detalhe || 'Ainda sem conhecimento';
    const barra = novoEl('span', 'fonte-barra');
    const cheio = novoEl('i');
    cheio.style.width = `${Math.round((n / maior) * 100)}%`;
    barra.append(cheio);
    item.append(novoEl('span', 'fonte-nome', rotulo), barra, novoEl('strong', null, numero(n)));
    lista.append(item);
  });
  bloco.append(lista);

  const meta = [];
  if (d.ultima_atualizacao) meta.push(`atualizado ${formatarQuando(d.ultima_atualizacao)}`);
  const emb = d.embeddings;
  if (emb && typeof emb === 'object') {
    const partes = [emb.modelo || 'embeddings'];
    if (emb.pendentes) partes.push(`${numero(emb.pendentes)} pendentes`);
    partes.push(emb.ollama_ok ? 'Ollama ok' : 'Ollama fora do ar');
    meta.push(partes.join(' · '));
  }
  if (meta.length) bloco.append(novoEl('small', 'conhecimento-meta', meta.join(' — ')));

  if (d.pode_ensinar) bloco.append(criarEnsino());
  return bloco;
}

// Ensinar o Cérebro sem o chat (só o Thomas): vale para a empresa do seletor do topo ("Todas" = regra comum).
let ensinoStatus = null; // { texto, erro }

function criarEnsino() {
  const caixa = novoEl('div', 'conhecimento-ensino');
  const campo = novoEl('textarea', 'form-entrada');
  campo.rows = 2;
  campo.placeholder = 'Ensinar o Cérebro (ex.: o check-in é às 15h)';
  campo.setAttribute('aria-label', 'Ensinar o Cérebro');
  const botao = novoEl('button', 'botao-secundario', 'Ensinar');
  botao.type = 'button';
  botao.addEventListener('click', () => {
    const texto = campo.value.trim();
    const empresa = empresaDaConversa('cobertura', 'cerebro');
    if (!texto) return;
    if (!empresa) {
      ensinoStatus = { texto: 'Escolha a empresa no seletor do topo (ou "Todas" para uma regra comum).', erro: true };
    } else if (enviar({ tipo: 'mensagem', andar: 'cobertura', agente: 'cerebro', texto: `Aprenda: ${texto}`, empresa })) {
      ensinoStatus = { texto: 'Ensinando…', erro: false };
    } else {
      ensinoStatus = { texto: 'Sem conexão com o servidor.', erro: true };
    }
    renderizarPerfil();
  });
  caixa.append(campo, botao);
  if (ensinoStatus) caixa.append(novoEl('p', `perfil-treino-resultado${ensinoStatus.erro ? ' erro' : ''}`, ensinoStatus.texto));
  return caixa;
}

// Resposta do Cérebro (o ensino ou um erro) aparece no campo de ensinar, já que ele não tem mais chat.
function aoRespostaCerebro(texto, erro = false) {
  ensinoStatus = { texto, erro };
  carregarConhecimento('cobertura', 'cerebro');
  if (chatEstaAberto('cobertura', 'cerebro')) renderizarPerfil();
}
