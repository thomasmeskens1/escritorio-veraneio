// 👍/👎 nas respostas dos agentes (Thomas, 29/10/2026): ensina o Cérebro quais conhecimentos ajudaram.
// Clicar de novo no voto marcado retira o voto.
// Reação negativa (Thomas, 30/10/2026): o 👎 ou uma mensagem do tipo "não era isso" abre um pop-up perguntando o
// porquê. A resposta vai para o registro de insatisfações do master (backend/insatisfacoes.py) e, com texto, também
// para a Diretoria aprovar como correção (backend/avaliacoes.py).

const CATEGORIAS_INSATISFACAO = [
  ['pedido', 'Não seguiu o pedido'],
  ['dados', 'Dados errados ou inventados'],
  ['faltou', 'Faltou alguma coisa'],
  ['qualidade', 'Visual ou qualidade fraca'],
  ['demora', 'Demorou demais ou travou'],
  ['outro', 'Outro motivo'],
];
// Mesma ideia de insatisfacoes.NEGATIVA no servidor: frases claras de insatisfação com a resposta.
const REACAO_NEGATIVA = /\b(n[aã]o\s+(gostei|curti|era\s+(isso|o\s+que)|foi\s+(isso|o\s+que)|ficou\s+(bom|legal)|[ée]\s+(isso|o\s+que))|(est[aá]|ficou)\s+(errad|ruim|horr[ií]vel|p[ée]ssim|feio)|p[ée]ssim|horr[ií]vel|decepcion|insatisfeit|pedi\s+.{1,80}\s+e\s+(veio|voc[eê]\s+(fez|mandou|entregou))|errou|errad[oa])/i;

async function enviarAvaliacao(tarefaId, valor, comentario = '') {
  if (!sessao) return false;
  try {
    const resposta = await fetch(`/api/tarefas/${tarefaId}/avaliar`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ valor, comentario }),
    });
    return resposta.ok;
  } catch {
    return false;
  }
}

async function enviarInsatisfacao(dados) {
  try {
    const resposta = await fetch('/api/insatisfacoes', {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    return resposta.ok;
  } catch {
    return false;
  }
}

// Pop-up "por que a insatisfação?". `origem`: 'voto' (👎) ou 'mensagem' (frase negativa no chat).
function perguntarInsatisfacao(tarefaId, origem = 'voto', mensagem = '') {
  if (!sessao || !tarefaId) return;
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-insatisfacao');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, 'O que não ficou bom?'),
    novoEl('p', null, 'Sua resposta fica registrada para a gente analisar e corrigir o agente.'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar sem responder');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);

  const form = novoEl('form', 'formulario-corpo insatisfacao-form');
  const opcoes = novoEl('fieldset', 'insatisfacao-opcoes');
  opcoes.append(novoEl('legend', 'form-rotulo', 'Motivo'));
  CATEGORIAS_INSATISFACAO.forEach(([valor, rotulo]) => {
    const item = novoEl('label', 'insatisfacao-opcao');
    const radio = novoEl('input');
    radio.type = 'radio';
    radio.name = 'categoria';
    radio.value = valor;
    item.append(radio, novoEl('span', null, rotulo));
    opcoes.append(item);
  });
  const campo = novoEl('textarea', 'insatisfacao-texto');
  campo.rows = 3;
  campo.maxLength = 1000;
  campo.placeholder = 'Conte o que aconteceu (ex.: pedi 6 Lodges e o carrossel saiu só com 1)';
  if (origem === 'mensagem') campo.value = mensagem.slice(0, 1000);
  const aviso = novoEl('p', 'form-aviso-fechar');
  aviso.hidden = true;
  const acoes = novoEl('div', 'insatisfacao-acoes');
  const pular = novoEl('button', 'botao-secundario', 'Agora não');
  pular.type = 'button';
  pular.addEventListener('click', fecharFormularioPopup);
  const enviar = novoEl('button', 'botao-primario', 'Registrar');
  enviar.type = 'submit';
  acoes.append(pular, enviar);
  form.append(opcoes, novoEl('label', 'form-rotulo', 'Detalhes'), campo, aviso, acoes);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const categoria = form.querySelector('input[name="categoria"]:checked')?.value || '';
    const motivo = campo.value.trim();
    if (!categoria && !motivo) {
      aviso.textContent = 'Escolha um motivo ou escreva o que aconteceu.';
      aviso.hidden = false;
      return;
    }
    enviar.disabled = true;
    const ok = await enviarInsatisfacao({ tarefa_id: tarefaId, categoria: categoria || 'outro', motivo, origem,
      mensagem: origem === 'mensagem' ? mensagem : '' });
    if (!ok) {
      aviso.textContent = 'Não consegui registrar agora. Tente de novo.';
      aviso.hidden = false;
      enviar.disabled = false;
      return;
    }
    // Com texto, também vira correção para a Diretoria aprovar (o mesmo caminho do 👎 com comentário).
    if (origem === 'voto' && motivo) enviarAvaliacao(tarefaId, -1, motivo);
    form.replaceChildren(novoEl('p', 'rotinas-nota', 'Obrigado! Ficou registrado para a análise.'));
    setTimeout(fecharFormularioPopup, 1500);
  });

  janela.append(barra, form);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  opcoes.querySelector('input')?.focus();
}

// Mensagem enviada no chat: se for uma reação negativa à última resposta do agente, pergunta o porquê.
function verificarReacaoNegativa(texto, tarefaId) {
  if (!tarefaId || texto.startsWith('Respostas') || !REACAO_NEGATIVA.test(texto)) return;
  setTimeout(() => perguntarInsatisfacao(tarefaId, 'mensagem', texto), 400);
}

function criarAvaliacao(tarefaId, valorInicial = 0) {
  const caixa = novoEl('div', 'msg-avaliacao');
  let valor = valorInicial;
  const botoes = [[1, '👍', 'Boa resposta'], [-1, '👎', 'Não ajudou']].map(([v, icone, rotulo]) => {
    const botao = novoEl('button', 'msg-voto', icone);
    botao.type = 'button';
    botao.title = rotulo;
    botao.setAttribute('aria-label', rotulo);
    botao.addEventListener('click', async () => {
      const novo = valor === v ? 0 : v;
      botoes.forEach((b) => { b.disabled = true; });
      if (await enviarAvaliacao(tarefaId, novo)) {
        valor = novo;
        if (valor === -1) perguntarInsatisfacao(tarefaId, 'voto');
      }
      marcar();
    });
    return botao;
  });
  const marcar = () => botoes.forEach((b, i) => {
    b.disabled = false;
    b.classList.toggle('ativo', valor === (i === 0 ? 1 : -1));
    b.setAttribute('aria-pressed', String(valor === (i === 0 ? 1 : -1)));
  });

  marcar();
  caixa.append(...botoes);
  return caixa;
}
