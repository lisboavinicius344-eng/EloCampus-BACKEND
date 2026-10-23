# Tipos de solicitante considerados funcionários da instituição.
# Equipamentos com elegibilidade "somente_funcionarios" (ex.: itens de
# laboratório ou de uso docente) não ficam disponíveis para os demais.
TIPOS_FUNCIONARIOS = ("professor", "servidor", "tecnico")


def verificar_elegibilidade(cursor, tipo_solicitante, equipamento_ids):
    """Recusa equipamentos restritos a funcionários para outros solicitantes.

    Deve ser chamada dentro da transação que já bloqueou os equipamentos.
    """
    if tipo_solicitante in TIPOS_FUNCIONARIOS:
        return

    cursor.execute("""
        SELECT id
        FROM equipamentos
        WHERE id = ANY(%s)
          AND elegibilidade = 'somente_funcionarios'
        ORDER BY id
    """, (list(equipamento_ids),))

    restritos = [registro[0] for registro in cursor.fetchall()]

    if restritos:
        raise ValueError(
            "Equipamentos disponíveis somente para professores e "
            f"servidores: {restritos}."
        )
