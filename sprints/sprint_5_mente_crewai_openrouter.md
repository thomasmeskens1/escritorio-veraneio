# Sprint 5: Integração com CrewAI e OpenRouter

## Objetivo
Conectar as mensagens recebidas pelo WebSocket ao CrewAI, usando modelos gratuitos do OpenRouter para gerar o comportamento autônomo.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro de IA (Python/CrewAI).

1. Adicione `crewai` e `langchain-openai` ao `requirements.txt` e faça o rebuild do Docker.
2. Crie uma pasta `backend/agents` e um arquivo `marketing_crew.py`.
3. Configure a conexão com o OpenRouter usando a base URL `https://openrouter.ai/api/v1` e o modelo `google/gemini-2.5-flash` ou `meta-llama/llama-3-8b-instruct:free` (obtenha a API Key via variável de ambiente do Docker).
4. No `marketing_crew.py`, instancie os 5 agentes do andar de Marketing com seus respectivos `role`, `goal` e `backstory` (Designer, Moviemaker, Gestor de Tráfego, Gestor, Carpinteiro). O Gestor deve ser configurado para delegar e revisar.
5. No `main.py` (FastAPI), atualize o recebimento de mensagens do WebSocket:
   - Quando receber uma tarefa para o `designer` (por exemplo), mude o status do agente no sistema para `trabalhando` (fazendo broadcast para o frontend).
   - Crie uma `Task` no CrewAI com o texto recebido e inicie a execução assíncrona (para não travar o servidor).
   - Ao terminar, pegue o output do CrewAI, envie de volta via WebSocket para o chat do frontend, e volte o status do agente para `disponivel`.