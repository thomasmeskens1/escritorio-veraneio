# Sprint 10: Lançamento (Deploy 100% Gratuito)

## Objetivo
Tirar o projeto do seu "localhost" (computador) e publicá-lo na internet para que qualquer pessoa da sua empresa possa acessar via celular ou computador.

## Instruções para o Claude (Cursor Composer)
Atue como um Engenheiro Cloud focado em opções gratuitas.

1. **Separação:** Vamos colocar o Frontend e o Backend em lugares diferentes.
2. **Backend:** Prepare o código para fazer deploy no **Render** (render.com). Crie um `render.yaml` ou guie o usuário sobre como conectar o repositório do GitHub lá, utilizando a opção Web Service (Plano Free) rodando o Docker.
3. **Frontend:** Prepare o projeto HTML/Phaser para fazer deploy na **Vercel** ou **Netlify** (ambos gratuitos).
4. **Ajuste de Variáveis:** Atualize as URLs no Frontend. Em vez de apontar para `ws://localhost:8000/ws`, ele deve apontar para a URL de produção (ex: `wss://seu-backend.onrender.com/ws`).
5. Gere o build final e verifique os logs de conexão do WebSocket.