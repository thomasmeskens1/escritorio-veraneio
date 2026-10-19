# Sprint 6: O Carpinteiro (Criação Dinâmica de Agentes)

## Objetivo
Transformar o "Carpinteiro" em um agente especial capaz de criar novos agentes para o escritório em tempo real, sem que o usuário precise programar.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro de Software Sênior.

1. **Backend:** Modifique o agente "Carpinteiro" no CrewAI. O objetivo dele não é retornar texto comum, mas sim receber um "briefing" do usuário (ex: "Crie um agente de Vendas") e gerar um arquivo JSON (ou registro no banco) contendo `nome`, `role`, `goal` e `backstory`.
2. Crie uma função que o Carpinteiro possa chamar (Tool/Tool-calling no CrewAI) que escreva de fato esse novo agente no sistema.
3. Crie um endpoint de WebSocket ou API que avise o Frontend que um "Novo Agente foi criado".
4. **Frontend:** No Phaser, quando o evento de "Novo Agente" chegar, desenhe dinamicamente uma nova mesa e um novo avatar no andar atual, e torne-o clicável como os outros.