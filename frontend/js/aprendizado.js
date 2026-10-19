// Seção "Aprendizado do Despachante" do painel: marcos de treino, modelo e ajustes automáticos.

const porcento = (v) => `${Math.round((Number(v) || 0) * 100)}%`;
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

function seloDificuldade(dificuldade) {
  return novoEl('span', `selo selo-${dificuldade}`, ROTULOS_DIFICULDADE[dificuldade] || dificuldade || '—');
}

// Degraus 10 → 50 → 100 → 200: cada um enche conforme as tarefas registradas.
function criarMarcos(registradas, marcos) {
  const lista = novoEl('ol', 'marcos');
  lista.setAttribute('aria-label', 'Marcos de treino');
  let anterior = 0;
  marcos.forEach((marco) => {
    const progresso = Math.min(1, Math.max(0, (registradas - anterior) / (marco - anterior)));
    const item = novoEl('li', 'marco');
    if (progresso >= 1) item.classList.add('feito');
    else if (progresso > 0 || registradas === anterior) item.classList.add('atual');
    const trilho = novoEl('span', 'marco-trilho');
    const enche = novoEl('i');
    enche.style.width = `${progresso * 100}%`;
    trilho.append(enche);
    item.append(trilho, novoEl('span', 'marco-rotulo', progresso >= 1 ? `✓ ${marco}` : String(marco)));
    item.title = progresso >= 1 ? `Treino com ${marco} tarefas concluído` : `Treino ao chegar a ${marco} tarefas`;
    lista.append(item);
    anterior = marco;
  });
  return lista;
}

function barraAcuracia(rotulo, valor, classe) {
  const linha = novoEl('div', `acuracia ${classe}`);
  const barra = novoEl('span', 'acuracia-barra');
  const enche = novoEl('i');
  enche.style.width = porcento(Math.min(1, Math.max(0, valor)));
  barra.append(enche);
  linha.append(novoEl('span', 'acuracia-rotulo', rotulo), barra, novoEl('strong', null, porcento(valor)));
  return linha;
}

function criarModeloTreinado(modelo, primeiroMarco) {
  const caixa = novoEl('div', 'aprendizado-modelo');
  if (!modelo) {
    caixa.classList.add('sem-modelo');
    caixa.append(
      novoEl('strong', null, 'Nenhum modelo treinado ainda'),
      novoEl('span', null, `As regras fixas decidem a dificuldade até o primeiro treino, com ${primeiroMarco} tarefas.`),
    );
    return caixa;
  }
  const topo = novoEl('div', 'aprendizado-modelo-topo');
  topo.append(
    novoEl('strong', null, 'Modelo treinado'),
    novoEl('span', `selo-modelo ${modelo.ativo ? 'ativo' : 'inativo'}`, modelo.ativo ? 'Ativo' : 'Inativo'),
  );
  const quando = formatarQuando(modelo.treinado_em);
  const treinado = /^(há|agora|—)/.test(quando) ? quando : `em ${quando}`;
  const info = novoEl('small', null, `${plural(modelo.amostras ?? 0, 'amostra', 'amostras')} · treinado ${treinado}`);
  caixa.append(
    topo, info,
    barraAcuracia('Modelo', modelo.acuracia, 'do-modelo'),
    barraAcuracia('Regras fixas', modelo.acuracia_regras, 'das-regras'),
  );
  if (!modelo.ativo) caixa.append(novoEl('small', 'aprendizado-nota', 'As regras fixas ainda acertam mais — o modelo só assume quando superá-las.'));
  return caixa;
}

function criarAjustes(ajustes) {
  const bloco = novoEl('div', 'ajustes');
  bloco.append(novoEl('h4', null, 'Ajustes automáticos'));
  if (!ajustes.length) {
    bloco.append(novoEl('p', 'aprendizado-nota', 'Nenhum ajuste automático até agora.'));
    return bloco;
  }
  const lista = novoEl('ul');
  ajustes.forEach((a) => {
    const item = novoEl('li');
    const linha = novoEl('div', 'ajuste-linha');
    linha.append(novoEl('strong', null, a.agente_nome || a.agente || '—'), seloDificuldade(a.de), novoEl('span', 'ajuste-seta', '→'), seloDificuldade(a.para));
    item.append(linha);
    if (a.motivo) item.append(novoEl('small', null, a.motivo));
    lista.append(item);
  });
  bloco.append(lista);
  return bloco;
}

function criarAprendizado(aprendizado) {
  if (!aprendizado || typeof aprendizado !== 'object') return null;
  const {
    tarefas_registradas: registradas = 0, marcos = [10, 50, 100, 200], janela = 200,
    retreino_a_cada: retreino = 50, proximo_treino_em: proximo, modelo = null, ajustes = [],
  } = aprendizado;
  const caixa = novoEl('section', 'credito aprendizado');
  caixa.append(novoEl('h3', null, 'Aprendizado do Despachante'));

  const resumo = novoEl('p', 'aprendizado-resumo');
  resumo.append(novoEl('strong', null, registradas), document.createTextNode(registradas === 1 ? ' tarefa registrada' : ' tarefas registradas'));
  if (proximo != null) {
    resumo.append(document.createTextNode(' · próximo treino em '), novoEl('strong', null, proximo), document.createTextNode(proximo === 1 ? ' tarefa' : ' tarefas'));
  }
  caixa.append(resumo);
  if (!registradas) {
    caixa.append(novoEl('p', 'aprendizado-nota', 'O Despachante aprende com cada tarefa concluída. Envie tarefas aos agentes e acompanhe a evolução aqui.'));
  }

  const ordenados = [...marcos].map(Number).filter((m) => m > 0).sort((a, b) => a - b);
  if (ordenados.length) caixa.append(criarMarcos(registradas, ordenados));
  if (ordenados.length && registradas >= ordenados[ordenados.length - 1]) {
    caixa.append(novoEl('p', 'aprendizado-nota', `Janela de ${janela} tarefas, retreino a cada ${retreino}.`));
  }

  const corpo = novoEl('div', 'aprendizado-corpo');
  corpo.append(criarModeloTreinado(modelo, ordenados[0] ?? 10), criarAjustes(Array.isArray(ajustes) ? ajustes : []));
  caixa.append(corpo);
  return caixa;
}
