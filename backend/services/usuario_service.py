import psycopg

from database.conexao import Conexao
from services import senha_provisoria


class UsuarioService:

    # Contas de alunos são criadas pelo autocadastro (/api/auth/cadastro-aluno).
    PAPEIS_DA_EQUIPE = ("admin", "operador")

    def listar(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nome, email, papel, ativo,
                           solicitante_id, criado_em, deve_trocar_senha
                    FROM usuarios
                    ORDER BY nome
                """)
                registros = cursor.fetchall()

        return [self._para_dict(r) for r in registros]

    def obter_por_id(self, usuario_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nome, email, papel, ativo,
                           solicitante_id, criado_em, deve_trocar_senha
                    FROM usuarios
                    WHERE id = %s
                """, (usuario_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def cadastrar(self, dados):
        """Cria uma conta da equipe com senha provisória enviada por e-mail.

        Retorna (usuario, email_enviado, senha). A senha só é devolvida
        quando o e-mail falhou, para o admin repassá-la pessoalmente.
        """
        nome = dados.get("nome")
        email = dados.get("email")
        papel = dados.get("papel", "operador")

        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("Informe o nome.")

        if not isinstance(email, str) or "@" not in email:
            raise ValueError("Informe um e-mail válido.")

        if papel not in self.PAPEIS_DA_EQUIPE:
            raise ValueError("O papel deve ser admin ou operador.")

        senha, senha_hash, expira_em = senha_provisoria.gerar()

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO usuarios (
                            nome, email, senha_hash, papel,
                            deve_trocar_senha, senha_provisoria_expira_em
                        )
                        VALUES (%s, %s, %s, %s, TRUE, %s)
                        RETURNING id
                    """, (
                        nome.strip(),
                        email.strip(),
                        senha_hash,
                        papel,
                        expira_em,
                    ))
                    usuario_id = cursor.fetchone()[0]

        except psycopg.errors.UniqueViolation:
            raise ValueError("Já existe uma conta com esse e-mail.") from None

        usuario = self.obter_por_id(usuario_id)
        enviado = senha_provisoria.enviar(
            usuario, senha, expira_em, "cadastro_usuario"
        )

        return usuario, enviado, None if enviado else senha

    def reenviar_senha(self, usuario_id):
        """Gera e envia uma nova senha provisória.

        A senha atual deixa de valer, e a pessoa precisará criar uma
        nova no próximo acesso. Retorna None se o usuário não existir.
        """
        senha, senha_hash, expira_em = senha_provisoria.gerar()

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    UPDATE usuarios
                    SET senha_hash = %s,
                        deve_trocar_senha = TRUE,
                        senha_provisoria_expira_em = %s,
                        reset_senha_hash = NULL,
                        reset_senha_expira_em = NULL
                    WHERE id = %s AND ativo = TRUE
                    RETURNING id
                """, (senha_hash, expira_em, usuario_id))

                if cursor.fetchone() is None:
                    return None

        usuario = self.obter_por_id(usuario_id)
        enviado = senha_provisoria.enviar(
            usuario, senha, expira_em, "senha_provisoria"
        )

        return usuario, enviado, None if enviado else senha

    def desativar(self, usuario_id, usuario_logado_id):
        # Os ids chegam como UUID (rota) ou texto (token): compara em texto.
        if str(usuario_id) == str(usuario_logado_id):
            raise ValueError("Você não pode desativar a própria conta.")

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT papel, ativo
                    FROM usuarios
                    WHERE id = %s
                    FOR UPDATE
                """, (usuario_id,))
                registro = cursor.fetchone()

                if registro is None:
                    return None

                papel, ativo = registro

                if not ativo:
                    raise ValueError("A conta já está desativada.")

                if papel == "admin":
                    # Bloqueia os administradores para que duas
                    # desativações simultâneas não removam o último.
                    cursor.execute("""
                        SELECT id
                        FROM usuarios
                        WHERE papel = 'admin' AND ativo = TRUE
                        FOR UPDATE
                    """)

                    if len(cursor.fetchall()) <= 1:
                        raise ValueError(
                            "Não é possível desativar o último administrador."
                        )

                cursor.execute("""
                    UPDATE usuarios
                    SET ativo = FALSE
                    WHERE id = %s
                """, (usuario_id,))

        return self.obter_por_id(usuario_id)

    @staticmethod
    def _para_dict(registro):
        return {
            "id": str(registro[0]),
            "nome": registro[1],
            "email": registro[2],
            "papel": registro[3],
            "ativo": registro[4],
            "solicitante_id": registro[5],
            "criado_em": (
                registro[6].isoformat() if registro[6] else None
            ),
            "deve_trocar_senha": registro[7],
        }
