// Comando e resposta por voz, em paralelo com o texto (Thomas, 12/11/2026). Usa a Web Speech API do navegador
// (Chrome/Edge; sem custo de IA): o reconhecimento passa pelo serviço do navegador e a fala sai das vozes do sistema.
//
// - O microfone do topo liga e desliga a escuta (começa desligada; cada navegador guarda a escolha).
// - "Olá Vera": a assistente do escritório. "Olá Vera, abre o escritório" lê o resumo do dia (backend/vera.py);
//   "Olá Vera, abre o chat do Gestor" abre o chat; qualquer outro pedido vai pela triagem ao agente certo.
// - Com um chat aberto, "Olá [nome do agente]" manda o pedido a ele, como se tivesse sido digitado.
// - A resposta dos agentes a um pedido falado é lida em voz alta; falar de novo ou clicar no microfone interrompe.
// - "Olá Vera" sozinho: ela responde "Pois não?" e o próximo trecho falado vira o pedido.

const ESPERA_COMANDO_MS = 8000;
const VOZ_VALE_MS = 30 * 60 * 1000;  // por quanto tempo as respostas de um chat pedido por voz são lidas
const LIMITE_FALA = 700;
const CHAVE_LIGADA = 'voz_ligada';

const normalizarFala = (texto) => String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[-–—]/g, ' ').replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();

// { alvo: 'vera' | 'agente', resto } quando a frase traz "olá vera" / "olá <agente>"; null quando não chama ninguém.
function acharChamado(texto, nomeAgente = '') {
  const frase = normalizarFala(texto);
  // O reconhecimento às vezes troca "Vera" por "bera"/"vela" e "Olá" por "alô"/"hola"; "Vera, ..." no começo vale.
  const nomes = [['vera', 'vera|bera|vela'], ...(nomeAgente ? [['agente', normalizarFala(nomeAgente)]] : [])];
  for (const [alvo, nome] of nomes) {
    const m = frase.match(new RegExp(`(?:^|\\s)(?:ola|oi|alo|hola|ei|hey)\\s+(?:${nome})(?:\\s+(.*))?$`))
      || (alvo === 'vera' && frase.match(/^vera(?:\s+(.*))?$/));
    if (m) return { alvo, resto: (m[1] || '').trim() };
  }
  return null;
}

// O que a Vera faz com o pedido: resumo do dia, abrir um chat, parar de falar ou triagem.
function comandoVera(resto, agentes = []) {
  const frase = normalizarFala(resto);
  if (!frase) return { tipo: 'esperar' };
  if (/^(para|pare|parar|silencio|chega|cancela|cancelar)\b/.test(frase)) return { tipo: 'parar' };
  if (/\b(abr\w* o escritorio|resumo|como (esta|anda)\w* o escritorio|relatorio do dia|novidades|bom dia|boa tarde|boa noite)\b/.test(frase)) {
    return { tipo: 'resumo' };
  }
  const abrir = frase.match(/^(?:abr\w*|mostr\w*|ir para|vai para)\s+(?:o |a )?(?:chat |conversa )?(?:d[oa] |com o |com a )?(.+)$/);
  if (abrir) {
    const alvo = agentes.find((a) => normalizarFala(a.nome) === abrir[1].trim());
    if (alvo) return { tipo: 'abrir', agente: alvo };
  }
  return { tipo: 'pedido', texto: String(resto).trim() };
}

// Texto da resposta em fala: sem markdown, links, listas e emojis; respostas longas terminam avisando o chat.
function textoParaFala(texto) {
  let limpo = String(texto || '').replace(/```[\s\S]*?```/g, ' ')
    .replace(/https?:\/\/\S+/g, 'link no chat').replace(/[*_#>`|]/g, ' ')
    .replace(/^\s*[-•]\s+/gm, '').replace(/\p{Extended_Pictographic}/gu, '').replace(/\s+/g, ' ').trim();
  if (limpo.length > LIMITE_FALA) {
    const corte = limpo.lastIndexOf('. ', LIMITE_FALA);
    limpo = `${limpo.slice(0, corte > 200 ? corte + 1 : LIMITE_FALA)} A resposta completa está no chat.`;
  }
  return limpo;
}

if (typeof module !== 'undefined') {
  module.exports = { normalizarFala, acharChamado, comandoVera, textoParaFala };
}

// --- Navegador -------------------------------------------------------------------------------

const Reconhecimento = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);
let escuta = null;
let escutaLigada = false;
let falando = false;
let esperando = null;            // { alvo, ate } depois de um "Olá Vera" sem pedido
const chatsPorVoz = new Map();   // chave do chat -> pedido por voz até (ms)

function veraBalao(texto, tipo = '') {
  const el = document.getElementById('vera-balao');
  if (!el) return;
  el.hidden = !texto;
  el.textContent = texto || '';
  el.className = `vera-balao ${tipo}`.trim();
}

function veraFalar(texto, depois) {
  if (!texto || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const fala = new SpeechSynthesisUtterance(texto);
  fala.lang = 'pt-BR';
  const voz = window.speechSynthesis.getVoices().find((v) => v.lang === 'pt-BR');
  if (voz) fala.voice = voz;
  falando = true;
  try { escuta?.abort(); } catch { /* a escuta volta sozinha no fim da fala */ }
  const fim = () => {
    falando = false;
    if (escutaLigada) iniciarEscuta();
    depois?.();
  };
  fala.onend = fim;
  fala.onerror = fim;
  veraBalao(`Vera: ${texto}`, 'vera-falando');
  window.speechSynthesis.speak(fala);
}

function pararDeFalar() {
  if (window.speechSynthesis?.speaking) window.speechSynthesis.cancel();
}

function agentesConhecidos() {
  if (typeof ANDARES === 'undefined') return [];
  return Object.entries(ANDARES).flatMap(([andar, dados]) => (dados.agentes || []).map((a) => ({ ...a, andar })));
}

function enviarNoChat(texto) {
  if (!chatAberto) return;
  chatsPorVoz.set(chave(chatAberto.andar, chatAberto.agente), Date.now() + VOZ_VALE_MS);
  modalInput.value = texto;
  ajustarAlturaInput();
  document.getElementById('modal-form').requestSubmit();
}

async function resumoDoDia() {
  try {
    const resposta = await fetch('/api/vera/resumo', { headers: { Authorization: `Bearer ${sessao.token}` } });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || `HTTP ${resposta.status}`);
    veraFalar(dados.texto);
  } catch (erro) {
    veraFalar(`Não consegui montar o resumo agora: ${erro.message}.`);
  }
}

async function pedidoParaVera(texto) {
  veraBalao(`Você: ${texto}`);
  try {
    const dados = await pedirTriagem('/api/triagem', { texto });
    const { sugestao } = dados;
    try { await pedirTriagem(`/api/triagem/${dados.id}/decisao`, { agente: sugestao.agente }); } catch { /* segue */ }
    chatsPorVoz.set(chave(sugestao.andar, sugestao.agente), Date.now() + VOZ_VALE_MS);
    veraFalar(`Mandei para ${sugestao.nome}. Leio a resposta quando chegar.`);
    enviarPelaTriagem(sugestao.andar, sugestao.agente, texto, `você pediu por voz à Vera (${sugestao.motivo})`);
  } catch (erro) {
    veraFalar(`Não consegui encaminhar: ${erro.message}.`);
  }
}

function executar(alvo, resto) {
  if (alvo === 'agente') {
    if (!normalizarFala(resto)) return veraFalar('Pois não?', () => { esperando = { alvo, ate: Date.now() + ESPERA_COMANDO_MS }; });
    veraBalao(`Você: ${resto}`);
    return enviarNoChat(resto);
  }
  const comando = comandoVera(resto, agentesConhecidos());
  if (comando.tipo === 'esperar') return veraFalar('Pois não?', () => { esperando = { alvo, ate: Date.now() + ESPERA_COMANDO_MS }; });
  if (comando.tipo === 'parar') return pararDeFalar();
  if (comando.tipo === 'resumo') return resumoDoDia();
  if (comando.tipo === 'abrir') {
    if (andarAtual !== comando.agente.andar && cena) renderizarAndar(comando.agente.andar);
    abrirAgente(comando.agente.andar, comando.agente.id);
    return veraFalar(`Abri o chat de ${comando.agente.nome}.`);
  }
  return pedidoParaVera(comando.texto);
}

function ouviu(transcricao) {
  if (falando) return;
  pararDeFalar();
  if (esperando && Date.now() < esperando.ate) {
    const { alvo } = esperando;
    esperando = null;
    return executar(alvo, transcricao);
  }
  esperando = null;
  const nome = chatAberto ? document.getElementById('modal-nome')?.textContent : '';
  const chamado = acharChamado(transcricao, nome);
  if (chamado) return executar(chamado.alvo, chamado.resto);
  // Parecia um chamado e não bateu: mostra o que o navegador entendeu (sem isso, nada acontecia na tela).
  if (pareceChamado(transcricao)) {
    veraBalao(`Ouvi: “${transcricao.trim()}”. Para me chamar, comece com “Olá Vera”.`, 'vera-dica');
    setTimeout(() => { if (escutaLigada && !falando) veraBalao(''); }, 6000);
  }
}

const pareceChamado = (texto) => /\b(ola|oi|alo|hola|vera|bera|vela)\b/.test(normalizarFala(texto));

const ERROS_VOZ = {
  network: 'Sem conexão com o serviço de voz do navegador. Confira a internet e tente de novo.',
  'audio-capture': 'Nenhum microfone encontrado. Confira se ele está conectado e liberado no Windows.',
  'language-not-supported': 'Este navegador não reconhece português. Use o Chrome ou o Edge atualizados.',
};

function iniciarEscuta() {
  if (!Reconhecimento || falando) return;
  if (!escuta) {
    escuta = new Reconhecimento();
    escuta.lang = 'pt-BR';
    escuta.continuous = true;
    escuta.interimResults = false;
    escuta.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) ouviu(e.results[i][0].transcript);
      }
    };
    escuta.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        ligarEscuta(false);
        veraBalao('O navegador não deixou usar o microfone. Libere o microfone deste site e tente de novo.', 'vera-erro');
      } else if (ERROS_VOZ[e.error]) {
        veraBalao(ERROS_VOZ[e.error], 'vera-erro');
      } // no-speech e aborted: silêncio ou pausa normal, a escuta volta sozinha
    };
    // O navegador encerra a escuta contínua de tempos em tempos: volta sozinha enquanto estiver ligada.
    escuta.onend = () => { if (escutaLigada && !falando) setTimeout(iniciarEscuta, 300); };
  }
  try { escuta.start(); } catch { /* já estava ouvindo */ }
}

function ligarEscuta(ligar) {
  escutaLigada = ligar;
  try { localStorage.setItem(CHAVE_LIGADA, ligar ? '1' : ''); } catch { /* sem armazenamento: só nesta aba */ }
  const botao = document.getElementById('voz-ligar');
  botao?.setAttribute('aria-pressed', String(ligar));
  botao?.classList.toggle('ligado', ligar);
  if (ligar) {
    iniciarEscuta();
    veraBalao('Ouvindo. Diga "Olá Vera" ou, num chat, "Olá" e o nome do agente.');
    setTimeout(() => { if (escutaLigada) veraBalao(''); }, 5000);
  } else {
    try { escuta?.abort(); } catch { /* nada a parar */ }
    pararDeFalar();
    veraBalao('');
  }
}

// Respostas dos agentes a pedidos falados: chamada pelo chat (js/chat.js, adicionarMensagem).
function vozNovaMensagem(andar, agente, mensagem) {
  const k = chave(andar, agente);
  const ate = chatsPorVoz.get(k);
  if (!ate || mensagem.tipo !== 'agente') return;
  if (Date.now() > ate) { chatsPorVoz.delete(k); return; }
  veraFalar(textoParaFala(mensagem.texto));
}

if (typeof document !== 'undefined') {
  const botao = document.getElementById('voz-ligar');
  if (botao && !Reconhecimento) {
    botao.disabled = true;
    botao.title = 'Comando de voz disponível só no Chrome ou no Edge';
  }
  botao?.addEventListener('click', () => {
    if (falando) { pararDeFalar(); return; }
    ligarEscuta(!escutaLigada);
  });
  let ligadaAntes = false;
  try { ligadaAntes = localStorage.getItem(CHAVE_LIGADA) === '1'; } catch { /* sem armazenamento */ }
  // O navegador só libera o microfone depois de um clique na página: a escolha anterior volta no primeiro clique.
  if (ligadaAntes && Reconhecimento) {
    document.addEventListener('click', function retomar() {
      document.removeEventListener('click', retomar);
      if (!escutaLigada && sessao) ligarEscuta(true);
    });
  }
}
