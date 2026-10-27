// Tela "Equipe": clicar num contador do topo mostra os agentes de cada andar com função, descrição e status.
// Função/descrição vêm de /api/equipe (uma vez por sessão); o status é o do WebSocket, ao vivo.

const ORDEM_ANDARES = ['marketing', 'comercial', 'cobertura', 'terreo', 'porao']; // Marketing primeiro: onde mais se trabalha
const FILTROS_EQUIPE = [['todos', 'Todos'], ['disponivel', 'Disponíveis'], ['trabalhando', 'Trabalhando'],
  ['construindo', 'Em construção'], ['dormindo', 'Pausados']];
const janelaEquipe = document.getElementById('equipe');
const equipeConteudo = document.getElementById('equipe-conteudo');
const equipeFiltros = document.getElementById('equipe-filtros');
let equipeAberta = false;
let filtroEquipe = 'todos';
let dadosEquipe = null; // { andar: [{id, nome, funcao, descricao, tipo}] }
let assinaturaEquipe = '';
let novosJaBuscados = '';

function abrirEquipe(status = 'todos') {
  if (!sessao) return;
  equipeAberta = true;
  filtroEquipe = status;
  janelaEquipe.classList.add('aberto');
  if (!dadosEquipe) {
    equipeConteudo.replaceChildren(novoEl('p', 'painel-aviso', 'Carregando a equipe...'));
    carregarEquipe();
  } else {
    renderizarEquipe(true);
  }
  document.getElementById('equipe-fechar').focus();
}

function fecharEquipe() {
  if (!equipeAberta) return;
  equipeAberta = false;
  janelaEquipe.classList.remove('aberto');
}

// Ao sair: a próxima sessão (talvez de outra role) busca a equipe de novo.
function limparEquipe() {
  fecharEquipe();
  dadosEquipe = null;
  assinaturaEquipe = '';
  novosJaBuscados = '';
  equipeConteudo.replaceChildren();
}

async function carregarEquipe() {
  try {
    const resposta = await fetch('/api/equipe', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (!resposta.ok) throw new Error(resposta.status);
    const { andares } = await resposta.json();
    dadosEquipe = Object.fromEntries(andares.map((a) => [a.andar, a.agentes]));
    renderizarEquipe(true);
  } catch {
    equipeConteudo.replaceChildren(novoEl('p', 'painel-aviso', 'Não foi possível carregar a equipe. Tente de novo.'));
  }
}

// Lista do andar: agentes do servidor (inclui os criados pelo Construtor) com o status ao vivo.
function agentesDoAndar(andar) {
  return (dadosEquipe[andar] || []).map((a) => ({ ...a, andar, status: dadosAgente(andar, a.id).status }));
}

function contarPorStatus(todos) {
  const contagem = { todos: todos.length };
  todos.forEach((a) => { contagem[a.status] = (contagem[a.status] || 0) + 1; });
  return contagem;
}

// `forcar`: redesenha mesmo sem mudança de status (troca de filtro, abertura).
function renderizarEquipe(forcar = false) {
  if (!equipeAberta || !dadosEquipe) return;
  // Agente novo (criado pelo Construtor) ainda fora da lista: busca a equipe de novo.
  const conhecidos = new Set(Object.values(dadosEquipe).flat().map((a) => a.id));
  const novos = Object.entries(estadoAgentes).filter(([n]) => podeAcessar(n))
    .flatMap(([, ags]) => Object.keys(ags || {})).filter((id) => !conhecidos.has(id)).join(',');
  if (novos && novos !== novosJaBuscados) { // uma busca por novidade (sem laço)
    novosJaBuscados = novos;
    carregarEquipe();
    return;
  }
  const andares = ORDEM_ANDARES.filter((n) => dadosEquipe[n] && podeAcessar(n));
  const todos = andares.flatMap(agentesDoAndar);
  const assinatura = `${filtroEquipe}|${todos.map((a) => `${a.id}:${a.status}`).join(',')}`;
  if (!forcar && assinatura === assinaturaEquipe) return;
  assinaturaEquipe = assinatura;

  const contagem = contarPorStatus(todos);
  document.getElementById('equipe-resumo').textContent =
    `${todos.length} agentes · ${contagem.trabalhando || 0} trabalhando agora`;
  equipeFiltros.replaceChildren(...FILTROS_EQUIPE.map(([valor, rotulo]) => {
    const botao = novoEl('button', `equipe-filtro filtro-${valor}`);
    botao.type = 'button';
    botao.setAttribute('role', 'tab');
    botao.setAttribute('aria-selected', String(valor === filtroEquipe));
    botao.append(novoEl('span', null, rotulo), novoEl('strong', null, String(contagem[valor] || 0)));
    botao.addEventListener('click', () => { filtroEquipe = valor; renderizarEquipe(true); });
    return botao;
  }));

  const secoes = andares.map((andar) => {
    const agentes = agentesDoAndar(andar).filter((a) => filtroEquipe === 'todos' || a.status === filtroEquipe);
    if (!agentes.length) return null;
    const secao = novoEl('section', 'equipe-andar');
    const grade = novoEl('div', 'equipe-grade');
    agentes.forEach((a) => grade.append(criarCartaoAgente(a)));
    secao.append(novoEl('h3', null, ANDARES[andar].nome), grade);
    return secao;
  }).filter(Boolean);
  equipeConteudo.replaceChildren(...(secoes.length ? secoes
    : [novoEl('p', 'painel-aviso', 'Nenhum agente com este status agora.')]));
}

function criarCartaoAgente(a) {
  const interativo = a.tipo !== 'estagiario';
  const cartao = novoEl(interativo ? 'button' : 'div', `equipe-cartao status-${a.status}`);
  const topo = novoEl('div', 'equipe-cartao-topo');
  const iniciais = a.nome.split(/\s+/).filter((p) => p.length > 2 || /\d/.test(p)).slice(0, 2)
    .map((p) => p[0]).join('').toUpperCase() || a.nome[0];
  const identidade = novoEl('div', 'equipe-identidade');
  identidade.append(novoEl('strong', 'equipe-nome', a.nome), novoEl('span', 'equipe-funcao', a.funcao));
  const status = novoEl('span', 'equipe-status');
  status.append(novoEl('i', null), document.createTextNode(ROTULOS_STATUS[a.status] || a.status));
  topo.append(novoEl('span', 'equipe-avatar', iniciais), identidade, status);
  cartao.append(topo, novoEl('p', 'equipe-descricao', a.descricao || 'Sem descrição.'));
  if (interativo) {
    cartao.type = 'button';
    cartao.title = a.tipo === 'sistema' ? `Abrir o painel do ${a.nome}` : `Conversar com ${a.nome}`;
    cartao.append(novoEl('span', 'equipe-acao', a.tipo === 'sistema' ? 'Abrir painel →' : 'Abrir conversa →'));
    cartao.addEventListener('click', () => {
      fecharEquipe();
      if (andarAtual !== a.andar && cena) renderizarAndar(a.andar); // leva ao andar do agente
      abrirAgente(a.andar, a.id);
    });
  }
  return cartao;
}

document.querySelectorAll('.contador[data-status]').forEach((botao) =>
  botao.addEventListener('click', () => abrirEquipe(botao.dataset.status)));
document.getElementById('equipe-fechar').addEventListener('click', fecharEquipe);
janelaEquipe.addEventListener('click', (e) => { if (e.target === janelaEquipe) fecharEquipe(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && equipeAberta) fecharEquipe();
});
