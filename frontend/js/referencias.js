// Onda 3 (31/10/2026): "Repetir para…" até 5 Lodges (copywriter-04) e modelos de estilo aprovados (cerebro-12).
// Servidor: backend/repetir_lodges.py e backend/cerebro_modelos.py.

const AGENTES_REPETIR = ['copywriter', 'social_media', 'email_marketing', 'gestor_trafego']; // = conferente.AGENTES
const MAX_LODGES_REPETIR = 5;
const CITA_LODGE = /\blodges?\s*(?:n[ºo°.]*\s*)?#?\d{1,3}\b/i;

function janelaReferencia(tituloTexto, subtitulo) {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-usuario');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, tituloTexto), novoEl('p', null, subtitulo));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);
  const corpo = novoEl('div', 'formulario-corpo usuario-corpo');
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  return corpo;
}

async function postarJson(url, corpo) {
  const resposta = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || `erro ${resposta.status}`);
  return dados;
}

// --- Repetir para… -------------------------------------------------------------------------------------------

// Botão abaixo de uma resposta de texto da Casa Veraneio que cita um Lodge; null quando não se aplica.
function criarBotaoRepetir(tarefaId, texto) {
  if (!chatAberto || !AGENTES_REPETIR.includes(chatAberto.agente) || !CITA_LODGE.test(texto || '')) return null;
  if (empresaDaConversa(chatAberto.andar, chatAberto.agente) !== 'casa_veraneio') return null;
  const botao = novoEl('button', 'botao-secundario msg-ajuste', 'Repetir para…');
  botao.type = 'button';
  botao.title = `Refaz este texto para até ${MAX_LODGES_REPETIR} outros Lodges, com os dados da ficha (modelo gratuito)`;
  botao.addEventListener('click', () => abrirRepetir(tarefaId));
  return botao;
}

function abrirRepetir(tarefaId) {
  const corpo = janelaReferencia('Repetir para outros Lodges',
    `Mesmo texto, refeito com a ficha de cada Lodge (até ${MAX_LODGES_REPETIR}, sem preços). Cada um chega no chat com a conferência.`);
  const rotulo = novoEl('label', 'form-rotulo', 'Números dos Lodges (separados por vírgula)');
  const campo = novoEl('input', 'form-entrada');
  campo.id = `repetir-lodges-${tarefaId}`;
  campo.placeholder = 'ex.: 12, 35, 140';
  campo.inputMode = 'numeric';
  rotulo.htmlFor = campo.id;
  const aviso = novoEl('p', 'rotinas-nota');
  const enviar = novoEl('button', 'botao-primario', 'Repetir');
  enviar.type = 'button';
  const acao = async () => {
    const lodges = [...new Set((campo.value.match(/\d{1,3}/g) || []).map(Number))];
    if (!lodges.length) { aviso.textContent = 'Escreva pelo menos um número de Lodge.'; return; }
    if (lodges.length > MAX_LODGES_REPETIR) { aviso.textContent = `No máximo ${MAX_LODGES_REPETIR} Lodges por vez.`; return; }
    enviar.disabled = true;
    aviso.textContent = 'Enviando…';
    try {
      await postarJson(`/api/tarefas/${tarefaId}/repetir`, { lodges });
      fecharFormularioPopup();
    } catch (erro) {
      aviso.textContent = erro.message;
      enviar.disabled = false;
    }
  };
  enviar.addEventListener('click', acao);
  campo.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); acao(); } });
  const acoes = novoEl('div', 'usuario-acoes');
  acoes.append(enviar);
  corpo.append(rotulo, campo, aviso, acoes);
  campo.focus();
}

// --- Modelos de estilo (ficha do Cérebro, só a Diretoria) ------------------------------------------------------

const modelosEstilo = { dados: null, em: 0 };

async function carregarModelosEstilo(forcar = false) {
  if (!sessao || (!forcar && modelosEstilo.dados && Date.now() - modelosEstilo.em < 30000)) return modelosEstilo.dados;
  try {
    const resposta = await fetch('/api/modelos', { headers: { Authorization: `Bearer ${sessao.token}` } });
    modelosEstilo.dados = resposta.ok ? await resposta.json() : null;
  } catch {
    modelosEstilo.dados = null;
  }
  modelosEstilo.em = Date.now();
  return modelosEstilo.dados;
}

// Pop-up "Guardar como modelo": texto inteiro (editável) e formato; `origem` = { observacao_id } ou { tarefa_id }.
async function abrirGuardarModelo(origem) {
  const consulta = origem.observacao_id ? `observacao_id=${origem.observacao_id}` : `tarefa_id=${origem.tarefa_id}`;
  let previa;
  try {
    const resposta = await fetch(`/api/modelos/previa?${consulta}`, { headers: { Authorization: `Bearer ${sessao.token}` } });
    previa = await resposta.json();
    if (!resposta.ok) throw new Error(previa.detail || resposta.status);
  } catch (erro) {
    correcoes.erro = `Não foi possível abrir o modelo: ${erro.message}`;
    return;
  }
  const corpo = janelaReferencia(`Guardar como modelo · ${previa.agente_nome}`,
    `Só da ${previa.empresa_nome}. Os agentes recebem como exemplo de tom e estrutura, nunca como fonte de fatos.`);
  const rotuloFormato = novoEl('label', 'form-rotulo', 'Formato');
  const formato = novoEl('select', 'form-entrada');
  formato.id = 'modelo-formato';
  rotuloFormato.htmlFor = formato.id;
  Object.entries(previa.formatos).forEach(([valor, rotulo]) => formato.append(new Option(rotulo, valor)));
  formato.value = previa.formato;
  const rotuloTexto = novoEl('label', 'form-rotulo', 'Texto do modelo (tire o que não for exemplo)');
  const texto = novoEl('textarea', 'form-entrada');
  texto.id = 'modelo-texto';
  rotuloTexto.htmlFor = texto.id;
  texto.rows = 10;
  texto.value = previa.texto;
  const aviso = novoEl('p', 'rotinas-nota');
  const guardar = novoEl('button', 'botao-primario', 'Guardar como modelo');
  guardar.type = 'button';
  guardar.addEventListener('click', async () => {
    guardar.disabled = true;
    try {
      await postarJson('/api/modelos', { ...origem, formato: formato.value, texto: texto.value });
      fecharFormularioPopup();
      await carregarModelosEstilo(true);
      if (chatAberto) carregarCorrecoes(chatAberto.andar, chatAberto.agente);
    } catch (erro) {
      aviso.textContent = erro.message;
      guardar.disabled = false;
    }
  });
  const acoes = novoEl('div', 'usuario-acoes');
  acoes.append(guardar);
  corpo.append(rotuloFormato, formato, rotuloTexto, texto, aviso, acoes);
}

// Botão no pop-up de um elogio (js/correcoes.js).
function botaoGuardarModelo(observacaoId) {
  const botao = novoEl('button', 'botao-secundario', 'Guardar como modelo de estilo');
  botao.type = 'button';
  botao.title = 'O texto inteiro vira exemplo de tom e estrutura (não vira regra)';
  botao.addEventListener('click', () => abrirGuardarModelo({ observacao_id: observacaoId }));
  return botao;
}

// Bloco na ficha do Cérebro: candidatos (👍 recentes) e modelos ativos, com "Remover".
function criarModelosEstilo() {
  const bloco = novoEl('details', 'correcao-regras');
  const resumo = novoEl('summary', null, 'Modelos de estilo');
  bloco.append(resumo);
  carregarModelosEstilo().then((d) => {
    if (!d) { bloco.remove(); return; }
    resumo.textContent = `Modelos de estilo (${d.modelos.length} ativos · ${d.candidatos.length} candidatos 👍)`;
    if (d.candidatos.length) bloco.append(novoEl('small', 'correcao-meta', 'Candidatos (respostas com 👍):'));
    d.candidatos.forEach((c) => {
      const linha = novoEl('div', 'correcao-regra-ativa');
      linha.append(novoEl('span', null, `👍 ${c.agente_nome} · ${c.empresa_nome} · ${c.autor}: ${c.previa}`),
        botaoGuardar(c.tarefa_id));
      bloco.append(linha);
    });
    if (d.modelos.length) bloco.append(novoEl('small', 'correcao-meta', `Ativos (${d.modelos.length}; ficam até você remover):`));
    d.modelos.forEach((m) => {
      const linha = novoEl('div', 'correcao-regra-ativa');
      const remover = novoEl('button', 'botao-secundario', 'Remover');
      remover.type = 'button';
      remover.addEventListener('click', async () => {
        remover.disabled = true;
        try {
          await postarJson(`/api/modelos/${m.id}/remover`, {});
          linha.remove();
          carregarModelosEstilo(true);
        } catch {
          remover.textContent = 'Não foi possível';
        }
      });
      linha.append(novoEl('span', null, `${m.formato} · ${m.agente_nome} · ${m.empresa_nome}: ${m.previa}`), remover);
      bloco.append(linha);
    });
  });
  return bloco;
}

function botaoGuardar(tarefaId) {
  const botao = novoEl('button', 'botao-secundario', 'Guardar');
  botao.type = 'button';
  botao.addEventListener('click', () => abrirGuardarModelo({ tarefa_id: tarefaId }));
  return botao;
}
