// Formulários no chat: sempre que o sistema precisa de informação do usuário, ela é pedida num formulário curto
// (nada fica faltando). Vêm de duas fontes: o agente escreve um bloco <<FORMULARIO>>{json}<<FIM DO FORMULARIO>> na
// resposta, ou o próprio sistema anexa um à mensagem (ex.: escolher a empresa da conversa).
// JSON: {"titulo": "...", "campos": [{"nome", "rotulo", "tipo": texto|texto_longo|opcoes|multipla|data|numero|hora,
//        "opcoes": [...], "marcados": [...] (multipla), "obrigatorio": true}]}. Ao enviar, as respostas vão como mensagem ao mesmo agente.

const BLOCO_FORMULARIO = /<<FORMULARIO>>([\s\S]*?)<<FIM DO FORMULARIO>>/;

// {texto sem o bloco, formulario | null}. Bloco malformado: some do texto e não vira formulário.
function extrairFormulario(texto) {
  const achado = BLOCO_FORMULARIO.exec(String(texto || ''));
  if (!achado) {
    // Bloco cortado pelo modelo (sem o fechamento): some do texto em vez de aparecer cru no chat.
    const inicio = String(texto || '').indexOf('<<FORMULARIO>>');
    return { texto: inicio >= 0 ? String(texto).slice(0, inicio).trim() : texto, formulario: null };
  }
  let formulario = null;
  try {
    const dados = JSON.parse(achado[1].trim());
    if (dados && Array.isArray(dados.campos) && dados.campos.length) formulario = dados;
  } catch {
    // modelo escreveu JSON inválido: mostra só o texto
  }
  return { texto: String(texto).replace(BLOCO_FORMULARIO, '').trim(), formulario };
}

function campoDoFormulario(campo, indice) {
  const id = `form-${Date.now()}-${indice}`;
  const rotulo = novoEl('label', 'form-rotulo', `${campo.rotulo || campo.nome}${campo.obrigatorio ? ' *' : ''}`);
  rotulo.htmlFor = id;
  let entrada;
  const opcoes = Array.isArray(campo.opcoes) ? campo.opcoes.map(String) : [];
  if (campo.tipo === 'opcoes' && opcoes.length) {
    entrada = novoEl('select', 'form-entrada');
    entrada.append(new Option('Escolha…', ''), ...opcoes.map((o) => new Option(o, o)));
  } else if (campo.tipo === 'multipla' && opcoes.length) {
    entrada = novoEl('div', 'form-multipla');
    opcoes.forEach((o) => {
      const item = novoEl('label', 'form-marcar');
      const marca = document.createElement('input');
      marca.type = 'checkbox';
      marca.value = o;
      marca.checked = (campo.marcados || []).includes(o); // já marcadas (ex.: agentes liberados de um usuário)
      item.append(marca, document.createTextNode(` ${o}`));
      entrada.append(item);
    });
  } else if (campo.tipo === 'texto_longo') {
    entrada = novoEl('textarea', 'form-entrada');
    entrada.rows = 3;
  } else {
    entrada = document.createElement('input');
    entrada.className = 'form-entrada';
    entrada.type = { data: 'date', numero: 'number', hora: 'time' }[campo.tipo] || 'text';
  }
  entrada.id = id;
  const grupo = novoEl('div', 'form-campo');
  grupo.append(rotulo, entrada);
  return { grupo, valor: () => (entrada.classList.contains('form-multipla')
    ? [...entrada.querySelectorAll('input:checked')].map((m) => m.value).join(', ')
    : String(entrada.value || '').trim()) };
}

// `aoEnviar(respostas, texto)`: padrão = mandar o texto como mensagem ao agente da conversa.
function criarFormulario(definicao, aoEnviar) {
  const form = novoEl('form', 'msg-formulario');
  if (definicao.titulo) form.append(novoEl('strong', 'form-titulo', definicao.titulo));
  const campos = definicao.campos.map((c, i) => ({ ...c, ...campoDoFormulario(c, i) }));
  campos.forEach((c) => form.append(c.grupo));
  const aviso = novoEl('p', 'form-aviso');
  const enviarBotao = novoEl('button', 'botao-primario', definicao.botao || 'Enviar respostas');
  enviarBotao.type = 'submit';
  form.append(aviso, enviarBotao);
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const respostas = Object.fromEntries(campos.map((c) => [c.nome, c.valor()]));
    const faltando = campos.filter((c) => c.obrigatorio && !respostas[c.nome]).map((c) => c.rotulo || c.nome);
    if (faltando.length) {
      aviso.textContent = `Preencha: ${faltando.join(', ')}.`;
      return;
    }
    const texto = [`Respostas${definicao.titulo ? ` — ${definicao.titulo}` : ''}:`,
      ...campos.filter((c) => respostas[c.nome]).map((c) => `- ${c.rotulo || c.nome}: ${respostas[c.nome]}`)].join('\n');
    form.querySelectorAll('input, select, textarea, button').forEach((el) => { el.disabled = true; });
    (aoEnviar || enviarRespostasDoFormulario)(respostas, texto);
  });
  return form;
}

// Formulário em pop-up (Thomas, 29/10/2026): o formulário não fica no chat; na conversa aparecem só as respostas
// enviadas. Um pop-up por vez, por cima do chat; fechar sem enviar deixa o "!" no agente até a resposta.
let popupFormulario = null;

function fecharFormularioPopup() {
  popupFormulario?.remove();
  popupFormulario = null;
  const proximo = popupsNaFila.shift();
  if (proximo) setTimeout(proximo, 0);
}

// Revisão de 30/10/2026 (2.27): um pop-up que abre sozinho (formulário de agente, pergunta de insatisfação) esperava
// nada e apagava o que a pessoa estava digitando em outro. Agora ele espera na fila até o atual fechar.
const popupsNaFila = [];

function abrirQuandoLivre(abrir) {
  if (popupFormulario?.dataset.preenchido) popupsNaFila.push(abrir);
  else abrir();
}

document.addEventListener('input', (e) => {
  if (popupFormulario?.contains(e.target)) popupFormulario.dataset.preenchido = '1';
});

// `aoFechar`: o usuário fechou sem enviar (X, Esc ou clique fora). Nos formulários dos agentes isso PARA a
// solicitação (Thomas, 29/10/2026), e o pop-up avisa antes.
function abrirFormularioPopup(definicao, aoEnviar, subtitulo = '', aoFechar = null) {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, definicao.titulo || 'Formulário'), novoEl('p', null, subtitulo || 'Responda para o agente seguir'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar o formulário');
  const fecharSemEnviar = () => {
    fecharFormularioPopup();
    aoFechar?.();
  };
  fechar.addEventListener('click', fecharSemEnviar);
  barra.append(titulo, fechar);
  const corpo = novoEl('div', 'formulario-corpo');
  if (aoFechar) corpo.append(novoEl('p', 'form-aviso-fechar', 'Fechar este formulário sem enviar encerra a solicitação.'));
  corpo.append(criarFormulario({ ...definicao, titulo: '' }, (respostas, texto) => {
    const enviado = (aoEnviar || enviarRespostasDoFormulario)(respostas, texto.replace(/^Respostas:/, `Respostas — ${definicao.titulo || 'Formulário'}:`));
    if (enviado === false) {  // chat bloqueado (sem conexão ou carregando): o pop-up fica, com o que foi preenchido
      corpo.querySelectorAll('input, select, textarea, button').forEach((el) => { el.disabled = false; });
      let aviso = corpo.querySelector('.form-aviso-envio');
      if (!aviso) corpo.append(aviso = novoEl('p', 'form-aviso-fechar form-aviso-envio'));
      aviso.textContent = 'Não deu para enviar agora (conexão caiu ou o chat ainda está carregando). Suas respostas '
        + 'continuam aqui: tente de novo em alguns segundos.';
      return;
    }
    fecharFormularioPopup();
  }));
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharSemEnviar(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharSemEnviar(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  corpo.querySelector('input, select, textarea')?.focus();
}

function enviarRespostasDoFormulario(_respostas, texto) {
  if (modalInput.disabled || modalEnviar.disabled) return false;
  modalInput.value = texto;
  document.getElementById('modal-form').requestSubmit();
  return true;
}
