"""Operações do administrador master."""
import logging

from database.conexao import Conexao


logger = logging.getLogger(__name__)

# O que "zerar os dados" apaga, na ordem do relatório. Contas, solicitantes,
# categorias e solicitações de acesso ficam.
TABELAS_ZERADAS = (
    "equipamentos",
    "emprestimos",
    "itens_emprestimo",
    "reservas",
    "itens_reserva",
    "manutencoes",
    "historico_movimentacoes",
)

# Texto que o master precisa digitar para confirmar.
CONFIRMACAO = "ZERAR DADOS"


def zerar_dados(confirmacao, usuario):
    """Apaga equipamentos e tudo que depende deles. Não há como desfazer.

    Retorna quantos registros cada tabela tinha.
    """
    if str(confirmacao or "").strip() != CONFIRMACAO:
        raise ValueError(
            f'Para confirmar, envie "confirmacao": "{CONFIRMACAO}". '
            "Esta ação apaga todos os equipamentos, reservas, empréstimos, "
            "manutenções e o histórico, e não pode ser desfeita."
        )

    with Conexao.conectar() as conexao:
        with conexao.cursor() as cursor:
            apagados = {}
            for tabela in TABELAS_ZERADAS:
                cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
                apagados[tabela] = cursor.fetchone()[0]

            # Sem CASCADE: se outra tabela depender destas, o comando falha
            # e nada é apagado. RESTART IDENTITY recomeça os números.
            cursor.execute(
                f"TRUNCATE {', '.join(TABELAS_ZERADAS)} RESTART IDENTITY"
            )

    logger.warning(
        "Dados zerados por %s (%s): %s",
        usuario["nome"], usuario["email"], apagados,
    )
    return apagados
