// Relatório do "Treinar agora" (Thomas, 29/10/2026): o que foi aprendido e por quê, desde o treino anterior.
// Duas frentes: o roteamento (dificuldade dos pedidos -> rota de modelos) e o Cérebro (conhecimento, uso, regras).

let ultimoRelatorioTreino = null;

const porcentoTreino = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);

function blocoTreino(titulo, explicacao) {
  const bloco = novoEl('section', 'treino-bloco');
  bloco.append(novoEl('h3', null, titulo));
  if (explicacao) bloco.append(novoEl('p', 'treino-explica', explicacao));
  return bloco;
}

function listaTreino(itens) {
  const ul = novoEl('ul', 'treino-lista');
  itens.forEach((t) => ul.append(novoEl('li', null, t)));
  return ul;
}

function contagensTreino(objeto) {
  return listaTreino(Object.entries(objeto || {}).map(([nome, n]) => `${nome}: ${n.toLocaleString('pt-BR')}`));
}

function abrirRelatorioTreino(r = ultimoRelatorioTreino) {
  if (!r) return;
  ultimoRelatorioTreino = r;
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-treino');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  const desde = new Date(r.desde).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  titulo.append(novoEl('h2', null, 'O que foi aprendido'),
    novoEl('p', null, r.primeiro_treino ? 'Últimos 7 dias (primeiro treino)' : `Desde o treino anterior (${desde})`));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);
  const corpo = novoEl('div', 'formulario-corpo treino-corpo');

  // 1. Roteamento
  const ro = r.roteamento;
  const rota = blocoTreino('1. Rota dos pedidos (dificuldade)',
    'O "Treinar agora" treina o classificador que decide se um pedido é simples, médio ou complexo. A dificuldade '
    + 'define a rota: modelos gratuitos, Max, fila do Claude e quanto tempo cada um tem.');
  const numeros = novoEl('div', 'treino-numeros');
  [[ro.amostras, 'tarefas analisadas'], [porcentoTreino(ro.acuracia), 'acerto do modelo'],
    [porcentoTreino(ro.acuracia_regras), 'acerto das regras fixas'], [ro.ativo ? 'Modelo' : 'Regras', 'decidindo agora']]
    .forEach(([n, rotulo]) => {
      const cartao = novoEl('div', 'conhecimento-cartao');
      cartao.append(novoEl('strong', null, String(n)), novoEl('span', null, rotulo));
      numeros.append(cartao);
    });
  rota.append(numeros, novoEl('p', 'treino-porque', `Por quê: ${ro.porque}`));
  rota.append(novoEl('h4', null, 'Como os pedidos realmente se comportaram (tempo e fila)'), contagensTreino(ro.observado));
  rota.append(novoEl('h4', null, 'Como as regras tinham classificado'), contagensTreino(ro.classificado));
  rota.append(novoEl('h4', null, 'Ajustes automáticos por agente'), ro.ajustes.length
    ? listaTreino(ro.ajustes.map((a) => `${a.agente}: ${a.de} → ${a.para} (${a.motivo})`))
    : novoEl('p', 'treino-explica', 'Nenhum: os agentes estão sendo classificados no nível certo.'));

  // 2. Cérebro
  const c = r.cerebro;
  const cerebro = blocoTreino('2. Cérebro (aprende sozinho, o tempo todo)',
    'Toda tarefa concluída vira conhecimento; o site, o Drive, os manuais e o painel são relidos; os trechos que '
    + 'ajudam em tarefas bem-sucedidas ganham prioridade nas próximas buscas; correções e elogios aprovados viram regra.');
  cerebro.append(novoEl('h4', null, `Conhecimento novo ou atualizado: ${c.novos_total.toLocaleString('pt-BR')} trechos`),
    contagensTreino(c.por_fonte), novoEl('h4', null, 'Por empresa'), contagensTreino(c.por_empresa));
  if (c.ultimos.length) {
    cerebro.append(novoEl('h4', null, 'Últimos que entraram'),
      listaTreino(c.ultimos.map((u) => `${u.titulo} — ${u.fonte}, ${u.empresa}`)));
  }
  cerebro.append(novoEl('h4', null, `Consultas dos agentes: ${c.consultas} (${c.consultas_sucesso} em tarefas que deram certo)`),
    contagensTreino(c.por_agente));
  if (c.mais_usados.length) {
    cerebro.append(novoEl('h4', null, 'O que mais ajudou (por isso ganha prioridade)'),
      listaTreino(c.mais_usados.map((m) => `${m.titulo} — ${m.fonte} · usado ${m.vezes}x`)));
  }
  cerebro.append(novoEl('h4', null, 'Regras aprovadas no período'), c.regras_aprovadas.length
    ? listaTreino(c.regras_aprovadas.map((g) => `${g.agente}: ${g.regra}`))
    : novoEl('p', 'treino-explica', 'Nenhuma regra nova.'));
  const pend = Object.entries(c.pendentes || {});
  cerebro.append(novoEl('p', 'treino-porque', pend.length
    ? `Esperando a Diretoria aprovar: ${pend.map(([k, n]) => `${n} ${k}`).join(' e ')} (lista "Correções e elogios").`
    : 'Nenhuma correção ou elogio esperando aprovação.'));

  corpo.append(rota, cerebro);

  // 3. Rede neural do Cérebro (backend/reranker.py)
  const rd = r.rede;
  if (rd) {
    const rede = blocoTreino('3. Rede neural do Cérebro',
      'Aprende, com os 👍/👎, elogios e correções, quais conhecimentos realmente ajudam nas respostas. Só passa a '
      + 'reordenar as buscas quando prova que acerta mais que a ordem atual.');
    const nums = novoEl('div', 'treino-numeros');
    [[`${rd.exemplos}/${rd.minimo}`, 'exemplos rotulados'], [rd.positivos, 'ajudaram'], [rd.negativos, 'atrapalharam'],
      [rd.ativo ? 'Ativa' : 'Aprendendo', 'situação']].forEach(([n, rotulo]) => {
      const cartao = novoEl('div', 'conhecimento-cartao');
      cartao.append(novoEl('strong', null, String(n)), novoEl('span', null, rotulo));
      nums.append(cartao);
    });
    rede.append(nums);
    if (rd.observacao) rede.append(novoEl('p', 'treino-porque', rd.observacao));
    // Prova do Cérebro (backend/cerebro_prova.py): perguntas de gabarito conferidas na busca, antes e depois do treino
    if (rd.prova?.observacao) rede.append(novoEl('p', 'treino-porque', rd.prova.observacao));
    corpo.append(rede);
  }

  // 4. Modelos (backend/corrida.py): ordem, tempo de espera e corrida aprendidos com o histórico
  if (r.modelos?.length) {
    const modelos = blocoTreino('4. Modelos: quem responde melhor',
      'Os modelos gratuitos são tentados na ordem do menor tempo esperado (o tempo típico de resposta + a chance de '
      + 'falhar). Se o primeiro passa do tempo em que costuma responder, o segundo começa junto e vale a primeira '
      + 'resposta boa.');
    modelos.append(listaTreino(r.modelos.slice(0, 8).map((m) => `${m.modelo.split('/').pop()}: `
      + `${Math.round(m.taxa * 100)}% de acerto em ${m.tentativas} tentativas`
      + (m.p50 != null ? `, costuma responder em ${Math.round(m.p50)} s` : ', ainda sem resposta boa'))));
    corpo.append(modelos);
  }
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  fechar.focus();
}
