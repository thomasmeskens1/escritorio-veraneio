// Popup da pasta de REFERÊNCIAS (12/11/2026). Rodar no PC: node --test tests/frontend/pasta_referencias.test.js

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const r = require(path.join(__dirname, '..', '..', 'frontend', 'js', 'pasta_referencias.js'));
const LINK = 'https://drive.google.com/drive/u/1/folders/1_rCQENXBusPiiLNeo13zW6MFEZgeZXD5';

test('pergunta só quando cita a pasta e ainda não respondeu', () => {
  assert.ok(r.precisaPerguntarUso(`Use os takes: ${LINK}`));
  assert.ok(r.precisaPerguntarUso('Escritório veraneio -> referencias -> Casa veraneio -> 12.11.26'));
  assert.ok(!r.precisaPerguntarUso('Post do Lodge 3 com referências da marca'));
  assert.ok(!r.precisaPerguntarUso(r.comMarcador(`Use: ${LINK}`, 'estudo')));
});

test('marcador igual ao que o backend lê', () => {
  assert.strictEqual(r.comMarcador(' Use: x ', 'usar'), 'Use: x\n\n[Pasta de referências: pode usar os arquivos na peça]');
  assert.strictEqual(r.comMarcador('Use: x', 'estudo'), 'Use: x\n\n[Pasta de referências: só para estudo]');
});
