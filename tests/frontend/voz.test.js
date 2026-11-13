// Comando de voz (12/11/2026). Rodar no PC: node --test tests/frontend/voz.test.js

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const v = require(path.join(__dirname, '..', '..', 'frontend', 'js', 'voz.js'));
const AGENTES = [{ id: 'gestor', nome: 'Gestor', andar: 'marketing' },
  { id: 'email_marketing', nome: 'E-mail Marketing', andar: 'marketing' }];

test('chamado da Vera e do agente do chat', () => {
  assert.deepStrictEqual(v.acharChamado('Olá, Vera! Abre o escritório.'), { alvo: 'vera', resto: 'abre o escritorio' });
  assert.deepStrictEqual(v.acharChamado('olá vera'), { alvo: 'vera', resto: '' });
  assert.deepStrictEqual(v.acharChamado('Olá Gestor, faça o post do Lodge 3', 'Gestor'),
    { alvo: 'agente', resto: 'faca o post do lodge 3' });
  assert.strictEqual(v.acharChamado('Olá Gestor, faça o post', ''), null); // fora do chat, só a Vera atende
  assert.deepStrictEqual(v.acharChamado('oi e-mail marketing', 'E-mail Marketing'), { alvo: 'agente', resto: '' });
  assert.strictEqual(v.acharChamado('a Vera disse olá ontem'), null);
  // variações que o reconhecimento do navegador devolve
  assert.deepStrictEqual(v.acharChamado('Vera, abre o escritório'), { alvo: 'vera', resto: 'abre o escritorio' });
  assert.deepStrictEqual(v.acharChamado('alô Vera abre o escritório'), { alvo: 'vera', resto: 'abre o escritorio' });
  assert.strictEqual(v.acharChamado('Oi bera').alvo, 'vera');
  assert.strictEqual(v.acharChamado('Post da Casa Vero'), null);
  assert.strictEqual(v.acharChamado('verão chegando'), null);
});

test('comandos da Vera', () => {
  assert.strictEqual(v.comandoVera('abre o escritório').tipo, 'resumo');
  assert.strictEqual(v.comandoVera('bom dia').tipo, 'resumo');
  assert.strictEqual(v.comandoVera('pare').tipo, 'parar');
  assert.strictEqual(v.comandoVera('').tipo, 'esperar');
  assert.strictEqual(v.comandoVera('abre o chat do Gestor', AGENTES).agente.id, 'gestor');
  assert.strictEqual(v.comandoVera('abrir e-mail marketing', AGENTES).agente.id, 'email_marketing');
  assert.deepStrictEqual(v.comandoVera('Faça um post do Lodge 3', AGENTES), { tipo: 'pedido', texto: 'Faça um post do Lodge 3' });
});

test('resposta em fala: sem markdown e com corte avisado', () => {
  assert.strictEqual(v.textoParaFala('**Pronto** ✅\n- item um\nVeja https://x.com/a'), 'Pronto item um Veja link no chat');
  const longa = v.textoParaFala('Frase longa de teste. '.repeat(80));
  assert.ok(longa.length < 760 && longa.endsWith('A resposta completa está no chat.'));
});
