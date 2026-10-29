// Correções que viram regra (ficha do Cérebro, só o Thomas): cada correção dele a um agente aparece aqui para
// virar regra (deste agente ou de todos) ou ser descartada; as regras ativas ficam listadas, com "Desativar".

const correcoes = { dados: null, erro: '', oculto: true };

async function carregarCorrecoes(andar, agente) {
  if (!sessao) return;
  try {
    const resposta = await fetch('/api/correcoes', { headers: { Authorization: `Bearer ${sessao.token}` } });
    if (resposta.status === 403 || resposta.status === 404) {
      Object.assign(correcoes, { dados: null, erro: '', oculto: true });
    } else if (!resposta.ok) {
      Object.assign(correcoes, { erro: 'Não foi possível carregar as correções.', oculto: false });
    } else {
      Object.assign(correcoes, { dados: await resposta.json(), erro: '', oculto: false });
    }
  } catch {
    Object.assign(correcoes, { erro: 'Servidor indisponível.', oculto: false });
  }
  if (chatEstaAberto(andar, agente)) renderizarPerfil();
}

async function decidirCorrecao(caminho, corpo) {
  const { andar, agente } = chatAberto || {};
  try {
    const resposta = await fetch(`/api/correcoes/${caminho}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${sessao.token}`, 'Content-Type': 'application/json' },
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    if (!resposta.ok) throw new Error((await resposta.json().catch(() => ({}))).detail || resposta.status);
  } catch (erro) {
    correcoes.erro = `Não foi possível salvar: ${erro.message}`;
  }
  if (andar) carregarCorrecoes(andar, agente);
}

function criarCorrecoes() {
  const bloco = novoEl('div', 'perfil-correcoes');
  const d = correcoes.dados;
  const n = d?.observacoes?.length || 0;
  bloco.append(novoEl('h4', null, n ? `Correções para revisar (${n})` : 'Correções para revisar'));
  if (correcoes.erro) bloco.append(novoEl('p', 'rotinas-nota erro', correcoes.erro));
  if (!d) return bloco;
  if (!n) {
    bloco.append(novoEl('p', 'rotinas-nota', 'Nenhuma pendente. Quando você corrigir um agente ("não é assim…", "na '
      + 'verdade…", "nunca…"), a correção aparece aqui para virar regra.'));
  }
  d.observacoes.forEach((o) => {
    const item = novoEl('div', 'correcao-item');
    item.append(novoEl('small', 'correcao-meta', `${o.agente_nome} · ${o.autor ? `por ${o.autor} · ` : ''}${formatarQuando(o.em)}`));
    if (o.resposta_anterior) {
      const antes = novoEl('details', 'correcao-antes');
      antes.append(novoEl('summary', null, 'Resposta corrigida'), novoEl('p', null, o.resposta_anterior));
      item.append(antes);
    }
    const regra = novoEl('textarea', 'correcao-regra');
    regra.rows = 2;
    regra.value = o.correcao;
    regra.setAttribute('aria-label', 'Texto da regra');
    const acoes = novoEl('div', 'correcao-acoes');
    const botao = (rotulo, classe, acao) => {
      const b = novoEl('button', classe, rotulo);
      b.type = 'button';
      b.addEventListener('click', () => { acoes.querySelectorAll('button').forEach((x) => { x.disabled = true; }); acao(); });
      return b;
    };
    acoes.append(
      botao(`Aprovar para ${o.agente_nome}`, 'botao-primario', () => decidirCorrecao(`${o.id}/aprovar`, { regra: regra.value, escopo: 'agente' })),
      botao('Aprovar para todos', 'botao-secundario', () => decidirCorrecao(`${o.id}/aprovar`, { regra: regra.value, escopo: 'todos' })),
      botao('Descartar', 'botao-secundario', () => decidirCorrecao(`${o.id}/descartar`)),
    );
    item.append(regra, acoes);
    bloco.append(item);
  });
  if (d.regras?.length) {
    const regras = novoEl('details', 'correcao-regras');
    regras.append(novoEl('summary', null, `Regras aprendidas ativas (${d.regras.length})`));
    d.regras.forEach((r) => {
      const linha = novoEl('div', 'correcao-regra-ativa');
      const desativar = novoEl('button', 'botao-secundario', 'Desativar');
      desativar.type = 'button';
      desativar.addEventListener('click', () => { desativar.disabled = true; decidirCorrecao(`regras/${r.id}/desativar`); });
      linha.append(novoEl('span', null, `${r.agente_nome}: ${r.regra}`), desativar);
      regras.append(linha);
    });
    bloco.append(regras);
  }
  return bloco;
}
