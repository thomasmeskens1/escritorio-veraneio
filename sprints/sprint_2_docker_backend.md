# Sprint 2: Containerização e Backend Base (Docker + FastAPI + WebSockets)

## Objetivo
Subir a infraestrutura do servidor utilizando Docker para isolar o ambiente Python, e criar a comunicação em tempo real via WebSockets.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro DevOps e Backend (Python/FastAPI).

1. Crie um arquivo `requirements.txt` na pasta `backend` com: `fastapi`, `uvicorn`, `websockets`, `pydantic`.
2. Crie um `Dockerfile` na pasta `backend` usando uma imagem leve do Python (ex: `python:3.11-slim`). Configure para expor a porta 8000 e rodar o uvicorn.
3. Crie um `docker-compose.yml` na raiz do projeto. Ele deve ter um serviço `api` (construído a partir do backend) e montar a pasta local como volume para hot-reload.
4. Crie o arquivo `backend/main.py`.
5. Nele, implemente uma aplicação FastAPI com um endpoint de WebSocket em `/ws`.
6. Crie um gerenciador de conexões WebSocket que suporte múltiplos clientes.
7. Crie um modelo de dados para o estado dos agentes (ex: dicionário dividindo-os por andares, com propriedades `nome`, `status: [dormindo, disponivel, trabalhando]`).
8. Crie uma rota de teste no FastAPI (`/test/{andar}/{agente}/{status}`) que, ao ser chamada, atualiza o status no dicionário e faz um broadcast via WebSocket enviando o novo estado para o frontend.