// Edição rápida sem o Max (Onda 3 de novembro; criador_imagens-03, designer-02, sonoplasta-02). Servidor:
// backend/edicao_rapida.py. "Editar textos" (artes da Casa Veraneio com molde) e "Outra música" (vídeos): o PC
// refaz só o necessário em código e o aviso de pronto chega depois neste chat. Usa janelaReferencia (js/referencias.js).

const ROTULOS_EDICAO = { kicker: 'Chamada (acima do título)', titulo: 'Título', subtitulo: 'Subtítulo', local: 'Local (Cidade / UF)',
  cta: 'CTA', linhas: 'Linhas (uma por linha)', contagem: 'Contagem' };
const MOLDES_EDICAO = { capa: 'Capa', ficha: 'Ficha do Lodge', fechamento: 'Fechamento', foto: 'Foto cheia' };

// Botões abaixo da entrega concluída pelo Max; [] quando não se aplicam.
function criarBotoesEdicaoRapida(tarefaId, texto) {
  if (!chatAberto || !tarefaId || !/^✅ Pedido concluído/.test(texto || '')) return [];
  const botoes = [];
  const empresa = empresaDaConversa(chatAberto.andar, chatAberto.agente);
  if (chatAberto.agente === 'criador_imagens' && empresa === 'casa_veraneio' && /\.png\b/i.test(texto)) {
    const editar = novoEl('button', 'botao-secundario msg-ajuste', 'Editar textos');
    editar.type = 'button';
    editar.title = 'Troca título, CTA ou contagem e refaz só os slides alterados, sem o Max (nova versão na mesma pasta)';
    editar.addEventListener('click', () => abrirEditarTextos(tarefaId, editar));
    botoes.push(editar);
  }
  if (/\.(mp4|mov)\b/i.test(texto)) {
    const musica = novoEl('button', 'botao-secundario msg-ajuste', 'Outra música');
    musica.type = 'button';
    musica.title = 'Refaz a versão com som com outra faixa aprovada da marca, sem o Max';
    musica.addEventListener('click', () => abrirOutraMusica(tarefaId));
    botoes.push(musica);
  }
  return botoes;
}

async function pedirEdicao(url, metodo, corpo) {
  const resposta = await fetch(url, {
    method: metodo,
    headers: { Authorization: `Bearer ${sessao.token}`, ...(corpo ? { 'Content-Type': 'application/json' } : {}) },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(typeof dados.detail === 'string' ? dados.detail : `erro ${resposta.status}`);
  return dados;
}

function avisoNoChat(texto) {
  if (chatAberto && texto) adicionarMensagem(chatAberto.andar, chatAberto.agente, { autor: 'sistema', texto, tipo: 'sistema' });
}

// --- Editar textos ---------------------------------------------------------------------------------------------

async function abrirEditarTextos(tarefaId, botao) {
  if (!sessao || botao.disabled) return;
  botao.disabled = true;
  botao.textContent = 'Lendo os textos…';
  let dados;
  try {
    dados = await pedirEdicao(`/api/producao/${tarefaId}/edicao/textos`, 'GET');
  } catch (erro) {
    avisoNoChat(erro.message || 'Não foi possível abrir os textos agora.');
    return;
  } finally {
    botao.disabled = false;
    botao.textContent = 'Editar textos';
  }
  if (!dados.ok) { avisoNoChat(dados.texto); return; }
  montarFormularioTextos(tarefaId, dados);
}

function campoDeTexto(id, rotulo, valor, limite, multilinha) {
  const caixa = novoEl('div');
  const nome = novoEl('label', 'form-rotulo', rotulo);
  const campo = novoEl(multilinha ? 'textarea' : 'input', 'form-entrada');
  campo.id = id;
  nome.htmlFor = id;
  campo.value = valor;
  if (multilinha) campo.rows = 3; else campo.maxLength = limite;
  const contador = novoEl('small', 'rotinas-nota');
  const contar = () => {
    const maior = Math.max(0, ...campo.value.split('\n').map((l) => l.length));
    contador.textContent = `${maior}/${limite}${multilinha ? ' por linha' : ''}`;
  };
  campo.addEventListener('input', contar);
  contar();
  caixa.append(nome, campo, contador);
  return { caixa, campo };
}

function montarFormularioTextos(tarefaId, { slides, limites }) {
  const corpo = janelaReferencia(`Editar textos · peça #${tarefaId}`,
    'Só os slides alterados são refeitos pelo molde, sem o Max, como nova versão na mesma pasta. O conferente confere antes de gravar.');
  const leitores = []; // { n, campo, antes, ler() }
  slides.filter((s) => Object.keys(s.campos || {}).length).forEach((slide) => {
    corpo.append(novoEl('h3', 'form-rotulo', `Slide ${slide.n} · ${MOLDES_EDICAO[slide.molde] || slide.molde}`));
    Object.entries(slide.campos).forEach(([campo, antes]) => {
      const id = `edicao-${tarefaId}-${slide.n}-${campo}`;
      if (campo === 'contagem') {
        const numero = campoDeTexto(`${id}-n`, 'Contagem: número', antes.numero || '', limites.contagem_numero);
        const texto = campoDeTexto(`${id}-t`, 'Contagem: texto (ex.: noites para o Réveillon)', antes.texto || '', limites.contagem_texto);
        corpo.append(numero.caixa, texto.caixa);
        leitores.push({ n: slide.n, campo, antes, ler: () => ({ numero: numero.campo.value.trim(), texto: texto.campo.value.trim() }) });
      } else if (campo === 'linhas') {
        const linhas = campoDeTexto(id, ROTULOS_EDICAO.linhas, (antes || []).join('\n'), limites.linha, true);
        corpo.append(linhas.caixa);
        leitores.push({ n: slide.n, campo, antes, ler: () => linhas.campo.value.split('\n').map((l) => l.trim()).filter(Boolean) });
      } else {
        const simples = campoDeTexto(id, ROTULOS_EDICAO[campo] || campo, antes || '', limites[campo] || 80);
        corpo.append(simples.caixa);
        leitores.push({ n: slide.n, campo, antes, ler: () => simples.campo.value.trim() });
      }
    });
  });
  const aviso = novoEl('p', 'rotinas-nota');
  const gravar = novoEl('button', 'botao-primario', 'Gravar nova versão');
  gravar.type = 'button';
  let confirmar = false;
  gravar.addEventListener('click', async () => {
    const mudancas = leitores.map((l) => ({ n: l.n, campo: l.campo, antes: l.antes, depois: l.ler() }))
      .filter((m) => JSON.stringify(m.depois) !== JSON.stringify(m.antes));
    if (!mudancas.length) { aviso.textContent = 'Nenhum texto mudou.'; return; }
    gravar.disabled = true;
    aviso.textContent = 'Conferindo…';
    try {
      const dados = await pedirEdicao(`/api/producao/${tarefaId}/edicao/textos`, 'POST', { mudancas, confirmar });
      if (dados.confirmar) {
        aviso.textContent = `${dados.texto} ${dados.avisos.map((a) => `• ${a}`).join(' ')}`;
        confirmar = true;
        gravar.textContent = 'Gravar mesmo assim';
        gravar.disabled = false;
        return;
      }
      fecharFormularioPopup();
      avisoNoChat(dados.texto);
    } catch (erro) {
      aviso.textContent = erro.message;
      gravar.disabled = false;
    }
  });
  const acoes = novoEl('div', 'usuario-acoes');
  acoes.append(gravar);
  if (!leitores.length) aviso.textContent = 'Esta peça não tem textos editáveis no molde (só fotos).';
  corpo.append(aviso, acoes);
}

// --- Outra música ----------------------------------------------------------------------------------------------

function abrirOutraMusica(tarefaId) {
  const corpo = janelaReferencia(`Outra música · peça #${tarefaId}`,
    'A versão com som é refeita com outra faixa aprovada da marca, sem o Max. O vídeo sem som fica como está.');
  const aviso = novoEl('p', 'rotinas-nota');
  const acoes = novoEl('div', 'usuario-acoes');
  [['', 'Qualquer outra'], ['calma', 'Mais calma'], ['animada', 'Mais animada']].forEach(([clima, rotulo]) => {
    const botao = novoEl('button', clima ? 'botao-secundario' : 'botao-primario', rotulo);
    botao.type = 'button';
    botao.addEventListener('click', async () => {
      acoes.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      aviso.textContent = 'Enviando…';
      try {
        const dados = await pedirEdicao(`/api/producao/${tarefaId}/edicao/musica`, 'POST', { clima });
        fecharFormularioPopup();
        avisoNoChat(dados.texto);
      } catch (erro) {
        aviso.textContent = erro.message;
        acoes.querySelectorAll('button').forEach((b) => { b.disabled = false; });
      }
    });
    acoes.append(botao);
  });
  corpo.append(aviso, acoes);
}
