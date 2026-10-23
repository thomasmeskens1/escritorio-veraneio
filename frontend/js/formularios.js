// Formulários no chat: sempre que o sistema precisa de informação do usuário, ela é pedida num formulário curto
// (nada fica faltando). Vêm de duas fontes: o agente escreve um bloco <<FORMULARIO>>{json}<<FIM DO FORMULARIO>> na
// resposta, ou o próprio sistema anexa um à mensagem (ex.: escolher a empresa da conversa).
// JSON: {"titulo": "...", "campos": [{"nome", "rotulo", "tipo": texto|texto_longo|opcoes|multipla|data|numero,
//        "opcoes": [...], "obrigatorio": true}]}. Ao enviar, as respostas vão como mensagem ao mesmo agente.

const BLOCO_FORMULARIO = /<<FORMULARIO>>([\s\S]*?)<<FIM DO FORMULARIO>>/;

// {texto sem o bloco, formulario | null}. Bloco malformado: some do texto e não vira formulário.
function extrairFormulario(texto) {
  const achado = BLOCO_FORMULARIO.exec(String(texto || ''));
  if (!achado) return { texto, formulario: null };
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
      item.append(marca, document.createTextNode(` ${o}`));
      entrada.append(item);
    });
  } else if (campo.tipo === 'texto_longo') {
    entrada = novoEl('textarea', 'form-entrada');
    entrada.rows = 3;
  } else {
    entrada = document.createElement('input');
    entrada.className = 'form-entrada';
    entrada.type = { data: 'date', numero: 'number' }[campo.tipo] || 'text';
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

function enviarRespostasDoFormulario(_respostas, texto) {
  if (modalInput.disabled) return;
  modalInput.value = texto;
  document.getElementById('modal-form').requestSubmit();
}
