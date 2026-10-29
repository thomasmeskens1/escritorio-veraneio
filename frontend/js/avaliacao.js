// 👍/👎 nas respostas dos agentes (Thomas, 29/10/2026): ensina o Cérebro quais conhecimentos ajudaram.
// Clicar de novo no voto marcado retira o voto. Depois do 👎 abre um campo opcional "o que faltou?", que vai para a
// Diretoria aprovar como correção (backend/avaliacoes.py).

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
        comentario.hidden = valor !== -1;
        if (!comentario.hidden) campo.focus();
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

  const comentario = novoEl('form', 'msg-voto-comentario');
  comentario.hidden = true;
  const campo = novoEl('input');
  campo.type = 'text';
  campo.maxLength = 1000;
  campo.placeholder = 'O que faltou? (opcional, vai para a Diretoria)';
  const enviar = novoEl('button', 'botao-secundario', 'Enviar');
  enviar.type = 'submit';
  comentario.append(campo, enviar);
  comentario.addEventListener('submit', async (e) => {
    e.preventDefault();
    const texto = campo.value.trim();
    if (!texto) return;
    enviar.disabled = true;
    if (await enviarAvaliacao(tarefaId, -1, texto)) comentario.replaceWith(novoEl('span', 'msg-encerrado', 'Obrigado! A Diretoria vai avaliar.'));
    else enviar.disabled = false;
  });

  marcar();
  caixa.append(...botoes, comentario);
  return caixa;
}
