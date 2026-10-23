// Educação das empresas (ficha do Cérebro, só o Thomas): um botão por empresa abre no chat o formulário com o que
// ainda está PENDENTE no documento dela; as respostas são gravadas no documento e reindexadas no Cérebro.

const entrevista = { dados: null, oculto: true };

async function carregarEntrevista(andar, agente) {
  if (!sessao) return;
  try {
    const resposta = await fetch('/api/cerebro/entrevista', { headers: { Authorization: `Bearer ${sessao.token}` } });
    Object.assign(entrevista, resposta.ok ? { dados: await resposta.json(), oculto: false } : { dados: null, oculto: true });
  } catch {
    Object.assign(entrevista, { dados: null, oculto: true });
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

function criarEntrevista() {
  const bloco = novoEl('div', 'perfil-correcoes');
  bloco.append(novoEl('h4', null, 'Educação das empresas'));
  Object.entries(entrevista.dados || {}).forEach(([empresa, { nome, pendentes }]) => {
    const linha = novoEl('div', 'correcao-regra-ativa');
    linha.append(novoEl('span', null, pendentes.length ? `${nome}: ${pendentes.length} ponto(s) pendente(s)` : `${nome}: completo ✓`));
    if (pendentes.length) {
      const botao = novoEl('button', 'botao-secundario', 'Responder entrevista');
      botao.type = 'button';
      botao.addEventListener('click', () => abrirEntrevista(empresa, nome, pendentes));
      linha.append(botao);
    }
    bloco.append(linha);
  });
  return bloco;
}

function abrirEntrevista(empresa, nome, pendentes) {
  const formulario = criarFormulario({
    titulo: `Entrevista — ${nome}`, botao: 'Salvar no conhecimento',
    campos: pendentes.map((rotulo) => ({ nome: rotulo, rotulo, tipo: 'texto_longo', obrigatorio: false })),
  }, async (respostas) => {
    const aviso = novoEl('p', 'rotinas-nota', 'Salvando...');
    formulario.append(aviso);
    try {
      const resposta = await fetch(`/api/cerebro/entrevista/${empresa}`, {
        method: 'POST', headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ respostas }),
      });
      const dados = await resposta.json();
      aviso.textContent = resposta.ok
        ? `Salvo: ${dados.preenchidos} ponto(s) no documento da ${nome}. Ainda pendentes: ${dados.faltam.length}.`
        : `Não foi possível salvar (${dados.detail || resposta.status}).`;
    } catch {
      aviso.textContent = 'Servidor indisponível. Tente de novo.';
    }
    if (chatAberto) carregarEntrevista(chatAberto.andar, chatAberto.agente);
  });
  const mensagem = novoEl('div', 'msg msg-sistema');
  mensagem.append(novoEl('span', 'msg-autor', 'sistema'),
    document.createTextNode(`Responda o que souber; o que ficar em branco continua PENDENTE (os agentes perguntam antes de usar). `
      + 'Regras de ouro valem para todas: sem WhatsApp e sem site nos criativos.'), formulario);
  modalHistorico.append(mensagem);
  modalHistorico.scrollTop = modalHistorico.scrollHeight;
}
