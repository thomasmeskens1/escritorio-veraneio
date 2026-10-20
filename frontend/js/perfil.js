// Ficha do agente (descrição, exemplo, tarefas, aprendizado, treino) e janela da Diretora.

const AVISO_PRODUCAO = 'A produção de imagens e vídeos é exclusiva da conta do Thomas. Fale com ele para solicitar.';

const perfis = {}; // 'andar/agente' -> resposta de GET /api/agentes/{andar}/{id}
const errosPerfil = {}; // 'andar/agente' -> mensagem de erro do último carregamento
let perfilExpandido = !window.matchMedia('(max-width: 640px)').matches;
let resultadoTreino = null; // { chave, texto, erro }
let treinando = false;
let diretoraAberta = null; // { andar, agente }
const rotinas = {}; // 'andar/agente' -> lista de GET /api/agendamentos (só as ativas)
const errosRotinas = {};
const cancelandoRotinas = new Set(); // ids com DELETE em andamento
const DICA_ROTINA = 'Para agendar, escreva por exemplo: "Analise as campanhas todos os dias às 08:00".';

const modalPerfil = document.getElementById('modal-perfil');
const modalRestrito = document.getElementById('modal-restrito');
const janelaDiretora = document.getElementById('diretora');
const diretoraConteudo = document.getElementById('diretora-conteudo');

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
  resultadoTreino = null;
}

// ---------- Ficha no popup do agente ----------
async function carregarPerfil(andar, agente) {
  const k = chave(andar, agente);
  delete errosPerfil[k];
  renderizarPerfil();
  carregarRotinas(andar, agente);
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

  if (!dados) {
    const texto = errosPerfil[k] || 'Carregando informações...';
    modalPerfil.replaceChildren(novoEl('p', `perfil-carregando${errosPerfil[k] ? ' erro' : ''}`, texto));
    return;
  }

  const corpo = novoEl('div', 'perfil-corpo');
  corpo.id = 'perfil-corpo';
  corpo.hidden = !perfilExpandido;
  if (dados.descricao) corpo.append(novoEl('p', 'perfil-descricao', dados.descricao));
  if (dados.exemplo) corpo.append(criarExemplo(dados.exemplo));
  corpo.append(criarFatos(dados));
  if (dados.tipo === 'ia') corpo.append(criarRotinas(chatAberto.andar, chatAberto.agente));
  const ajustes = dados.aprendizado?.ajustes;
  if (Array.isArray(ajustes) && ajustes.length) corpo.append(criarAjustesAgente(ajustes));
  if (dados.pode_treinar) corpo.append(criarTreino(k));

  modalPerfil.replaceChildren(criarAlternador(dados), corpo);
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

function criarTreino(k) {
  const bloco = novoEl('div', 'perfil-treino');
  const botao = novoEl('button', 'botao-secundario', treinando ? 'Treinando...' : 'Treinar agora');
  botao.type = 'button';
  botao.disabled = treinando;
  botao.addEventListener('click', treinarAgora);
  bloco.append(botao);
  if (resultadoTreino?.chave === k) {
    const resultado = novoEl('p', `perfil-treino-resultado${resultadoTreino.erro ? ' erro' : ''}`, resultadoTreino.texto);
    resultado.setAttribute('role', 'status');
    bloco.append(resultado);
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
    else resultadoTreino = { chave: k, erro: false, texto: textoTreino(dados) };
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

// ---------- Janela da Diretora (só leitura) ----------
function formatarTamanho(kb) {
  const n = Number(kb) || 0;
  if (n >= 1024) return `${(n / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`;
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} KB`;
}

function atualizarCabecalhoDiretora() {
  if (!diretoraAberta) return;
  const dados = dadosAgente(diretoraAberta.andar, diretoraAberta.agente);
  document.getElementById('diretora-nome').textContent = dados.nome;
  document.getElementById('diretora-funcao').textContent = dados.funcao || 'Conhecimento da empresa';
  const status = document.getElementById('diretora-status');
  status.className = `status status-${dados.status}`;
  status.title = ROTULOS_STATUS[dados.status] || '';
}

function renderizarDiretora(dados, erro) {
  if (erro || !dados) {
    diretoraConteudo.replaceChildren(novoEl('p', `perfil-carregando${erro ? ' erro' : ''}`, erro || 'Carregando informações...'));
    return;
  }
  const info = dados.diretora || {};
  const documentos = Array.isArray(info.documentos) ? info.documentos : [];
  const blocos = [];
  if (dados.descricao) blocos.push(novoEl('p', 'perfil-descricao', dados.descricao));

  const numeros = novoEl('div', 'resumo');
  [[documentos.length, documentos.length === 1 ? 'Documento' : 'Documentos'], [info.consultas ?? 0, 'Consultas']].forEach(([n, rotulo]) => {
    const cartao = novoEl('div', 'resumo-cartao resumo-fila');
    cartao.append(novoEl('strong', null, n), novoEl('span', null, rotulo));
    numeros.append(cartao);
  });
  blocos.push(numeros);

  const secao = novoEl('section', 'diretora-documentos');
  secao.append(novoEl('h3', null, 'Documentos que ela guarda'));
  if (!documentos.length) {
    secao.append(novoEl('p', 'aprendizado-nota', 'Nenhum documento cadastrado ainda.'));
  } else {
    const lista = novoEl('ul');
    documentos.forEach((d) => {
      const item = novoEl('li');
      item.append(novoEl('span', 'doc-nome', d.nome || '—'), novoEl('span', 'doc-tamanho', formatarTamanho(d.tamanho_kb)));
      lista.append(item);
    });
    secao.append(lista);
  }
  blocos.push(secao, novoEl('p', 'diretora-nota', 'Ela é consultada apenas pelos agentes.'));
  diretoraConteudo.replaceChildren(...blocos);
}

async function abrirDiretora(andar, agente) {
  if (typeof fecharChat === 'function') fecharChat();
  fecharPainel();
  diretoraAberta = { andar, agente };
  atualizarCabecalhoDiretora();
  const k = chave(andar, agente);
  renderizarDiretora(perfis[k]);
  janelaDiretora.classList.add('aberto');
  document.getElementById('diretora-fechar').focus();
  try {
    const dados = await buscarAgente(andar, agente);
    if (!dados) return;
    perfis[k] = dados;
    if (diretoraAberta?.agente === agente) renderizarDiretora(dados);
  } catch (erro) {
    if (diretoraAberta?.agente === agente && !perfis[k]) {
      renderizarDiretora(null, erro instanceof ErroApi ? erro.message : 'Servidor indisponível.');
    }
  }
}

function fecharDiretora() {
  diretoraAberta = null;
  janelaDiretora.classList.remove('aberto');
}

document.getElementById('diretora-fechar').addEventListener('click', fecharDiretora);
janelaDiretora.addEventListener('click', (e) => {
  if (e.target === janelaDiretora) fecharDiretora();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && diretoraAberta) fecharDiretora();
});
