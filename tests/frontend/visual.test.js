// Visual do escritório (migração para o 3D, 13/11/2026): o master abre no 3D, os demais seguem no 2D, e
// "?visual=" força um dos dois. Rodar no PC: node --test tests/frontend/visual.test.js

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CODIGO = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'js', 'visual.js'), 'utf8');
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const token = (payload) => `${b64({ alg: 'none' })}.${b64(payload)}.x`;

function carregar({ busca = '', tokenSalvo = null } = {}) {
  const escritos = [];
  const ctx = {
    location: { search: busca },
    localStorage: { getItem: () => tokenSalvo },
    atob: (s) => Buffer.from(s, 'base64').toString('latin1'),
    URLSearchParams,
    document: { documentElement: { dataset: {} }, write: (t) => escritos.push(t) },
  };
  vm.runInNewContext(`${CODIGO}\nthis.VISUAL = VISUAL; this.visualDaSessao = visualDaSessao;`, ctx);
  return { ctx, escritos };
}

test('master abre no 3D; os demais e quem não entrou, no 2D', () => {
  assert.strictEqual(carregar({ tokenSalvo: token({ sub: 't', master: true }) }).ctx.VISUAL, '3d');
  assert.strictEqual(carregar({ tokenSalvo: token({ sub: 'j', role: 'diretoria' }) }).ctx.VISUAL, '2d');
  assert.strictEqual(carregar().ctx.VISUAL, '2d');
  assert.strictEqual(carregar({ tokenSalvo: 'lixo' }).ctx.VISUAL, '2d');
});

test('?visual= força o 2D ou o 3D', () => {
  assert.strictEqual(carregar({ busca: '?visual=2d', tokenSalvo: token({ master: true }) }).ctx.VISUAL, '2d');
  assert.strictEqual(carregar({ busca: '?visual=3d' }).ctx.VISUAL, '3d');
  assert.strictEqual(carregar({ busca: '?visual=xyz', tokenSalvo: token({ master: true }) }).ctx.VISUAL, '3d');
});

test('scripts certos de cada visual, na ordem', () => {
  const { escritos: s3d, ctx } = carregar({ tokenSalvo: token({ master: true }) });
  assert.deepStrictEqual(s3d, ['<script src="js/escritorio3d/estado.js"></script>']);
  assert.strictEqual(ctx.document.documentElement.dataset.visual, '3d');
  const s2d = carregar().escritos.join('');
  assert.ok(s2d.indexOf('phaser') < s2d.indexOf('js/cenario/iso.js'));
  assert.ok(s2d.indexOf('js/cenario/laboratorio.js') < s2d.indexOf('js/escritorio.js'));
  assert.ok(s2d.endsWith('<script src="js/visitas.js"></script>'));
});

test('quem entra depois do carregamento usa o mesmo critério', () => {
  const { ctx } = carregar();
  assert.strictEqual(ctx.visualDaSessao({ master: true }), '3d');
  assert.strictEqual(ctx.visualDaSessao({ master: false }), '2d');
});
