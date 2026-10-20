// Destaque de setor no hover: o chão do setor vira um fundo sólido acima do resto do andar,
// os móveis, mesas, vagas e agentes do setor ficam sobre ele e o nome fica acima de tudo.

const ELEVACAO_DESTAQUE = 300000; // acima de qualquer objeto ou rótulo de outro setor
const PROF_NOME_DESTAQUE = 700000;
let setorDestacado = null;

// Guarda no registro do setor os objetos criados por `criar`.
function registrarObjetosSetor(setor, criar) {
  const antes = elementos.length;
  criar();
  const reg = setoresAndar[setor];
  if (reg) (reg.objetos ||= []).push(...elementos.slice(antes));
}

function setorNoTile(x, y) {
  const setor = setoresDoAndar(andarAtual).find(({ area: [ax, ay, w, d] }) =>
    x >= ax && x < ax + w && y >= ay && y < ay + d);
  return setor ? setor.id : null;
}

// Móveis do cenário (decoração) pertencem ao setor que contém a sua posição.
function distribuirMoveisNosSetores(moveis = []) {
  moveis.forEach(({ x, y, objetos }) => {
    const reg = setoresAndar[setorNoTile(x, y)];
    if (reg) (reg.objetos ||= []).push(...objetos);
  });
}

// Setor sob o ponto (coordenadas do mundo), invertendo a projeção isométrica.
function setorNoPonto(xMundo, yMundo) {
  const origem = isoParaTela(0, 0);
  const u = (xMundo - origem.x) / (TILE_W / 2);
  const v = (yMundo - origem.y) / (TILE_H / 2);
  return setorNoTile((u + v) / 2, (v - u) / 2);
}

// Avatares de visitantes (js/visitas.js) que estão dentro do setor agora.
function objetosDeVisitantes(setor) {
  return Object.values(presencas).filter((p) => setorNoTile(p.g.x, p.g.y) === setor).flatMap((p) => p.avatar.objetos);
}

function aplicarDestaque(id, ativo) {
  const reg = setoresAndar[id];
  if (!reg) return;
  if (ativo) reg.visitantes = objetosDeVisitantes(id);
  // Chão: fundo sólido, tapete e brilho logo acima do resto do andar (e abaixo dos objetos do setor).
  reg.fundo.setVisible(ativo).setDepth(ELEVACAO_DESTAQUE);
  [reg.tapete, reg.brilho].forEach((g) => {
    if (ativo) g.profundidadeBase = g.depth;
    g.setDepth(ativo ? ELEVACAO_DESTAQUE + 1 : g.profundidadeBase);
  });
  [...(reg.objetos || []), ...(reg.visitantes || [])].forEach((obj) => {
    if (!obj.active) return;
    if (ativo) {
      obj.profundidadeBase = obj.depth;
      obj.setDepth(obj.depth + ELEVACAO_DESTAQUE);
    } else if (obj.profundidadeBase !== undefined) {
      obj.setDepth(obj.profundidadeBase);
    }
  });
  if (ativo) {
    reg.rotulo.profundidadeBase = reg.rotulo.depth;
    reg.rotulo.setDepth(PROF_NOME_DESTAQUE).setAlpha(1);
  } else {
    reg.rotulo.setDepth(reg.rotulo.profundidadeBase ?? reg.rotulo.depth).setAlpha(reg.ativo ? 1 : 0.6);
  }
}

function destacarSetor(id) {
  if (id === setorDestacado) return;
  if (setorDestacado) aplicarDestaque(setorDestacado, false);
  setorDestacado = id;
  if (id) aplicarDestaque(id, true);
}

function configurarDestaqueSetores() {
  cena.input.on('pointermove', (ponteiro) => destacarSetor(setorNoPonto(ponteiro.worldX, ponteiro.worldY)));
  cena.input.on('gameout', () => destacarSetor(null));
}
