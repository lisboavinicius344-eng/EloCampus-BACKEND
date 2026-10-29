"""Solicitação de acesso: a pessoa pede, o admin aprova ou recusa.

Fluxo:
1. A pessoa informa nome e e-mail em "Solicitar acesso".
2. O pedido fica pendente para o admin.
3. Ao aprovar, o sistema cria (ou vincula) o solicitante, cria a conta
   e envia por e-mail, automaticamente, a senha provisória.
4. A senha provisória vale um único acesso: no primeiro login ela é
   trocada no banco, e a pessoa cria a própria senha.
"""
import os
import re

import psycopg

from database.conexao import Conexao
from models.solicitante import Solicitante
from services import identificadores, senha_provisoria


EMAIL_VALIDO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TIPOS = Solicitante.TIPOS_COM_CONTA

CAMPOS = """
    sa.id, sa.nome, sa.email, sa.tipo, sa.matricula, sa.mensagem,
    sa.status, sa.criado_em, sa.analisado_por, analista.nome,
    sa.analisado_em, sa.motivo_recusa, sa.usuario_id
"""


def _dominios_permitidos():
    """Domínios aceitos (ACESSO_DOMINIOS_PERMITIDOS), ou None para todos."""
    valor = os.getenv("ACESSO_DOMINIOS_PERMITIDOS", "")
    dominios = {d.strip().lower().lstrip("@") for d in valor.split(",")}
    dominios.discard("")
    return dominios or None


def _texto(valor, campo, tamanho, obrigatorio=False):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ValueError(f"Informe o {campo}.")
        return None

    if not isinstance(valor, str):
        raise ValueError(f"O campo {campo} deve ser um texto.")

    valor = " ".join(valor.split())

    if len(valor) > tamanho:
        raise ValueError(
            f"O campo {campo} deve ter no máximo {tamanho} caracteres."
        )

    return valor


def _tipo(valor, obrigatorio=False):
    if valor is None or valor == "":
        if obrigatorio:
            raise ValueError(
                "Informe se a pessoa é aluno ou professor."
            )
        return None

    tipo = str(valor).strip().lower()

    if tipo not in TIPOS:
        raise ValueError("O tipo deve ser aluno ou professor.")

    return tipo


class SolicitacaoAcessoService:

    def solicitar(self, dados):
        """Registra o pedido. Retorna True se um pedido novo foi criado.

        A rota responde sempre igual: não revela se o e-mail já tem conta
        ou pedido pendente.
        """
        nome = _texto(dados.get("nome"), "nome", 120, obrigatorio=True)
        email = _texto(dados.get("email"), "e-mail", 150, obrigatorio=True)

        if not EMAIL_VALIDO.match(email):
            raise ValueError("Informe um e-mail válido.")

        email = email.lower()
        dominios = _dominios_permitidos()

        if dominios and email.rsplit("@", 1)[1] not in dominios:
            raise ValueError(
                "Use o seu e-mail institucional ("
                + ", ".join(sorted("@" + d for d in dominios)) + ")."
            )

        tipo = _tipo(dados.get("tipo"))
        matricula = _texto(dados.get("matricula"), "matrícula", 40)
        mensagem = _texto(dados.get("mensagem"), "mensagem", 500)

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM usuarios WHERE LOWER(email) = %s
                """, (email,))

                # Quem já tem conta usa "Esqueci minha senha".
                if cursor.fetchone() is not None:
                    return False

                cursor.execute("""
                    INSERT INTO solicitacoes_acesso
                        (nome, email, tipo, matricula, mensagem)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT ((LOWER(email))) WHERE status = 'pendente'
                    DO NOTHING
                    RETURNING id
                """, (nome, email, tipo, matricula, mensagem))

                return cursor.fetchone() is not None

    def listar(self, status=None):
        filtro = ""
        parametros = ()

        if status:
            if status not in ("pendente", "aprovada", "recusada"):
                raise ValueError(
                    "Status inválido. Use pendente, aprovada ou recusada."
                )
            filtro = "WHERE sa.status = %s"
            parametros = (status,)

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT {CAMPOS}
                    FROM solicitacoes_acesso sa
                    LEFT JOIN usuarios analista ON analista.id = sa.analisado_por
                    {filtro}
                    ORDER BY (sa.status = 'pendente') DESC, sa.criado_em DESC
                """, parametros)
                registros = cursor.fetchall()

        return [self._para_dict(r) for r in registros]

    def obter_por_id(self, solicitacao_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT {CAMPOS}
                    FROM solicitacoes_acesso sa
                    LEFT JOIN usuarios analista ON analista.id = sa.analisado_por
                    WHERE sa.id = %s
                """, (solicitacao_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def aprovar(self, solicitacao_id, dados, analista_id):
        """Aprova: cria (ou vincula) o solicitante, a conta e envia o e-mail.

        Retorna (solicitacao, usuario, email_enviado, senha). A senha só
        é devolvida quando o e-mail falhou, para o admin repassá-la.
        """
        solicitacao_id = identificadores.usuario_id(
            solicitacao_id, "solicitação"
        )
        analista_id = identificadores.usuario_id(analista_id)
        vincular_id = dados.get("solicitante_id")

        if vincular_id is not None:
            vincular_id = identificadores.solicitante_id(vincular_id)

        senha, senha_hash, expira_em = senha_provisoria.gerar()

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        SELECT nome, email, tipo, matricula, status
                        FROM solicitacoes_acesso
                        WHERE id = %s
                        FOR UPDATE
                    """, (solicitacao_id,))
                    pedido = cursor.fetchone()

                    if pedido is None:
                        return None

                    nome_pedido, email, tipo_pedido, matricula, status = pedido

                    if status != "pendente":
                        raise ValueError(
                            f"Esta solicitação já foi {status}."
                        )

                    cursor.execute("""
                        SELECT 1 FROM usuarios WHERE LOWER(email) = LOWER(%s)
                    """, (email,))

                    if cursor.fetchone() is not None:
                        raise ValueError(
                            "Já existe uma conta com este e-mail. Recuse a "
                            "solicitação e oriente a pessoa a usar "
                            "\"Esqueci minha senha\"."
                        )

                    solicitante_id, nome, tipo = self._solicitante_para(
                        cursor, dados, vincular_id, email,
                        nome_pedido, tipo_pedido, matricula
                    )

                    cursor.execute("""
                        INSERT INTO usuarios
                            (nome, email, senha_hash, papel, solicitante_id,
                             deve_trocar_senha, senha_provisoria_expira_em)
                        VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                        RETURNING id
                    """, (
                        nome, email, senha_hash, tipo, solicitante_id,
                        expira_em,
                    ))
                    usuario_id = cursor.fetchone()[0]

                    cursor.execute("""
                        UPDATE solicitacoes_acesso
                        SET status = 'aprovada',
                            analisado_por = %s,
                            analisado_em = NOW(),
                            usuario_id = %s
                        WHERE id = %s
                    """, (analista_id, usuario_id, solicitacao_id))

        except psycopg.errors.UniqueViolation as erro:
            restricao = getattr(erro.diag, "constraint_name", "") or ""

            if "matricula" in restricao:
                raise ValueError(
                    "Já existe um solicitante com essa matrícula."
                ) from None

            raise ValueError(
                "Já existe uma conta ou um solicitante com este e-mail."
            ) from None

        usuario = {
            "id": usuario_id,
            "nome": nome,
            "email": email,
            "papel": tipo,
            "solicitante_id": solicitante_id,
        }
        enviado = senha_provisoria.enviar(
            usuario, senha, expira_em, "cadastro_aluno"
        )

        return (
            self.obter_por_id(solicitacao_id),
            usuario,
            enviado,
            None if enviado else senha,
        )

    def recusar(self, solicitacao_id, dados, analista_id):
        solicitacao_id = identificadores.usuario_id(
            solicitacao_id, "solicitação"
        )
        analista_id = identificadores.usuario_id(analista_id)
        motivo = _texto(dados.get("motivo"), "motivo", 500)

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT status
                    FROM solicitacoes_acesso
                    WHERE id = %s
                    FOR UPDATE
                """, (solicitacao_id,))
                registro = cursor.fetchone()

                if registro is None:
                    return None

                if registro[0] != "pendente":
                    raise ValueError(
                        f"Esta solicitação já foi {registro[0]}."
                    )

                cursor.execute("""
                    UPDATE solicitacoes_acesso
                    SET status = 'recusada',
                        analisado_por = %s,
                        analisado_em = NOW(),
                        motivo_recusa = %s
                    WHERE id = %s
                """, (analista_id, motivo, solicitacao_id))

        return self.obter_por_id(solicitacao_id)

    @staticmethod
    def _solicitante_para(cursor, dados, vincular_id, email, nome_pedido,
                          tipo_pedido, matricula_pedido):
        """Devolve (solicitante_id, nome, tipo) para a conta nova.

        Usa o solicitante indicado pelo admin, ou o solicitante ativo com
        o mesmo e-mail, ou cria um novo com os dados do pedido (que o
        admin pode corrigir no corpo da aprovação).
        """
        if vincular_id is None:
            cursor.execute("""
                SELECT id FROM solicitantes
                WHERE LOWER(email) = LOWER(%s) AND ativo = TRUE
            """, (email,))
            existente = cursor.fetchone()
            vincular_id = existente[0] if existente else None

        if vincular_id is not None:
            cursor.execute("""
                SELECT s.nome, s.tipo,
                       EXISTS (SELECT 1 FROM usuarios u
                               WHERE u.solicitante_id = s.id)
                FROM solicitantes s
                WHERE s.id = %s AND s.ativo = TRUE
                FOR UPDATE
            """, (vincular_id,))
            solicitante = cursor.fetchone()

            if solicitante is None:
                raise ValueError("Solicitante não encontrado ou inativo.")

            nome, tipo, tem_conta = solicitante

            if tem_conta:
                raise ValueError("Este solicitante já tem conta.")

            if tipo not in TIPOS:
                raise ValueError(
                    "Só alunos e professores têm conta de acesso. Este "
                    f"solicitante está cadastrado como {tipo}."
                )

            return vincular_id, nome, tipo

        tipo = _tipo(dados.get("tipo") or tipo_pedido, obrigatorio=True)
        novo = Solicitante(
            nome=_texto(dados.get("nome"), "nome", 120) or nome_pedido,
            tipo=tipo,
            email=email,
            matricula=dados.get("matricula", matricula_pedido),
            setor=dados.get("setor"),
            telefone=dados.get("telefone"),
        )

        cursor.execute("""
            INSERT INTO solicitantes
                (nome, tipo, setor, email, telefone, matricula)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            novo.nome, novo.tipo, novo.setor, novo.email, novo.telefone,
            novo.matricula,
        ))

        return cursor.fetchone()[0], novo.nome, novo.tipo

    @staticmethod
    def _para_dict(registro):
        return {
            "id": registro[0],
            "nome": registro[1],
            "email": registro[2],
            "tipo": registro[3],
            "matricula": registro[4],
            "mensagem": registro[5],
            "status": registro[6],
            "criado_em": registro[7].isoformat() if registro[7] else None,
            "analisado_por": registro[8],
            "analisado_por_nome": registro[9],
            "analisado_em": (
                registro[10].isoformat() if registro[10] else None
            ),
            "motivo_recusa": registro[11],
            "usuario_id": registro[12],
        }
