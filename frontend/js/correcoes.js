// Correções que viram regra (ficha do Cérebro, só o Thomas): cada correção dele a um agente aparece aqui para
// virar regra (deste agente ou de todos) ou ser descartada; as regras ativas ficam listadas, com "Desativar".

const correcoes = { dados: null, erro: '', oculto: true };

async function carregarCorrecoes(andar, agente) {
  if (!sessao) return;
  try {
    const resposta = await fetch('/api/correcoes', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.status === 403 || resposta.status === 404) {
      Object.assign(correcoes, { dados: null, erro: '', oculto: true });
    } else if (!resposta.ok) {
      Object.assign(correcoes, { erro: 'Não foi possível carregar as correções.', oculto: false });
    } else {
      Object.assign(correcoes, { dados: await resposta.json(), erro: '', oculto: false });
    }
  } catch {
    Object.assign(correcoes, { erro: 'Servidor indisponível.', oculto: false });
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

// Tipos de observação (backend/correcoes.py, avaliacoes.py e consolidacao_semanal.py).
const rotuloObservacao = (tipo) => ({ elogio: '👍 Elogio', aprendizado: '🧠 Aprendizado da semana' }[tipo] || '✏️ Correção');

async function decidirCorrecao(caminho, corpo) {
  const { andar, agente } = chatAberto || {};
  try {
    const resposta = await fetch(`/api/correcoes/${caminho}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    if (!resposta.ok) throw new Error((await resposta.json().catch(() => ({}))).detail || resposta.status);
  } catch (erro) {
    correcoes.erro = `Não foi possível salvar: ${erro.message}`;
  }
  if (andar) carregarCorrecoes(andar, agente);
}

// Pop-up de uma correção ou elogio: a mensagem inteira, a resposta do agente e as três decisões (só aqui).
function abrirCorrecao(o) {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-usuario');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, `${rotuloObservacao(o.tipo)} · ${o.agente_nome}`),
    novoEl('p', null, `${o.autor ? `por ${o.autor} · ` : ''}${formatarQuando(o.em)}`));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);

  const corpo = novoEl('div', 'formulario-corpo usuario-corpo');
  const mensagem = novoEl('div', 'reg-mensagem reg-pedido');
  mensagem.append(novoEl('strong', null, `Mensagem de ${o.autor || 'quem escreveu'}`), novoEl('p', null, o.correcao));
  corpo.append(mensagem);
  if (o.resposta_anterior) {
    const resposta = novoEl('div', 'reg-mensagem reg-resposta');
    resposta.append(novoEl('strong', null, o.tipo === 'aprendizado' ? 'Evidência da semana'
      : `Resposta do ${o.agente_nome} que motivou`), novoEl('p', null, o.resposta_anterior));
    corpo.append(resposta);
  }
  const rotulo = novoEl('label', 'form-rotulo', 'Regra que vai valer (edite antes de aprovar)');
  const regra = novoEl('textarea', 'form-entrada');
  regra.id = `correcao-regra-${o.id}`;
  rotulo.htmlFor = regra.id;
  regra.rows = 3;
  regra.value = o.tipo === 'elogio' ? `Seguir este padrão aprovado por ${o.autor || 'a equipe'}: ${o.correcao}` : o.correcao;
  if (o.tipo === 'aprendizado') mensagem.firstChild.textContent = 'Aprendizado proposto pelo Cérebro (consolidação semanal)';
  const acoes = novoEl('div', 'usuario-acoes');
  const decidir = (caminho, corpoPedido) => async () => {
    acoes.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    await decidirCorrecao(caminho, corpoPedido?.());
    fecharFormularioPopup();
  };
  const botao = (texto, classe, acao) => {
    const b = novoEl('button', classe, texto);
    b.type = 'button';
    b.addEventListener('click', acao);
    return b;
  };
  acoes.append(
    botao(`Aprovar para o ${o.agente_nome}`, 'botao-primario',
      decidir(`${o.id}/aprovar`, () => ({ regra: regra.value, escopo: 'agente' }))),
    botao('Aprovar para o Cérebro (todos os agentes)', 'botao-secundario',
      decidir(`${o.id}/aprovar`, () => ({ regra: regra.value, escopo: 'todos' }))),
    botao('Descartar', 'botao-secundario botao-perigo', decidir(`${o.id}/descartar`)),
  );
  corpo.append(rotulo, regra, acoes);
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  regra.focus();
}

// Consolidação semanal (toda segunda, 07:00): o master pode rodar agora. O Max lê a semana e os itens chegam aqui.
function criarBotaoConsolidar() {
  const botao = novoEl('button', 'botao-secundario', 'Consolidar a semana agora');
  botao.type = 'button';
  botao.title = 'O Max lê as tarefas, 👍/👎, elogios e correções da semana e propõe aprendizados para aprovar';
  botao.addEventListener('click', async () => {
    botao.disabled = true;
    try {
      const resposta = await fetch('/api/cerebro/consolidar', { method: 'POST', headers: { Authorization: `Bearer ${sessao.token}` } });
      const dados = await resposta.json().catch(() => ({}));
      botao.textContent = dados.mensagem || dados.detail || 'Não foi possível iniciar.';
    } catch {
      botao.textContent = 'Sem conexão com o servidor.';
    }
  });
  return botao;
}

function criarCorrecoes() {
  const bloco = novoEl('div', 'perfil-correcoes');
  const d = correcoes.dados;
  const n = d?.observacoes?.length || 0;
  bloco.append(novoEl('h4', null, n ? `Correções e elogios para revisar (${n})` : 'Correções e elogios para revisar'));
  if (correcoes.erro) bloco.append(novoEl('p', 'rotinas-nota erro', correcoes.erro));
  if (sessao?.master) bloco.append(criarBotaoConsolidar());
  if (!d) return bloco;
  if (!n) {
    bloco.append(novoEl('p', 'rotinas-nota', 'Nenhuma pendente. Quando alguém corrigir um agente ("não é assim…", '
      + '"na verdade…") ou elogiar uma resposta ("adorei, podemos seguir assim"), aparece aqui para virar regra.'));
  }
  // Uma linha por observação (como o painel de usuários); o clique abre o pop-up com a mensagem inteira e as
  // decisões (Thomas, 29/10/2026).
  const lista = novoEl('ul', 'correcoes-lista');
  d.observacoes.forEach((o) => {
    const item = novoEl('li');
    const linha = novoEl('button', 'correcao-linha');
    linha.type = 'button';
    linha.title = 'Abrir para aprovar ou descartar';
    linha.append(novoEl('small', 'correcao-meta', `${rotuloObservacao(o.tipo)} · `
      + `${o.agente_nome}${o.autor ? ` · por ${o.autor}` : ''} · ${formatarQuando(o.em)}`),
    novoEl('span', 'correcao-previa', o.correcao.replace(/\s+/g, ' ').slice(0, 110)), novoEl('span', 'usuario-seta', '›'));
    linha.addEventListener('click', () => abrirCorrecao(o));
    item.append(linha);
    lista.append(item);
  });
  bloco.append(lista);
  if (d.regras?.length) {
    const regras = novoEl('details', 'correcao-regras');
    regras.append(novoEl('summary', null, `Regras aprendidas ativas (${d.regras.length})`));
    d.regras.forEach((r) => {
      const linha = novoEl('div', 'correcao-regra-ativa');
      const desativar = novoEl('button', 'botao-secundario', 'Desativar');
      desativar.type = 'button';
      desativar.addEventListener('click', () => { desativar.disabled = true; decidirCorrecao(`regras/${r.id}/desativar`); });
      linha.append(novoEl('span', null, `${r.agente_nome}: ${r.regra}`), desativar);
      regras.append(linha);
    });
    bloco.append(regras);
  }
  return bloco;
}
