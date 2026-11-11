// Ficha de pedido do manual 16 na tela do agente (Onda 2 de novembro: professor-07, analista_metricas-21,
// estrategista-25, sonoplasta-23). GET /api/fichas-pedido/{agente} entrega só a ficha daquele agente; agente sem
// ficha no manual não tem cartão. Os pedidos prontos colam o MODELO no campo (Lodge, data e nome viram lacunas), da
// empresa escolhida no seletor quando houver exemplo dela.

const fichasPedido = {}; // agente -> ficha | null (sem ficha no manual)
const carregandoFichas = new Set();
const MAX_PEDIDOS_PRONTOS = 3;

function limparFichasPedido() {
  Object.keys(fichasPedido).forEach((k) => delete fichasPedido[k]);
}

async function carregarFichaPedido(andar, agente) {
  if (!sessao || carregandoFichas.has(agente)) return;
  carregandoFichas.add(agente);
  try {
    const resposta = await fetch(`/api/fichas-pedido/${encodeURIComponent(agente)}`, {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    fichasPedido[agente] = resposta.ok ? ((await resposta.json()).ficha || null) : null;
  } catch {
    return; // sem cartão desta vez; tenta de novo na próxima abertura
  } finally {
    carregandoFichas.delete(agente);
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

function pedidosProntos(ficha, empresa) {
  const exemplos = ficha.exemplos || [];
  const daEmpresa = exemplos.filter((e) => empresa && e.empresa === empresa);
  const gerais = exemplos.filter((e) => !e.empresa);
  return (daEmpresa.length ? [...daEmpresa, ...gerais] : (gerais.length ? gerais : exemplos)).slice(0, MAX_PEDIDOS_PRONTOS);
}

function listaFicha(titulo, itens, classe) {
  const bloco = novoEl('div', classe);
  bloco.append(novoEl('small', null, titulo));
  const ul = novoEl('ul');
  itens.forEach((t) => ul.append(novoEl('li', null, t)));
  bloco.append(ul);
  return bloco;
}

function usarPedidoPronto(texto) {
  if (modalInput.disabled) return;
  modalInput.value = texto;
  ajustarAlturaInput();
  modalInput.focus();
}

// Cartão para a ficha do agente (null enquanto carrega ou quando o manual não tem ficha dele).
function criarFichaPedido(andar, agente) {
  if (!(agente in fichasPedido)) {
    carregarFichaPedido(andar, agente);
    return null;
  }
  const ficha = fichasPedido[agente];
  if (!ficha) return null;
  const cartao = novoEl('div', 'ficha-pedido');
  cartao.append(novoEl('h4', null, 'Ficha de pedido'));
  if (ficha.obrigatorio?.length) cartao.append(listaFicha('O que eu preciso receber', ficha.obrigatorio, 'ficha-obrigatorio'));
  if (ficha.opcional?.length) cartao.append(listaFicha('Opcional', ficha.opcional, 'ficha-opcional'));
  (ficha.notas || []).forEach((n) => {
    const nota = novoEl('p', 'ficha-nota');
    nota.append(novoEl('strong', null, `${n.rotulo}: `), document.createTextNode(n.texto));
    cartao.append(nota);
  });
  const prontos = pedidosProntos(ficha, empresaDaConversa(andar, agente));
  if (prontos.length) {
    const bloco = novoEl('div', 'ficha-prontos');
    bloco.append(novoEl('small', null, 'Pedidos prontos (clique e complete as lacunas)'));
    prontos.forEach((e) => {
      const botao = novoEl('button', 'perfil-exemplo');
      botao.type = 'button';
      botao.title = 'Usar como modelo';
      botao.append(novoEl('small', null, e.rotulo ? `Exemplo · ${e.rotulo}` : 'Exemplo'), novoEl('span', null, `“${e.modelo || e.texto}”`));
      botao.addEventListener('click', () => usarPedidoPronto(e.modelo || e.texto));
      bloco.append(botao);
    });
    cartao.append(bloco);
  }
  if (ficha.geral) cartao.append(novoEl('p', 'ficha-geral', ficha.geral));
  return cartao;
}
