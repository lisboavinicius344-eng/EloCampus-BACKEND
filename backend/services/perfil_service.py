"""Perfil do próprio usuário: consultar e editar os dados pessoais.

- nome: qualquer conta. Em aluno e professor, o cadastro de solicitante
  é atualizado junto, para o nome sair igual nos empréstimos.
- telefone: só aluno e professor (fica no cadastro de solicitante).
- e-mail: não é editável aqui. É o login e o endereço que recebe a
  senha; trocar por conta própria driblaria a aprovação do admin.
"""
import re

from database.conexao import Conexao


TELEFONE_VALIDO = re.compile(r"^[0-9()+\-.\s]{8,30}$")
CAMPOS_EDITAVEIS = ("nome", "telefone")


def _nome(valor):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("Informe o nome.")

    valor = " ".join(valor.split())

    if len(valor) > 120:
        raise ValueError("O nome deve ter no máximo 120 caracteres.")

    return valor


def _telefone(valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None

    if not isinstance(valor, str) or not TELEFONE_VALIDO.match(valor.strip()):
        raise ValueError(
            "Informe um telefone válido, por exemplo (77) 99999-0000."
        )

    return valor.strip()


class PerfilService:

    def obter(self, usuario_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT u.id, u.nome, u.email, u.papel, u.solicitante_id,
                           s.telefone, s.matricula, s.setor
                    FROM usuarios u
                    LEFT JOIN solicitantes s ON s.id = u.solicitante_id
                    WHERE u.id = %s AND u.ativo = TRUE
                """, (usuario_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def atualizar(self, usuario_id, dados):
        """Atualiza só os campos enviados. Retorna o perfil atualizado."""
        desconhecidos = sorted(
            campo for campo in dados if campo not in CAMPOS_EDITAVEIS
        )

        if "email" in desconhecidos:
            raise ValueError(
                "O e-mail não pode ser alterado pelo perfil. Procure a "
                "administração."
            )

        if not any(campo in dados for campo in CAMPOS_EDITAVEIS):
            raise ValueError("Envie o nome ou o telefone para atualizar.")

        nome = _nome(dados["nome"]) if "nome" in dados else None
        telefone = _telefone(dados.get("telefone"))

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT solicitante_id
                    FROM usuarios
                    WHERE id = %s AND ativo = TRUE
                    FOR UPDATE
                """, (usuario_id,))
                registro = cursor.fetchone()

                if registro is None:
                    return None

                solicitante_id = registro[0]

                if "telefone" in dados and solicitante_id is None:
                    raise ValueError(
                        "Contas da equipe não têm telefone no cadastro."
                    )

                if nome is not None:
                    cursor.execute("""
                        UPDATE usuarios SET nome = %s WHERE id = %s
                    """, (nome, usuario_id))

                if solicitante_id is not None:
                    cursor.execute("""
                        UPDATE solicitantes
                        SET nome = COALESCE(%s, nome),
                            telefone = CASE WHEN %s THEN %s ELSE telefone END
                        WHERE id = %s
                    """, (
                        nome,
                        "telefone" in dados,
                        telefone,
                        solicitante_id,
                    ))

        return self.obter(usuario_id)

    @staticmethod
    def _para_dict(registro):
        tem_solicitante = registro[4] is not None

        return {
            "id": registro[0],
            "nome": registro[1],
            "email": registro[2],
            "papel": registro[3],
            "solicitante_id": registro[4],
            "telefone": registro[5],
            "matricula": registro[6],
            "setor": registro[7],
            # O que a tela pode deixar editar.
            "editaveis": (
                ["nome", "telefone"] if tem_solicitante else ["nome"]
            ),
        }
