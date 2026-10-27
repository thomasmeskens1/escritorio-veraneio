// Cenários dos andares divididos em setores (Porão, Marketing, Comercial e Cobertura).
// As áreas e mesas de cada setor ficam em setores.js; aqui só piso, paredes e móveis de decoração.

// Infraestrutura: oficina do Construtor, operações, servidores e depósito.
CENARIOS.porao = {
  grade: 12,
  chao: { estilo: 'concreto', cor: 0x5f646b },
  parede: { cor: 0x4a4f57, acabamento: 'blocos' },
  paredes: [
    { tipo: 'canos', lado: 'esq', descida: 5.5 },
    { tipo: 'canos', lado: 'dir', alturas: [ALTURA_PAREDE - 22] },
    { tipo: 'ferramentas', lado: 'esq', t0: 1.0, t1: 3.6, z0: 36, z1: 80 },
    { tipo: 'arandela', lado: 'esq', t: 4.4, z: 84 },
    { tipo: 'painel', lado: 'esq', t0: 7.4, t1: 8.2, z0: 46, z1: 84 },
    { tipo: 'arandela', lado: 'esq', t: 9.6, z: 84 },
    { tipo: 'arandela', lado: 'dir', t: 1.6, z: 84 },
    { tipo: 'prateleira', lado: 'dir', t0: 2.6, t1: 4.8, z: 70, itens: [0xffc300, 0x1971c2, 0xc92a2a, 0xadb5bd] },
    { tipo: 'painel', lado: 'dir', t0: 5.0, t1: 5.7, z0: 42, z1: 82 },
    { tipo: 'tv', lado: 'dir', t0: 7.1, t1: 9.9, z0: 44, z1: 88 },
    { tipo: 'elevador', lado: 'dir', t0: 10.2, t1: 11.4, letra: 'P' },
  ],
  moveis: [
    { tipo: 'tapete', x: 10.2, y: 0.12, w: 1.2, d: 0.5, cores: [0x212529, 0xffc300, 0x212529, 0xffc300, 0x212529, 0xffc300] },
    // Oficina
    { tipo: 'prototipo', x: 4, y: 3 },
    { tipo: 'caixas', x: 0, y: 0, pilha: 1 },
    // Operações
    { tipo: 'rack', x: 6, y: 0 },
    // Servidores
    { tipo: 'rack', x: 0, y: 6 },
    { tipo: 'rack', x: 0, y: 7 },
    { tipo: 'rack', x: 0, y: 8 },
    { tipo: 'rack', x: 0, y: 9 },
    { tipo: 'rack', x: 2, y: 7 },
    { tipo: 'rack', x: 2, y: 8 },
    { tipo: 'rack', x: 2, y: 9 },
    // Depósito
    { tipo: 'caixas', x: 7, y: 7 },
    { tipo: 'caixas', x: 8, y: 7, pilha: 1 },
    { tipo: 'caixas', x: 11, y: 7 },
    { tipo: 'tambores', x: 7, y: 9 },
    { tipo: 'tambores', x: 10, y: 9 },
    { tipo: 'caixas', x: 11, y: 10, pilha: 1 },
  ],
};

// Agência criativa: um setor por equipe, sala de reunião e copa.
CENARIOS.marketing = {
  grade: 14,
  chao: { estilo: 'madeira', cor: 0x7f6a55 },
  parede: { cor: 0x2f4858, acabamento: 'liso' },
  paredes: [
    { tipo: 'quadro', lado: 'esq', t0: 1.0, t1: 3.2, z0: 50, z1: 90, fundo: 0xfff1e6, cores: [0xd4af37, 0x7b2cbf, 0xe9c46a] },
    { tipo: 'janela', lado: 'esq', t0: 5.4, t1: 8.6, z0: 42, z1: 102 },
    { tipo: 'relogio', lado: 'esq', t: 9.6, z: 92 },
    { tipo: 'tv', lado: 'esq', t0: 10.6, t1: 13.2, z0: 44, z1: 92 },
    { tipo: 'prateleira', lado: 'dir', t0: 0.8, t1: 3.6, z: 74, itens: [0xd4af37, 0xe9c46a, 0xf8f9fa] },
    { tipo: 'moodboard', lado: 'dir', t0: 5.6, t1: 10.4, z0: 42, z1: 96 },
    { tipo: 'arandela', lado: 'dir', t: 11.2, z: 90 },
    { tipo: 'elevador', lado: 'dir', t0: 12.2, t1: 13.4, letra: '1' },
  ],
  moveis: [
    { tipo: 'tapete', x: 12.25, y: 0.15, w: 1.1, d: 0.8, cores: [0x264653, 0x2a9d8f] },
    { tipo: 'planta', x: 0, y: 0, alta: true },
    { tipo: 'planta', x: 4, y: 0 },
    // Reunião
    { tipo: 'mesaReuniao', x: 6.5, y: 5.5 },
    { tipo: 'cadeirasFrente', x: 6.5, y: 6.9 },
    // Copa
    { tipo: 'cafeteira', x: 10, y: 4 },
    { tipo: 'bebedouro', x: 13, y: 4 },
    { tipo: 'sofa', x: 11, y: 5, cor: 0x6d597a },
    { tipo: 'mesinha', x: 11.5, y: 6.1 },
    { tipo: 'poltrona', x: 13, y: 6.5, cor: 0xe76f51 },
    { tipo: 'planta', x: 13, y: 8 },
    // Performance
    { tipo: 'planta', x: 13, y: 13 },
  ],
};

// Comercial: Hospedagem e Corporativo, sala de reunião com clientes e lounge.
CENARIOS.comercial = {
  grade: 12,
  chao: { estilo: 'madeira', cor: 0x6b5a48 },
  parede: { cor: 0x1f3b36, acabamento: 'liso' },
  paredes: [
    { tipo: 'quadro', lado: 'esq', t0: 1.0, t1: 3.4, z0: 50, z1: 90, fundo: 0xf0dbc3, cores: [0x00361b, 0xd9a15b, 0x2a9d8f] },
    { tipo: 'janela', lado: 'esq', t0: 4.6, t1: 8.4, z0: 42, z1: 102 },
    { tipo: 'relogio', lado: 'esq', t: 9.6, z: 92 },
    { tipo: 'tv', lado: 'dir', t0: 1.0, t1: 4.0, z0: 44, z1: 92 },
    { tipo: 'prateleira', lado: 'dir', t0: 5.0, t1: 8.6, z: 74, itens: [0xd9a15b, 0xf0dbc3, 0x2a9d8f] },
    { tipo: 'arandela', lado: 'dir', t: 9.4, z: 90 },
    { tipo: 'elevador', lado: 'dir', t0: 10.2, t1: 11.4, letra: '2' },
  ],
  moveis: [
    { tipo: 'tapete', x: 10.2, y: 0.12, w: 1.2, d: 0.6, cores: [0x00361b, 0xd9a15b] },
    { tipo: 'planta', x: 0, y: 0, alta: true },
    { tipo: 'planta', x: 5, y: 0 },
    // Reunião
    { tipo: 'mesaReuniao', x: 1.5, y: 7.5 },
    { tipo: 'cadeirasFrente', x: 1.5, y: 8.9 },
    { tipo: 'planta', x: 5, y: 11 },
    // Lounge
    { tipo: 'cafeteira', x: 8, y: 6 },
    { tipo: 'sofa', x: 8, y: 8, cor: 0x00361b },
    { tipo: 'mesinha', x: 8.5, y: 9.1 },
    { tipo: 'poltrona', x: 11, y: 9, cor: 0xd9a15b },
    { tipo: 'planta', x: 11, y: 11, alta: true },
  ],
};

// Cobertura: reunião do conselho (onde ficam os estagiários), laboratório do Cérebro e lounge.
CENARIOS.cobertura = {
  grade: 12,
  chao: { estilo: 'marmore', cor: 0x2b2d42 },
  parede: { cor: 0x1f2235, acabamento: 'painel', rodape: 0xd4af37 },
  paredes: [
    { tipo: 'janela', lado: 'esq', t0: 0.5, t1: 5.6, z0: 26, z1: 108, skyline: true, ceu: 0x23365f, moldura: 0x2b2b2b },
    { tipo: 'formulas', lado: 'esq', t0: 6.2, t1: 8.8, z0: 44, z1: 108 },
    { tipo: 'mapaEmpresa', lado: 'esq', t0: 9.2, t1: 11.7, z0: 62, z1: 108 },
    { tipo: 'prateleira', lado: 'esq', t0: 9.3, t1: 11.6, z: 44, itens: [0x63e6be, 0xff8fab, 0xc77dff, 0xffd43b, 0xe3fafc] },
    { tipo: 'janela', lado: 'dir', t0: 0.5, t1: 9.4, z0: 26, z1: 108, skyline: true, ceu: 0x23365f, moldura: 0x2b2b2b },
    { tipo: 'elevador', lado: 'dir', t0: 10.2, t1: 11.4, letra: 'C', moldura: 0xd4af37 },
  ],
  moveis: [
    { tipo: 'planta', x: 0, y: 0, alta: true },
    // Conselho
    { tipo: 'mesaReuniao', x: 2, y: 1.6 },
    { tipo: 'mesaReuniao', x: 5, y: 1.6 },
    { tipo: 'cadeirasFrente', x: 2, y: 3 },
    { tipo: 'cadeirasFrente', x: 5, y: 3 },
    { tipo: 'bar', x: 0, y: 2.5 },
    // Laboratório
    { tipo: 'bancadaLab', x: 0, y: 6.4 },
    { tipo: 'tanque', x: 1, y: 6, reserva: true },
    { tipo: 'monitoresCerebro', x: 2, y: 6 },
    { tipo: 'tanque', x: 4, y: 6, cor: 0xc77dff },
    // Lounge
    { tipo: 'poltrona', x: 9, y: 4, cor: 0x7f5539 },
    { tipo: 'mesinha', x: 10, y: 4 },
    { tipo: 'poltrona', x: 10, y: 5, cor: 0x7f5539 },
    { tipo: 'abajur', x: 11, y: 3 },
    { tipo: 'planta', x: 6, y: 11, alta: true },
  ],
};
