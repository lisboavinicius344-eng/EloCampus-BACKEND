"""Regras de negócio de prazos e pendências, num lugar só.

Para mudar um limite, altere a constante aqui: reservas, retiradas e
empréstimos usam estes valores.
"""
from datetime import datetime, timedelta, timezone


# Empréstimo: devolução prevista em no máximo 15 dias.
PRAZO_MAXIMO_EMPRESTIMO = timedelta(days=15)

# Reserva: dura no máximo 7 dias e é marcada com até 30 dias de
# antecedência.
DURACAO_MAXIMA_RESERVA = timedelta(days=7)
ANTECEDENCIA_MAXIMA_RESERVA = timedelta(days=30)

# A retirada de uma reserva aprovada pode ser registrada a partir de
# 2 horas antes do início, até o fim do período reservado.
ANTECEDENCIA_RETIRADA = timedelta(hours=2)

# Cada pessoa pode ter no máximo 3 equipamentos ao mesmo tempo, somando
# os que está usando (empréstimo em aberto) e os que reservou (reserva
# pendente ou aprovada).
LIMITE_ITENS_POR_PESSOA = 3

# Uma reserva vira "expirada" quando o tempo passa sem ação da equipe:
# pendente cujo início já passou, ou aprovada cujo fim já passou sem
# retirada. É aplicado antes de ler ou alterar reservas.
SQL_EXPIRAR_RESERVAS = """
    UPDATE reservas
    SET status = 'expirada'
    WHERE (status = 'pendente' AND data_inicio <= NOW())
       OR (status = 'aprovada' AND data_fim <= NOW())
"""


def agora():
    return datetime.now(timezone.utc)


def expirar_reservas(cursor):
    cursor.execute(SQL_EXPIRAR_RESERVAS)


def verificar_limite_itens(cursor, solicitante_id, quantidade_nova):
    """Recusa o pedido que passaria do limite de itens por pessoa.

    Chame depois de expirar_reservas, para reservas vencidas não
    contarem.
    """
    cursor.execute("""
        SELECT
            (SELECT COUNT(*)
             FROM itens_emprestimo ie
             JOIN emprestimos em ON em.id = ie.emprestimo_id
             WHERE em.solicitante_id = %(id)s
               AND em.status = 'em_andamento'
               AND ie.data_devolucao IS NULL),
            (SELECT COUNT(*)
             FROM itens_reserva ir
             JOIN reservas r ON r.id = ir.reserva_id
             WHERE r.solicitante_id = %(id)s
               AND r.status IN ('pendente', 'aprovada'))
    """, {"id": solicitante_id})
    em_uso, reservados = cursor.fetchone()

    if em_uso + reservados + quantidade_nova > LIMITE_ITENS_POR_PESSOA:
        raise ValueError(
            f"Cada pessoa pode ter até {LIMITE_ITENS_POR_PESSOA} "
            f"equipamentos ao mesmo tempo (emprestados e reservados). "
            f"Esta pessoa já tem {em_uso} emprestado(s) e {reservados} "
            f"reservado(s); este pedido inclui {quantidade_nova}."
        )


def verificar_pendencias(cursor, solicitante_id):
    """Recusa quem tem equipamento com devolução atrasada."""
    cursor.execute("""
        SELECT 1
        FROM itens_emprestimo ie
        JOIN emprestimos em ON em.id = ie.emprestimo_id
        WHERE em.solicitante_id = %s
          AND em.status = 'em_andamento'
          AND ie.data_devolucao IS NULL
          AND em.data_prevista_devolucao < NOW()
        LIMIT 1
    """, (solicitante_id,))

    if cursor.fetchone() is not None:
        raise ValueError(
            "Este solicitante tem equipamento com devolução atrasada. "
            "Registre a devolução antes de novas reservas ou empréstimos."
        )


def validar_prazo_emprestimo(data_prevista, momento=None):
    # momento: o "agora" com o mesmo tipo de data (com ou sem fuso).
    if data_prevista - (momento or agora()) > PRAZO_MAXIMO_EMPRESTIMO:
        raise ValueError(
            "A devolução deve ser prevista para no máximo "
            f"{PRAZO_MAXIMO_EMPRESTIMO.days} dias."
        )


def validar_periodo_reserva(inicio, fim):
    momento = agora()

    if inicio <= momento:
        raise ValueError("A reserva deve começar no futuro.")

    if inicio - momento > ANTECEDENCIA_MAXIMA_RESERVA:
        raise ValueError(
            "A reserva pode ser feita com no máximo "
            f"{ANTECEDENCIA_MAXIMA_RESERVA.days} dias de antecedência."
        )

    if fim - inicio > DURACAO_MAXIMA_RESERVA:
        raise ValueError(
            "A reserva pode durar no máximo "
            f"{DURACAO_MAXIMA_RESERVA.days} dias."
        )


def validar_janela_retirada(inicio, fim):
    momento = agora()

    if momento < inicio - ANTECEDENCIA_RETIRADA:
        horas = int(ANTECEDENCIA_RETIRADA.total_seconds() // 3600)
        raise ValueError(
            "A retirada só pode ser registrada a partir de "
            f"{horas} horas antes do início da reserva."
        )

    if momento >= fim:
        raise ValueError("O período desta reserva já terminou.")
