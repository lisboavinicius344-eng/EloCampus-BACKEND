"""Redefine a senha de um administrador direto no banco.

Uso (na pasta backend, com as variáveis DB_* configuradas):

    python redefinir_senha_admin.py admin@exemplo.com

Sem o e-mail na linha de comando, o script pergunta. Serve para quando
nenhum admin consegue entrar; com acesso, prefira "Alterar senha" no
perfil ou "Esqueci minha senha".
"""
import sys
from getpass import getpass

from werkzeug.security import generate_password_hash

from database.conexao import Conexao


email = (sys.argv[1] if len(sys.argv) > 1 else input("E-mail do admin: "))
email = email.strip()

if "@" not in email:
    raise SystemExit("Informe um e-mail válido.")

senha = getpass("Digite a nova senha para o administrador: ")
confirmacao = getpass("Confirme a nova senha: ")

if len(senha) < 8:
    raise SystemExit("A senha deve ter pelo menos 8 caracteres.")

if senha != confirmacao:
    raise SystemExit("As senhas não coincidem.")

senha_hash = generate_password_hash(senha)

with Conexao.conectar() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE usuarios
            SET senha_hash = %s,
                deve_trocar_senha = FALSE,
                senha_provisoria_expira_em = NULL,
                reset_senha_hash = NULL,
                reset_senha_expira_em = NULL
            WHERE LOWER(email) = LOWER(%s)
              AND papel = 'admin'
              AND ativo = TRUE
            RETURNING id, email, papel
            """,
            (senha_hash, email)
        )
        usuario = cur.fetchone()

        if usuario is None:
            raise SystemExit(
                "Conta administrativa ativa não encontrada para esse "
                "e-mail. Nada foi alterado."
            )

print(f"Senha redefinida para a conta: {usuario[1]}")
