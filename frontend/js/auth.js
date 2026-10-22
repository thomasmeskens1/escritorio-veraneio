// Login, sessão (JWT no localStorage) e inicialização da página.

const CHAVE_TOKEN = 'veraneio_token';

let sessao = null; // { token, usuario, role }

const telaLogin = document.getElementById('login');
const formLogin = document.getElementById('login-form');
const erroLogin = document.getElementById('login-erro');

function lerToken() {
  try {
    return localStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

function guardarToken(token) {
  try {
    localStorage.setItem(CHAVE_TOKEN, token);
  } catch {
    // sem storage: a sessão vale só até recarregar a página
  }
}

function apagarToken() {
  try {
    localStorage.removeItem(CHAVE_TOKEN);
  } catch {
    // nada a fazer
  }
}

// Decodifica o payload do JWT apenas para a interface; quem valida é o servidor.
function lerPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const binario = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
    const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

function sessaoDoToken(token) {
  const payload = token && lerPayload(token);
  if (!payload?.sub) return null;
  if (payload.exp && payload.exp * 1000 <= Date.now()) return null;
  return { token, usuario: payload.nome || payload.sub, role: payload.role };
}

function mostrarErroLogin(texto) {
  erroLogin.textContent = texto;
}

async function entrar(evento) {
  evento.preventDefault();
  const usuario = formLogin.usuario.value.trim();
  const senha = formLogin.senha.value;
  if (!usuario || !senha) {
    mostrarErroLogin('Informe usuário e senha.');
    return;
  }

  const botao = document.getElementById('login-entrar');
  botao.disabled = true;
  mostrarErroLogin('');
  try {
    const resposta = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, senha }),
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      mostrarErroLogin(typeof dados.detail === 'string' ? dados.detail : 'Não foi possível entrar.');
      return;
    }
    const nova = sessaoDoToken(dados.token);
    if (!nova) {
      mostrarErroLogin('Resposta inválida do servidor.');
      return;
    }
    guardarToken(dados.token);
    iniciarSessao(nova);
  } catch {
    mostrarErroLogin('Servidor indisponível. Tente novamente.');
  } finally {
    botao.disabled = false;
  }
}

function iniciarSessao(nova) {
  sessao = nova;
  formLogin.reset();
  mostrarErroLogin('');
  telaLogin.hidden = true;
  document.getElementById('app').hidden = false;
  document.getElementById('usuario-logado').textContent = `${sessao.usuario} · ${sessao.role}`;
  configurarModelos(); // ícone "Modelos de IA" só para a diretoria
  configurarElevador();
  iniciarEscritorio();
  conectar();
}

// Volta para o login; `aviso` aparece abaixo do formulário (ex.: sessão expirada).
function encerrarSessao(aviso = '') {
  apagarToken();
  sessao = null;
  desconectar();
  fecharChat();
  fecharPainel();
  limparRegistro();
  limparEquipe();
  limparModelos();
  limparChat();
  limparPerfis();
  atualizarContadores({});
  limparToasts();
  encerrarEscritorio();
  document.getElementById('app').hidden = true;
  telaLogin.hidden = false;
  mostrarErroLogin(aviso);
  formLogin.usuario.focus();
}

formLogin.addEventListener('submit', entrar);
document.getElementById('sair').addEventListener('click', () => encerrarSessao());

// Entra direto se já existe um token não expirado.
const sessaoSalva = sessaoDoToken(lerToken());
if (sessaoSalva) {
  iniciarSessao(sessaoSalva);
} else {
  apagarToken();
  formLogin.usuario.focus();
}
