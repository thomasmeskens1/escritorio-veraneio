// Piloto da prospecção (Onda 2, prospectador-09): na ficha do Prospectador, o botão abre as 3 prévias do piloto e
// cada vendedor dá uma nota de 1 a 5 ("ligaria?"), com comentário, para cada lead. Quando as 3 têm nota, aparece o
// resumo. Os leads aparecem sem e-mail, telefone nem site, e nada aqui cria lead no Monday (backend/prospeccao_piloto.py).

function criarPilotoProspeccao() {
  const bloco = novoEl('div', 'perfil-piloto');
  const botao = novoEl('button', 'botao-secundario', 'Piloto: dar nota aos leads');
  botao.type = 'button';
  botao.title = 'Nota de 1 a 5 para cada lead das prévias do piloto';
  botao.addEventListener('click', abrirPilotoProspeccao);
  bloco.append(botao);
  return bloco;
}

async function pilotoApi(caminho, corpo) {
  const resposta = await fetch(`/api/prospeccao/${caminho}`, {
    method: corpo ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${sessao.token}`, ...(corpo ? { 'Content-Type': 'application/json' } : {}) },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(Array.isArray(dados.detail) ? dados.detail.map((d) => d.msg).join('; ') : dados.detail || resposta.status);
  return dados;
}

function linhaLeadPiloto(previaId, lead, aviso) {
  const item = novoEl('div', 'reg-mensagem reg-resposta');
  const detalhes = [lead.local, lead.segmento, lead.porte].filter(Boolean).join(' · ');
  item.append(novoEl('strong', null, `${lead.n}. ${lead.empresa}${detalhes ? ` (${detalhes})` : ''}`));
  if (lead.motivo) item.append(novoEl('p', null, `Por quê: ${lead.motivo}`));
  const minha = lead.notas.find((n) => n.minha);
  lead.notas.forEach((n) => item.append(novoEl('small', 'correcao-meta',
    `${n.nome}: ${n.nota}${n.comentario ? ` · ${n.comentario}` : ''}`)));
  const nota = novoEl('select', 'form-entrada');
  [1, 2, 3, 4, 5].forEach((v) => {
    const op = novoEl('option', null, String(v));
    op.value = String(v);
    nota.append(op);
  });
  nota.value = String(minha?.nota || 3);
  nota.setAttribute('aria-label', `Nota do lead ${lead.n}`);
  const comentario = novoEl('input', 'form-entrada');
  comentario.placeholder = 'Comentário (sem e-mail nem telefone)';
  comentario.maxLength = 500;
  comentario.value = minha?.comentario || '';
  const salvar = novoEl('button', 'botao-primario', 'Salvar nota');
  salvar.type = 'button';
  salvar.addEventListener('click', async () => {
    salvar.disabled = true;
    try {
      const r = await pilotoApi(`previas/${previaId}/notas`, { lead: lead.n, nota: Number(nota.value), comentario: comentario.value });
      salvar.textContent = r.completo ? 'Salva · piloto completo' : 'Salva';
      aviso.textContent = '';
    } catch (erro) {
      aviso.textContent = `Não foi possível salvar: ${erro.message}`;
      salvar.disabled = false;
    }
  });
  item.append(nota, comentario, salvar);
  return item;
}

function resumoPiloto(r) {
  const bloco = novoEl('div', 'reg-mensagem reg-pedido');
  bloco.append(novoEl('strong', null, 'Resumo do piloto'),
    novoEl('p', null, `${r.leads} leads, ${r.notas} notas, média ${r.media_geral ?? '—'}. Ligariam: ${r.ligaria} (${r.ligaria_pct}%).`),
    novoEl('p', null, `Notas 1 a 5: ${Object.entries(r.distribuicao).map(([k, v]) => `${k}: ${v}`).join(' · ')}`),
    novoEl('p', null, `Por vendedor: ${r.por_vendedor.map((v) => `${v.nome} ${v.media} (${v.notas})`).join(' · ')}`),
    novoEl('p', null, `Melhores: ${r.melhores.map((m) => `${m.empresa} ${m.media}`).join(' · ')}`));
  r.comentarios.forEach((c) => bloco.append(novoEl('small', 'correcao-meta', `${c.empresa} · ${c.nome} (${c.nota}): ${c.comentario}`)));
  return bloco;
}

async function abrirPilotoProspeccao() {
  fecharFormularioPopup();
  const fundo = novoEl('div', 'modal aberto modal-formulario');
  const janela = novoEl('section', 'janela janela-formulario janela-usuario');
  janela.setAttribute('role', 'dialog');
  janela.setAttribute('aria-modal', 'true');
  const barra = novoEl('header', 'janela-barra');
  const titulo = novoEl('div', 'janela-titulo');
  titulo.append(novoEl('h2', null, 'Piloto da prospecção'),
    novoEl('p', null, 'Nota de 1 a 5 para cada lead: você ligaria para esta empresa? Nada é criado no Monday.'));
  const fechar = novoEl('button', 'fechar', '×');
  fechar.type = 'button';
  fechar.setAttribute('aria-label', 'Fechar');
  fechar.addEventListener('click', fecharFormularioPopup);
  barra.append(titulo, fechar);
  const corpo = novoEl('div', 'formulario-corpo usuario-corpo');
  const aviso = novoEl('p', 'rotinas-nota erro');
  corpo.append(aviso);
  janela.append(barra, corpo);
  fundo.append(janela);
  fundo.addEventListener('click', (e) => { if (e.target === fundo) fecharFormularioPopup(); });
  fundo.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fecharFormularioPopup(); } });
  document.body.append(fundo);
  popupFormulario = fundo;
  try {
    const dados = await pilotoApi('piloto');
    if (!dados.previas.length) {
      corpo.append(novoEl('p', 'rotinas-nota', 'O piloto ainda não tem prévias. O master escolhe as 3 prévias quando quiser.'));
      return;
    }
    if (dados.resumo) corpo.append(resumoPiloto(dados.resumo));
    dados.previas.forEach((p) => {
      corpo.append(novoEl('h4', null, p.existe ? `Prévia #${p.id}${p.pedido ? ` · ${p.pedido}` : ''}` : `Prévia #${p.id} (não encontrada)`));
      p.leads.forEach((l) => corpo.append(linhaLeadPiloto(p.id, l, aviso)));
    });
    if (dados.faltam_previas) corpo.append(novoEl('p', 'rotinas-nota', `Faltam ${dados.faltam_previas} prévia(s) no piloto.`));
  } catch (erro) {
    aviso.textContent = `Não foi possível abrir o piloto: ${erro.message}`;
  }
}
