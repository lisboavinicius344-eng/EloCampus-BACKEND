from datetime import datetime, timezone

import psycopg
from werkzeug.security import check_password_hash, generate_password_hash

from database.conexao import Conexao
from services import senha_provisoria


TAMANHO_MINIMO_SENHA = 8


class AuthService:
    @staticmethod
    def login(dados):
        email = dados.get("email")
        senha = dados.get("senha")

        if not isinstance(email, str) or not email.strip():
            raise ValueError("Informe um e-mail válido.")

        if not isinstance(senha, str) or not senha:
            raise ValueError("Informe a senha.")

        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, nome, email, senha_hash, papel,
                           ativo, solicitante_id,
                           deve_trocar_senha, senha_provisoria_expira_em
                    FROM usuarios
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email.strip(),)
                )
                usuario = cur.fetchone()

        if usuario is None or not usuario[5]:
            raise ValueError("E-mail ou senha inválidos.")

        if not check_password_hash(usuario[3], senha):
            raise ValueError("E-mail ou senha inválidos.")

        deve_trocar_senha = usuario[7]
        expira_em = usuario[8]

        if (
            deve_trocar_senha
            and expira_em is not None
            and expira_em <= datetime.now(timezone.utc)
        ):
            raise ValueError(
                "Sua senha provisória expirou. Procure a administração "
                "para receber uma nova."
            )

        return {
            "id": usuario[0],
            "nome": usuario[1],
            "email": usuario[2],
            "papel": usuario[4],
            "solicitante_id": usuario[6],
            "deve_trocar_senha": deve_trocar_senha,
        }

    @staticmethod
    def cadastrar_aluno(dados):
        """Autocadastro de aluno ou professor.

        A pessoa não escolhe a senha aqui: recebe uma senha provisória
        por e-mail e cria a própria senha no primeiro acesso.
        """
        nome = dados.get("nome")
        email = dados.get("email")
        solicitante_id = dados.get("solicitante_id")

        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("Informe o nome.")

        if not isinstance(email, str) or "@" not in email:
            raise ValueError("Informe um e-mail válido.")

        if (
            not isinstance(solicitante_id, int)
            or isinstance(solicitante_id, bool)
            or solicitante_id <= 0
        ):
            raise ValueError("Informe um solicitante_id válido.")

        senha, senha_hash, expira_em = senha_provisoria.gerar()

        try:
            with Conexao.conectar() as conn:
                with conn.cursor() as cur:
                    # O papel da conta vem do tipo cadastrado pela
                    # equipe, nunca de um valor escolhido pelo cliente.
                    cur.execute(
                        """
                        SELECT tipo
                        FROM solicitantes
                        WHERE id = %s
                          AND ativo = TRUE
                          AND tipo IN ('aluno', 'professor')
                        FOR UPDATE
                        """,
                        (solicitante_id,)
                    )
                    solicitante = cur.fetchone()

                    if solicitante is None:
                        raise ValueError(
                            "Aluno ou professor não encontrado "
                            "ou cadastro inativo."
                        )

                    papel = solicitante[0]

                    cur.execute(
                        """
                        SELECT id
                        FROM usuarios
                        WHERE LOWER(email) = LOWER(%s)
                        """,
                        (email.strip(),)
                    )
                    if cur.fetchone() is not None:
                        raise ValueError(
                            "Já existe uma conta com esse e-mail."
                        )

                    cur.execute(
                        """
                        INSERT INTO usuarios
                            (nome, email, senha_hash, papel, ativo,
                             solicitante_id, deve_trocar_senha,
                             senha_provisoria_expira_em)
                        VALUES (%s, %s, %s, %s, TRUE, %s, TRUE, %s)
                        RETURNING id, nome, email, papel, solicitante_id
                        """,
                        (
                            nome.strip(),
                            email.strip(),
                            senha_hash,
                            papel,
                            solicitante_id,
                            expira_em,
                        )
                    )
                    registro = cur.fetchone()

        except psycopg.errors.UniqueViolation:
            raise ValueError(
                "Já existe uma conta para esse solicitante ou e-mail."
            ) from None

        usuario = {
            "id": registro[0],
            "nome": registro[1],
            "email": registro[2],
            "papel": registro[3],
            "solicitante_id": registro[4],
        }

        email_enviado = senha_provisoria.enviar(
            usuario, senha, expira_em, "cadastro_aluno"
        )

        return usuario, email_enviado

    @staticmethod
    def trocar_senha(usuario_id, dados):
        """Troca a senha do próprio usuário (obrigatória no 1º acesso)."""
        senha_atual = dados.get("senha_atual")
        nova_senha = dados.get("nova_senha")

        if not isinstance(senha_atual, str) or not senha_atual:
            raise ValueError("Informe a senha atual.")

        if (
            not isinstance(nova_senha, str)
            or len(nova_senha) < TAMANHO_MINIMO_SENHA
        ):
            raise ValueError(
                f"A nova senha deve ter pelo menos "
                f"{TAMANHO_MINIMO_SENHA} caracteres."
            )

        if nova_senha == senha_atual:
            raise ValueError(
                "A nova senha deve ser diferente da senha atual."
            )

        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT senha_hash
                    FROM usuarios
                    WHERE id = %s AND ativo = TRUE
                    FOR UPDATE
                    """,
                    (usuario_id,)
                )
                registro = cur.fetchone()

                if registro is None:
                    raise ValueError("Usuário não encontrado ou inativo.")

                if not check_password_hash(registro[0], senha_atual):
                    raise ValueError("A senha atual está incorreta.")

                cur.execute(
                    """
                    UPDATE usuarios
                    SET senha_hash = %s,
                        deve_trocar_senha = FALSE,
                        senha_provisoria_expira_em = NULL
                    WHERE id = %s
                    """,
                    (generate_password_hash(nova_senha), usuario_id)
                )
