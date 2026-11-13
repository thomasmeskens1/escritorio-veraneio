// Qual visual do escritório carregar. Desde a Fase 6 da migração (Thomas, 13/11/2026), o 3D é o padrão para todos.
// O 2D fica como reserva por "?visual=2d" no endereço até ser removido (depois de uma semana de uso do 3D).
// Precisa rodar antes dos scripts do escritório: escreve as tags na ordem, como se estivessem no HTML.

const VISUAL_PEDIDO = (() => {
  const v = new URLSearchParams(location.search).get('visual');
  return v === '2d' || v === '3d' ? v : null;
})();

// Mesmo critério antes do login e para quem acabou de entrar (js/auth.js).
function visualDaSessao() {
  return VISUAL_PEDIDO || '3d';
}

const VISUAL = visualDaSessao();

document.documentElement.dataset.visual = VISUAL;
(VISUAL === '3d'
  ? ['js/escritorio3d/estado.js'] // a cena 3D (three.js) só carrega depois do login
  : ['vendor/phaser-3.80.1.min.js', 'js/cenario/iso.js', 'js/cenario/avatar_partes.js', 'js/cenario/avatar.js',
    'js/cenario/paredes.js', 'js/cenario/moveis.js', 'js/cenario/estacoes.js', 'js/cenario/decoracao.js',
    'js/cenario/cenarios_setores.js', 'js/cenario/estacoes_setores.js', 'js/cenario/setores.js', 'js/cenario/cerebro.js',
    'js/cenario/laboratorio.js', 'js/escritorio.js', 'js/destaque_setor.js', 'js/visitas.js']
).forEach((src) => document.write(`<script src="${src}"><\/script>`));
