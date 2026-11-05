// Modelos de pedido do Gestor (Onda 2, item 12; gestor-03 e analista_tendencias-26, 31/10/2026): no chat do Gestor,
// o botão "Modelos" abre a escolha de uma ficha pronta para as campanhas que se repetem; a ficha usa o pop-up de
// formulário que já existe (js/formularios.js) e vira uma mensagem com os campos já separados. O texto livre
// continua valendo. No máximo 7 campos, quase todos opcionais; o que ficar vazio o Gestor decide ou pergunta.

const SUGERIR = 'Deixe o sistema sugerir';
const PAPEIS = ['Descoberta', 'Consideração', 'Confiança', 'Conversão', 'Relacionamento', SUGERIR]; // manual 15 §5
const VALORES_ARTE = ['Sem valores (padrão)', 'Com a diária do período'];
const REFERENCIAS = { nome: 'referencias', rotulo: 'Referências (links, peças anteriores, observações)', tipo: 'texto_longo' };

const MODELOS_PEDIDO = [
  {
    titulo: 'Carrossel de feriado com várias casas', empresa: 'Casa Veraneio', formato: 'CARROSSEL',
    campos: [
      { nome: 'ocasiao', rotulo: 'Feriado ou ocasião (ex.: 20/11, Corpus Christi)', tipo: 'texto', obrigatorio: true },
      { nome: 'data', rotulo: 'Data de postagem', tipo: 'data' },
      { nome: 'lodges', rotulo: 'Lodges pelo número (o principal primeiro)', tipo: 'texto' },
      { nome: 'condicao', rotulo: 'Condição especial', tipo: 'opcoes', opcoes: ['Não', 'Sim (descrevo nas referências)'] },
      { nome: 'valores', rotulo: 'Valores na arte', tipo: 'opcoes', opcoes: VALORES_ARTE },
      { nome: 'papel', rotulo: 'Papel na jornada', tipo: 'opcoes', opcoes: PAPEIS },
      REFERENCIAS,
    ],
  },
  {
    titulo: 'Reels de contagem regressiva', empresa: 'Casa Veraneio', formato: 'REELS',
    campos: [
      { nome: 'momento', rotulo: 'Momento', tipo: 'opcoes', opcoes: ['Réveillon', 'Carnaval', 'Feriado'], obrigatorio: true },
      { nome: 'data', rotulo: 'Data de postagem (a contagem depende dela)', tipo: 'data', obrigatorio: true },
      { nome: 'lodges', rotulo: 'Lodges pelo número', tipo: 'texto' },
      // Todo vídeo sai sem som e com som (Sonoplasta, 05/11/2026): aqui só o clima da trilha da versão com som.
      { nome: 'musica', rotulo: 'Clima da música (o vídeo sai com e sem som)', tipo: 'opcoes', opcoes: ['O Sonoplasta escolhe', 'Mais calma', 'Mais animada'] },
      { nome: 'valores', rotulo: 'Valores na arte', tipo: 'opcoes', opcoes: VALORES_ARTE },
      REFERENCIAS,
    ],
  },
  {
    titulo: 'Lodge em destaque', empresa: 'Casa Veraneio', formato: '',
    campos: [
      { nome: 'lodge', rotulo: 'Lodge pelo número', tipo: 'texto', obrigatorio: true },
      { nome: 'formato', rotulo: 'Formato', tipo: 'opcoes', opcoes: ['POST', 'CARROSSEL', 'REELS', 'STORIES'], obrigatorio: true },
      { nome: 'data', rotulo: 'Data de postagem', tipo: 'data' },
      { nome: 'periodo', rotulo: 'Período da diária na legenda', tipo: 'opcoes', opcoes: ['Réveillon', 'Feriado', 'Carnaval', 'Sem diária'] },
      { nome: 'valores', rotulo: 'Valores na arte', tipo: 'opcoes', opcoes: VALORES_ARTE },
      { nome: 'papel', rotulo: 'Papel na jornada', tipo: 'opcoes', opcoes: PAPEIS },
      REFERENCIAS,
    ],
  },
  {
    titulo: 'Campanha de data comercial', empresa: 'Casa Veraneio', formato: '',
    campos: [
      { nome: 'momento', rotulo: 'Momento', tipo: 'opcoes', opcoes: ['Réveillon', 'Carnaval', 'Feriado', 'Black Friday', 'Férias'], obrigatorio: true },
      { nome: 'condicao', rotulo: 'Condição especial', tipo: 'opcoes', opcoes: ['Não', 'Sim (descrevo abaixo)'], obrigatorio: true },
      { nome: 'base_valor', rotulo: 'Base de valor', tipo: 'opcoes', opcoes: ['Sem valores', 'Diária cheia do período', 'A partir de (só os Lodges da peça)'] },
      { nome: 'lodges', rotulo: 'Lodges pelo número', tipo: 'texto' },
      { nome: 'minimo', rotulo: 'Mínimo de noites (se for diferente da ficha)', tipo: 'numero' },
      { nome: 'pecas', rotulo: 'Peças', tipo: 'multipla', opcoes: ['POST', 'CARROSSEL', 'REELS', 'STORIES'] },
      REFERENCIAS,
    ],
  },
  {
    titulo: 'Case de evento (Corporativo)', empresa: 'Casa Veraneio Corporativo', formato: 'CARROSSEL',
    campos: [
      { nome: 'evento', rotulo: 'Tipo de evento (ex.: off-site, confraternização)', tipo: 'texto', obrigatorio: true },
      { nome: 'espaco', rotulo: 'Espaço do Corporativo (Lodge N da ficha Corp)', tipo: 'texto' },
      { nome: 'prova', rotulo: 'Feedback real do cliente (só se houver)', tipo: 'texto_longo' },
      { nome: 'canal', rotulo: 'Canal principal', tipo: 'opcoes', opcoes: ['Instagram', 'LinkedIn', 'Os dois'] },
      { nome: 'data', rotulo: 'Data de postagem', tipo: 'data' },
      { nome: 'papel', rotulo: 'Papel na jornada', tipo: 'opcoes', opcoes: PAPEIS },
      REFERENCIAS,
    ],
  },
  {
    titulo: 'Imóvel Vero em destaque', empresa: 'Casa Vero', formato: '',
    campos: [
      { nome: 'imovel', rotulo: 'Imóvel (Vero N ou link do site)', tipo: 'texto', obrigatorio: true },
      { nome: 'formato', rotulo: 'Formato', tipo: 'opcoes', opcoes: ['CARROSSEL', 'REELS', 'POST', 'SHORTS'], obrigatorio: true },
      { nome: 'publico', rotulo: 'Fala com', tipo: 'opcoes', opcoes: ['Comprador', 'Proprietário'] },
      { nome: 'valor', rotulo: 'Valor do imóvel', tipo: 'opcoes', opcoes: ['Não mostrar (padrão)', 'Autorizo mostrar o valor de venda'] },
      { nome: 'angulo', rotulo: 'Ângulo', tipo: 'opcoes', opcoes: ['Arquitetura', 'Paisagismo e terreno', 'Lazer e wellness', 'Entorno', SUGERIR] },
      { nome: 'data', rotulo: 'Data de postagem', tipo: 'data' },
      REFERENCIAS,
    ],
  },
];

// Texto da mensagem ao Gestor: empresa e formato explícitos, um campo por linha (só os preenchidos).
function textoDoModelo(modelo, respostas) {
  const linhas = [`Pedido pelo modelo "${modelo.titulo}". A empresa é a ${modelo.empresa}.`];
  if (modelo.formato) linhas.push(`Formato: ${modelo.formato}`);
  modelo.campos.forEach((c) => { if (respostas[c.nome]) linhas.push(`- ${c.rotulo}: ${respostas[c.nome]}`); });
  linhas.push('Campos vazios: decida e explique; pergunte só o que for indispensável.');
  return linhas.join('\n');
}

function abrirModeloPedido(modelo) {
  abrirFormularioPopup({ titulo: modelo.titulo, campos: modelo.campos, botao: 'Enviar ao Gestor' },
    (respostas) => enviarRespostasDoFormulario(respostas, textoDoModelo(modelo, respostas)),
    `${modelo.empresa}: preencha o que já souber`);
}

function escolherModeloPedido() {
  const opcoes = MODELOS_PEDIDO.map((m) => m.titulo);
  abrirFormularioPopup({ titulo: 'Usar modelo de pedido', botao: 'Abrir modelo',
    campos: [{ nome: 'modelo', rotulo: 'Modelo', tipo: 'opcoes', opcoes, obrigatorio: true }] },
  (respostas) => {
    const modelo = MODELOS_PEDIDO.find((m) => m.titulo === respostas.modelo);
    // O pop-up da escolha fecha logo depois deste retorno: a ficha abre no próximo ciclo.
    if (modelo) setTimeout(() => abrirModeloPedido(modelo), 0);
  }, 'Fichas prontas para as campanhas que se repetem');
}

// Chamado ao abrir um chat (js/chat.js): o botão só aparece no Gestor.
function mostrarModelosPedido(agente) {
  let botao = document.getElementById('modal-modelos-pedido');
  if (!botao) {
    botao = novoEl('button', 'botao-anexar botao-modelos-pedido', 'Modelos');
    botao.id = 'modal-modelos-pedido';
    botao.type = 'button';
    botao.title = 'Usar uma ficha pronta de pedido (carrossel de feriado, contagem regressiva, Lodge em destaque...)';
    botao.addEventListener('click', escolherModeloPedido);
    document.getElementById('modal-input').before(botao);
  }
  botao.hidden = agente !== 'gestor';
}
