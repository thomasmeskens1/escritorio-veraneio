// Textos e regras do chat sem tela (Onda 1 de 11/11/2026, Térreo): sinais de empresa, pedidos de ajuste rápido,
// "Levar para uma Peça final", aviso de espera e título da aba. Sem DOM: o teste roda no Node
// (tests/frontend/chat_textos.test.js).

const NOMES_CURTOS_EMPRESA = { casa_veraneio: 'Casa Veraneio', cv_corporativo: 'Corporativo', casa_vero: 'Casa Vero', '*': 'todas' };

// Poucas palavras fortes por empresa (recepcionista-25, ajuste do crítico): "evento" sozinho não entra, porque o
// Réveillon da Casa Veraneio também é evento. `servem`: empresas em que o sinal faz sentido; `sugere`: a provável.
const SINAIS_EMPRESA = [
  { padrao: /\bvero\s*(?:n[ºo°.]*\s*)?#?\d{1,4}\b/i, servem: ['casa_vero'], sugere: 'casa_vero' },
  { padrao: /\bim[oó]ve(?:l|is)\s+(?:à|a)\s+venda\b/i, servem: ['casa_vero'], sugere: 'casa_vero' },
  { padrao: /\bcolaboradores\b/i, servem: ['cv_corporativo'], sugere: 'cv_corporativo' },
  { padrao: /\bconfraterniza\w*/i, servem: ['cv_corporativo'], sugere: 'cv_corporativo' },
  { padrao: /\beventos?\s+(?:corporativ\w+|de empresas?|da empresa)\b/i, servem: ['cv_corporativo'], sugere: 'cv_corporativo' },
  // Lodge existe na Casa Veraneio e no Corporativo; só contradiz a Casa Vero (que usa "Vero N").
  { padrao: /\blodges?\s*(?:n[ºo°.]*\s*)?#?\d{1,3}\b/i, servem: ['casa_veraneio', 'cv_corporativo'], sugere: 'casa_veraneio' },
];

// Sinal de outra empresa no texto: { sugere, trecho } ou null. Sem empresa escolhida, com "Todas" ou com uma
// empresa citada pelo nome (o servidor já troca sozinho), não avisa.
function sinalDeOutraEmpresa(texto, selecionada, citada = '') {
  if (!texto || !selecionada || selecionada === '*' || citada) return null;
  for (const { padrao, servem, sugere } of SINAIS_EMPRESA) {
    const achado = padrao.exec(texto);
    if (achado && !servem.includes(selecionada)) return { sugere, trecho: achado[0] };
  }
  return null;
}

const rotuloEnviar = (empresa) => (NOMES_CURTOS_EMPRESA[empresa] ? `Enviar para ${NOMES_CURTOS_EMPRESA[empresa]}` : 'Enviar Tarefa');

// Ajustes rápidos (recepcionista-31, professor-03, copywriter-04): cada botão vira um pedido comum, com 👍/👎 e
// aprendizado. A ordem "mantenha igual o que não foi pedido" evita que a parte boa suma na versão seguinte.
const MANTER_IGUAL = 'Mantenha igual tudo o que não foi pedido: os fatos, a empresa, o Lodge ou imóvel, o CTA, a '
  + 'estrutura e as regras de ouro.';
const AJUSTES_RAPIDOS = [
  { rotulo: 'Mais curto', texto: `Reescreva a sua última resposta mais curta, sem perder a ideia principal. ${MANTER_IGUAL}` },
  { rotulo: 'Mais informal', texto: `Reescreva a sua última resposta com um tom mais informal e próximo. ${MANTER_IGUAL}` },
  { rotulo: 'Mais fluido', texto: `Reescreva a sua última resposta com o texto mais fluido, com frases que se ligam melhor. ${MANTER_IGUAL}` },
  { rotulo: '3 variações', texto: `Escreva 3 variações da sua última resposta, numeradas de 1 a 3. ${MANTER_IGUAL}` },
];
const AGENTES_AJUSTE_RAPIDO = ['copywriter', 'email_marketing']; // agentes de texto, sem Max (crítico: Social Media fica de fora)

// "Levar para uma Peça final" (copywriter-07, professor-16, recepcionista-32): o campo do Gestor já preenchido;
// a pessoa completa o formato e envia. `___` é a lacuna onde o cursor fica.
const LACUNA_FORMATO = '___';
const LIMITE_TEXTO_PECA = 20000; // o Gestor aceita 30 mil; sobra espaço para o resto do pedido

function textoParaPecaFinal(texto) {
  let aprovado = String(texto || '').trim();
  const cortado = aprovado.length > LIMITE_TEXTO_PECA;
  if (cortado) aprovado = `${aprovado.slice(0, LIMITE_TEXTO_PECA)}\n[texto cortado: confira o fim antes de enviar]`;
  const lodge = /\blodges?\s*(?:n[ºo°.]*\s*)?#?(\d{1,3})\b/i.exec(aprovado);
  const vero = /\bvero\s*(?:n[ºo°.]*\s*)?#?(\d{1,4})\b/i.exec(aprovado);
  const imovel = lodge ? `Lodge ${lodge[1]}` : vero ? `Vero ${vero[1]}` : LACUNA_FORMATO;
  return `Peça final: formato: ${LACUNA_FORMATO}\nLodge ou imóvel: ${imovel}\n`
    + `Texto aprovado (não reescrever; usar igual na arte e na legenda):\n${aprovado}`;
}

// Aviso de tarefa adiada em linguagem simples (recepcionista-20, ajuste do crítico: sem lugar na fila).
const FRASE_PODE_FECHAR = 'Pode fechar o escritório: a resposta chega aqui e na Caixa de entrada. Não precisa enviar de novo.';
const JARGAO_ESPERA = /modelos imediatos|conting[eê]ncia/i;

function textoDeEspera(texto) {
  const base = JARGAO_ESPERA.test(texto || '') ? 'Seu pedido entrou na fila e vai ser feito assim que um modelo ficar livre.'
    : String(texto || '').trim();
  return base.includes('Não precisa enviar de novo') ? base : `${base} ${FRASE_PODE_FECHAR}`.trim();
}

// Etapa "Na fila (fila de contingência ...)" do painel Andamento, em palavras simples.
const etapaSimples = (texto) => (/^Na fila \(/.test(texto || '') ? 'Na fila: a resposta chega aqui, pode fechar' : texto);

// Título da aba com as respostas que chegaram com a aba escondida (recepcionista-21, professor-08).
const tituloComContador = (base, n) => (n > 0 ? `(${n > 99 ? '99+' : n}) ${base}` : base);

if (typeof module !== 'undefined') {
  module.exports = { sinalDeOutraEmpresa, rotuloEnviar, AJUSTES_RAPIDOS, AGENTES_AJUSTE_RAPIDO, MANTER_IGUAL,
    textoParaPecaFinal, LACUNA_FORMATO, textoDeEspera, etapaSimples, tituloComContador, NOMES_CURTOS_EMPRESA };
}
