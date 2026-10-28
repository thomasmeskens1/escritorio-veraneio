// Setores (zonas de trabalho) dos andares: área no chão, nome pintado e mesas.
// `area` = [x, y, largura, profundidade] em tiles. `mesas` = tiles das estações, na ordem
// em que os agentes do setor ocupam; as que sobram viram "vagas". Setores sem mesas são só decoração.
// `estacao` é o estilo para agentes sem estação própria; `vaga`, o da mesa vazia.
// `semVagas`: mesas sem dono ficam só com a estação (sem a pílula "Vaga").

const SETORES = {
  porao: [
    { id: 'oficina', nome: 'Oficina', area: [0, 0, 6, 5], cor: 0xf4a261, estacao: 'bancada', vaga: 'vagaOficina', mesas: [[2, 1], [4, 1], [2, 3]] },
    { id: 'operacoes', nome: 'Operações', area: [6, 0, 4, 5], cor: 0x4dabf7, estacao: 'central', vaga: 'vagaOperacoes', mesas: [[7, 1], [9, 1], [7, 3]] },
    { id: 'servidores', nome: 'Servidores', area: [0, 6, 5, 6], cor: 0x69db7c },
    { id: 'deposito', nome: 'Depósito', area: [6, 6, 6, 6], cor: 0xadb5bd },
  ],
  marketing: [
    { id: 'gestao', nome: 'Gestão', area: [0, 0, 5, 4], cor: 0xd4af37, estacao: 'executiva', vaga: 'vagaExecutiva', mesas: [[1, 1], [3, 1]] },
    { id: 'criacao', nome: 'Criação', area: [5, 0, 6, 4], cor: 0xc77dff, estacao: 'design', mesas: [[6, 1], [8, 1], [10, 1]] },
    { id: 'conteudo', nome: 'Conteúdo', area: [0, 5, 6, 4], cor: 0xff8fab, estacao: 'redacao', mesas: [[1, 6], [3, 6], [5, 6]] },
    { id: 'reuniao', nome: 'Reunião', area: [6, 5, 4, 4], cor: 0x8ecae6 },
    { id: 'copa', nome: 'Copa', area: [10, 4, 4, 5], cor: 0xe9c46a },
    { id: 'video', nome: 'Vídeo', area: [0, 10, 7, 4], cor: 0xff6b6b, estacao: 'video', mesas: [[1, 11], [3, 11], [5, 11]] },
    { id: 'performance', nome: 'Performance', area: [7, 10, 7, 4], cor: 0x2a9d8f, estacao: 'graficos', mesas: [[8, 11], [10, 11], [12, 11]] },
  ],
  comercial: [
    { id: 'hospedagem', nome: 'Hospedagem', area: [0, 0, 6, 5], cor: 0xe9c46a, estacao: 'mesa', vaga: 'vaga', mesas: [[1, 1], [3, 1], [1, 3]] },
    { id: 'corporativo', nome: 'Corporativo', area: [6, 0, 4, 5], cor: 0x2a9d8f, estacao: 'executiva', vaga: 'vagaExecutiva', mesas: [[7, 1], [9, 1], [7, 3]] },
    // O Estrategista senta à mesa de reunião (cadeiras do fundo, sem estação própria), como os estagiários.
    { id: 'reuniao', nome: 'Reunião', area: [0, 6, 6, 6], cor: 0x8ecae6, estacao: 'nenhuma', mesas: [[1.7, 7.35], [3.7, 7.35]], semVagas: true },
    { id: 'lounge', nome: 'Lounge', area: [7, 6, 5, 6], cor: 0xd4af37 },
  ],
  cobertura: [
    // Os estagiários dividem a mesa de reunião (lugares nas cadeiras do fundo, sem estação própria).
    { id: 'reuniao', nome: 'Reunião', area: [1, 1, 8, 4], cor: 0x8ecae6, estacao: 'nenhuma', mesas: [[2.2, 1.45], [4.2, 1.45], [5.2, 1.45], [7.2, 1.45]], semVagas: true },
    // Laboratório do Cérebro (RAG central), sem vagas extras.
    { id: 'laboratorio', nome: 'Laboratório', area: [0, 6, 6, 6], cor: 0xff8fab, estacao: 'pedestal', mesas: [[3, 9]], semVagas: true },
  ],
};

function setoresDoAndar(nivel) {
  return SETORES[nivel] || [];
}

// Desenha uma estação (cadeira atrás do agente, mesa à frente) no tile (x, y).
function desenharEstacao(ctx, nome, x, y) {
  const estacao = ESTACOES[nome] || ESTACOES.mesa;
  if (estacao.atras) {
    const pes = isoParaTela(x + AGENTE_NO_TILE, y + AGENTE_NO_TILE);
    const g = ctx.cena.add.graphics().setDepth(PROF_BASE + pes.y - 1);
    estacao.atras(g, x, y);
    ctx.extras.push(g);
  }
  const frente = ctx.cena.add.graphics().setDepth(profundidade(x + 1, y + 1));
  estacao.frente(frente, x, y);
  ctx.extras.push(frente);
}

// Mesa vazia esperando um agente, com a pílula "Vaga" (não interativa; `semRotulo` omite a pílula).
function desenharVaga(ctx, { x, y, estacao, semRotulo }, escala) {
  desenharEstacao(ctx, estacao, x, y);
  if (semRotulo) return;
  const pes = isoParaTela(x + AGENTE_NO_TILE, y + AGENTE_NO_TILE);
  const t = ctx.cena.add.text(0, 0, 'Vaga', {
    fontFamily: 'system-ui, sans-serif', fontSize: '10px', color: '#ced4da',
  }).setOrigin(0.5);
  const largura = t.width + 14;
  const fundo = ctx.cena.add.graphics();
  fundo.fillStyle(0x15171c, 0.55);
  fundo.fillRoundedRect(-largura / 2, -8, largura, 16, 8);
  fundo.lineStyle(1, 0xffffff, 0.18);
  fundo.strokeRoundedRect(-largura / 2, -8, largura, 16, 8);
  const y0 = pes.y - 52;
  ctx.extras.push(ctx.cena.add.container(pes.x, y0, [fundo, t])
    .setDepth(PROF_ROTULOS + y0).setScale(escala).setAlpha(0.75));
}

// Contorno de uma área [x0,x1] x [y0,y1] do chão.
function contornoArea(g, x0, y0, x1, y1, largura, cor, alfa) {
  g.lineStyle(largura, cor, alfa);
  g.strokePoints([pIso(x0, y0), pIso(x1, y0), pIso(x1, y1), pIso(x0, y1)], true);
}

const ANGULO_EIXO_X = Math.atan2(TILE_H / 2, TILE_W / 2); // direção do eixo x na tela

// Tapete do setor, nome pintado na borda da frente e o brilho (oculto) de setor ativo.
// Devolve { setorId: registro } para alternar o brilho com definirBrilhoSetor.
function desenharSetores(nivel, ctx, escalaTexto = 1) {
  const registros = {};
  setoresDoAndar(nivel).forEach((s) => {
    const [ax, ay, w, d] = s.area;
    const x0 = ax + 0.12, y0 = ay + 0.12, x1 = ax + w - 0.12, y1 = ay + d - 0.12;
    // Chão sólido do setor, mostrado só no destaque (cobre o que de outros setores invade a área).
    const fundo = ctx.cena.add.graphics().setVisible(false);
    quadChao(fundo, ax, ay, ax + w, ay + d, tomCor(CENARIOS[nivel].chao.cor, 0.8), 1);
    quadChao(fundo, x0, y0, x1, y1, s.cor, 0.22);
    contornoArea(fundo, x0, y0, x1, y1, 2, s.cor, 0.8);
    ctx.extras.push(fundo);

    const g = ctx.cena.add.graphics().setDepth(PROF_PAREDE + 1);
    quadChao(g, x0, y0, x1, y1, s.cor, 0.12);
    quadChao(g, x0 + 0.12, y0 + 0.12, x1 - 0.12, y1 - 0.12, s.cor, 0.06);
    contornoArea(g, x0, y0, x1, y1, 2, s.cor, 0.45);
    contornoArea(g, x0 + 0.12, y0 + 0.12, x1 - 0.12, y1 - 0.12, 1, s.cor, 0.2);
    ctx.extras.push(g);

    const brilho = ctx.cena.add.graphics().setDepth(PROF_PAREDE + 1).setVisible(false);
    quadChao(brilho, x0, y0, x1, y1, tomCor(s.cor, 1.3), 0.3);
    contornoArea(brilho, x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05, 6, tomCor(s.cor, 1.5), 0.35);
    contornoArea(brilho, x0, y0, x1, y1, 2.5, tomCor(s.cor, 1.75), 1);
    ctx.extras.push(brilho);

    // Nome ao longo da borda da frente (eixo x), como faixa pintada no chão.
    const p = pIso(x0 + 0.3, y1 - 0.34);
    const rotulo = ctx.cena.add.text(p.x, p.y, s.nome.toUpperCase(), {
      fontFamily: 'Consolas, "Lucida Console", Menlo, monospace', fontSize: '16px', fontStyle: 'bold',
      color: `#${tomCor(s.cor, 1.5).toString(16).padStart(6, '0')}`,
    }).setOrigin(0, 0.5).setRotation(ANGULO_EIXO_X).setDepth(PROF_PAREDE + 2)
      .setScale(escalaTexto).setAlpha(0.6);
    rotulo.setLetterSpacing?.(3);
    ctx.extras.push(rotulo);

    registros[s.id] = { fundo, tapete: g, brilho, rotulo, ativo: false, tween: null };
  });
  return registros;
}

// Acende (pulsando) ou apaga o setor; não recria nada.
function definirBrilhoSetor(reg, ativo) {
  if (!reg || reg.ativo === ativo) return;
  reg.ativo = ativo;
  reg.tween?.remove();
  reg.tween = null;
  reg.brilho.setVisible(ativo).setAlpha(1);
  reg.rotulo.setAlpha(ativo ? 1 : 0.6);
  if (ativo) {
    reg.tween = cena.tweens.add({
      targets: reg.brilho, alpha: 0.55, duration: 1100, yoyo: true, repeat: -1, ease: 'Sine.inOut',
    });
  }
}
