# Sprint 8: Banco de Dados e Memória

## Objetivo
Evitar que os chats, agentes criados pelo Carpinteiro e tarefas agendadas sumam quando o Docker for reiniciado.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro de Dados e Backend.

1. **Backend:** Vamos usar o `SQLite` (é leve, nativo do Python e 100% gratuito, perfeito para isso). Use `SQLAlchemy` como ORM.
2. Crie tabelas para: `Usuarios`, `Agentes`, `Historico_Chat` e `Crons`.
3. Ajuste o FastAPI para salvar cada mensagem trocada no WebSocket dentro do `Historico_Chat`.
4. **Frontend:** Quando o usuário clicar em um agente, o Modal de Chat não deve vir vazio. O frontend deve fazer um fetch no backend para carregar o histórico anterior da conversa.
5. Adicione um volume no `docker-compose.yml` para que o arquivo `.sqlite` não seja apagado quando o container reiniciar.