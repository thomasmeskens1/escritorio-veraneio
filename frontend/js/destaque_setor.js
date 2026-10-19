// Destaque de setor no hover: mesas, vagas, agentes e rótulos do setor vão para a frente,
// e o nome do setor fica acima de tudo. O tapete (chão) não muda.

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

// Setor sob o ponto (coordenadas do mundo), invertendo a projeção isométrica.
function setorNoPonto(xMundo, yMundo) {
  const origem = isoParaTela(0, 0);
  const u = (xMundo - origem.x) / (TILE_W / 2);
  const v = (yMundo - origem.y) / (TILE_H / 2);
  const x = (u + v) / 2;
  const y = (v - u) / 2;
  const setor = setoresDoAndar(andarAtual).find(({ area: [ax, ay, w, d] }) =>
    x >= ax && x < ax + w && y >= ay && y < ay + d);
  return setor ? setor.id : null;
}

function aplicarDestaque(id, ativo) {
  const reg = setoresAndar[id];
  if (!reg) return;
  (reg.objetos || []).forEach((obj) => {
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
