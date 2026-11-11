// Testes do Worker (despachante-05). Rodar no PC: node --test deploy/worker/test/borda.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker, { rotaInterna } from '../src/index.js';

const INTERNAS = ['/api/producao/proxima', '/api/producao/12/concluir', '/api/producao/12/progresso',
  '/api/producao/12/bloqueios', '/api/producao/12/devolver', '/api/producao/12/falhar', '/api/producao/12/folha',
  '/api/producao/trabalhos/3/concluir', '/api/producao/trabalhos/3/status', '/api/producao/trabalhos/3/falhar',
  '/api/cerebro/ingerir', '/api/integracoes/monday/criativos/9', '/api%2Fproducao%2Fproxima',
  '//api/producao/proxima', '/api/producao/proxima/'];
const DA_EQUIPE = ['/', '/index.html', '/api/login', '/api/producao/uso-max', '/api/producao/12/desdobrar',
  '/api/producao/trabalhos', '/api/integracoes/monday/webhook/abc', '/api/cerebro/estatisticas', '/api/saude'];

test('rotas do trabalhador são barradas e as da equipe passam', () => {
  for (const c of INTERNAS) assert.equal(rotaInterna(c), true, c);
  for (const c of DA_EQUIPE) assert.equal(rotaInterna(c), false, c);
});

function envFalso() {
  const pedidos = [];
  return { pedidos, ESCRITORIO: { fetch: async (url, init) => { pedidos.push({ url, init }); return new Response('ok'); } } };
}

test('rota interna responde 404 sem chegar ao PC', async () => {
  const env = envFalso();
  const resposta = await worker.fetch(new Request('https://x.workers.dev/api/producao/proxima'), env);
  assert.equal(resposta.status, 404);
  assert.equal(env.pedidos.length, 0);
});

test('pedido da equipe chega ao PC com a marca da borda', async () => {
  const env = envFalso();
  const pedido = new Request('https://x.workers.dev/api/login', {
    method: 'POST', body: '{}', headers: { 'CF-Connecting-IP': '203.0.113.7', 'X-Escritorio-Borda': '' } });
  const resposta = await worker.fetch(pedido, env);
  assert.equal(resposta.status, 200);
  const cabecalhos = env.pedidos[0].init.headers;
  assert.equal(cabecalhos.get('X-Escritorio-Borda'), 'worker');  // o visitante não apaga a marca
  assert.equal(cabecalhos.get('X-Forwarded-Host'), 'x.workers.dev');
  assert.equal(cabecalhos.get('X-Forwarded-For'), '203.0.113.7');
});
