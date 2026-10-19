# Sprint 4: Interação com Agentes (Popups e Chat)

## Objetivo
Criar a interface onde o usuário conversa com a IA e visualiza os detalhes do agente clicado, conectando isso ao WebSocket.

## Instruções para o Claude (Cursor Composer)
Atue como um Desenvolvedor UI/Frontend.

1. Crie um Modal/Popup em HTML/CSS sobreposto ao jogo. Ele deve iniciar oculto (`display: none`).
2. O Modal deve ter o visual de um terminal ou janela de sistema, contendo:
   - Cabeçalho: Nome e Função do Agente, e um indicador visual do seu status (bolinha colorida).
   - Corpo: Área de histórico de mensagens (chat).
   - Rodapé: Input de texto e botão "Enviar Tarefa".
3. No `script.js`, altere o evento de clique nos sprites dos agentes: ao clicar, o Modal deve abrir, carregando os dados do agente específico.
4. Conecte o botão "Enviar": ele deve pegar o texto, limpar o input, adicionar a mensagem na tela como "Você", e enviar um JSON via WebSocket no formato: `{"tipo": "mensagem", "andar": "marketing", "agente": "designer", "texto": "..."}`.
5. Atualize o listener do WebSocket no frontend: quando receber uma mensagem do tipo `resposta_agente`, adicione o texto no modal (se estiver aberto).