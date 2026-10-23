import psycopg
from werkzeug.security import generate_password_hash

from database.conexao import Conexao


class UsuarioService:

    # Contas de alunos são criadas pelo autocadastro (/api/auth/cadastro-aluno).
    PAPEIS_DA_EQUIPE = ("admin", "operador")

    def listar(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nome, email, papel, ativo,
                           solicitante_id, criado_em
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
                           solicitante_id, criado_em
                    FROM usuarios
                    WHERE id = %s
                """, (usuario_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def cadastrar(self, dados):
        nome = dados.get("nome")
        email = dados.get("email")
        senha = dados.get("senha")
        papel = dados.get("papel", "operador")

        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("Informe o nome.")

        if not isinstance(email, str) or "@" not in email:
            raise ValueError("Informe um e-mail válido.")

        if not isinstance(senha, str) or len(senha) < 8:
            raise ValueError("A senha deve ter pelo menos 8 caracteres.")

        if papel not in self.PAPEIS_DA_EQUIPE:
            raise ValueError("O papel deve ser admin ou operador.")

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO usuarios (nome, email, senha_hash, papel)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        nome.strip(),
                        email.strip(),
                        generate_password_hash(senha),
                        papel,
                    ))
                    usuario_id = cursor.fetchone()[0]

        except psycopg.errors.UniqueViolation:
            raise ValueError("Já existe uma conta com esse e-mail.") from None

        return self.obter_por_id(usuario_id)

    def desativar(self, usuario_id, usuario_logado_id):
        if usuario_id == usuario_logado_id:
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
            "id": registro[0],
            "nome": registro[1],
            "email": registro[2],
            "papel": registro[3],
            "ativo": registro[4],
            "solicitante_id": registro[5],
            "criado_em": (
                registro[6].isoformat() if registro[6] else None
            ),
        }
