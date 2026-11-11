// Testes do frontend sem navegador (Onda 1 de 11/11/2026, Térreo). Rodar no PC: node --test tests/frontend/chat_textos.test.js
// O contêiner dos testes Python não tem Node nem a pasta frontend, por isso ficam aqui.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const raiz = path.join(__dirname, '..', '..');
const t = require(path.join(raiz, 'frontend', 'js', 'chat_textos.js'));

test('aviso de empresa: só sinais fortes e nunca com empresa citada', () => {
  assert.deepStrictEqual(t.sinalDeOutraEmpresa('Post do Vero 12 na praia', 'casa_veraneio'),
    { sugere: 'casa_vero', trecho: 'Vero 12' });
  assert.strictEqual(t.sinalDeOutraEmpresa('Convite da confraternização dos colaboradores', 'casa_veraneio').sugere,
    'cv_corporativo');
  assert.strictEqual(t.sinalDeOutraEmpresa('Legenda do Lodge 20', 'casa_vero').sugere, 'casa_veraneio');
  assert.strictEqual(t.sinalDeOutraEmpresa('Legenda do Lodge 20', 'cv_corporativo'), null); // Lodge vale nas duas
  assert.strictEqual(t.sinalDeOutraEmpresa('Evento de Réveillon no Lodge 3', 'casa_veraneio'), null); // "evento" sozinho não
  assert.strictEqual(t.sinalDeOutraEmpresa('Vero 12', 'casa_veraneio', 'casa_vero'), null); // o servidor troca sozinho
  assert.strictEqual(t.sinalDeOutraEmpresa('Vero 12', ''), null);
  assert.strictEqual(t.sinalDeOutraEmpresa('Vero 12', '*'), null);
});

test('botão de envio diz a empresa', () => {
  assert.strictEqual(t.rotuloEnviar('cv_corporativo'), 'Enviar para Corporativo');
  assert.strictEqual(t.rotuloEnviar('casa_vero'), 'Enviar para Casa Vero');
  assert.strictEqual(t.rotuloEnviar(''), 'Enviar Tarefa');
});

test('ajustes rápidos: os 4 botões, todos com a ordem de manter igual', () => {
  assert.deepStrictEqual(t.AJUSTES_RAPIDOS.map((a) => a.rotulo), ['Mais curto', 'Mais informal', 'Mais fluido', '3 variações']);
  t.AJUSTES_RAPIDOS.forEach((a) => assert.ok(a.texto.includes(t.MANTER_IGUAL), a.rotulo));
  assert.ok(t.MANTER_IGUAL.startsWith('Mantenha igual tudo o que não foi pedido'));
  assert.deepStrictEqual(t.AGENTES_AJUSTE_RAPIDO, ['copywriter', 'email_marketing']);
});

test('Peça final: texto aprovado intacto, Lodge achado e lacuna do formato', () => {
  const legenda = 'Lareira acesa no Lodge 18.\nReserve a data do seu grupo. Link na bio';
  const pedido = t.textoParaPecaFinal(legenda);
  assert.ok(pedido.startsWith(`Peça final: formato: ${t.LACUNA_FORMATO}`));
  assert.ok(pedido.includes('Lodge ou imóvel: Lodge 18'));
  assert.ok(pedido.includes('não reescrever'));
  assert.ok(pedido.endsWith(legenda));
  assert.ok(t.textoParaPecaFinal('Casa do Vero 7').includes('Lodge ou imóvel: Vero 7'));
  assert.ok(t.textoParaPecaFinal('x'.repeat(25000)).includes('[texto cortado'));
});

test('espera em palavras simples', () => {
  const adiada = t.textoDeEspera('Os modelos imediatos não concluíram a tarefa a tempo. Ela foi para a fila de '
    + 'contingência (gratuitos e local); a resposta chega assim que for processada.');
  assert.ok(!/imediatos|conting/i.test(adiada));
  assert.ok(adiada.includes('Não precisa enviar de novo'));
  const producao = t.textoDeEspera('Pedido enviado ao Claude Code (Max) para produção.');
  assert.ok(producao.startsWith('Pedido enviado ao Claude Code') && producao.includes('Pode fechar'));
  assert.strictEqual(t.textoDeEspera(adiada), adiada); // não repete a frase
  assert.strictEqual(t.etapaSimples('Na fila (fila de contingência (gratuitos e local))'), 'Na fila: a resposta chega aqui, pode fechar');
  assert.strictEqual(t.etapaSimples('Pedido recebido'), 'Pedido recebido');
});

test('título da aba com contador', () => {
  assert.strictEqual(t.tituloComContador('Escritório Veraneio', 0), 'Escritório Veraneio');
  assert.strictEqual(t.tituloComContador('Escritório Veraneio', 2), '(2) Escritório Veraneio');
  assert.strictEqual(t.tituloComContador('Escritório Veraneio', 120), '(99+) Escritório Veraneio');
});

// Agentes de chat do estado.py, lidos pelo texto (sem Python): [id, nome].
function agentesDoEstado() {
  const fonte = fs.readFileSync(path.join(raiz, 'backend', 'estado.py'), 'utf8');
  return [...fonte.matchAll(/Agente\(id="(\w+)", nome="([^"]+)"([\s\S]*?)aparencia=/g)]
    .filter(([, , , resto]) => !/tipo="(sistema|estagiario)"/.test(resto))
    .map(([, id, nome]) => [id, nome]);
}

// Agentes sem passo no tour, de propósito (11/11/2026): aparecem no texto do passo do setor.
const FORA_DO_TOUR = ['designer', 'moviemaker', 'email_marketing', 'gestor_trafego', 'analista_metricas'];

test('tour: todo agente de chat aparece num passo, e a Caixa de entrada tem o seu', () => {
  const tour = fs.readFileSync(path.join(raiz, 'frontend', 'js', 'onboarding.js'), 'utf8');
  const agentes = agentesDoEstado();
  assert.ok(agentes.length >= 18, `poucos agentes lidos do estado.py: ${agentes.length}`);
  const faltam = agentes.filter(([id, nome]) => !FORA_DO_TOUR.includes(id)
    && !tour.includes(`agente: '${id}'`) && !tour.includes(nome)).map(([, nome]) => nome);
  assert.deepStrictEqual(faltam, [], `escreva um passo ou cite no tour (frontend/js/onboarding.js): ${faltam}`);
  assert.ok(tour.includes("ui: '#abrir-caixa'"));
});

test('frontend sem jargão nas mensagens', () => {
  const pasta = path.join(raiz, 'frontend', 'js');
  const proibidas = [/exclusiva da conta do Thomas/, /modelos imediatos/, /fila de conting/, /'Agente não encontrado\.'/];
  fs.readdirSync(pasta).filter((n) => n.endsWith('.js') && n !== 'chat_textos.js').forEach((nome) => {
    const fonte = fs.readFileSync(path.join(pasta, nome), 'utf8');
    proibidas.forEach((p) => assert.ok(!p.test(fonte), `${nome}: ${p}`));
  });
});
