// Painel de andamento do popup: etapas da tarefa ativa do agente e o status de cada uma.
// Aparece ao lado da conversa (janela mais larga) só enquanto há tarefa ativa; atualiza a cada 3 s.

const INTERVALO_ANDAMENTO = 3000;
const ICONES_ETAPA = { concluida: '✓', andamento: '●', pendente: '○', falhou: '✕' };
const ROTULOS_ETAPA = { concluida: 'concluída', andamento: 'em andamento', pendente: 'pendente', falhou: 'falhou' };
const modalAndamento = document.getElementById('modal-andamento');
let timerAndamento = null;

function acompanharAndamento(andar, agente) {
  pararAndamento();
  const atualizar = async () => {
    if (!sessao || !chatEstaAberto(andar, agente)) return pararAndamento();
    try {
      const resposta = await fetch(`/api/agentes/${encodeURIComponent(andar)}/${encodeURIComponent(agente)}/andamento`,
        { headers: { Authorization: `Bearer ${sessao.token}` } });
      if (!resposta.ok) return;
      const { ativa } = await resposta.json();
      if (chatEstaAberto(andar, agente)) mostrarAndamento(ativa);
    } catch {
      // sem conexão: tenta de novo no próximo ciclo
    }
  };
  atualizar();
  timerAndamento = setInterval(atualizar, INTERVALO_ANDAMENTO);
}

function pararAndamento() {
  clearInterval(timerAndamento);
  timerAndamento = null;
  mostrarAndamento(null);
}

function mostrarAndamento(ativa) {
  modalAndamento.closest('.janela-agente')?.classList.toggle('com-andamento', !!ativa);
  modalAndamento.hidden = !ativa;
  if (!ativa) {
    modalAndamento.replaceChildren();
    return;
  }
  const lista = novoEl('ol', 'andamento-lista');
  ativa.etapas.forEach(({ texto, status, sub }) => {
    // subitem: slide, página ou cena da peça acima
    const item = novoEl('li', `andamento-etapa etapa-${status}${sub ? ' andamento-sub' : ''}`);
    item.title = ROTULOS_ETAPA[status] || status;
    item.append(novoEl('span', 'andamento-icone', ICONES_ETAPA[status] || '○'), novoEl('span', 'andamento-texto', texto));
    lista.append(item);
  });
  const principais = ativa.etapas.filter((e) => !e.sub);  // a contagem é por etapa/peça; slides são detalhe
  const feitas = principais.filter((e) => e.status === 'concluida').length;
  const titulo = chatAberto && ativa.agente && ativa.agente !== dadosAgente(chatAberto.andar, chatAberto.agente).nome
    ? `Andamento · ${ativa.agente}` : 'Andamento';  // tarefa nascida aqui rodando em outro agente
  modalAndamento.replaceChildren(...[
    novoEl('h3', null, titulo),
    novoEl('p', 'andamento-pedido', ativa.pedido),
    novoEl('p', 'andamento-progresso', `${feitas} de ${principais.length} etapas`),
    criarEstimativa(ativa.estimativa),
    lista,
  ].filter(Boolean));
}

// "Tempo estimado: ~12 min (por volta de 15:40)", pelo ritmo das peças já feitas ou pela média do agente.
function criarEstimativa(estimativa) {
  if (!estimativa) return null;
  const minutos = Math.max(1, Math.round(estimativa.restante_s / 60));
  const hora = new Date(estimativa.previsao).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return novoEl('p', 'andamento-estimativa', `Tempo estimado: ~${minutos} min (por volta de ${hora})`);
}
