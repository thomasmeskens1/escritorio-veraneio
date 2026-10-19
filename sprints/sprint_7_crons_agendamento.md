# Sprint 7: Tarefas Autônomas (Crons)

## Objetivo
Implementar rotinas automáticas para que os agentes trabalhem sozinhos em horários específicos, sem depender de uma mensagem do usuário.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro de Automação Python.

1. **Backend:** Adicione a biblioteca `APScheduler` ao `requirements.txt` e instale no Docker.
2. No `main.py` (FastAPI), configure o agendador (BackgroundScheduler) para rodar junto com o servidor.
3. Crie uma interface (pode ser via chat do agente "Gestor") onde o usuário possa digitar: "Gestor de tráfego, analise as campanhas todos os dias às 08:00".
4. O backend deve traduzir isso para um Job no `APScheduler`.
5. Quando a Cron rodar, o backend muda o status do agente para "Trabalhando" no Phaser, executa a tarefa no CrewAI, salva o resultado no histórico de mensagens dele e volta para "Disponível", notificando o usuário.