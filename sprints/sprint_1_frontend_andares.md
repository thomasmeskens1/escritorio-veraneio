# Sprint 1: Interface Isométrica e Navegação de Andares

## Objetivo
Criar a base visual do "Escritório" usando Phaser.js (visão isométrica 2D) e implementar a navegação entre os 4 andares definidos.

## Estrutura de Andares
1. **Porão** (Vazio por enquanto, estrutura de infraestrutura).
2. **Térreo** (Agentes de onboarding/guia de uso do sistema).
3. **1º Andar - Marketing** (Designer, Moviemaker, Gestor de Tráfego, Gestor, Carpinteiro).
4. **Cobertura** (Agentes executivos - acesso restrito).

## Instruções para o Claude (Cursor Composer)
Atue como um Desenvolvedor Frontend Sênior especializado em Phaser.js e UI/UX.

1. Configure o `index.html` com a importação do Phaser 3 via CDN.
2. Crie uma interface HTML/CSS (sobreposta ao canvas) com um menu lateral ou botões de elevador para alternar entre os 4 andares.
3. No `script.js`, inicialize o Phaser com suporte a uma grade isométrica simples.
4. Crie uma função `renderizarAndar(nivel)`. Quando o usuário clicar no menu do elevador, o canvas deve limpar os elementos atuais e renderizar o chão correspondente.
5. Para o "1º Andar", desenhe 5 mesas (losangos isométricos) e 5 sprites/quadrados em cima delas representando os agentes de Marketing.
6. Adicione interatividade de clique: ao clicar em um agente, faça um `console.log` com o nome dele e seu andar.
7. Deixe a visualização da Cobertura bloqueada visualmente (um ícone de cadeado) na UI do elevador, pois trataremos a autenticação depois.