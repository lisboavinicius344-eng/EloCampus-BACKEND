from urllib.parse import parse_qs, urlparse

from database.conexao import Conexao


# Situação exibida pelo frontend, derivada do status do equipamento:
#   disponivel | emprestado | atrasado | manutencao | inativo
# "atrasado" = emprestado com a devolução prevista já vencida.
SITUACAO_SQL = """
    CASE
        WHEN e.status = 'baixado' THEN 'inativo'
        WHEN e.status = 'manutencao' THEN 'manutencao'
        WHEN e.status = 'emprestado' AND EXISTS (
            SELECT 1
            FROM itens_emprestimo ie
            JOIN emprestimos em ON em.id = ie.emprestimo_id
            WHERE ie.equipamento_id = e.id
              AND ie.data_devolucao IS NULL
              AND em.data_prevista_devolucao < NOW()
        ) THEN 'atrasado'
        WHEN e.status = 'emprestado' THEN 'emprestado'
        ELSE 'disponivel'
    END
"""

# Parâmetros que o QR Code pode trazer quando contém uma URL.
PARAMETROS_DO_QR = ("codigo", "patrimonio", "qr", "id")


class PainelService:

    def resumo(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""
                    WITH situacoes AS (
                        SELECT {SITUACAO_SQL} AS situacao
                        FROM equipamentos e
                    )
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (WHERE situacao = 'disponivel'),
                        COUNT(*) FILTER (WHERE situacao = 'emprestado'),
                        COUNT(*) FILTER (WHERE situacao = 'atrasado'),
                        COUNT(*) FILTER (WHERE situacao = 'manutencao'),
                        COUNT(*) FILTER (WHERE situacao = 'inativo')
                    FROM situacoes
                """)
                registro = cursor.fetchone()

        return {
            "total": registro[0],
            "disponiveis": registro[1],
            "emprestados": registro[2],
            "atrasados": registro[3],
            "manutencao": registro[4],
            "inativos": registro[5],
        }

    def consultar_qr(self, codigo, incluir_emprestimo=False):
        termo = self._extrair_codigo(codigo)

        if not termo:
            raise ValueError(
                "Informe o patrimônio, identificador ou QR Code."
            )

        equipamento_id = int(termo) if termo.isdigit() else None

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                # Prioridade: QR Code exato, depois patrimônio, depois ID.
                cursor.execute(f"""
                    SELECT
                        e.id,
                        e.nome,
                        e.numero_patrimonio,
                        c.nome,
                        e.setor,
                        e.localizacao,
                        e.estado_conservacao,
                        e.status,
                        {SITUACAO_SQL} AS situacao,
                        e.imagem_tipo,
                        e.imagem_atualizada_em
                    FROM equipamentos e
                    JOIN categorias c ON c.id = e.categoria_id
                    WHERE e.qr_code = %(termo)s
                       OR LOWER(e.numero_patrimonio) = LOWER(%(termo)s)
                       OR e.id = %(id)s
                    ORDER BY
                        CASE
                            WHEN e.qr_code = %(termo)s THEN 0
                            WHEN LOWER(e.numero_patrimonio) = LOWER(%(termo)s)
                                THEN 1
                            ELSE 2
                        END
                    LIMIT 1
                """, {"termo": termo, "id": equipamento_id})
                registro = cursor.fetchone()

                if registro is None:
                    return None

                emprestimo = None

                if incluir_emprestimo and registro[7] == "emprestado":
                    cursor.execute("""
                        SELECT
                            em.id,
                            s.nome,
                            em.data_emprestimo,
                            em.data_prevista_devolucao,
                            em.data_prevista_devolucao < NOW()
                        FROM itens_emprestimo ie
                        JOIN emprestimos em ON em.id = ie.emprestimo_id
                        JOIN solicitantes s ON s.id = em.solicitante_id
                        WHERE ie.equipamento_id = %s
                          AND ie.data_devolucao IS NULL
                        LIMIT 1
                    """, (registro[0],))
                    ativo = cursor.fetchone()

                    if ativo:
                        emprestimo = {
                            "id": ativo[0],
                            "solicitante": ativo[1],
                            "data_emprestimo": ativo[2].isoformat(),
                            "data_prevista_devolucao": ativo[3].isoformat(),
                            "atrasado": ativo[4],
                        }

        return {
            "equipamento": {
                "id": registro[0],
                "nome": registro[1],
                "numero_patrimonio": registro[2],
                "patrimonio": registro[2],
                "categoria": registro[3],
                "setor": registro[4],
                "localizacao": registro[5],
                "estado_conservacao": registro[6],
                "status": registro[7],
                "situacao": registro[8],
                "imagem_url": (
                    f"/equipamentos/{registro[0]}/imagem"
                    f"?v={int(registro[10].timestamp())}"
                    if registro[9]
                    else None
                ),
            },
            "emprestimo": emprestimo,
        }

    @staticmethod
    def _extrair_codigo(codigo):
        """Aceita o código puro ou uma URL gravada no QR Code."""
        bruto = str(codigo or "").strip()
        url = urlparse(bruto)

        if url.scheme in ("http", "https") and url.netloc:
            parametros = parse_qs(url.query)

            for nome in PARAMETROS_DO_QR:
                if parametros.get(nome):
                    return parametros[nome][0].strip()

            partes = [parte for parte in url.path.split("/") if parte]
            return partes[-1].strip() if partes else ""

        return bruto
