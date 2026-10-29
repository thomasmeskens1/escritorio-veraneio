// Visitas: agentes com `visitando` (os estagiários da Cobertura) saem da sua mesa, aparecem
// no elevador do andar visitado e caminham até ficar ao lado do agente atendido; depois voltam.
// Vários podem visitar ao mesmo tempo (inclusive o mesmo agente): cada um num lugar livre.

// Porta do elevador na parede da direita (y = 0), perto do fim da grade do andar.
const portaElevador = () => ({ x: GRADE - 1.2, y: 0.15 });
const saidaElevador = () => ({ x: GRADE - 1.2, y: 0.85 });
const VEL_CAMINHADA = 2.6; // tiles por segundo
const ROTULO_VISITA = 22; // sobe o nome para não cobrir o do agente consultado

let presencas = {}; // id -> { avatar, chave, alvo, g: {x, y}, tweens, saindo }
let casasAndar = {}; // id -> { pos, etiqueta } estação no andar renderizado
let escalaVisitas = 1;

// Estação no andar renderizado: guarda a posição e cria a etiqueta "fora" (oculta).
function registrarCasa(id, pos, escalaRotulo) {
  const pes = isoParaTela(pos.x, pos.y);
  const etiqueta = criarEtiqueta(cena, pes.x, pes.y - 46, 'Atendendo outro andar', escalaRotulo)
    .setVisible(false);
  elementos.push(etiqueta);
  casasAndar[id] = { pos, etiqueta };
}

// Todos os agentes visitantes conhecidos (de qualquer andar), com o andar de origem.
function agentesVisitantes() {
  const lista = [];
  Object.keys(ANDARES).forEach((casa) => {
    idsDoAndar(casa).forEach((id) => {
      const dados = dadosAgente(casa, id);
      if (ehVisitante(dados)) lista.push({ id, casa, dados });
    });
  });
  return lista;
}

// Lugar já tomado por outro visitante perto de (x, y)?
const lugarTomado = (reservados, x, y) => reservados.some((r) => Math.hypot(r.x - x, r.y - y) < 0.7);

// Lugar livre ao lado do agente consultado (tile dele em `a`), virado para ele.
function lugarAoLado(agenteId, a, reservados = []) {
  const px = a.x + AGENTE_NO_TILE, py = a.y + AGENTE_NO_TILE;
  const outros = Object.entries(posicoesAndar).filter(([id]) => id !== agenteId).map(([, p]) => p);
  const opcoes = [[0.85, -0.55, -1], [-0.55, 0.85, 1], [1.1, 0.05, -1], [0.05, 1.15, 1], [-0.75, 0.2, 1], [0.2, -0.75, -1],
    [1.0, 0.9, -1], [-0.8, -0.6, 1]];
  let melhor = null;
  opcoes.forEach(([dx, dy, sentido], i) => {
    const x = px + dx, y = py + dy;
    if (x < 0.2 || y < 0.2 || x > GRADE - 0.2 || y > GRADE - 0.2) return;
    const celula = `${Math.floor(x)},${Math.floor(y)}`;
    const propria = celula === `${a.x},${a.y}`;
    const custo = i + (ocupadasAndar.has(celula) && !propria ? 50 : 0) + (lugarTomado(reservados, x, y) ? 200 : 0)
      + 0.5 * outros.reduce((soma, o) => soma + sobreposicao(o, { x, y }), 0);
    if (!melhor || custo < melhor.custo) melhor = { x, y, sentido, custo };
  });
  return melhor || lugarPerto(GRADE - 1.8, 1.45, reservados);
}

// Perto do elevador quando o agente atendido não está no andar (um ao lado do outro).
function lugarPerto(x, y, reservados) {
  let n = 0;
  while (n < 6 && lugarTomado(reservados, x - n * 0.8, y + n * 0.3)) n++;
  return { x: x - n * 0.8, y: y + n * 0.3, sentido: -1 };
}

// Chave do lugar do agente no andar renderizado (null = fora dele).
function chaveNoAndar(id, casa, dados) {
  const v = dados.visitando;
  if (v && v.andar === andarAtual) return `visita:${v.agente}`;
  if (!v && casa === andarAtual && casasAndar[id]) return 'casa';
  return null;
}

// Alvo para a chave: estação (casa) ou um lugar livre ao lado do agente visitado.
function alvoNoAndar(id, chaveAlvo, dados, reservados) {
  if (chaveAlvo === 'casa') return { chave: 'casa', ...casasAndar[id].pos, sentido: 1, rotulo: 0 };
  const agente = dados.visitando.agente;
  const a = posicoesAndar[agente];
  const lugar = a ? lugarAoLado(agente, a, reservados) : lugarPerto(GRADE - 2.4, 1.6, reservados);
  return { chave: chaveAlvo, ...lugar, rotulo: ROTULO_VISITA };
}

function pararCaminhada(p) {
  p.tweens.forEach((t) => t.remove());
  p.tweens = [];
}

// Caminha pelos `pontos` (tiles) em ~2–3 s; ao final executa `aoFim`. `ritmo` < 1 acelera (o tour da
// Recepcionista usa 0,55: os colaboradores não ficam esperando ela andar).
function caminhar(p, pontos, aoFim, ritmo = 1) {
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
  const duracao = ritmo * Math.min(3000, Math.max(total < 1.5 ? 700 : 2000, (total / VEL_CAMINHADA) * 1000));
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

function criarPresenca(id, casa, dados, inicio, rotulo) {
  const pes = isoParaTela(inicio.x, inicio.y);
  const avatar = criarBoneco(cena, pes.x, pes.y, {
    ...dados, escalaRotulo: escalaVisitas, rotuloAcima: rotulo, aoClicar: cliqueDoAgente(casa, id, dados),
  });
  return { avatar, g: { x: inicio.x, y: inicio.y }, tweens: [], chave: null, saindo: false };
}

// Leva o agente ao alvo: aparece direto (sem animação) ou entra/caminha.
function irPara(id, casa, dados, alvo, animar) {
  let p = presencas[id];
  const chegar = () => {
    p.avatar.virar(alvo.sentido);
    p.avatar.ajustarRotulo(alvo.rotulo);
  };
  if (!p) {
    const inicio = animar ? portaElevador() : alvo;
    p = presencas[id] = criarPresenca(id, casa, dados, inicio, alvo.rotulo);
    if (animar) {
      p.avatar.definirAlfa(0);
      caminhar(p, [saidaElevador(), alvo], chegar);
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
  p.alvo = alvo;
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
  caminhar(p, [saidaElevador(), portaElevador()], () => {
    p.tweens.push(cena.tweens.add({ targets: p.avatar.objetos, alpha: 0, duration: 300, onComplete: remover }));
  });
}

// Compara o estado atual com o que está na tela e anima só as diferenças.
function sincronizarVisitas(animar, escalaRotulo) {
  if (!cena) return;
  if (escalaRotulo) escalaVisitas = escalaRotulo;
  const lista = agentesVisitantes();
  const vistos = new Set(lista.map((v) => v.id));
  // Quem já está no lugar certo fica onde está; os demais escolhem entre os lugares livres.
  const reservados = [];
  const mudancas = [];
  lista.forEach((v) => {
    const chaveAlvo = chaveNoAndar(v.id, v.casa, v.dados);
    const p = presencas[v.id];
    if (chaveAlvo && p && !p.saindo && p.chave === chaveAlvo) {
      if (p.alvo) reservados.push(p.alvo);
      p.avatar.definirStatus(v.dados.status);
    } else mudancas.push({ ...v, chaveAlvo });
  });
  mudancas.forEach(({ id, casa, dados, chaveAlvo }) => {
    if (!chaveAlvo) {
      presencas[id]?.avatar.definirStatus(dados.status);
      sairDoAndar(id, animar);
      return;
    }
    const alvo = alvoNoAndar(id, chaveAlvo, dados, reservados);
    reservados.push(alvo);
    irPara(id, casa, dados, alvo, animar);
  });
  Object.keys(presencas).filter((id) => !vistos.has(id)).forEach((id) => sairDoAndar(id, animar));
  Object.keys(casasAndar).forEach(atualizarEtiqueta);
}

// "Atendendo outro andar" aparece só depois que o visitante saiu da estação.
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
