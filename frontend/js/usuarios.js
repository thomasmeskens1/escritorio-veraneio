// Painel de usuários (só o master, Thomas, 29/10/2026): incluir pessoas, mudar o perfil, ativar/desativar,
// redefinir a senha e escolher os agentes que cada uma pode usar (padrão: todos). API em /api/usuarios.

const janelaUsuarios = document.getElementById('usuarios');
const usuariosConteudo = document.getElementById('usuarios-conteudo');
const NOMES_ANDARES_USUARIOS = { porao: 'Porão', terreo: 'Térreo', marketing: 'Marketing', comercial: 'Comercial',
  cobertura: 'Cobertura' };

let usuariosAbertos = false;
let dadosUsuarios = null; // { usuarios, agentes, roles }
let mensagemUsuarios = null; // { texto, erro }

function configurarUsuarios() {
  document.getElementById('abrir-usuarios').hidden = !sessao?.master;
}

async function chamarUsuarios(caminho = '', opcoes = {}) {
  const resposta = await fetch(`/api/usuarios${caminho}`, {
    ...opcoes,
    headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
  });
  if (resposta.status === 401) {
    encerrarSessao('Sessão expirada. Entre novamente.');
    throw new Error('Sessão expirada.');
  }
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new Error(typeof dados.detail === 'string' ? dados.detail : 'Confira os campos e tente de novo.');
  }
  return dados;
}

async function carregarUsuarios() {
  try {
    dadosUsuarios = await chamarUsuarios();
  } catch (erro) {
    mensagemUsuarios = { texto: erro.message, erro: true };
  }
  renderizarUsuarios();
}

function abrirUsuarios() {
  if (!sessao?.master) return;
  usuariosAbertos = true;
  janelaUsuarios.classList.add('aberto');
  usuariosConteudo.replaceChildren(novoEl('p', 'usuarios-nota', 'Carregando…'));
  carregarUsuarios();
}

function fecharUsuarios() {
  usuariosAbertos = false;
  mensagemUsuarios = null;
  janelaUsuarios.classList.remove('aberto');
}

const resumoAgentes = (agentes, total) => (agentes === '*' ? 'Todos os agentes'
  : `${agentes.length} de ${total} agentes`);

function dataCurta(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'nunca';
}

function renderizarUsuarios() {
  if (!usuariosAbertos) return;
  const partes = [];
  if (mensagemUsuarios) {
    partes.push(novoEl('p', `usuarios-nota${mensagemUsuarios.erro ? ' erro' : ' ok'}`, mensagemUsuarios.texto));
  }
  if (!dadosUsuarios) {
    usuariosConteudo.replaceChildren(...partes);
    return;
  }
  const total = dadosUsuarios.agentes.length;
  const lista = novoEl('ul', 'usuarios-lista');
  dadosUsuarios.usuarios.forEach((u) => {
    const item = novoEl('li', `usuario-item${u.ativo ? '' : ' inativo'}`);
    const info = novoEl('div', 'usuario-info');
    const nome = novoEl('strong', null, u.nome);
    if (u.master) nome.append(novoEl('span', 'usuario-selo', 'master'));
    if (!u.ativo) nome.append(novoEl('span', 'usuario-selo inativo', 'desativado'));
    info.append(nome, novoEl('small', null, u.login),
      novoEl('small', null, `${u.tarefas} tarefa(s) · última: ${dataCurta(u.ultima_tarefa)}`
        + (u.mais_usados.length ? ` · mais usados: ${u.mais_usados.join(', ')}` : '')));
    const acoes = novoEl('div', 'usuario-acoes');
    const perfil = novoEl('select', 'form-entrada');
    perfil.setAttribute('aria-label', `Perfil de ${u.nome}`);
    dadosUsuarios.roles.forEach((r) => perfil.append(new Option(r === 'diretoria' ? 'Diretoria' : 'Funcionário', r)));
    perfil.value = u.role;
    perfil.disabled = u.master;
    perfil.addEventListener('change', () => alterarUsuario(u, { role: perfil.value }, 'Perfil atualizado.'));
    const agentes = novoEl('button', 'botao-secundario', resumoAgentes(u.agentes, total));
    agentes.type = 'button';
    agentes.disabled = u.master;
    agentes.title = u.master ? 'O master usa todos os agentes' : 'Escolher os agentes deste usuário';
    agentes.addEventListener('click', () => editarAgentes(u));
    const senha = novoEl('button', 'botao-secundario', 'Redefinir senha');
    senha.type = 'button';
    senha.addEventListener('click', () => redefinirSenha(u));
    acoes.append(perfil, agentes, senha);
    if (!u.master) {
      const ativo = novoEl('button', 'botao-secundario', u.ativo ? 'Desativar' : 'Reativar');
      ativo.type = 'button';
      ativo.addEventListener('click', () => alterarUsuario(u, { ativo: !u.ativo },
        u.ativo ? `${u.nome} foi desativado: a sessão dele caiu e o login fica bloqueado.` : `${u.nome} foi reativado.`));
      acoes.append(ativo);
    }
    item.append(info, acoes);
    lista.append(item);
  });
  partes.push(lista);
  usuariosConteudo.replaceChildren(...partes);
}

async function alterarUsuario(u, campos, sucesso) {
  try {
    await chamarUsuarios(`/${encodeURIComponent(u.login)}`, { method: 'PATCH', body: JSON.stringify(campos) });
    mensagemUsuarios = { texto: sucesso, erro: false };
  } catch (erro) {
    mensagemUsuarios = { texto: erro.message, erro: true };
  }
  carregarUsuarios();
}

function novoUsuario() {
  const agentes = dadosUsuarios?.agentes || [];
  abrirFormularioPopup({
    titulo: 'Novo usuário', botao: 'Incluir usuário',
    campos: [
      { nome: 'login', rotulo: 'E-mail (login)', tipo: 'texto', obrigatorio: true },
      { nome: 'nome', rotulo: 'Nome exibido', tipo: 'texto', obrigatorio: true },
      { nome: 'role', rotulo: 'Perfil', tipo: 'opcoes', obrigatorio: true, opcoes: ['Funcionário', 'Diretoria'] },
      { nome: 'senha', rotulo: 'Senha inicial (mínimo 8 caracteres)', tipo: 'texto', obrigatorio: true },
    ],
  }, async (r) => {
    try {
      await chamarUsuarios('', { method: 'POST', body: JSON.stringify({
        login: r.login, nome: r.nome, senha: r.senha, role: r.role === 'Diretoria' ? 'diretoria' : 'funcionario',
        agentes: '*' }) });
      mensagemUsuarios = { texto: `${r.nome} foi incluído com acesso a todos os ${agentes.length} agentes.`, erro: false };
    } catch (erro) {
      mensagemUsuarios = { texto: erro.message, erro: true };
    }
    carregarUsuarios();
  }, 'Começa com acesso a todos os agentes; ajuste depois em "Agentes"');
}

function redefinirSenha(u) {
  abrirFormularioPopup({
    titulo: `Nova senha de ${u.nome}`, botao: 'Salvar senha',
    campos: [{ nome: 'senha', rotulo: 'Nova senha (mínimo 8 caracteres)', tipo: 'texto', obrigatorio: true }],
  }, (r) => alterarUsuario(u, { senha: r.senha }, `Senha de ${u.nome} redefinida.`), u.login);
}

// Lista de agentes por andar, com "Todos os agentes" no topo.
function editarAgentes(u) {
  const agentes = dadosUsuarios.agentes;
  const chaveAg = (a) => `${a.andar}/${a.id}`;
  const rotulo = (a) => `${NOMES_ANDARES_USUARIOS[a.andar] || a.andar} · ${a.nome}`;
  const TODOS_ROTULO = 'Todos os agentes (inclusive os que forem criados depois)';
  const marcados = u.agentes === '*' ? [TODOS_ROTULO] : agentes.filter((a) => u.agentes.includes(chaveAg(a))).map(rotulo);
  abrirFormularioPopup({
    titulo: `Agentes de ${u.nome}`, botao: 'Salvar acesso',
    campos: [{ nome: 'agentes', rotulo: 'Pode usar', tipo: 'multipla', opcoes: [TODOS_ROTULO, ...agentes.map(rotulo)],
      marcados }],
  }, (r) => {
    const escolhidos = r.agentes ? r.agentes.split(', ') : [];
    const lista = escolhidos.includes(TODOS_ROTULO) ? '*'
      : agentes.filter((a) => escolhidos.includes(rotulo(a))).map(chaveAg);
    alterarUsuario(u, { agentes: lista }, `Acesso de ${u.nome} atualizado: ${resumoAgentes(lista, agentes.length)}.`);
  }, 'Andares sem nenhum agente marcado ficam trancados para ele');
}

document.getElementById('abrir-usuarios').addEventListener('click', abrirUsuarios);
document.getElementById('usuarios-fechar').addEventListener('click', fecharUsuarios);
document.getElementById('usuarios-novo').addEventListener('click', () => { if (dadosUsuarios) novoUsuario(); });
janelaUsuarios.addEventListener('click', (e) => { if (e.target === janelaUsuarios) fecharUsuarios(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && usuariosAbertos && !popupFormulario) fecharUsuarios();
});
