// Visual do escritório: desde a Fase 6 da migração (13/11/2026) todos abrem no 3D; "?visual=2d" é a reserva
// até o 2D ser removido. Rodar no PC: node --test tests/frontend/visual.test.js

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CODIGO = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'js', 'visual.js'), 'utf8');

function carregar({ busca = '' } = {}) {
  const escritos = [];
  const ctx = {
    location: { search: busca },
    URLSearchParams,
    document: { documentElement: { dataset: {} }, write: (t) => escritos.push(t) },
  };
  vm.runInNewContext(`${CODIGO}\nthis.VISUAL = VISUAL; this.visualDaSessao = visualDaSessao;`, ctx);
  return { ctx, escritos };
}

test('todos abrem no 3D', () => {
  const { ctx } = carregar();
  assert.strictEqual(ctx.VISUAL, '3d');
  assert.strictEqual(ctx.visualDaSessao({ master: false }), '3d');
  assert.strictEqual(ctx.visualDaSessao(null), '3d');
});

test('?visual=2d continua como reserva', () => {
  assert.strictEqual(carregar({ busca: '?visual=2d' }).ctx.VISUAL, '2d');
  assert.strictEqual(carregar({ busca: '?visual=xyz' }).ctx.VISUAL, '3d');
});

test('scripts certos de cada visual, na ordem', () => {
  const { escritos: s3d, ctx } = carregar();
  assert.deepStrictEqual(s3d, ['<script src="js/escritorio3d/estado.js"></script>']);
  assert.strictEqual(ctx.document.documentElement.dataset.visual, '3d');
  const s2d = carregar({ busca: '?visual=2d' }).escritos.join('');
  assert.ok(s2d.indexOf('phaser') < s2d.indexOf('js/cenario/iso.js'));
  assert.ok(s2d.indexOf('js/cenario/laboratorio.js') < s2d.indexOf('js/escritorio.js'));
  assert.ok(s2d.endsWith('<script src="js/visitas.js"></script>'));
});
