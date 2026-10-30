// Popup do agente: conversa (a ficha de informações fica em js/perfil.js).

const ROTULOS_STATUS = { dormindo: 'Pausado', disponivel: 'Disponível', trabalhando: 'Trabalhando', construindo: 'Em construção' };

const historicos = {}; // 'andar/agente' -> [{ autor, texto, tipo, meta?, tarefa_id? }]
let respondendoTarefa = null; // tarefa cujo formulário está sendo respondido (vai junto com a mensagem)
const pendentes = new Set(); // agentes com tarefa enviada aguardando resposta
const rascunhos = {}; // 'andar/agente' -> texto digitado e não enviado
const historicoCarregado = new Set(); // agentes cujo histórico salvo já veio do servidor
const carregandoHistorico = new Set(); // agentes com a busca do histórico em curso
const assinaturas = {}; // 'andar/agente' -> Set de mensagens com tarefa já exibidas (evita repetir)
let geracaoHistorico = 0; // muda ao sair: buscas antigas são descartadas
let chatAberto = null; // { andar, agente }

const modal = document.getElementById('modal');
const modalHistorico = document.getElementById('modal-historico');
const modalInput = document.getElementById('modal-input');
const modalEnviar = document.getElementById('modal-enviar');
const modalAnexar = document.getElementById('modal-anexar');
const modalArquivo = document.getElementById('modal-arquivo');
const modalAnexos = document.getElementById('modal-anexos');
const modalAviso = document.getElementById('modal-anexos-aviso');
const modalProgresso = document.getElementById('modal-progresso');

// Anexos: imagens e PDF, até 4 por mensagem e 15 MB cada (o servidor valida de novo).
const TIPOS_ANEXO = ['image/png', 'image/jpeg', 'image/webp', 'application/pdf'];
const MAX_ANEXOS = 4;
const TAMANHO_MAX_ANEXO = 15 * 1024 * 1024;
const selecionados = {}; // 'andar/agente' -> [{ arquivo: File, url? }] ainda não enviados
const urlsAnexo = {}; // id do anexo -> Promise<blob URL> (miniaturas no histórico)
let enviandoAnexos = false;

const chave = (andar, agente) => `${andar}/${agente}`;
// "Ana", "Ana e Bia", "Ana, Bia e Caio".
const listaNomes = (nomes) => (nomes.length < 2 ? nomes.join('')
  : `${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`);

const tamanhoLegivel = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// Rede de segurança: se o modelo responder em Markdown, no chat vira texto corrido de conversa.
function textoNatural(texto) {
  return String(texto || '')
    .replace(/\*\*(.+?)\*\*/g, '$1').replace(/__(.+?)__/g, '$1')       // negrito
    .replace(/^[ \t]*#{1,6}[ \t]+/gm, '')                              // títulos
    .replace(/^[ \t]*\|?([ \t]*:?-{3,}:?[ \t]*\|)+[ \t]*:?-*:?[ \t]*$/gm, '') // separador de tabela
    .replace(/^[ \t]*\|(.+)\|[ \t]*$/gm, (_, linha) => linha.split('|').map((c) => c.trim()).filter(Boolean).join(' · '))
    .replace(/^[ \t]*([-*_])\1{2,}[ \t]*$/gm, '')                      // linhas ---
    .replace(/^([ \t]*)[*•][ \t]+/gm, '$1- ')                          // marcadores
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/<<LEGENDA>>/g, 'Legenda:').replace(/<<FIM DA LEGENDA>>/g, '')   // marcas para o Monday
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function criarMensagem({ autor, texto, tipo, meta, anexos, tarefa_id, opcoes, formulario, link, relatorio,
  formulario_encerrado: encerrado, avaliacao, id_envio }) {
  const div = document.createElement('div');
  div.className = `msg msg-${tipo}`;
  if (id_envio) div.dataset.envio = id_envio;
  const nome = document.createElement('span');
  nome.className = 'msg-autor';
  nome.textContent = autor;
  // Formulário pedido pelo agente (bloco <<FORMULARIO>>) ou anexado pelo sistema (js/formularios.js).
  const extraido = tipo === 'agente' ? extrairFormulario(texto) : { texto, formulario: null };
  div.append(nome, document.createTextNode(tipo === 'agente' ? textoNatural(extraido.texto) : texto));
  const pedido = formulario || extraido.formulario;
  // O formulário abre em pop-up (js/formularios.js); no chat fica só o botão para reabrir. Fechado sem resposta,
  // a solicitação foi parada e o formulário não reabre.
  if (pedido && (encerrado || formulariosEncerrados.has(tarefa_id))) {
    div.append(novoEl('span', 'msg-encerrado', 'Formulário encerrado sem resposta.'));
  } else if (pedido) div.append(criarBotaoFormulario(pedido, tarefa_id));
  if (anexos?.length) div.append(criarAnexosDaMensagem(anexos));
  if (tipo === 'agente' && link && LINK_DRIVE.test(link)) div.append(criarBotaoVisualizar(link));
  if (tipo === 'agente' && relatorio && LINK_RELATORIO.test(relatorio)) div.append(criarBotaoRelatorio(relatorio));
  if (tipo === 'agente' && tarefa_id && /^✅ Pedido concluído/.test(texto)) div.append(criarBotaoAjuste(tarefa_id));
  if (opcoes?.length) div.append(criarOpcoes(opcoes));
  if (tipo === 'agente' && tarefa_id) div.append(criarAvaliacao(tarefa_id, avaliacao)); // 👍/👎 (js/avaliacao.js)
  if (meta) {
    const linha = document.createElement('span');
    linha.className = 'msg-meta';
    linha.textContent = meta;
    div.append(linha);
  }
  return div;
}

// A resposta leva a tarefa do formulário: o servidor continua aquela tarefa (e a empresa dela).
function abrirFormularioDaMensagem(pedido, tarefaId) {
  const nome = chatAberto ? dadosAgente(chatAberto.andar, chatAberto.agente).nome : '';
  abrirQuandoLivre(() => abrirFormularioPopup(pedido, tarefaId ? (respostas, textoRespostas) => {
    respondendoTarefa = tarefaId;
    const enviado = enviarRespostasDoFormulario(respostas, textoRespostas);
    if (!enviado) respondendoTarefa = null;
    return enviado;
  } : undefined, nome ? `${nome} precisa destas respostas para seguir` : '',
  tarefaId ? () => pararSolicitacao(`/api/tarefas/${tarefaId}/parar`) : null)); // fechar sem responder = parar
}

// "Parar" (botão do chat ou formulário fechado): o servidor para a tarefa ou encerra o formulário (parar.py) e
// avisa no chat; o aviso tira o "pensando..." e o "!".
const formulariosEncerrados = new Set(); // tarefa_id dos formulários fechados sem resposta nesta sessão

async function pararSolicitacao(caminho) {
  if (!sessao) return;
  const alvo = chatAberto && { ...chatAberto };
  try {
    const resposta = await fetch(caminho, { method: 'POST', headers: { Authorization: `Bearer ${sessao.token}` } });
    if (!resposta.ok && alvo) {
      const dados = await resposta.json().catch(() => ({}));
      adicionarMensagem(alvo.andar, alvo.agente, { autor: 'sistema', tipo: 'sistema',
        texto: dados.detail || 'Não foi possível parar agora. Tente de novo.' });
    }
  } catch {
    if (alvo) adicionarMensagem(alvo.andar, alvo.agente, { autor: 'sistema', tipo: 'sistema', texto: 'Sem conexão com o servidor.' });
  }
  atualizarPendencias();
}

const botaoParar = document.getElementById('modal-parar');
botaoParar.addEventListener('click', () => {
  if (!chatAberto) return;
  botaoParar.disabled = true;
  const { andar, agente } = chatAberto;
  pararSolicitacao(`/api/chats/${encodeURIComponent(andar)}/${encodeURIComponent(agente)}/parar`)
    .finally(() => { botaoParar.disabled = false; });
});

function criarBotaoFormulario(pedido, tarefaId) {
  const botao = novoEl('button', 'botao-secundario msg-ajuste', 'Responder formulário');
  botao.type = 'button';
  botao.addEventListener('click', () => abrirFormularioDaMensagem(pedido, tarefaId));
  return botao;
}

// Última mensagem da conversa pede um formulário: o pop-up abre sozinho (uma vez por formulário; depois, pelo botão).
const formulariosMostrados = new Set();

function formularioDaMensagem(m) {
  if (!m || m.tipo === 'voce' || m.formulario_encerrado || formulariosEncerrados.has(m.tarefa_id)) return null;
  return m.formulario || (m.tipo === 'agente' ? extrairFormulario(m.texto).formulario : null);
}

function mostrarFormularioPendente(andar, agente) {
  if (!chatEstaAberto(andar, agente)) return;
  const lista = historicos[chave(andar, agente)] || [];
  const ultima = lista[lista.length - 1];
  const pedido = formularioDaMensagem(ultima);
  const assinatura = ultima && `${chave(andar, agente)}|${ultima.tarefa_id ?? ''}|${ultima.texto}`;
  if (!pedido || formulariosMostrados.has(assinatura)) return;
  formulariosMostrados.add(assinatura);
  abrirFormularioDaMensagem(pedido, ultima.tarefa_id);
}

// Respostas rápidas (ex.: "Só o planejamento" / "Peça final"): o clique envia a resposta como mensagem.
function criarOpcoes(opcoes) {
  const grupo = document.createElement('div');
  grupo.className = 'msg-opcoes';
  opcoes.forEach(({ rotulo, texto }) => {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'botao-secundario msg-ajuste';
    botao.textContent = rotulo;
    botao.addEventListener('click', () => {
      if (modalInput.disabled || modalEnviar.disabled) return;
      grupo.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      modalInput.value = texto;
      document.getElementById('modal-form').requestSubmit();
    });
    grupo.append(botao);
  });
  return grupo;
}

// Entrega de produção: "Visualizar" abre a pasta da entrega no Google Drive (link montado pelo trabalhador do Max).
const LINK_DRIVE = /^https:\/\/drive\.google\.com\/drive\/folders\/[\w-]+$/;
// Página com gráficos da resposta do Analista de Métricas (em teste): os números vêm direto do painel.
const LINK_RELATORIO = /^\/relatorios\/\d+-[\w-]{20,}\.html$/;

function criarBotaoRelatorio(link) {
  const botao = criarBotaoVisualizar(link);
  botao.textContent = 'Ver relatório';
  botao.title = 'Abrir o relatório com gráficos numa nova aba';
  return botao;
}

function criarBotaoVisualizar(link) {
  const botao = document.createElement('a');
  botao.className = 'botao-secundario msg-ajuste msg-visualizar';
  botao.href = link;
  botao.target = '_blank';
  botao.rel = 'noopener noreferrer';
  botao.textContent = 'Visualizar';
  botao.title = 'Abrir a pasta da entrega no Google Drive';
  return botao;
}

// Entrega de produção: "Pedir ajuste" prepara o pedido; a nova versão sai na mesma pasta (_v2, _v3...).
function criarBotaoAjuste(tarefaId) {
  const botao = document.createElement('button');
  botao.type = 'button';
  botao.className = 'botao-secundario msg-ajuste';
  botao.textContent = 'Pedir ajuste';
  botao.title = 'Gera uma nova versão desta peça, na mesma pasta';
  botao.addEventListener('click', () => {
    if (modalInput.disabled) return;
    modalInput.value = `Ajuste na peça #${tarefaId}: `;
    ajustarAlturaInput();
    modalInput.focus();
  });
  return botao;
}

const chatEstaAberto = (andar, agente) =>
  !!chatAberto && chave(chatAberto.andar, chatAberto.agente) === chave(andar, agente);

function rolarParaFim() {
  modalHistorico.scrollTop = modalHistorico.scrollHeight;
}

// Mesma tarefa + mesmo tipo + mesmo texto = mesma mensagem (ao vivo x histórico salvo).
const assinaturaMensagem = (m) => (m.tarefa_id != null ? `${m.tipo}|${m.tarefa_id}|${m.texto}` : null);

// Ao juntar com o histórico salvo, a mensagem do usuário (sem número de tarefa) também se reconhece pelo texto:
// antes ela aparecia duplicada a cada reconexão (revisão de 30/10/2026, 2.26).
const assinaturaNaMescla = (m) => assinaturaMensagem(m) || (m.tipo === 'voce' ? `voce|${m.texto}` : null);

// Registra a assinatura; false se a mensagem já foi exibida.
function marcarVista(k, mensagem) {
  const a = assinaturaMensagem(mensagem);
  if (!a) return true;
  const vistas = (assinaturas[k] ||= new Set());
  if (vistas.has(a)) return false;
  vistas.add(a);
  return true;
}

// Guarda no histórico do agente e mostra na tela se o modal dele estiver aberto.
function adicionarMensagem(andar, agente, mensagem) {
  const k = chave(andar, agente);
  if (!marcarVista(k, mensagem)) return;
  (historicos[k] ||= []).push(mensagem);
  if (chatEstaAberto(andar, agente)) {
    modalHistorico.append(criarMensagem(mensagem));
    rolarParaFim();
    mostrarFormularioPendente(andar, agente);
  }
  if (formularioDaMensagem(mensagem)) atualizarPendencias(); // "!" no agente
}

// Atualiza cabeçalho, indicador "pensando" e bloqueio de envio.
function atualizarChat() {
  if (!chatAberto) return;
  const { andar, agente } = chatAberto;
  const dados = dadosAgente(andar, agente);
  // Trava só pelo SEU pedido em andamento: o agente trabalhando para outro usuário não bloqueia você (cada pedido
  // roda separado, com conversa própria). Antes, o chat de B ficava em "pensando..." pelo pedido de A.
  const ocupado = pendentes.has(chave(andar, agente));
  const online = conectado();
  const restrito = producaoRestrita(andar, agente);
  const carregando = carregandoHistorico.has(chave(andar, agente));

  document.getElementById('modal-nome').textContent = dados.nome;
  const outros = estadoAgentes[andar]?.[agente]?.em_uso || [];
  document.getElementById('modal-funcao').textContent = outros.length
    ? `${listaNomes(outros.map((o) => o.nome))} também ${outros.length > 1 ? 'estão' : 'está'} usando agora · conversas separadas`
    : (dados.funcao || ANDARES[andar].nome);
  const status = document.getElementById('modal-status');
  status.className = `status status-${dados.status}`;
  status.title = ROTULOS_STATUS[dados.status];

  document.getElementById('modal-pensando').hidden = !ocupado;
  // Envio espera o histórico chegar, para a pergunta nova não se repetir ao mesclar.
  const bloqueado = ocupado || !online || restrito || carregando || enviandoAnexos;
  modalInput.disabled = bloqueado;
  modalEnviar.disabled = bloqueado;
  modalAnexar.disabled = bloqueado;
  modalAnexos.querySelectorAll('button').forEach((b) => { b.disabled = enviandoAnexos; });
  if (restrito) modalInput.placeholder = 'Envio indisponível para esta conta';
  else if (!online) modalInput.placeholder = 'Sem conexão com o servidor...';
  else modalInput.placeholder = carregando ? 'Carregando histórico…' : 'Descreva a tarefa...';
}

// A ficha do agente abre/fecha e muda a altura da conversa: quem estava no fim continua vendo a última mensagem.
let alturaConversa = 0;
new ResizeObserver(() => {
  // "No fim" medido com a altura de antes: quem rolou para cima lendo o histórico não é puxado para baixo.
  const estavaNoFim = modalHistorico.scrollHeight - modalHistorico.scrollTop - alturaConversa < 40;
  alturaConversa = modalHistorico.clientHeight;
  if (estavaNoFim && chatAberto) rolarParaFim();
}).observe(modalHistorico);

// Redesenha a conversa do agente aberto (com o aviso de carregamento, se for o caso) e mostra a última interação.
function renderizarHistorico(andar, agente) {
  const k = chave(andar, agente);
  modalHistorico.replaceChildren(...(historicos[k] || []).map(criarMensagem));
  if (carregandoHistorico.has(k)) {
    const aviso = document.createElement('p');
    aviso.className = 'msg-carregando';
    aviso.textContent = 'Carregando histórico…';
    modalHistorico.prepend(aviso);
  }
  rolarParaFim();
  mostrarFormularioPendente(andar, agente);
}

function abrirChat(andar, agente) {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = { andar, agente };
  mostrarSeletorEmpresa(andar, agente); // empresa da conversa (Marketing e Cérebro)
  modalInput.value = rascunhos[chave(andar, agente)] || '';
  ajustarAlturaInput();
  avisarAnexo('');
  renderizarSelecao();
  carregarHistorico(andar, agente);
  document.getElementById('modal-onboarding').hidden = agente !== 'recepcionista';
  modal.classList.add('aberto');
  ajustarAlturaInput();
  renderizarHistorico(andar, agente); // abre na última interação (rolada até o fim)
  carregarPerfil(andar, agente);
  acompanharAndamento(andar, agente);
  avisarChatAberto(); // os outros veem "Em uso: <você>" neste agente
  caixaChatAberto(andar, agente); // concluídos deste chat saem da caixa de entrada
  atualizarChat();
  if (!modalInput.disabled) modalInput.focus();
}

// Mensagem do agente no formato das respostas ao vivo (modelo na linha de metadados).
// `por`: a resposta veio de outro agente (Gestor, produção) para o chat onde o pedido nasceu.
function mensagemDoAgente(andar, agente, dados) {
  const nome = dados.por || dadosAgente(andar, agente).nome;
  const meta = metadadosResposta(dados);
  const autor = !meta && dados.modelo ? `${nome} · ${dados.modelo}` : nome;
  return { autor, texto: dados.texto, tipo: 'agente', meta, tarefa_id: dados.tarefa_id, link: dados.link,
    relatorio: dados.relatorio, formulario_encerrado: dados.formulario_encerrado, avaliacao: dados.avaliacao };
}

function converterDoServidor(andar, agente, m) {
  if (m.autor === 'voce') return { autor: 'Você', texto: m.texto, tipo: 'voce', tarefa_id: m.tarefa_id, anexos: m.anexos };
  if (m.autor === 'agente') return mensagemDoAgente(andar, agente, { ...m.meta, texto: m.texto, tarefa_id: m.tarefa_id });
  return { autor: 'sistema', texto: m.texto, tipo: 'sistema', tarefa_id: m.tarefa_id };
}

// Busca a conversa salva (uma vez por sessão da página) e a coloca antes das mensagens ao vivo.
async function carregarHistorico(andar, agente) {
  const k = chave(andar, agente);
  if (!sessao || historicoCarregado.has(k) || carregandoHistorico.has(k)) return;
  const geracao = geracaoHistorico;
  carregandoHistorico.add(k);
  let dados = null;
  let status = 0;
  try {
    const resposta = await fetch(`/api/historico/${encodeURIComponent(andar)}/${encodeURIComponent(agente)}`, {
      headers: { Authorization: `Bearer ${sessao.token}` },
    });
    status = resposta.status;
    if (resposta.ok) dados = await resposta.json();
  } catch (erro) {
    console.warn('Falha ao carregar o histórico:', erro);
  }
  if (geracao !== geracaoHistorico) return; // saiu da conta enquanto buscava
  carregandoHistorico.delete(k);
  if (status === 401) {
    encerrarSessao('Sessão expirada. Entre novamente.');
    return;
  }

  const aberto = chatEstaAberto(andar, agente);
  if (dados) {
    historicoCarregado.add(k);
    // Mensagem ao vivo que também está no histórico fica na posição cronológica dele.
    const salvas = (dados.mensagens || []).map((m) => converterDoServidor(andar, agente, m));
    const noHistorico = new Set(salvas.map(assinaturaNaMescla).filter(Boolean));
    const aoVivo = (historicos[k] || []).filter((m) => !noHistorico.has(assinaturaNaMescla(m)));
    salvas.forEach((m) => marcarVista(k, m));
    historicos[k] = [...salvas, ...aoVivo];
    if (dados.pendentes?.length && dadosAgente(andar, agente).status === 'trabalhando') pendentes.add(k);
  }
  if (aberto) {
    renderizarHistorico(andar, agente);
    // Erro fica só na tela: na próxima abertura tenta de novo.
    if (!dados) modalHistorico.prepend(criarMensagem({ autor: 'sistema', texto: 'Não foi possível carregar o histórico.', tipo: 'sistema' }));
    atualizarChat();
  }
}

// Reconectou: o que chegou enquanto a conexão estava fora (ex.: resposta do Gestor no chat de origem) só
// existe no histórico salvo. Busca de novo (as assinaturas evitam mensagens repetidas).
function recarregarHistoricos() {
  historicoCarregado.clear();
  if (chatAberto) carregarHistorico(chatAberto.andar, chatAberto.agente);
}

function fecharChat() {
  if (chatAberto) rascunhos[chave(chatAberto.andar, chatAberto.agente)] = modalInput.value;
  chatAberto = null;
  modal.classList.remove('aberto');
  pararAndamento();
  avisarChatAberto(); // some o "Em uso" para os outros
}

function limparChat() {
  Object.keys(historicos).forEach((k) => delete historicos[k]);
  Object.keys(rascunhos).forEach((k) => delete rascunhos[k]);
  Object.keys(assinaturas).forEach((k) => delete assinaturas[k]);
  historicoCarregado.clear();
  carregandoHistorico.clear();
  geracaoHistorico += 1;
  modalInput.value = '';
  pendentes.clear();
  Object.values(selecionados).flat().forEach((s) => s.url && URL.revokeObjectURL(s.url));
  Object.keys(selecionados).forEach((k) => delete selecionados[k]);
  Object.values(urlsAnexo).forEach((p) => p.then((url) => url && URL.revokeObjectURL(url)));
  Object.keys(urlsAnexo).forEach((k) => delete urlsAnexo[k]);
  renderizarSelecao();
}

// ---------- Anexos ----------

function avisarAnexo(texto) {
  modalAviso.textContent = texto;
  modalAviso.hidden = !texto;
}

function mostrarProgresso(fracao) {
  modalProgresso.hidden = fracao == null;
  const pct = Math.round((fracao || 0) * 100);
  modalProgresso.firstElementChild.style.width = `${pct}%`;
  modalProgresso.setAttribute('aria-valuenow', pct);
}

const iconePdf = () => {
  const i = document.createElement('span');
  i.className = 'anexo-icone-pdf';
  i.textContent = 'PDF';
  return i;
};

// Chips dos arquivos escolhidos (ainda não enviados) do agente aberto.
function renderizarSelecao() {
  const lista = chatAberto ? selecionados[chave(chatAberto.andar, chatAberto.agente)] || [] : [];
  modalAnexos.hidden = !lista.length;
  modalAnexos.replaceChildren(...lista.map((s, i) => {
    const chip = document.createElement('div');
    chip.className = 'anexo-chip';
    if (s.url) {
      const img = document.createElement('img');
      img.src = s.url;
      img.alt = '';
      chip.append(img);
    } else chip.append(iconePdf());
    const info = document.createElement('span');
    info.className = 'anexo-info';
    const nome = document.createElement('span');
    nome.className = 'anexo-nome';
    nome.textContent = s.arquivo.name;
    nome.title = s.arquivo.name;
    const tamanho = document.createElement('span');
    tamanho.className = 'anexo-tamanho';
    tamanho.textContent = tamanhoLegivel(s.arquivo.size);
    info.append(nome, tamanho);
    const remover = document.createElement('button');
    remover.type = 'button';
    remover.className = 'anexo-remover';
    remover.textContent = '×';
    remover.setAttribute('aria-label', `Remover ${s.arquivo.name}`);
    remover.disabled = enviandoAnexos;
    remover.addEventListener('click', () => {
      if (s.url) URL.revokeObjectURL(s.url);
      lista.splice(i, 1);
      avisarAnexo('');
      renderizarSelecao();
    });
    chip.append(info, remover);
    return chip;
  }));
}

function escolherArquivos() {
  if (!chatAberto) return;
  const lista = (selecionados[chave(chatAberto.andar, chatAberto.agente)] ||= []);
  const avisos = [];
  for (const arquivo of modalArquivo.files) {
    if (!TIPOS_ANEXO.includes(arquivo.type)) avisos.push(`${arquivo.name}: envie apenas imagens (PNG, JPG, WEBP) ou PDF.`);
    else if (arquivo.size > TAMANHO_MAX_ANEXO) avisos.push(`${arquivo.name} tem ${tamanhoLegivel(arquivo.size)}; o limite é 15 MB.`);
    else if (lista.length >= MAX_ANEXOS) { avisos.push(`Máximo de ${MAX_ANEXOS} arquivos por mensagem.`); break; }
    else lista.push({ arquivo, url: arquivo.type.startsWith('image/') ? URL.createObjectURL(arquivo) : null });
  }
  modalArquivo.value = '';
  avisarAnexo(avisos.join(' '));
  renderizarSelecao();
  modalInput.focus();
}

// Upload (XHR para ter progresso) -> [{ id, nome, mime, tamanho }].
function enviarArquivos(arquivos) {
  return new Promise((resolve, reject) => {
    const dados = new FormData();
    arquivos.forEach((a) => dados.append('arquivos', a, a.name));
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/anexos');
    xhr.setRequestHeader('Authorization', `Bearer ${sessao.token}`);
    xhr.upload.addEventListener('progress', (e) => e.lengthComputable && mostrarProgresso(e.loaded / e.total));
    xhr.addEventListener('load', () => {
      let corpo = null;
      try { corpo = JSON.parse(xhr.responseText); } catch { /* resposta sem JSON */ }
      if (xhr.status === 401) encerrarSessao('Sessão expirada. Entre novamente.');
      if (xhr.status >= 200 && xhr.status < 300 && Array.isArray(corpo)) resolve(corpo);
      else reject(new Error(typeof corpo?.detail === 'string' ? corpo.detail : 'Não foi possível enviar os anexos.'));
    });
    xhr.addEventListener('error', () => reject(new Error('Falha de rede ao enviar os anexos.')));
    mostrarProgresso(0);
    xhr.send(dados);
  });
}

// Blob URL do anexo (GET com o token), buscado uma vez.
function urlDoAnexo(id) {
  urlsAnexo[id] ||= fetch(`/api/anexos/${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${sessao?.token}` } })
    .then((r) => (r.ok ? r.blob() : null))
    .then((blob) => (blob ? URL.createObjectURL(blob) : null))
    .catch(() => null);
  return urlsAnexo[id];
}

// Anexos dentro da mensagem "Você": miniatura (imagem) ou ícone (PDF); clique abre o arquivo.
function criarAnexosDaMensagem(anexos) {
  const caixa = document.createElement('div');
  caixa.className = 'msg-anexos';
  anexos.forEach((a) => {
    const link = document.createElement('a');
    link.className = 'msg-anexo';
    link.href = '#';
    link.title = `${a.nome} (${tamanhoLegivel(a.tamanho || 0)})`;
    if (a.mime?.startsWith('image/')) {
      const img = document.createElement('img');
      img.alt = a.nome;
      link.append(img);
      urlDoAnexo(a.id).then((url) => { if (url) img.src = url; else link.classList.add('msg-anexo-erro'); });
    } else {
      const nome = document.createElement('span');
      nome.textContent = a.nome;
      link.append(iconePdf(), nome);
    }
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      const url = await urlDoAnexo(a.id);
      if (url) window.open(url, '_blank', 'noopener');
    });
    caixa.append(link);
  });
  return caixa;
}

async function enviarTarefa(evento) {
  evento.preventDefault();
  if (!chatAberto || modalEnviar.disabled) return;
  const { andar, agente } = chatAberto;
  const k = chave(andar, agente);
  const escolhidos = [...(selecionados[k] || [])];
  // O servidor exige texto: com anexo e sem texto, vai uma frase padrão.
  const texto = modalInput.value.trim() || (escolhidos.length ? 'Veja o anexo.' : '');
  if (!texto) return;
  // "/palavra": quem decide o que é o servidor; não pede empresa nem aparece como mensagem na conversa.
  if (/^\/\S+$/.test(texto) && !escolhidos.length) {
    if (enviar({ tipo: 'mensagem', andar, agente, texto })) {
      modalInput.value = '';
      rascunhos[k] = '';
      ajustarAlturaInput();
    }
    return;
  }
  if (!garantirEmpresa(andar, agente, texto)) return; // sem empresa: a citada no pedido ou o formulário (js/empresa.js)
  // Lida antes do upload (revisão de 30/10/2026, 2.22): trocar de chat durante o envio dos anexos não muda a empresa.
  const empresa = empresaDaConversa(andar, agente);

  let anexos = [];
  if (escolhidos.length) {
    enviandoAnexos = true;
    avisarAnexo('');
    atualizarChat();
    try {
      anexos = await enviarArquivos(escolhidos.map((s) => s.arquivo));
    } catch (erro) {
      avisarAnexo(erro.message);
      return;
    } finally {
      enviandoAnexos = false;
      mostrarProgresso(null);
      atualizarChat();
    }
    // A miniatura local já serve para o histórico (evita baixar de novo).
    anexos.forEach((a, i) => { if (escolhidos[i]?.url) urlsAnexo[a.id] = Promise.resolve(escolhidos[i].url); });
  }

  const mensagem = { tipo: 'mensagem', andar, agente, texto, id_envio: novoIdEnvio() };
  if (empresa) mensagem.empresa = empresa;
  if (anexos.length) mensagem.anexos = anexos.map((a) => a.id);
  if (respondendoTarefa && texto.startsWith('Respostas')) mensagem.responde_a = respondendoTarefa;
  respondendoTarefa = null;
  if (!enviar(mensagem)) {
    avisarAnexo('Sem conexão com o servidor. Tente de novo.');
    return;
  }
  aguardarConfirmacao(mensagem);

  selecionados[k] = [];
  rascunhos[k] = '';
  setTimeout(atualizarPendencias, 2000); // a resposta ao formulário tira o "!" do agente
  if (chatEstaAberto(andar, agente)) {
    modalInput.value = '';
    ajustarAlturaInput();
  }
  renderizarSelecao();
  pendentes.add(k);
  const ultimaResposta = [...(historicos[k] || [])].reverse().find((m) => m.tipo === 'agente' && m.tarefa_id);
  verificarReacaoNegativa(texto, ultimaResposta?.tarefa_id); // "não era isso": pergunta o porquê (js/avaliacao.js)
  adicionarMensagem(andar, agente, { autor: 'Você', texto, tipo: 'voce', anexos, id_envio: mensagem.id_envio });
  atualizarChat();
}

// Confirmação de recebimento (revisão de 30/10/2026, 2.25): sem o "recebido" do servidor em 10 s, a mensagem fica
// marcada como não enviada, com "Reenviar" (o servidor ignora a repetição se a primeira tinha chegado).
const ESPERA_CONFIRMACAO = 10000;
const envios = new Map(); // id_envio -> { dados, timer }

function novoIdEnvio() {
  return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const elementosDoEnvio = (id) => modalHistorico.querySelectorAll(`.msg[data-envio="${CSS.escape(id)}"]`);

function aguardarConfirmacao(dados) {
  clearTimeout(envios.get(dados.id_envio)?.timer);
  envios.set(dados.id_envio, { dados, timer: setTimeout(() => marcarNaoEnviada(dados.id_envio), ESPERA_CONFIRMACAO) });
}

function confirmarEnvio(id) {
  const envio = envios.get(id);
  if (!envio) return;
  clearTimeout(envio.timer);
  envios.delete(id);
  elementosDoEnvio(id).forEach((el) => {
    el.classList.remove('msg-nao-enviada');
    el.querySelector('.msg-reenviar')?.remove();
  });
}

function marcarNaoEnviada(id) {
  const envio = envios.get(id);
  if (!envio) return;
  const { andar, agente } = envio.dados;
  pendentes.delete(chave(andar, agente));
  atualizarChat();
  elementosDoEnvio(id).forEach((el) => {
    el.classList.add('msg-nao-enviada');
    if (el.querySelector('.msg-reenviar')) return;
    const reenviar = novoEl('button', 'botao-secundario msg-reenviar', 'Não chegou ao servidor. Reenviar');
    reenviar.type = 'button';
    reenviar.addEventListener('click', () => {
      if (!enviar(envio.dados)) return;
      reenviar.remove();
      el.classList.remove('msg-nao-enviada');
      pendentes.add(chave(andar, agente));
      atualizarChat();
      aguardarConfirmacao(envio.dados);
    });
    el.append(reenviar);
  });
}

// Limpeza só da tela (o servidor guardou a partir de onde mostrar; a memória dos agentes não muda).
function limparConversas({ andar, agente, todos }) {
  const chaves = todos ? Object.keys(historicos) : [chave(andar, agente)];
  chaves.forEach((k) => {
    historicos[k] = [];
    historicoCarregado.add(k);
    pendentes.delete(k);
  });
  if (chatAberto && (todos || chatEstaAberto(andar, agente))) renderizarHistorico(chatAberto.andar, chatAberto.agente);
  atualizarChat();
}

// Resposta pode vir com extras (dificuldade, tempo, adiada); o modelo vai na linha de metadados.
function receberResposta(msg) {
  const { andar, agente, texto } = msg;
  pendentes.delete(chave(andar, agente));
  if (agente === 'cerebro') aoRespostaCerebro(texto); // o Cérebro não tem chat: a resposta vai para o campo de ensinar
  adicionarMensagem(andar, agente, mensagemDoAgente(andar, agente, msg));
  if (chatEstaAberto(andar, agente)) carregarPerfil(andar, agente); // atualiza o contador de tarefas
  else mostrarToast(andar, agente, texto);
  atualizarPendencias();
  atualizarChat();
  avisarPainel();
}

// Tarefa estourou o tempo/falhou localmente e foi para a fila do Claude.
function receberAdiada({ andar, agente, texto, tarefa_id }) {
  if (!andar || !agente) return;
  pendentes.delete(chave(andar, agente));
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema', tarefa_id });
  atualizarChat();
  avisarPainel();
}

// Aviso do servidor ligado a um agente (ex.: agente criado, agendamento criado): mensagem de sistema
// no chat dele e toast se o chat não estiver aberto.
// `liberar`: o pedido não vai gerar resposta neste chat (ex.: encaminhado ao Gestor, rotina agendada).
// `opcoes`: botões de resposta rápida ([{rotulo, texto}]); o clique envia o texto como mensagem.
function receberAviso({ andar, agente, texto, titulo, liberar, opcoes, formulario, tarefa_id }) {
  if (!andar || !agente) {
    console.info('Aviso do servidor:', texto);
    return;
  }
  if (liberar) pendentes.delete(chave(andar, agente));
  if (titulo === 'Solicitação parada' && tarefa_id) { // formulário encerrado: some o botão de responder
    formulariosEncerrados.add(tarefa_id);
    if (chatEstaAberto(andar, agente)) renderizarHistorico(andar, agente);
  }
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema', opcoes, formulario });
  if (!chatEstaAberto(andar, agente)) mostrarToast(andar, agente, texto, titulo || 'Aviso');
  if (titulo === 'Rotina agendada') atualizarRotinas(andar, agente); // lista do popup do agente
  atualizarChat();
}

function receberErro({ andar, agente, texto, tarefa_id }) {
  if (!andar || !agente) {
    console.warn('Erro do servidor:', texto);
    return;
  }
  pendentes.delete(chave(andar, agente));
  if (agente === 'cerebro') aoRespostaCerebro(texto, true);
  adicionarMensagem(andar, agente, { autor: 'sistema', texto, tipo: 'sistema', tarefa_id });
  if (!chatAberto) console.warn(`Erro (${andar}/${agente}):`, texto);
  atualizarChat();
}

// Conexão caiu: tarefas pendentes não terão resposta nesta conexão.
function liberarPendentes() {
  pendentes.clear();
  atualizarChat();
}

function ajustarAlturaInput() {
  if (!modalInput.offsetParent) return; // janela fechada: mede ao abrir
  modalInput.style.height = 'auto';
  modalInput.style.height = `${Math.min(modalInput.scrollHeight + 2, 150)}px`;
}

document.getElementById('modal-form').addEventListener('submit', enviarTarefa);
modalInput.addEventListener('input', ajustarAlturaInput);
modalInput.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return; // Shift+Enter: nova linha
  e.preventDefault();
  document.getElementById('modal-form').requestSubmit();
});
modalAnexar.addEventListener('click', () => modalArquivo.click());
modalArquivo.addEventListener('change', escolherArquivos);
document.getElementById('modal-fechar').addEventListener('click', fecharChat);
modal.addEventListener('click', (e) => {
  if (e.target === modal) fecharChat();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatAberto) fecharChat();
});
