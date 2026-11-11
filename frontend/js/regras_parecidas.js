// Regra parecida (Onda 2, cerebro-21): no pop-up da correção, antes de aprovar, o aviso "parecida com a regra #N"
// (backend/regras_parecidas.py, por embedding ou por texto) e a escolha: substituir a antiga, unir (editar o texto e
// substituir) ou manter as duas. A escolha fica em regra.dataset.substituir, que js/correcoes.js manda no aprovar.
// A regra substituída não se apaga: sai do contexto e fica guardada.

function avisoRegrasParecidas(o, regra, antesDe) {
  const bloco = novoEl('div', 'reg-mensagem reg-resposta regra-parecida');
  bloco.hidden = true;
  antesDe.before(bloco);

  const opcao = (texto, valor, marcada) => {
    const rotulo = novoEl('label', 'form-rotulo');
    const radio = novoEl('input');
    radio.type = 'radio';
    radio.name = `regra-parecida-${o.id}`;
    radio.checked = !!marcada;
    radio.addEventListener('change', () => {
      if (valor) regra.dataset.substituir = String(valor);
      else delete regra.dataset.substituir;
    });
    rotulo.append(radio, document.createTextNode(` ${texto}`));
    return rotulo;
  };

  const desenhar = (lista) => {
    delete regra.dataset.substituir;
    bloco.replaceChildren();
    bloco.hidden = !lista.length;
    if (!lista.length) return;
    bloco.append(novoEl('strong', null, 'Atenção: regra parecida'));
    lista.forEach((c) => {
      const quando = (c.em || '').slice(0, 10);
      bloco.append(novoEl('p', null, c.tipo === 'regra'
        ? `Parecida com a regra #${c.id} (${c.agente_nome || c.agente}): ${c.texto}`
        : `Parecida com uma proposta descartada em ${quando}: ${c.texto}`));
      if (c.tipo === 'regra') {
        bloco.append(opcao(`Substituir a regra #${c.id} por esta (para unir as duas, edite o texto acima e substitua)`, c.id));
      }
    });
    bloco.append(opcao('Manter as duas', '', true));
  };

  const consultar = async () => {
    try {
      const resposta = await fetch(`/api/correcoes/${o.id}/parecidas`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ regra: regra.value, escopo: 'agente' }),
      });
      if (resposta.ok) desenhar((await resposta.json()).parecidas || []);
    } catch {
      // sem conexão: o aviso só não aparece; a aprovação segue normal
    }
  };
  consultar();
  regra.addEventListener('change', consultar);
}
