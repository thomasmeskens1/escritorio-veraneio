// Agentes de "conhecimento" (Diretora): ficam no arquivo do Térreo e, quando outro
// agente os consulta (`visitando`), caminham até ele. Não são interativos.

const PORTA_ELEVADOR = { x: 6.8, y: 0.15 }; // porta na parede da direita (y = 0)
const SAIDA_ELEVADOR = { x: 6.8, y: 0.85 };
const VEL_CAMINHADA = 2.6; // tiles por segundo
const ROTULO_VISITA = 22; // sobe o nome para não cobrir o do agente consultado

let presencas = {}; // id -> { avatar, chave, g: {x, y}, tweens, saindo }
let casasAndar = {}; // id -> { pos, etiqueta } estação no andar renderizado
let escalaVisitas = 1;

// Estação no andar renderizado: guarda a posição e cria a etiqueta "fora" (oculta).
function registrarCasa(id, pos, escalaRotulo) {
  const pes = isoParaTela(pos.x, pos.y);
  const etiqueta = criarEtiqueta(cena, pes.x, pes.y - 46, 'Trabalhando em outro andar', escalaRotulo)
    .setVisible(false);
  elementos.push(etiqueta);
  casasAndar[id] = { pos, etiqueta };
}

// Todos os agentes de conhecimento conhecidos, com o andar de origem.
function agentesConhecimento() {
  const lista = [];
  Object.keys(ANDARES).forEach((casa) => {
    idsDoAndar(casa).forEach((id) => {
      const dados = dadosAgente(casa, id);
      if (dados.tipo === 'conhecimento') lista.push({ id, casa, dados });
    });
  });
  return lista;
}

// Lugar livre ao lado do agente consultado (tile dele em `a`), virado para ele.
function lugarAoLado(agenteId, a) {
  const px = a.x + AGENTE_NO_TILE, py = a.y + AGENTE_NO_TILE;
  const outros = Object.entries(posicoesAndar).filter(([id]) => id !== agenteId).map(([, p]) => p);
  const opcoes = [[0.85, -0.55, -1], [-0.55, 0.85, 1], [1.1, 0.05, -1], [0.05, 1.15, 1], [-0.75, 0.2, 1], [0.2, -0.75, -1]];
  let melhor = null;
  opcoes.forEach(([dx, dy, sentido], i) => {
    const x = px + dx, y = py + dy;
    if (x < 0.2 || y < 0.2 || x > GRADE - 0.2 || y > GRADE - 0.2) return;
    const celula = `${Math.floor(x)},${Math.floor(y)}`;
    const propria = celula === `${a.x},${a.y}`;
    const custo = i + (ocupadasAndar.has(celula) && !propria ? 50 : 0)
      + 0.5 * outros.reduce((soma, o) => soma + sobreposicao(o, { x, y }), 0);
    if (!melhor || custo < melhor.custo) melhor = { x, y, sentido, custo };
  });
  return melhor || { x: SAIDA_ELEVADOR.x - 0.6, y: SAIDA_ELEVADOR.y + 0.6, sentido: -1 };
}

// Onde o agente deve estar no andar renderizado (null = fora dele).
function alvoNoAndar(id, casa, dados) {
  const v = dados.visitando;
  if (v && v.andar === andarAtual) {
    const a = posicoesAndar[v.agente];
    const lugar = a ? lugarAoLado(v.agente, a) : { x: 5.6, y: 1.6, sentido: -1 };
    return { chave: `visita:${v.agente}`, ...lugar, rotulo: ROTULO_VISITA };
  }
  const c = casasAndar[id];
  if (!v && casa === andarAtual && c) return { chave: 'casa', ...c.pos, sentido: 1, rotulo: 0 };
  return null;
}

function pararCaminhada(p) {
  p.tweens.forEach((t) => t.remove());
  p.tweens = [];
}

// Caminha pelos `pontos` (tiles) em ~2–3 s; ao final executa `aoFim`.
function caminhar(p, pontos, aoFim) {
  pararCaminhada(p);
  const trechos = [];
  let total = 0;
  let de = { ...p.g };
  pontos.forEach((para) => {
    const dist = Math.hypot(para.x - de.x, para.y - de.y);
    if (dist > 0.01) trechos.push({ para, dist });
    total += dist;
    de = para;
  });
  const duracao = Math.min(3000, Math.max(total < 1.5 ? 700 : 2000, (total / VEL_CAMINHADA) * 1000));
  p.avatar.caminhar(true);

  const proximo = (i) => {
    if (i >= trechos.length) {
      p.avatar.caminhar(false);
      aoFim?.();
      return;
    }
    const { para, dist } = trechos[i];
    // Para a esquerda da tela quando x - y diminui.
    p.avatar.virar(para.x - para.y < p.g.x - p.g.y ? -1 : 1);
    p.tweens.push(cena.tweens.add({
      targets: p.g, x: para.x, y: para.y,
      duration: (duracao * dist) / total,
      onUpdate: () => posicionar(p),
      onComplete: () => proximo(i + 1),
    }));
  };
  proximo(0);
}

function posicionar(p) {
  const pes = isoParaTela(p.g.x, p.g.y);
  p.avatar.mover(pes.x, pes.y);
}

function criarPresenca(id, dados, inicio, rotulo) {
  const pes = isoParaTela(inicio.x, inicio.y);
  const avatar = criarAvatar(cena, pes.x, pes.y, { ...dados, escalaRotulo: escalaVisitas, rotuloAcima: rotulo });
  return { avatar, g: { x: inicio.x, y: inicio.y }, tweens: [], chave: null, saindo: false };
}

// Leva o agente ao alvo: aparece direto (sem animação) ou entra/caminha.
function irPara(id, dados, alvo, animar) {
  let p = presencas[id];
  const chegar = () => {
    p.avatar.virar(alvo.sentido);
    p.avatar.ajustarRotulo(alvo.rotulo);
  };
  if (!p) {
    const inicio = animar ? PORTA_ELEVADOR : alvo;
    p = presencas[id] = criarPresenca(id, dados, inicio, alvo.rotulo);
    if (animar) {
      p.avatar.definirAlfa(0);
      caminhar(p, [SAIDA_ELEVADOR, alvo], chegar);
      cena.tweens.add({ targets: p.avatar.objetos, alpha: 1, duration: 350 });
    } else {
      chegar();
    }
  } else {
    p.saindo = false;
    p.avatar.definirAlfa(1);
    p.avatar.ajustarRotulo(alvo.rotulo);
    if (animar) caminhar(p, [alvo], chegar);
    else {
      pararCaminhada(p);
      p.avatar.caminhar(false);
      p.g = { x: alvo.x, y: alvo.y };
      posicionar(p);
      chegar();
    }
  }
  p.chave = alvo.chave;
  p.avatar.definirStatus(dados.status);
}

// Sai pelo elevador (ou some de imediato, sem animação).
function sairDoAndar(id, animar) {
  const p = presencas[id];
  if (!p || p.saindo) return;
  const remover = () => {
    pararCaminhada(p);
    p.avatar.destruir();
    if (presencas[id] === p) delete presencas[id];
    atualizarEtiqueta(id);
  };
  if (!animar) {
    remover();
    return;
  }
  p.saindo = true;
  p.chave = null;
  caminhar(p, [SAIDA_ELEVADOR, PORTA_ELEVADOR], () => {
    p.tweens.push(cena.tweens.add({ targets: p.avatar.objetos, alpha: 0, duration: 300, onComplete: remover }));
  });
}

// Compara o estado atual com o que está na tela e anima só as diferenças.
function sincronizarVisitas(animar, escalaRotulo) {
  if (!cena) return;
  if (escalaRotulo) escalaVisitas = escalaRotulo;
  const vistos = new Set();
  agentesConhecimento().forEach(({ id, casa, dados }) => {
    vistos.add(id);
    const alvo = alvoNoAndar(id, casa, dados);
    const p = presencas[id];
    if (!alvo) {
      p?.avatar.definirStatus(dados.status);
      sairDoAndar(id, animar);
    } else if (p && !p.saindo && p.chave === alvo.chave) p.avatar.definirStatus(dados.status);
    else irPara(id, dados, alvo, animar);
  });
  Object.keys(presencas).filter((id) => !vistos.has(id)).forEach((id) => sairDoAndar(id, animar));
  Object.keys(casasAndar).forEach(atualizarEtiqueta);
}

// "Trabalhando em outro andar" aparece só depois que ela saiu da estação.
function atualizarEtiqueta(id) {
  const casa = casasAndar[id];
  if (!casa) return;
  const v = dadosAgente(andarAtual, id).visitando;
  casa.etiqueta.setVisible(!!v && v.andar !== andarAtual && !presencas[id]);
}

// Chamado ao trocar de andar/encerrar: os objetos já são destruídos com a cena ou aqui.
function limparVisitas() {
  Object.values(presencas).forEach((p) => p.avatar.objetos.forEach((o) => o.active && o.destroy()));
  presencas = {};
  casasAndar = {};
}
