// Voz no PC (backend/voz_local.py; Thomas, 13/11/2026): o navegador continua só detectando o "Olá Vera"; o trecho
// falado vai para o Whisper local, que conhece o vocabulário do escritório (o Chrome ouvia "máquina" no lugar de
// "marketing"), e a resposta da Vera sai na voz Kokoro "Dora". Sem os modelos no PC, tudo volta para a voz do navegador.
//
// Captura: os últimos 20 s do microfone ficam guardados em PCM 16 kHz (AudioContext + ScriptProcessor, que não
// precisa de módulo externo e passa pela política de segurança do site). Quando a Vera é chamada, o trecho desde o
// começo da frase vira um WAV e vai para /api/voz/transcrever.

const VOZ_LOCAL_JANELA_S = 20;
const VOZ_LOCAL_PRAZO_MS = 12000;
const vozLocal = { transcrever: false, falar: false, conferido: false };
let captura = null;      // { ctx, fonte, processador, stream, blocos: [{ t, dados }] }
let audioAtual = null;   // fala da Kokoro tocando agora
let filaFala = null;     // { cancelada } da fala em andamento

async function conferirVozLocal() {
  if (vozLocal.conferido || typeof sessao === 'undefined' || !sessao) return vozLocal;
  try {
    const resposta = await fetch('/api/voz/disponivel', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.ok) Object.assign(vozLocal, await resposta.json());
  } catch { /* sem a voz local: segue a do navegador */ }
  vozLocal.conferido = true;
  return vozLocal;
}

async function iniciarCaptura() {
  if (captura || !navigator.mediaDevices?.getUserMedia) return;
  await conferirVozLocal();
  if (!vozLocal.transcrever) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    const ctx = new AudioContext({ sampleRate: 16000 });
    const fonte = ctx.createMediaStreamSource(stream);
    const processador = ctx.createScriptProcessor(4096, 1, 1);
    const blocos = [];
    processador.onaudioprocess = (e) => {
      const agora = performance.now();
      blocos.push({ t: agora, dados: new Float32Array(e.inputBuffer.getChannelData(0)) });
      while (blocos.length && agora - blocos[0].t > VOZ_LOCAL_JANELA_S * 1000) blocos.shift();
    };
    fonte.connect(processador);
    processador.connect(ctx.destination); // a saída fica em silêncio: só lemos a entrada
    captura = { ctx, fonte, processador, stream, blocos };
  } catch {
    captura = null; // sem captura: o texto do navegador continua valendo
  }
}

function pararCaptura() {
  if (!captura) return;
  captura.stream.getTracks().forEach((t) => t.stop());
  try { captura.processador.disconnect(); captura.fonte.disconnect(); captura.ctx.close(); } catch { /* já fechado */ }
  captura = null;
}

// PCM float -> WAV 16 bits mono (o formato que o servidor lê sem ffmpeg)
function wavDePcm(amostras, taxa = 16000) {
  const buffer = new ArrayBuffer(44 + amostras.length * 2);
  const v = new DataView(buffer);
  const texto = (pos, s) => [...s].forEach((c, i) => v.setUint8(pos + i, c.charCodeAt(0)));
  texto(0, 'RIFF'); v.setUint32(4, 36 + amostras.length * 2, true); texto(8, 'WAVE'); texto(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, taxa, true);
  v.setUint32(28, taxa * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); texto(36, 'data');
  v.setUint32(40, amostras.length * 2, true);
  amostras.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buffer], { type: 'audio/wav' });
}

// Texto do trecho falado desde `inicio` (performance.now), pelo Whisper local; null se não deu (usa o do navegador).
async function transcreverDesde(inicio) {
  if (!captura || !vozLocal.transcrever) return null;
  const blocos = captura.blocos.filter((b) => b.t >= inicio);
  const total = blocos.reduce((s, b) => s + b.dados.length, 0);
  if (total < 16000 * 0.4) return null; // menos de 0,4 s: nada útil
  const amostras = new Float32Array(total);
  let pos = 0;
  blocos.forEach((b) => { amostras.set(b.dados, pos); pos += b.dados.length; });
  const controle = new AbortController();
  const prazo = setTimeout(() => controle.abort(), VOZ_LOCAL_PRAZO_MS);
  try {
    const resposta = await fetch('/api/voz/transcrever', {
      method: 'POST', body: wavDePcm(amostras), signal: controle.signal,
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'audio/wav' },
    });
    if (!resposta.ok) return null;
    const { texto } = await resposta.json();
    return texto || null;
  } catch {
    return null;
  } finally {
    clearTimeout(prazo);
  }
}

// Fala na voz Kokoro, frase a frase (a próxima é gerada enquanto a anterior toca). Devolve false se não deu para
// começar, e aí quem chamou usa a voz do navegador.
async function falarLocal(frases, aoTerminar) {
  await conferirVozLocal();
  if (!vozLocal.falar || !frases.length) return false;
  pararFalaLocal();
  const fila = { cancelada: false };
  filaFala = fila;
  const gerar = (frase) => fetch('/api/voz/falar', {
    method: 'POST', headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: frase }),
  }).then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`HTTP ${r.status}`))));
  let proxima = gerar(frases[0]);
  try {
    await proxima; // a primeira precisa sair, senão volta para a voz do navegador
  } catch {
    return false;
  }
  (async () => {
    for (let i = 0; i < frases.length && !fila.cancelada; i++) {
      let blob;
      try { blob = await proxima; } catch { break; }
      if (i + 1 < frases.length) proxima = gerar(frases[i + 1]);
      if (fila.cancelada) break;
      const url = URL.createObjectURL(blob);
      audioAtual = new Audio(url);
      await new Promise((fim) => {
        audioAtual.onended = fim;
        audioAtual.onerror = fim;
        audioAtual.play().catch(fim);
      });
      URL.revokeObjectURL(url);
    }
    audioAtual = null;
    if (filaFala === fila) filaFala = null;
    aoTerminar();
  })();
  return true;
}

function pararFalaLocal() {
  if (filaFala) filaFala.cancelada = true;
  if (audioAtual) { audioAtual.pause(); audioAtual.onended?.(); }
}

if (typeof module !== 'undefined') module.exports = { wavDePcm };
