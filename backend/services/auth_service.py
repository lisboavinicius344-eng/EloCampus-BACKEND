from datetime import datetime, timedelta, timezone

import psycopg
from werkzeug.security import check_password_hash, generate_password_hash

from database.conexao import Conexao
from services import senha_provisoria


TAMANHO_MINIMO_SENHA = 8

# Pedidos de "Esqueci minha senha" para a mesma conta dentro deste
# intervalo são ignorados (evita encher a caixa de e-mail de alguém).
INTERVALO_ENTRE_PEDIDOS_SEGUNDOS = 120

MENSAGEM_SENHA_EXPIRADA = (
    "Sua senha provisória expirou. Use \"Esqueci minha senha\" para "
    "receber uma nova."
)


class AuthService:
    @staticmethod
    def login(dados):
        email = dados.get("email")
        senha = dados.get("senha")

        if not isinstance(email, str) or not email.strip():
            raise ValueError("Informe um e-mail válido.")

        if not isinstance(senha, str) or not senha:
            raise ValueError("Informe a senha.")

        agora = datetime.now(timezone.utc)

        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, nome, email, senha_hash, papel,
                           ativo, solicitante_id,
                           deve_trocar_senha, senha_provisoria_expira_em,
                           reset_senha_hash, reset_senha_expira_em
                    FROM usuarios
                    WHERE LOWER(email) = LOWER(%s)
                    FOR UPDATE
                    """,
                    (email.strip(),)
                )
                usuario = cur.fetchone()

                if usuario is None or not usuario[5]:
                    raise ValueError("E-mail ou senha inválidos.")

                deve_trocar_senha = usuario[7]
                expira_em = usuario[8]
                reset_hash = usuario[9]
                reset_expira_em = usuario[10]

                if check_password_hash(usuario[3], senha):
                    if (
                        deve_trocar_senha
                        and expira_em is not None
                        and expira_em <= agora
                    ):
                        raise ValueError(MENSAGEM_SENHA_EXPIRADA)

                    if reset_hash is not None:
                        # Lembrou a senha: o pedido de recuperação perde
                        # o efeito.
                        AuthService._limpar_recuperacao(cur, usuario[0])

                elif reset_hash is not None and check_password_hash(
                    reset_hash, senha
                ):
                    if reset_expira_em is None or reset_expira_em <= agora:
                        raise ValueError(MENSAGEM_SENHA_EXPIRADA)

                    # A senha de recuperação vira a senha da conta, com a
                    # troca obrigatória (o mesmo fluxo do primeiro acesso).
                    cur.execute(
                        """
                        UPDATE usuarios
                        SET senha_hash = reset_senha_hash,
                            deve_trocar_senha = TRUE,
                            senha_provisoria_expira_em = reset_senha_expira_em,
                            reset_senha_hash = NULL,
                            reset_senha_expira_em = NULL
                        WHERE id = %s
                        """,
                        (usuario[0],)
                    )
                    deve_trocar_senha = True

                else:
                    raise ValueError("E-mail ou senha inválidos.")

        return {
            "id": usuario[0],
            "nome": usuario[1],
            "email": usuario[2],
            "papel": usuario[4],
            "solicitante_id": usuario[6],
            "deve_trocar_senha": deve_trocar_senha,
        }

    @staticmethod
    def esqueci_senha(dados):
        """Envia uma senha provisória para quem esqueceu a senha.

        Não revela se o e-mail existe: a rota responde sempre igual. A
        senha atual continua valendo até a senha nova ser usada, então
        um pedido feito por outra pessoa não tira o acesso de ninguém.
        Retorna True se um e-mail foi enviado (só para logs e testes).
        """
        email = dados.get("email")

        if (
            not isinstance(email, str)
            or "@" not in email
            or len(email.strip()) > 150
        ):
            raise ValueError("Informe um e-mail válido.")

        senha, senha_hash, expira_em = senha_provisoria.gerar(
            timedelta(minutes=senha_provisoria.validade_recuperacao_em_minutos())
        )

        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE usuarios
                    SET reset_senha_hash = %s,
                        reset_senha_expira_em = %s,
                        reset_senha_solicitado_em = NOW()
                    WHERE LOWER(email) = LOWER(%s)
                      AND ativo = TRUE
                      AND (
                          reset_senha_solicitado_em IS NULL
                          OR reset_senha_solicitado_em
                             < NOW() - make_interval(secs => %s)
                      )
                    RETURNING id, nome, email, papel, solicitante_id
                    """,
                    (
                        senha_hash,
                        expira_em,
                        email.strip(),
                        INTERVALO_ENTRE_PEDIDOS_SEGUNDOS,
                    )
                )
                registro = cur.fetchone()

        if registro is None:
            # E-mail inexistente, conta inativa ou pedido repetido.
            return False

        usuario = {
            "id": registro[0],
            "nome": registro[1],
            "email": registro[2],
            "papel": registro[3],
            "solicitante_id": registro[4],
        }

        return senha_provisoria.enviar(
            usuario, senha, expira_em, "recuperacao_senha"
        )

    @staticmethod
    def _limpar_recuperacao(cur, usuario_id):
        cur.execute(
            """
            UPDATE usuarios
            SET reset_senha_hash = NULL,
                reset_senha_expira_em = NULL
            WHERE id = %s
            """,
            (usuario_id,)
        )

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
                        senha_provisoria_expira_em = NULL,
                        reset_senha_hash = NULL,
                        reset_senha_expira_em = NULL
                    WHERE id = %s
                    """,
                    (generate_password_hash(nova_senha), usuario_id)
                )
