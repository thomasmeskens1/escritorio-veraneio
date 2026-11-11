// Planejamento do mês em tabela (Onda 2 de novembro, social_media-05): o Gestor fecha o planejamento com uma tabela
// (backend/plano_tabela.py). No chat, o marcador "[Tabela do planejamento #N: ...]" vira a tabela: a pessoa marca as
// peças, muda a data e o Lodge e clica em "Gravar no Monday (N peças)". O servidor grava EXATAMENTE as linhas
// marcadas, pelo código (sem o modelo reinterpretar). Linha já gravada fica travada, com o resultado do Monday.

const MARCADOR_PLANO = /\[Tabela do planejamento #(\d+): \d+ peças?[^\]]*\]/;

// {texto sem o marcador, tabela: elemento | null}. Chamado por criarMensagem (js/chat.js).
function extrairPlanoTabela(texto) {
  const achado = MARCADOR_PLANO.exec(String(texto || ''));
  if (!achado) return { texto, tabela: null };
  return { texto: String(texto).replace(MARCADOR_PLANO, '').trim(), tabela: criarPlanoTabela(Number(achado[1])) };
}

function estiloPlanoTabela() {
  if (document.getElementById('estilo-plano-tabela')) return;
  const estilo = document.createElement('style');
  estilo.id = 'estilo-plano-tabela';
  estilo.textContent = `
    .plano-tabela { margin-top: 8px; display: grid; gap: 8px; }
    .plano-rolagem { overflow-x: auto; max-width: 100%; }
    .plano-tabela table { border-collapse: collapse; font-size: 0.85em; min-width: 560px; width: 100%; }
    .plano-tabela th, .plano-tabela td { border-bottom: 1px solid color-mix(in srgb, currentColor 18%, transparent);
      padding: 4px 6px; text-align: left; vertical-align: top; }
    .plano-tabela input[type=date] { width: 9.5em; }
    .plano-tabela input.plano-lodge { width: 4.5em; }
    .plano-tabela .plano-aviso { font-size: 0.85em; opacity: 0.8; }
    .plano-tabela tr.plano-gravada { opacity: 0.6; }
    .plano-acoes { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }`;
  document.head.append(estilo);
}

async function chamarPlano(caminho, corpo) {
  const resposta = await fetch(`/api/plano/${caminho}`, corpo ? {
    method: 'POST',
    headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  } : { headers: { Authorization: `Bearer ${sessao.token}` } });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || `erro ${resposta.status}`);
  return dados;
}

function criarPlanoTabela(tarefaId) {
  estiloPlanoTabela();
  const caixa = novoEl('div', 'plano-tabela', 'Carregando a tabela do planejamento…');
  if (sessao) {
    chamarPlano(String(tarefaId))
      .then((dados) => desenharPlanoTabela(caixa, tarefaId, dados.linhas || [], dados.monday))
      .catch((erro) => { caixa.textContent = `Não foi possível abrir a tabela: ${erro.message}`; });
  }
  return caixa;
}

function celula(conteudo) {
  const td = document.createElement('td');
  if (conteudo instanceof Node) td.append(conteudo);
  else td.textContent = conteudo || '—';
  return td;
}

function desenharPlanoTabela(caixa, tarefaId, linhas, mondayLigado, mensagem = '') {
  const tabela = document.createElement('table');
  const cabeca = document.createElement('tr');
  ['', 'Data', 'Formato', 'Tema', 'Lodge', 'Papel', 'Avisos'].forEach((t) => cabeca.append(novoEl('th', null, t)));
  tabela.append(cabeca);
  const campos = linhas.map((l) => {
    const tr = document.createElement('tr');
    const marca = document.createElement('input');
    marca.type = 'checkbox';
    marca.checked = !l.gravado;
    marca.disabled = Boolean(l.gravado);
    marca.setAttribute('aria-label', `Gravar ${l.tema}`);
    const data = document.createElement('input');
    data.type = 'date';
    data.className = 'form-entrada';
    data.value = l.data || '';
    const lodge = document.createElement('input');
    lodge.className = 'form-entrada plano-lodge';
    lodge.inputMode = 'numeric';
    lodge.maxLength = 4;
    lodge.value = l.lodge || '';
    if (l.gravado) { data.disabled = true; lodge.disabled = true; tr.className = 'plano-gravada'; }
    const avisos = l.gravado ? `No Monday: ${l.gravado}` : (l.avisos || []).join('; ');
    tr.append(celula(marca), celula(data), celula(l.tipo), celula(l.tema), celula(lodge), celula(l.papel),
      celula(novoEl('span', 'plano-aviso', avisos || '—')));
    tabela.append(tr);
    return { linha: l, marca, data, lodge };
  });
  const rolagem = novoEl('div', 'plano-rolagem');
  rolagem.append(tabela);
  const acoes = novoEl('div', 'plano-acoes');
  const gravarBotao = novoEl('button', 'botao-primario');
  gravarBotao.type = 'button';
  const tudoBotao = novoEl('button', 'botao-secundario msg-ajuste', 'Gravar tudo');
  tudoBotao.type = 'button';
  const aviso = novoEl('span', 'plano-aviso', mensagem || (mondayLigado === false ? 'O Monday não está ligado neste servidor.' : ''));
  const abertos = () => campos.filter((c) => !c.linha.gravado);
  const contar = () => {
    const n = abertos().filter((c) => c.marca.checked).length;
    gravarBotao.textContent = `Gravar no Monday (${n} peça${n === 1 ? '' : 's'})`;
    gravarBotao.disabled = n === 0 || mondayLigado === false;
    tudoBotao.disabled = !abertos().length || mondayLigado === false;
  };
  campos.forEach((c) => c.marca.addEventListener('change', contar));
  const gravar = async (escolhidos) => {
    if (!escolhidos.length) return;
    gravarBotao.disabled = true;
    tudoBotao.disabled = true;
    aviso.textContent = 'Gravando no Monday…';
    try {
      const dados = await chamarPlano(`${tarefaId}/gravar`, {
        linhas: escolhidos.map((c) => ({ indice: c.linha.indice, data: c.data.value || '', lodge: c.lodge.value.trim() })),
      });
      const erros = dados.resultado.filter((r) => !r.ok).map((r) => r.texto);
      const resumo = `${dados.criados} de ${dados.pedidas} peça(s) gravada(s) no Monday.${erros.length ? ` Falhou: ${erros.join(' | ')}` : ''}`;
      desenharPlanoTabela(caixa, tarefaId, dados.linhas, mondayLigado, resumo);
    } catch (erro) {
      aviso.textContent = `Não gravou: ${erro.message}`;
      contar();
    }
  };
  gravarBotao.addEventListener('click', () => gravar(abertos().filter((c) => c.marca.checked)));
  tudoBotao.addEventListener('click', () => gravar(abertos()));
  acoes.append(gravarBotao, tudoBotao, aviso);
  caixa.replaceChildren(rolagem, acoes);
  contar();
}
