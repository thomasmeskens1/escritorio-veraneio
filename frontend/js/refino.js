// Botões nas respostas de texto e título da aba (Onda 1 de 11/11/2026, Térreo). Os textos ficam em js/chat_textos.js.
// - Ajustes rápidos ("Mais curto", "Mais informal", "Mais fluido", "3 variações"): só na última resposta do Copywriter
//   e do E-mail Marketing; o clique envia um pedido comum, com a ordem de manter igual o que não foi pedido.
// - "Levar para uma Peça final" (Copywriter): abre o Gestor na mesma empresa com o campo preenchido. NÃO envia.
// - Título da aba: "(2) Escritório Veraneio" quando chegam respostas com a aba escondida.

const TITULO_BASE = document.title;
let respostasNovas = 0;

const podeLevarAoGestor = () => !!estadoAgentes.marketing?.gestor && !agenteBloqueado('marketing', 'gestor');

// Extras abaixo de uma resposta de texto (chamado por criarMensagem, js/chat.js); null quando não se aplica.
function criarExtrasDoTexto(texto) {
  if (!chatAberto || /^✅ Pedido concluído/.test(texto || '')) return null;
  const { agente } = chatAberto;
  const ajustes = AGENTES_AJUSTE_RAPIDO.includes(agente);
  const peca = agente === 'copywriter' && podeLevarAoGestor();
  if (!ajustes && !peca) return null;
  const grupo = novoEl('div', 'msg-opcoes msg-refino');
  if (ajustes) {
    AJUSTES_RAPIDOS.forEach(({ rotulo, texto: pedido }) => {
      const botao = novoEl('button', 'botao-secundario msg-ajuste msg-ajuste-rapido', rotulo);
      botao.type = 'button';
      botao.title = 'Envia o pedido de ajuste desta resposta, mantendo igual o resto';
      botao.addEventListener('click', () => {
        if (modalInput.disabled || modalEnviar.disabled) return; // um ajuste por vez: espera a resposta chegar
        modalInput.value = pedido;
        document.getElementById('modal-form').requestSubmit();
      });
      grupo.append(botao);
    });
  }
  if (peca) {
    const botao = novoEl('button', 'botao-secundario msg-ajuste', 'Levar para uma Peça final');
    botao.type = 'button';
    botao.title = 'Abre o Gestor com este texto já no campo; você completa o formato e envia';
    botao.addEventListener('click', () => levarParaPecaFinal(texto));
    grupo.append(botao);
  }
  return grupo;
}

function levarParaPecaFinal(texto) {
  if (!chatAberto) return;
  const empresa = empresaDaConversa(chatAberto.andar, chatAberto.agente);
  if (empresa) gravarEmpresa('marketing', 'gestor', empresa); // a empresa do destino é a da origem
  rascunhos[chave('marketing', 'gestor')] = textoParaPecaFinal(textoNatural(texto));
  abrirChat('marketing', 'gestor');
  const i = modalInput.value.indexOf(LACUNA_FORMATO);
  if (i < 0 || modalInput.disabled) return;
  modalInput.focus();
  modalInput.setSelectionRange(i, i + LACUNA_FORMATO.length); // digitar o formato substitui a lacuna
}

// Os ajustes rápidos aparecem só na última resposta da conversa (menos botões na tela).
function marcarUltimaResposta() {
  const respostas = modalHistorico.querySelectorAll('.msg-agente');
  respostas.forEach((m) => m.classList.remove('ultima-resposta'));
  respostas[respostas.length - 1]?.classList.add('ultima-resposta');
}
new MutationObserver(marcarUltimaResposta).observe(modalHistorico, { childList: true });

// Chamado por receberResposta (js/chat.js).
function contarRespostaNova() {
  if (!document.hidden) return;
  respostasNovas += 1;
  document.title = tituloComContador(TITULO_BASE, respostasNovas);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  respostasNovas = 0;
  document.title = TITULO_BASE;
});
