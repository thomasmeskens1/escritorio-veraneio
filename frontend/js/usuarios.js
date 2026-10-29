// Painel de usuários (só o master, Thomas, 29/10/2026): incluir pessoas, mudar o perfil, ativar/desativar,
// redefinir a senha e escolher os agentes que cada uma pode usar (padrão: todos). API em /api/usuarios.

const janelaUsuarios = document.getElementById('usuarios');
const usuariosConteudo = document.getElementById('usuarios-conteudo');
const NOMES_ANDARES_USUARIOS = { porao: 'Porão', terreo: 'Térreo', marketing: 'Marketing', comercial: 'Comercial',
  cobertura: 'Cobertura' };

const STATUS_USUARIO = { ativo: 'Ativo agora', ausente: 'Ausente (conectado, sem mexer há 5 min)',
  offline: 'Offline' };
const INTERVALO_USUARIOS = 30000; // status ao vivo enquanto o painel está aberto
let timerUsuarios = null;
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
  clearInterval(timerUsuarios);
  timerUsuarios = setInterval(carregarUsuarios, INTERVALO_USUARIOS);
}

function fecharUsuarios() {
  usuariosAbertos = false;
  mensagemUsuarios = null;
  clearInterval(timerUsuarios);
  janelaUsuarios.classList.remove('aberto');
}

const resumoAndares = (andares) => (andares === '*' ? 'Todos os andares'
  : `${andares.length} de ${dadosUsuarios?.andares.length ?? 5} andares`);
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
  // Cada usuário é um botão: o clique abre a tela dele (perfil, agentes, senha, desativar).
  dadosUsuarios.usuarios.forEach((u) => {
    const item = novoEl('li');
    const botao = novoEl('button', `usuario-item${u.ativo ? '' : ' inativo'}`);
    botao.type = 'button';
    botao.title = `Abrir ${u.nome}: perfil, agentes, senha e acesso`;
    const info = novoEl('div', 'usuario-info');
    const nome = novoEl('strong');
    const status = novoEl('span', `usuario-status ${u.status || 'offline'}`);
    status.title = STATUS_USUARIO[u.status] || STATUS_USUARIO.offline;
    status.setAttribute('aria-label', status.title);
    nome.append(status, document.createTextNode(u.nome));
    if (u.master) nome.append(novoEl('span', 'usuario-selo', 'master'));
    if (!u.ativo) nome.append(novoEl('span', 'usuario-selo inativo', 'desativado'));
    info.append(nome, novoEl('small', null, u.login),
      novoEl('small', null, `${u.tarefas} tarefa(s) · última: ${dataCurta(u.ultima_tarefa)}`
        + (u.mais_usados.length ? ` · mais usados: ${u.mais_usados.join(', ')}` : '')));
    const resumo = novoEl('div', 'usuario-resumo');
    resumo.append(novoEl('span', null, u.role === 'diretoria' ? 'Diretoria' : 'Funcionário'),
      novoEl('span', null, resumoAndares(u.andares)), novoEl('span', null, resumoAgentes(u.agentes, total)),
      novoEl('span', 'usuario-seta', '›'));
    botao.append(info, resumo);
    botao.addEventListener('click', () => abrirUsuario(u));
    item.append(botao);
    lista.append(item);
  });
  partes.push(lista);
  usuariosConteudo.replaceChildren(...partes);
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
  }, 'Começa com acesso a todos os agentes; para ajustar, clique no usuário na lista');
}

// Tela do usuário (clique na lista): perfil, agentes por andar, redefinir senha e desativar, tudo num pop-up.
function abrirUsuario(u) {
  fecharFormularioPopup();
  const agentes = dadosUsuarios.agentes;
  const chaveAg = (a) => `${a.andar}/${a.id}`;
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-usuario');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, u.nome), novoEl('p', null, `${u.login}${u.master ? ' · master' : ''}`));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);

  const corpo = novoEl('div', 'formulario-corpo usuario-corpo');
  const aviso = novoEl('p', 'form-aviso');

  // Perfil
  const grupoPerfil = novoEl('div', 'form-campo');
  const perfil = novoEl('select', 'form-entrada');
  perfil.id = 'usuario-perfil';
  dadosUsuarios.roles.forEach((r) => perfil.append(new Option(r === 'diretoria' ? 'Diretoria' : 'Funcionário', r)));
  perfil.value = u.role;
  perfil.disabled = u.master;
  const rotuloPerfil = novoEl('label', 'form-rotulo', 'Perfil');
  rotuloPerfil.htmlFor = perfil.id;
  grupoPerfil.append(rotuloPerfil, perfil);

  // Andares (camada acima dos agentes): andar fechado tranca o andar no elevador e trava os agentes dele.
  const grupoAndares = novoEl('fieldset', 'usuario-agentes');
  grupoAndares.append(novoEl('legend', 'form-rotulo', u.master ? 'Andares (o master acessa todos)' : 'Andares que pode acessar'));
  const andaresLiberados = (andar) => u.andares === '*' || u.andares.includes(andar);
  const caixasAndares = {};
  const linhaAndares = novoEl('div', 'usuario-andar');
  Object.entries(NOMES_ANDARES_USUARIOS).forEach(([andar, nomeAndar]) => {
    if (!dadosUsuarios.andares.includes(andar)) return;
    const caixa = document.createElement('input');
    caixa.type = 'checkbox';
    caixa.value = andar;
    caixa.checked = andaresLiberados(andar);
    caixa.disabled = u.master;
    const linha = novoEl('label', 'form-marcar');
    linha.append(caixa, document.createTextNode(` ${nomeAndar}`));
    linhaAndares.append(linha);
    caixasAndares[andar] = caixa;
  });
  grupoAndares.append(linhaAndares);

  // Agentes por andar ("Todos" marca e trava os demais)
  const grupoAgentes = novoEl('fieldset', 'usuario-agentes');
  grupoAgentes.append(novoEl('legend', 'form-rotulo', u.master ? 'Agentes (o master usa todos)' : 'Agentes que pode usar'));
  const marcarTodos = document.createElement('input');
  marcarTodos.type = 'checkbox';
  marcarTodos.checked = u.agentes === '*';
  const linhaTodos = novoEl('label', 'form-marcar usuario-todos');
  linhaTodos.append(marcarTodos, document.createTextNode(' Todos os agentes (inclusive os criados depois)'));
  grupoAgentes.append(linhaTodos);
  const caixas = [];
  const blocosAgentes = {};
  Object.entries(NOMES_ANDARES_USUARIOS).forEach(([andar, nomeAndar]) => {
    const doAndar = agentes.filter((a) => a.andar === andar);
    if (!doAndar.length) return;
    const bloco = novoEl('div', 'usuario-andar');
    blocosAgentes[andar] = bloco;
    bloco.append(novoEl('strong', null, nomeAndar));
    doAndar.forEach((a) => {
      const caixa = document.createElement('input');
      caixa.type = 'checkbox';
      caixa.value = chaveAg(a);
      caixa.dataset.andar = a.andar;
      caixa.checked = u.agentes === '*' || u.agentes.includes(chaveAg(a));
      const linha = novoEl('label', 'form-marcar');
      linha.title = a.funcao || '';
      linha.append(caixa, document.createTextNode(` ${a.nome}`));
      bloco.append(linha);
      caixas.push(caixa);
    });
    grupoAgentes.append(bloco);
  });
  // A escolha de agentes de um andar fechado fica guardada (volta igual se o andar for liberado de novo).
  const sincronizar = () => {
    Object.entries(blocosAgentes).forEach(([andar, bloco]) => {
      bloco.classList.toggle('desativado', !caixasAndares[andar]?.checked);
    });
    caixas.forEach((c) => {
      if (marcarTodos.checked) c.checked = true;
      c.disabled = marcarTodos.checked || u.master || !caixasAndares[c.dataset.andar]?.checked;
    });
  };
  marcarTodos.disabled = u.master;
  marcarTodos.addEventListener('change', sincronizar);
  Object.values(caixasAndares).forEach((c) => c.addEventListener('change', sincronizar));
  sincronizar();

  // Senha (abre o campo ao clicar)
  const grupoSenha = novoEl('div', 'form-campo usuario-senha');
  grupoSenha.hidden = true;
  const senha = document.createElement('input');
  senha.className = 'form-entrada';
  senha.id = 'usuario-senha';
  senha.type = 'text';
  senha.autocomplete = 'off';
  const rotuloSenha = novoEl('label', 'form-rotulo', 'Nova senha (mínimo 8 caracteres)');
  rotuloSenha.htmlFor = senha.id;
  const salvarSenha = novoEl('button', 'botao-primario', 'Salvar senha');
  salvarSenha.type = 'button';
  grupoSenha.append(rotuloSenha, senha, salvarSenha);

  // Ações
  const acoes = novoEl('div', 'usuario-acoes');
  const salvar = novoEl('button', 'botao-primario', 'Salvar alterações');
  salvar.type = 'button';
  salvar.hidden = u.master;
  const abrirSenha = novoEl('button', 'botao-secundario', 'Redefinir senha');
  abrirSenha.type = 'button';
  acoes.append(salvar, abrirSenha);
  let alternarAtivo = null;
  if (!u.master) {
    alternarAtivo = novoEl('button', `botao-secundario${u.ativo ? ' botao-perigo' : ''}`, u.ativo ? 'Desativar' : 'Reativar');
    alternarAtivo.type = 'button';
    acoes.append(alternarAtivo);
  }

  const enviar = async (campos, sucesso) => {
    [salvar, abrirSenha, salvarSenha, alternarAtivo].forEach((b) => { if (b) b.disabled = true; });
    try {
      await chamarUsuarios(`/${encodeURIComponent(u.login)}`, { method: 'PATCH', body: JSON.stringify(campos) });
      mensagemUsuarios = { texto: sucesso, erro: false };
      fecharFormularioPopup();
      carregarUsuarios();
    } catch (erro) {
      aviso.textContent = erro.message;
      [salvar, abrirSenha, salvarSenha, alternarAtivo].forEach((b) => { if (b) b.disabled = false; });
    }
  };
  salvar.addEventListener('click', () => {
    const lista = marcarTodos.checked ? '*' : caixas.filter((c) => c.checked).map((c) => c.value);
    const todosAndares = Object.values(caixasAndares).every((c) => c.checked);
    const andares = todosAndares ? '*' : Object.values(caixasAndares).filter((c) => c.checked).map((c) => c.value);
    enviar({ role: perfil.value, agentes: lista, andares },
      `${u.nome}: ${perfil.value === 'diretoria' ? 'Diretoria' : 'Funcionário'}, ${resumoAndares(andares)}, `
      + `${resumoAgentes(lista, agentes.length)}.`);
  });
  abrirSenha.addEventListener('click', () => {
    grupoSenha.hidden = false;
    senha.focus();
  });
  salvarSenha.addEventListener('click', () => {
    if (senha.value.length < 8) {
      aviso.textContent = 'A senha precisa ter pelo menos 8 caracteres.';
      return;
    }
    enviar({ senha: senha.value }, `Senha de ${u.nome} redefinida.`);
  });
  alternarAtivo?.addEventListener('click', () => {
    if (u.ativo && !window.confirm(`Desativar ${u.nome}? A sessão dele cai agora e o login fica bloqueado.`)) return;
    enviar({ ativo: !u.ativo }, u.ativo ? `${u.nome} foi desativado.` : `${u.nome} foi reativado.`);
  });

  corpo.append(grupoPerfil, grupoAndares, grupoAgentes, grupoSenha, aviso, acoes);
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  perfil.focus();
}

document.getElementById('abrir-usuarios').addEventListener('click', abrirUsuarios);
document.getElementById('usuarios-fechar').addEventListener('click', fecharUsuarios);
document.getElementById('usuarios-novo').addEventListener('click', () => { if (dadosUsuarios) novoUsuario(); });
janelaUsuarios.addEventListener('click', (e) => { if (e.target === janelaUsuarios) fecharUsuarios(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && usuariosAbertos && !popupFormulario) fecharUsuarios();
});
