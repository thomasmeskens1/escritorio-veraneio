// Botão "Corrigir o mecânico" na legenda do chat (Onda 2 de novembro, copywriter-03; backend/conferente_rotas.py).
// Aparece quando a conferência automática apontou travessão, hashtag ou "Cidade / UF". Sem IA: o servidor faz só as
// trocas que não mudam o sentido e devolve o antes e o depois; nada é gravado, a pessoa copia se quiser.

const MECANICO_AVISO = /Conferência automática/;
const MECANICO_ITENS = /travess|hashtag|Cidade \/ UF/i;

function textoDaMensagem(div) {
  return [...div.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join('');
}

function blocoMecanico(titulo, texto) {
  const bloco = document.createElement('div');
  const rotulo = document.createElement('strong');
  rotulo.textContent = titulo;
  const pre = document.createElement('pre');
  pre.style.whiteSpace = 'pre-wrap';
  pre.style.margin = '4px 0 8px';
  pre.textContent = texto;
  bloco.append(rotulo, pre);
  return bloco;
}

function mostrarMecanico(div, dados) {
  div.querySelector('.msg-mecanico-painel')?.remove();
  const painel = document.createElement('div');
  painel.className = 'msg-mecanico-painel';
  if (!dados.antes || !dados.trocas?.length) {
    painel.textContent = dados.antes ? 'Nada mecânico para corrigir nesta legenda.' : 'Não achei a legenda nesta resposta.';
    div.append(painel);
    return;
  }
  const trocas = document.createElement('ul');
  dados.trocas.forEach((t) => trocas.append(Object.assign(document.createElement('li'), { textContent: t })));
  painel.append(blocoMecanico('Antes', dados.antes), blocoMecanico('Depois', dados.depois), trocas);
  if (dados.avisos?.length) {
    painel.append(blocoMecanico('Continua para você conferir (não é mecânico)', dados.avisos.map((a) => `- ${a}`).join('\n')));
  }
  const copiar = document.createElement('button');
  copiar.type = 'button';
  copiar.className = 'botao-secundario msg-ajuste';
  copiar.textContent = 'Copiar a legenda corrigida';
  copiar.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(dados.depois);
      copiar.textContent = 'Copiada';
    } catch {
      copiar.textContent = 'Não consegui copiar: selecione o texto acima';
    }
  });
  painel.append(copiar);
  div.append(painel);
}

function criarBotaoMecanico(div) {
  const botao = document.createElement('button');
  botao.type = 'button';
  botao.className = 'botao-secundario msg-ajuste msg-mecanico';
  botao.textContent = 'Corrigir o mecânico';
  botao.title = 'Troca só travessão, hashtag e "Cidade / UF" na legenda, sem IA. Você vê o antes e o depois.';
  botao.addEventListener('click', async () => {
    if (!sessao || botao.disabled) return;
    botao.disabled = true;
    try {
      const empresa = chatAberto ? empresaDaConversa(chatAberto.andar, chatAberto.agente) : '';
      const resposta = await fetch('/api/conferencia/mecanico', {
        method: 'POST',
        headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto: textoDaMensagem(div), empresa: empresa === '*' ? '' : (empresa || '') }),
      });
      const dados = await resposta.json().catch(() => ({}));
      if (resposta.ok) mostrarMecanico(div, dados);
      else mostrarMecanico(div, { antes: '' });
    } catch {
      mostrarMecanico(div, { antes: '' });
    } finally {
      botao.disabled = false;
    }
  });
  return botao;
}

function marcarMensagensComLegenda(raiz) {
  raiz.querySelectorAll('.msg-agente').forEach((div) => {
    if (div.querySelector('.msg-mecanico')) return;
    const texto = textoDaMensagem(div);
    if (MECANICO_AVISO.test(texto) && MECANICO_ITENS.test(texto)) div.append(criarBotaoMecanico(div));
  });
}

new MutationObserver(() => marcarMensagensComLegenda(modalHistorico))
  .observe(modalHistorico, { childList: true });
