import logging

import psycopg

from database.conexao import Conexao
from models.equipamento import Equipamento
from services import imagem_equipamento
from services.manutencao_service import abrir_automatica
from services.painel_service import SITUACAO_SQL
from services.n8n_service import notificar_equipamento


logger = logging.getLogger(__name__)

ELEGIBILIDADES_VALIDAS = ("todos", "somente_funcionarios")


class EquipamentoService:

    @staticmethod
    def _notificar_com_seguranca(equipamento, evento):
        if equipamento is None:
            return

        try:
            notificar_equipamento(equipamento, evento)
        except Exception:
            logger.exception(
                "Falha ao notificar o n8n sobre o evento %s.",
                evento,
            )

    def listar(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT
                        e.id,
                        e.nome,
                        e.numero_patrimonio,
                        e.categoria_id,
                        c.nome AS categoria,
                        e.setor,
                        e.localizacao,
                        e.estado_conservacao,
                        e.status,
                        e.qr_code,
                        e.observacoes,
                        e.criado_em,
                        e.elegibilidade,
                        {SITUACAO_SQL} AS situacao,
                        e.imagem_tipo,
                        e.imagem_atualizada_em
                    FROM equipamentos e
                    JOIN categorias c ON c.id = e.categoria_id
                    ORDER BY e.id
                """)
                registros = cursor.fetchall()

        return [self._para_dict(r) for r in registros]

    def obter_por_id(self, equipamento_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    SELECT
                        e.id,
                        e.nome,
                        e.numero_patrimonio,
                        e.categoria_id,
                        c.nome AS categoria,
                        e.setor,
                        e.localizacao,
                        e.estado_conservacao,
                        e.status,
                        e.qr_code,
                        e.observacoes,
                        e.criado_em,
                        e.elegibilidade,
                        {SITUACAO_SQL} AS situacao,
                        e.imagem_tipo,
                        e.imagem_atualizada_em
                    FROM equipamentos e
                    JOIN categorias c ON c.id = e.categoria_id
                    WHERE e.id = %s
                """, (equipamento_id,))
                registro = cursor.fetchone()

        return self._para_dict(registro) if registro else None

    def cadastrar(self, dados):
        equipamento = self._validar_dados(dados)
        _, imagem, imagem_tipo = imagem_equipamento.ler(dados)

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    equipamento["categoria_id"] = self._resolver_categoria(
                        cursor, equipamento
                    )

                    cursor.execute("""
                        INSERT INTO equipamentos (
                            nome,
                            numero_patrimonio,
                            categoria_id,
                            setor,
                            localizacao,
                            estado_conservacao,
                            status,
                            qr_code,
                            observacoes,
                            elegibilidade,
                            imagem,
                            imagem_tipo,
                            imagem_atualizada_em
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, CASE WHEN %s THEN NOW() END)
                        RETURNING id
                    """, (
                        equipamento["nome"],
                        equipamento["numero_patrimonio"],
                        equipamento["categoria_id"],
                        equipamento["setor"],
                        equipamento["localizacao"],
                        equipamento["estado_conservacao"],
                        equipamento["status"],
                        equipamento["qr_code"],
                        equipamento["observacoes"],
                        equipamento.get("elegibilidade") or "todos",
                        imagem,
                        imagem_tipo,
                        imagem is not None
                    ))

                    equipamento_id = cursor.fetchone()[0]

                    if equipamento["status"] == "manutencao":
                        abrir_automatica(
                            cursor,
                            equipamento_id,
                            None,
                            "Cadastrado com conservação danificada.",
                        )

        except psycopg.errors.UniqueViolation:
            raise ValueError(
                "Já existe um equipamento com esse número de patrimônio."
            ) from None

        equipamento_criado = self.obter_por_id(equipamento_id)
        self._notificar_com_seguranca(
            equipamento_criado,
            "equipamento_cadastrado",
        )

        return equipamento_criado

    def atualizar(self, equipamento_id, dados):
        equipamento = self._validar_dados(dados)
        acao_imagem, imagem, imagem_tipo = imagem_equipamento.ler(dados)

        try:
            with Conexao.conectar() as conexao:
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, status, estado_conservacao
                        FROM equipamentos
                        WHERE id = %s
                        FOR UPDATE
                    """, (equipamento_id,))

                    equipamento_atual = cursor.fetchone()

                    if equipamento_atual is None:
                        return None

                    status_atual = equipamento_atual[1]
                    estado_atual = equipamento_atual[2]
                    novo_estado = equipamento["estado_conservacao"]

                    if status_atual == "emprestado":
                        if novo_estado != estado_atual:
                            raise ValueError(
                                "Não é permitido alterar a conservação "
                                "de um equipamento emprestado. Atualize "
                                "a conservação durante a devolução."
                            )

                    cursor.execute("""
                        SELECT 1
                        FROM manutencoes
                        WHERE equipamento_id = %s
                          AND status IN ('aberta', 'em_andamento')
                    """, (equipamento_id,))
                    manutencao_aberta = cursor.fetchone() is not None

                    # Com manutenção aberta, quem libera o equipamento é
                    # a finalização da manutenção, não a edição.
                    if manutencao_aberta and novo_estado != estado_atual:
                        raise ValueError(
                            "Este equipamento está em manutenção. A "
                            "conservação é atualizada ao finalizar a "
                            "manutenção."
                        )

                    equipamento["categoria_id"] = self._resolver_categoria(
                        cursor, equipamento
                    )

                    # O status operacional não é recebido livremente
                    # do cliente. A conservação danificada exige
                    # manutenção, exceto durante um empréstimo.
                    if status_atual in ("emprestado", "baixado"):
                        novo_status = status_atual

                    elif manutencao_aberta or novo_estado == "danificado":
                        novo_status = "manutencao"

                    else:
                        novo_status = "disponivel"

                    cursor.execute("""
                        UPDATE equipamentos
                        SET nome = %s,
                            numero_patrimonio = %s,
                            categoria_id = %s,
                            setor = %s,
                            localizacao = %s,
                            estado_conservacao = %s,
                            status = %s,
                            qr_code = %s,
                            observacoes = %s,
                            elegibilidade = COALESCE(%s, elegibilidade)
                        WHERE id = %s
                    """, (
                        equipamento["nome"],
                        equipamento["numero_patrimonio"],
                        equipamento["categoria_id"],
                        equipamento["setor"],
                        equipamento["localizacao"],
                        novo_estado,
                        novo_status,
                        equipamento["qr_code"],
                        equipamento["observacoes"],
                        equipamento.get("elegibilidade"),
                        equipamento_id
                    ))

                    if novo_status == "manutencao" and not manutencao_aberta:
                        abrir_automatica(
                            cursor,
                            equipamento_id,
                            None,
                            "Conservação alterada para danificada no "
                            "cadastro do equipamento.",
                        )

                    if acao_imagem != imagem_equipamento.MANTER:
                        cursor.execute("""
                            UPDATE equipamentos
                            SET imagem = %s,
                                imagem_tipo = %s,
                                imagem_atualizada_em = CASE
                                    WHEN %s THEN NOW()
                                END
                            WHERE id = %s
                        """, (
                            imagem,
                            imagem_tipo,
                            imagem is not None,
                            equipamento_id
                        ))

        except psycopg.errors.UniqueViolation:
            raise ValueError(
                "Já existe um equipamento com esse número de patrimônio."
            ) from None

        equipamento_atualizado = self.obter_por_id(equipamento_id)
        self._notificar_com_seguranca(
            equipamento_atualizado,
            "equipamento_atualizado",
        )

        return equipamento_atualizado

    def inativar(self, equipamento_id):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT status
                    FROM equipamentos
                    WHERE id = %s
                    FOR UPDATE
                """, (equipamento_id,))

                registro = cursor.fetchone()

                if registro is None:
                    return None

                if registro[0] == "emprestado":
                    raise ValueError(
                        "Não é possível baixar um equipamento emprestado."
                    )

                if registro[0] == "baixado":
                    raise ValueError("O equipamento já está baixado.")

                cursor.execute("""
                    UPDATE equipamentos
                    SET status = 'baixado'
                    WHERE id = %s
                """, (equipamento_id,))

        equipamento_baixado = self.obter_por_id(equipamento_id)
        self._notificar_com_seguranca(
            equipamento_baixado,
            "equipamento_baixado",
        )

        return equipamento_baixado

    def obter_imagem(self, equipamento_id):
        """Retorna (conteudo, tipo) da imagem, ou None se não houver."""
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT imagem, imagem_tipo
                    FROM equipamentos
                    WHERE id = %s AND imagem IS NOT NULL
                """, (equipamento_id,))
                registro = cursor.fetchone()

        if registro is None:
            return None

        return bytes(registro[0]), registro[1]

    @staticmethod
    def _resolver_categoria(cursor, equipamento):
        """Devolve o ID da categoria, criando-a quando veio só o nome."""
        if equipamento["categoria_id"] is not None:
            cursor.execute(
                """
                SELECT id
                FROM categorias
                WHERE id = %s AND ativo = TRUE
                """,
                (equipamento["categoria_id"],)
            )

            if cursor.fetchone() is None:
                raise ValueError(
                    "Categoria não encontrada ou inativa."
                )

            return equipamento["categoria_id"]

        nome = equipamento["categoria_nome"]

        cursor.execute(
            """
            INSERT INTO categorias (nome)
            VALUES (%s)
            ON CONFLICT ((LOWER(nome))) DO NOTHING
            """,
            (nome,)
        )
        cursor.execute(
            """
            SELECT id, nome, ativo
            FROM categorias
            WHERE LOWER(nome) = LOWER(%s)
            """,
            (nome,)
        )
        categoria = cursor.fetchone()

        if not categoria[2]:
            raise ValueError(
                f"A categoria \"{categoria[1]}\" está desativada. "
                "Reative-a ou escolha outra."
            )

        return categoria[0]

    @staticmethod
    def _validar_dados(dados):
        nome = dados.get("nome")

        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("O nome do equipamento é obrigatório.")

        # A categoria pode vir pelo ID ou pelo nome. Pelo nome, ela é
        # criada se ainda não existir (cadastro direto pelo formulário).
        categoria_nome = None

        if dados.get("categoria_id") not in (None, ""):
            try:
                categoria_id = int(dados.get("categoria_id"))

                if categoria_id <= 0:
                    raise ValueError

            except (TypeError, ValueError):
                raise ValueError(
                    "Informe um categoria_id válido."
                ) from None

        else:
            categoria_id = None
            categoria_nome = dados.get("categoria")

            if not isinstance(categoria_nome, str) or not categoria_nome.strip():
                raise ValueError(
                    "Informe a categoria do equipamento."
                )

            categoria_nome = " ".join(categoria_nome.split())

            if len(categoria_nome) > 80:
                raise ValueError(
                    "O nome da categoria deve ter no máximo 80 caracteres."
                )

        estado = dados.get("estado_conservacao", "bom")

        # O cliente não escolhe livremente o status operacional.
        status = (
            "manutencao"
            if estado == "danificado"
            else "disponivel"
        )

        equipamento = Equipamento(
            nome=nome,
            categoria_id=categoria_id,
            numero_patrimonio=dados.get("numero_patrimonio"),
            setor=dados.get("setor"),
            localizacao=dados.get("localizacao"),
            estado_conservacao=estado,
            status=status,
            qr_code=dados.get("qr_code"),
            observacoes=dados.get("observacoes")
        )

        elegibilidade = dados.get("elegibilidade")

        if (
            elegibilidade is not None
            and elegibilidade not in ELEGIBILIDADES_VALIDAS
        ):
            raise ValueError(
                "Elegibilidade inválida. Use: "
                + ", ".join(ELEGIBILIDADES_VALIDAS) + "."
            )

        patrimonio = equipamento.numero_patrimonio

        if patrimonio is not None:
            if not isinstance(patrimonio, str):
                raise ValueError(
                    "O número de patrimônio deve ser um texto."
                )

            patrimonio = patrimonio.strip() or None

        return {
            "nome": equipamento.nome,
            "numero_patrimonio": patrimonio,
            "categoria_id": categoria_id,
            "categoria_nome": categoria_nome,
            "setor": equipamento.setor,
            "localizacao": equipamento.localizacao,
            "estado_conservacao": equipamento.estado_conservacao,
            "status": equipamento.status,
            "qr_code": equipamento.qr_code,
            "observacoes": equipamento.observacoes,
            # None = não informado (na atualização, mantém o valor atual).
            "elegibilidade": elegibilidade
        }

    @staticmethod
    def _para_dict(registro):
        return {
            "id": registro[0],
            "nome": registro[1],
            "numero_patrimonio": registro[2],
            "categoria_id": registro[3],
            "categoria": registro[4],
            "setor": registro[5],
            "localizacao": registro[6],
            "estado_conservacao": registro[7],
            "status": registro[8],
            "qr_code": registro[9],
            "observacoes": registro[10],
            "criado_em": (
                registro[11].isoformat()
                if registro[11] is not None
                else None
            ),
            "elegibilidade": registro[12],
            "situacao": registro[13],
            # Endereço relativo à base da API (ELO_API_BASE_URL). O ?v=
            # muda a cada troca de imagem, para o navegador não usar a
            # versão antiga guardada em cache.
            "imagem_url": (
                f"/equipamentos/{registro[0]}/imagem"
                f"?v={int(registro[15].timestamp())}"
                if registro[14]
                else None
            )
        }
