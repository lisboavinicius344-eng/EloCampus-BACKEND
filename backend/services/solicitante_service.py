import psycopg

from database.conexao import Conexao
from models.solicitante import Solicitante


CAMPOS = """
    id, nome, tipo, setor, email, telefone, ativo, criado_em, matricula,
    EXISTS (
        SELECT 1 FROM usuarios u WHERE u.solicitante_id = solicitantes.id
    ) AS tem_conta
"""


def _erro_duplicado(erro):
    restricao = getattr(erro.diag, "constraint_name", "") or ""

    if "matricula" in restricao:
        return ValueError("Já existe um solicitante com essa matrícula.")

    return ValueError("Já existe um solicitante ativo com esse e-mail.")


class SolicitanteService:
    def listar(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT {CAMPOS}
                    FROM solicitantes
                    ORDER BY nome
                """)
                registros = cursor.fetchall()

        return [self._para_dict(r) for r in registros]

    def obter_por_id(self, solicitante_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT {CAMPOS}
                    FROM solicitantes
                    WHERE id = %s
                """, (solicitante_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def cadastrar(self, dados):
        solicitante = self._ler(dados)

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO solicitantes
                            (nome, tipo, setor, email, telefone, matricula)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        solicitante.nome,
                        solicitante.tipo,
                        solicitante.setor,
                        solicitante.email,
                        solicitante.telefone,
                        solicitante.matricula
                    ))
                    solicitante_id = cursor.fetchone()[0]

        except psycopg.errors.UniqueViolation as erro:
            raise _erro_duplicado(erro) from None

        return self.obter_por_id(solicitante_id)

    def atualizar(self, solicitante_id, dados):
        solicitante = self._ler(dados)

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        SELECT id
                        FROM solicitantes
                        WHERE id = %s
                        FOR UPDATE
                    """, (solicitante_id,))

                    if cursor.fetchone() is None:
                        return None

                    cursor.execute("""
                        SELECT id
                        FROM usuarios
                        WHERE solicitante_id = %s
                    """, (solicitante_id,))
                    conta = cursor.fetchone()

                    # A conta segue o tipo do cadastro (aluno <->
                    # professor). Servidores, técnicos e externos não
                    # têm conta própria.
                    if conta is not None:
                        if solicitante.tipo not in Solicitante.TIPOS_COM_CONTA:
                            raise ValueError(
                                "Esta pessoa tem conta de acesso, que só "
                                "existe para alunos e professores. "
                                "Desative o solicitante em vez de mudar o "
                                "tipo."
                            )

                        cursor.execute("""
                            UPDATE usuarios
                            SET papel = %s
                            WHERE id = %s
                        """, (solicitante.tipo, conta[0]))

                    cursor.execute("""
                        UPDATE solicitantes
                        SET nome = %s,
                            tipo = %s,
                            setor = %s,
                            email = %s,
                            telefone = %s,
                            matricula = %s
                        WHERE id = %s
                    """, (
                        solicitante.nome,
                        solicitante.tipo,
                        solicitante.setor,
                        solicitante.email,
                        solicitante.telefone,
                        solicitante.matricula,
                        solicitante_id
                    ))

        except psycopg.errors.UniqueViolation as erro:
            raise _erro_duplicado(erro) from None

        return self.obter_por_id(solicitante_id)

    def desativar(self, solicitante_id):
        """Desativa a pessoa, a conta dela e as reservas ainda futuras."""
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM solicitantes
                    WHERE id = %s AND ativo = TRUE
                    FOR UPDATE
                """, (solicitante_id,))

                if cursor.fetchone() is None:
                    return None

                cursor.execute("""
                    SELECT COUNT(*)
                    FROM itens_emprestimo ie
                    JOIN emprestimos em ON em.id = ie.emprestimo_id
                    WHERE em.solicitante_id = %s
                      AND em.status = 'em_andamento'
                      AND ie.data_devolucao IS NULL
                """, (solicitante_id,))
                pendentes = cursor.fetchone()[0]

                if pendentes:
                    raise ValueError(
                        f"Este solicitante ainda está com {pendentes} "
                        "equipamento(s) emprestado(s). Registre a "
                        "devolução antes de desativar."
                    )

                cursor.execute("""
                    UPDATE reservas
                    SET status = 'cancelada'
                    WHERE solicitante_id = %s
                      AND status IN ('pendente', 'aprovada')
                """, (solicitante_id,))

                cursor.execute("""
                    UPDATE usuarios
                    SET ativo = FALSE
                    WHERE solicitante_id = %s
                """, (solicitante_id,))

                cursor.execute("""
                    UPDATE solicitantes
                    SET ativo = FALSE
                    WHERE id = %s
                """, (solicitante_id,))

        return self.obter_por_id(solicitante_id)

    @staticmethod
    def _ler(dados):
        return Solicitante(
            nome=dados.get("nome"),
            tipo=dados.get("tipo"),
            setor=dados.get("setor"),
            email=dados.get("email"),
            telefone=dados.get("telefone"),
            matricula=dados.get("matricula")
        )

    @staticmethod
    def _para_dict(registro):
        if registro is None:
            return None

        return {
            "id": registro[0],
            "nome": registro[1],
            "tipo": registro[2],
            "setor": registro[3],
            "email": registro[4],
            "telefone": registro[5],
            "ativo": registro[6],
            "criado_em": (
                registro[7].isoformat()
                if registro[7] else None
            ),
            "matricula": registro[8],
            # Indica se a pessoa já criou a conta de acesso.
            "tem_conta": registro[9]
        }
