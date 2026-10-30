// Triagem: porta de entrada única (Thomas, 30/10/2026). Barra de espaço duas vezes dentro de um andar (sem chat,
// painel ou outra janela aberta) abre a caixa; a triagem indica o agente certo (backend/triagem.py) e o pedido vai
// para o chat dele, como se o usuário tivesse escrito lá. Trocar o agente sugerido ensina a triagem.

const INTERVALO_ESPACO_DUPLO = 400;
let ultimoEspaco = 0;

function podeAbrirTriagem() {
  if (!sessao || onboarding || popupFormulario || document.querySelector('.modal.aberto')) return false;
  const foco = document.activeElement;
  return !(foco && (foco.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(foco.tagName)));
}

document.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' || e.repeat || e.ctrlKey || e.altKey || e.metaKey || !podeAbrirTriagem()) {
    if (e.code !== 'Space') ultimoEspaco = 0;
    return;
  }
  const agora = Date.now();
  if (agora - ultimoEspaco <= INTERVALO_ESPACO_DUPLO) {
    e.preventDefault();
    ultimoEspaco = 0;
    abrirTriagem();
  } else {
    ultimoEspaco = agora;
  }
});

async function pedirTriagem(caminho, corpo) {
  const resposta = await fetch(caminho, {
    method: 'POST',
    headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || `HTTP ${resposta.status}`);
  return dados;
}

function abrirTriagem() {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-triagem');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, 'Triagem'), novoEl('p', null, 'Escreva o pedido: eu indico o agente certo'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);

  const corpo = novoEl('form', 'formulario-corpo triagem-corpo');
  const campo = novoEl('textarea', 'form-entrada');
  campo.rows = 4;
  campo.maxLength = 30000;
  campo.placeholder = 'Ex.: escreve a legenda do Lodge 28 para o Instagram';
  campo.setAttribute('aria-label', 'Pedido');
  const acoes = novoEl('div', 'triagem-acoes');
  const encaminhar = novoEl('button', 'botao-primario', 'Encaminhar');
  encaminhar.type = 'submit';
  acoes.append(novoEl('span', 'triagem-dica', 'Ctrl+Enter também envia'), encaminhar);
  const resultado = novoEl('div', 'triagem-resultado');
  corpo.append(campo, acoes, resultado);

  campo.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); corpo.requestSubmit(); }
  });
  corpo.addEventListener('submit', async (e) => {
    e.preventDefault();
    const texto = campo.value.trim();
    if (texto.length < 3 || encaminhar.disabled) return;
    encaminhar.disabled = true;
    resultado.replaceChildren(novoEl('p', 'triagem-dica', 'Analisando o pedido…'));
    try {
      mostrarSugestao(resultado, texto, await pedirTriagem('/api/triagem', { texto }));
    } catch (erro) {
      resultado.replaceChildren(novoEl('p', 'rotinas-nota erro', `Não foi possível fazer a triagem: ${erro.message}`));
    } finally {
      encaminhar.disabled = false;
    }
  });

  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  campo.focus();
}

function mostrarSugestao(caixa, texto, dados) {
  const { sugestao } = dados;
  const cartao = novoEl('div', 'triagem-sugestao');
  cartao.append(novoEl('strong', null, `Vai para: ${sugestao.nome}`), novoEl('span', 'triagem-funcao', sugestao.funcao),
    novoEl('p', null, `Por quê: ${sugestao.motivo}.`));

  const rotulo = novoEl('label', 'form-rotulo', 'Mandar para');
  const seletor = novoEl('select', 'form-entrada');
  seletor.id = `triagem-agente-${dados.id}`;
  rotulo.htmlFor = seletor.id;
  const chaveItem = (a) => `${a.andar}/${a.agente}`;
  const sugeridos = [sugestao, ...dados.alternativas];
  const grupoSugeridos = novoEl('optgroup');
  grupoSugeridos.label = 'Sugeridos';
  sugeridos.forEach((a, i) => grupoSugeridos.append(new Option(i ? a.nome : `${a.nome} (sugestão)`, chaveItem(a))));
  const grupoTodos = novoEl('optgroup');
  grupoTodos.label = 'Todos os agentes';
  dados.todos.filter((a) => !sugeridos.some((s) => chaveItem(s) === chaveItem(a)))
    .forEach((a) => grupoTodos.append(new Option(`${a.nome} · ${a.andar}`, chaveItem(a))));
  seletor.append(grupoSugeridos, grupoTodos);

  const enviarBotao = novoEl('button', 'botao-primario', `Enviar ao ${sugestao.nome}`);
  enviarBotao.type = 'button';
  seletor.addEventListener('change', () => {
    const escolhido = dados.todos.find((a) => chaveItem(a) === seletor.value);
    enviarBotao.textContent = `Enviar ao ${escolhido?.nome || 'agente'}`;
  });
  enviarBotao.addEventListener('click', async () => {
    const [andar, agente] = seletor.value.split('/');
    enviarBotao.disabled = true;
    try {
      await pedirTriagem(`/api/triagem/${dados.id}/decisao`, { agente }); // a escolha ensina a triagem
    } catch {
      // o envio segue mesmo sem registrar a escolha
    }
    const trocou = agente !== sugestao.agente;
    fecharFormularioPopup();
    enviarPelaTriagem(andar, agente, texto, trocou ? 'você escolheu este agente na triagem'
      : sugestao.motivo);
  });

  const rodape = novoEl('div', 'triagem-acoes');
  const aprendizado = dados.aprendizado?.ativo
    ? `Aprendendo com ${dados.aprendizado.exemplos} pedidos`
    : `Aprendizado começa com ${dados.aprendizado?.minimo || 30} pedidos`;
  rodape.append(novoEl('span', 'triagem-dica', aprendizado), enviarBotao);
  caixa.replaceChildren(cartao, rotulo, seletor, rodape);
  enviarBotao.focus();
}

// Abre o chat do agente (no andar dele), registra o porquê da triagem e envia como se o usuário tivesse escrito lá.
function enviarPelaTriagem(andar, agente, texto, motivo) {
  if (andarAtual !== andar && cena) renderizarAndar(andar);
  abrirAgente(andar, agente);
  if (!chatAberto || chatAberto.agente !== agente) return;
  adicionarMensagem(andar, agente, { autor: 'sistema', tipo: 'sistema', texto: `Triagem: trouxe para cá porque ${motivo}.` });
  modalInput.value = texto;
  ajustarAlturaInput();
  document.getElementById('modal-form').requestSubmit();
}
