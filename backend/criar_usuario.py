"""Cria ou atualiza um usuário. A senha é pedida no terminal (ou lida da entrada padrão).

Uso: docker compose exec api python criar_usuario.py <login> "<nome>" <diretoria|funcionario>
"""

import argparse
import getpass
import sys

from auth import salvar_usuario

ROLES = ("diretoria", "funcionario")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("login", help="e-mail ou nome de usuário")
parser.add_argument("nome", help="nome exibido no escritório")
parser.add_argument("role", choices=ROLES)
args = parser.parse_args()

senha = getpass.getpass("Senha: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
if len(senha) < 8:
    sys.exit("A senha precisa ter pelo menos 8 caracteres.")

salvar_usuario(args.login, args.nome, senha, args.role)
print(f"Usuário '{args.login}' salvo como {args.role}.")
