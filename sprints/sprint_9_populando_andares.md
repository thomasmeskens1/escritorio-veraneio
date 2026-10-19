# Sprint 9: Populando o Térreo e a Cobertura

## Objetivo
Criar as lógicas específicas para os agentes de Onboarding e os agentes Executivos, finalizando a estrutura do prédio.

## Instruções para o Claude (Cursor Composer)
Atue como um Arquiteto de Soluções AI.

1. **Térreo (Onboarding):** Crie um arquivo `onboarding_crew.py`. Crie agentes focados em ler a documentação do seu próprio sistema e explicar para novos usuários como interagir com o prédio. Eles não executam ferramentas, apenas conversam.
2. **Cobertura (Executivos):** Crie um arquivo `executivos_crew.py`. Crie agentes (ex: Analista Financeiro, Diretor de Estratégia).
3. **Segurança Adicional:** No FastAPI, bloqueie os endpoints do WebSocket da Cobertura. O backend deve checar o Token JWT do usuário; se ele não for `diretoria`, o backend recusa a interação com esses agentes.
4. **Frontend:** Atualize a interface isométrica para desenhar um visual mais luxuoso (chão diferente) para a Cobertura e um saguão (recepção) para o Térreo.