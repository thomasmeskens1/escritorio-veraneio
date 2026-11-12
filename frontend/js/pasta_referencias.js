// Pasta de REFERÊNCIAS do Drive no pedido (Thomas, 12/11/2026): antes de enviar, o popup pergunta se os arquivos da
// pasta podem entrar na peça ou se são só para estudo. A resposta vai no fim do texto, num marcador que o backend e o
// trabalhador do Max leem (backend/referencias_pedido.py e scripts/max/pasta_referencias.py). Sem marcador = só estudo.

const LINK_PASTA_DRIVE = /https:\/\/drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\/[\w-]{10,80}/i;
// "Escritório veraneio -> referencias -> Casa veraneio -> ..." ou "REFERENCIAS > CASA VERANEIO" ou "REFERENCIAS/..."
const CAMINHO_REFERENCIAS = /\brefer[eê]ncias\s*(?:->|>|\/|\\)/i;
const MARCADOR_REFERENCIAS = /\[Pasta de refer[eê]ncias:[^\]]*\]/i;
const USO_REFERENCIAS = {
  estudo: { rotulo: 'Só para estudo', marcador: '[Pasta de referências: só para estudo]' },
  usar: { rotulo: 'Podem ser usados na peça', marcador: '[Pasta de referências: pode usar os arquivos na peça]' },
};

const citaPastaReferencias = (texto) => LINK_PASTA_DRIVE.test(texto || '') || CAMINHO_REFERENCIAS.test(texto || '');
const precisaPerguntarUso = (texto) => citaPastaReferencias(texto) && !MARCADOR_REFERENCIAS.test(texto || '');
const comMarcador = (texto, uso) => `${String(texto || '').trim()}\n\n${USO_REFERENCIAS[uso].marcador}`;

// true = pode enviar agora; false = abriu o popup, que reenvia o pedido com o marcador.
function garantirUsoReferencias(texto) {
  if (!precisaPerguntarUso(texto)) return true;
  const opcoes = Object.entries(USO_REFERENCIAS);
  abrirFormularioPopup({
    titulo: 'Os arquivos dessa pasta podem entrar na peça?', botao: 'Confirmar',
    campos: [{ nome: 'uso', rotulo: 'Arquivos da pasta citada', tipo: 'opcoes', obrigatorio: true,
      opcoes: opcoes.map(([, o]) => o.rotulo) }],
  }, (respostas) => {
    const escolhida = opcoes.find(([, o]) => o.rotulo === respostas.uso);
    if (!escolhida) return;
    const campo = document.getElementById('modal-input');
    campo.value = comMarcador(campo.value || texto, escolhida[0]);
    document.getElementById('modal-form').requestSubmit(); // envia o pedido que estava esperando
  }, 'Só estudo: a equipe aprende com eles, mas a peça usa só o acervo oficial. Nos dois casos, o que for aprendido '
    + 'passa pela aprovação da Diretoria antes de entrar no Cérebro.');
  return false;
}

if (typeof module !== 'undefined') {
  module.exports = { citaPastaReferencias, precisaPerguntarUso, comMarcador, USO_REFERENCIAS };
}
