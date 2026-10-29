import secrets
from datetime import datetime, timedelta, timezone

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

                    if deve_trocar_senha:
                        # Senha provisória: vale um único acesso.
                        AuthService._consumir_senha_provisoria(
                            cur, usuario[0]
                        )

                    if reset_hash is not None:
                        # Lembrou a senha: o pedido de recuperação perde
                        # o efeito.
                        AuthService._limpar_recuperacao(cur, usuario[0])

                elif reset_hash is not None and check_password_hash(
                    reset_hash, senha
                ):
                    if reset_expira_em is None or reset_expira_em <= agora:
                        raise ValueError(MENSAGEM_SENHA_EXPIRADA)

                    # A senha de recuperação também vale um único acesso:
                    # a conta passa a exigir a criação de uma senha nova
                    # (o mesmo fluxo do primeiro acesso).
                    AuthService._limpar_recuperacao(cur, usuario[0])
                    AuthService._consumir_senha_provisoria(cur, usuario[0])
                    deve_trocar_senha = True

                else:
                    raise ValueError("E-mail ou senha inválidos.")

        return {
            "id": str(usuario[0]),
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
    def _consumir_senha_provisoria(cur, usuario_id):
        """Troca no banco a senha provisória que acabou de ser usada.

        Ela é substituída por um valor aleatório que ninguém conhece: o
        e-mail recebido deixa de servir, e a pessoa cria a própria senha
        com o token deste login (POST /auth/trocar-senha). Se sair antes,
        usa "Esqueci minha senha".
        """
        cur.execute(
            """
            UPDATE usuarios
            SET senha_hash = %s,
                deve_trocar_senha = TRUE
            WHERE id = %s
            """,
            (generate_password_hash(secrets.token_urlsafe(32)), usuario_id)
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
    def trocar_senha(usuario_id, dados):
        """Cria ou troca a senha do próprio usuário.

        No primeiro acesso (e depois de "Esqueci minha senha"), a senha
        provisória já foi consumida no login: o token desse login basta e
        "senha_atual" é ignorada. Fora disso, a senha atual é exigida.
        """
        senha_atual = dados.get("senha_atual")
        nova_senha = dados.get("nova_senha")

        if (
            not isinstance(nova_senha, str)
            or len(nova_senha) < TAMANHO_MINIMO_SENHA
        ):
            raise ValueError(
                f"A nova senha deve ter pelo menos "
                f"{TAMANHO_MINIMO_SENHA} caracteres."
            )

        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT senha_hash, deve_trocar_senha
                    FROM usuarios
                    WHERE id = %s AND ativo = TRUE
                    FOR UPDATE
                    """,
                    (usuario_id,)
                )
                registro = cur.fetchone()

                if registro is None:
                    raise ValueError("Usuário não encontrado ou inativo.")

                if not registro[1]:
                    if not isinstance(senha_atual, str) or not senha_atual:
                        raise ValueError("Informe a senha atual.")

                    if not check_password_hash(registro[0], senha_atual):
                        raise ValueError("A senha atual está incorreta.")

                    if nova_senha == senha_atual:
                        raise ValueError(
                            "A nova senha deve ser diferente da senha atual."
                        )

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
