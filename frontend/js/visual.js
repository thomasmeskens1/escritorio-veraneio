// Qual visual do escritório carregar (migração para o 3D, Thomas 13/11/2026). Enquanto a migração está em teste,
// o 3D é só do master; os demais seguem no 2D. "?visual=2d" ou "?visual=3d" no endereço força um dos dois.
// Precisa rodar antes dos scripts do escritório: escreve as tags na ordem, como se estivessem no HTML.

const VISUAL_PEDIDO = (() => {
  const v = new URLSearchParams(location.search).get('visual');
  return v === '2d' || v === '3d' ? v : null;
})();

// Mesmo critério para a sessão salva (antes do login) e para quem acabou de entrar (js/auth.js).
function visualDaSessao(s) {
  return VISUAL_PEDIDO || (s?.master ? '3d' : '2d');
}

const VISUAL = (() => {
  let payload = null;
  try {
    const token = localStorage.getItem('veraneio_token');
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    payload = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')));
  } catch {
    // sem sessão salva
  }
  return visualDaSessao(payload ? { master: !!payload.master } : null);
})();

document.documentElement.dataset.visual = VISUAL;
(VISUAL === '3d'
  ? ['js/escritorio3d/estado.js'] // a cena 3D (three.js) só carrega depois do login
  : ['vendor/phaser-3.80.1.min.js', 'js/cenario/iso.js', 'js/cenario/avatar_partes.js', 'js/cenario/avatar.js',
    'js/cenario/paredes.js', 'js/cenario/moveis.js', 'js/cenario/estacoes.js', 'js/cenario/decoracao.js',
    'js/cenario/cenarios_setores.js', 'js/cenario/estacoes_setores.js', 'js/cenario/setores.js', 'js/cenario/cerebro.js',
    'js/cenario/laboratorio.js', 'js/escritorio.js', 'js/destaque_setor.js', 'js/visitas.js']
).forEach((src) => document.write(`<script src="${src}"><\/script>`));
