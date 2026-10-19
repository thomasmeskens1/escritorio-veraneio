# Sprint 3: Autenticação e Controle de Acesso para a Cobertura

## Objetivo
Criar uma tela de login antes de carregar o escritório e proteger o acesso à "Cobertura" usando validação simples de cargo/role.

## Instruções para o Claude (Cursor Composer)
Atue como um Desenvolvedor Full-Stack focado em Segurança.

1. **Frontend:** Oculte o canvas do Phaser inicialmente. Crie uma tela de Login limpa e corporativa (HTML/CSS) pedindo Usuário e Senha.
2. **Backend:** No FastAPI (`main.py`), crie uma rota de login via POST (`/api/login`).
3. Para o MVP, crie usuários fixos em um dicionário (mock database). Exemplo: usuário `admin` (role: `diretoria`) e `user1` (role: `funcionario`).
4. A rota deve retornar um token JWT simples (instale `pyjwt`) contendo o `role` do usuário.
5. **Integração:** No frontend, após o login bem-sucedido, salve o token no `localStorage`, esconda a tela de login e exiba o canvas do Phaser.
6. Atualize o menu do Elevador: A "Cobertura" só deve ser clicável e renderizada se o token do usuário contiver o role `diretoria`. Caso contrário, exiba um alerta de "Acesso Negado".
7. Atualize a conexão WebSocket para passar o token JWT logo na abertura da conexão, para que o backend saiba quem está conectado.