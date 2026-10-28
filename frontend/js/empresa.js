// Empresa da conversa: o Marketing e o Cérebro trabalham sempre para UMA empresa do grupo, escolhida no seletor do
// topo do chat (guardado por conversa). Sem empresa escolhida, nada é enviado: aparece um formulário pedindo.

const EMPRESAS_DO_GRUPO = [
  ['casa_veraneio', 'Casa Veraneio'], ['cv_corporativo', 'Casa Veraneio Corporativo'], ['casa_vero', 'Casa Vero Imóveis'],
];
const TODAS_AS_EMPRESAS = ['*', 'Todas (só para ensinar regras comuns)'];
// Quem pode trabalhar com o grupo inteiro (Thomas, 28/10/2026: "como estão as métricas das 3 empresas").
const VISAO_DO_GRUPO = { analista_metricas: ['*', 'Todas as empresas (visão do grupo)'] };
const seletorEmpresa = document.getElementById('modal-empresa');
const chaveEmpresa = (andar, agente) => `empresa:${andar}/${agente}`;

const ehCerebroEmpresa = (andar, agente) => dadosAgente(andar, agente).visual === 'cerebro';
const precisaEmpresa = (andar, agente) => andar === 'marketing' || ehCerebroEmpresa(andar, agente);
const opcaoTodas = (andar, agente) => (ehCerebroEmpresa(andar, agente) ? [TODAS_AS_EMPRESAS]
  : VISAO_DO_GRUPO[agente] ? [VISAO_DO_GRUPO[agente]] : []);

function lerEmpresa(andar, agente) {
  try {
    return localStorage.getItem(chaveEmpresa(andar, agente)) || '';
  } catch {
    return seletorEmpresa.dataset.valor || '';
  }
}

function gravarEmpresa(andar, agente, valor) {
  seletorEmpresa.dataset.valor = valor;
  try {
    localStorage.setItem(chaveEmpresa(andar, agente), valor);
  } catch {
    // sem armazenamento: vale só nesta sessão da página
  }
}

// Ao abrir a conversa: mostra o seletor (só onde a empresa importa) com a escolha salva.
function mostrarSeletorEmpresa(andar, agente) {
  const precisa = precisaEmpresa(andar, agente);
  seletorEmpresa.hidden = !precisa;
  if (!precisa) return;
  const opcoes = [['', 'Escolha a empresa…'], ...EMPRESAS_DO_GRUPO, ...opcaoTodas(andar, agente)];
  seletorEmpresa.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor)));
  seletorEmpresa.value = lerEmpresa(andar, agente);
  seletorEmpresa.dataset.empresa = seletorEmpresa.value;
}

function empresaDaConversa(andar, agente) {
  return precisaEmpresa(andar, agente) ? seletorEmpresa.value : '';
}

// Antes de enviar: sem empresa, mostra o formulário de escolha e devolve false (a mensagem fica no campo e é
// enviada assim que a empresa for escolhida).
function garantirEmpresa(andar, agente) {
  if (!precisaEmpresa(andar, agente) || seletorEmpresa.value) return true;
  const opcoes = [...EMPRESAS_DO_GRUPO, ...opcaoTodas(andar, agente)];
  const formulario = criarFormulario({
    titulo: 'Para qual empresa é esta conversa?', botao: 'Confirmar empresa',
    campos: [{ nome: 'empresa', rotulo: 'Empresa', tipo: 'opcoes', obrigatorio: true, opcoes: opcoes.map(([, r]) => r) }],
  }, (respostas) => {
    const escolhida = opcoes.find(([, rotulo]) => rotulo === respostas.empresa);
    if (!escolhida) return;
    seletorEmpresa.value = escolhida[0];
    seletorEmpresa.dispatchEvent(new Event('change'));
    document.getElementById('modal-form').requestSubmit(); // envia o pedido que estava esperando
  });
  const aviso = novoEl('div', 'msg msg-sistema');
  aviso.append(novoEl('span', 'msg-autor', 'sistema'),
    document.createTextNode('Cada empresa tem dados próprios e nada é misturado. Escolha a empresa desta conversa:'),
    formulario);
  modalHistorico.append(aviso);
  modalHistorico.scrollTop = modalHistorico.scrollHeight;
  return false;
}

seletorEmpresa.addEventListener('change', () => {
  if (!chatAberto) return;
  gravarEmpresa(chatAberto.andar, chatAberto.agente, seletorEmpresa.value);
  seletorEmpresa.dataset.empresa = seletorEmpresa.value;
});
