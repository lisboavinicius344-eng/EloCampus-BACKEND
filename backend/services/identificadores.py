"""Validação dos identificadores de pessoas.

usuarios.id é UUID e solicitantes.id é texto (VARCHAR 250, um UUID
gerado pelo banco). Os demais ids (equipamentos, empréstimos...) seguem
números inteiros.
"""
import uuid


TAMANHO_SOLICITANTE_ID = 250


def usuario_id(valor, campo="usuário"):
    """Devolve o UUID em texto, ou levanta ValueError."""
    if isinstance(valor, uuid.UUID):
        return str(valor)

    if isinstance(valor, str):
        try:
            return str(uuid.UUID(valor.strip()))
        except ValueError:
            pass

    raise ValueError(f"Informe um identificador de {campo} válido.")


def usuario_id_opcional(valor, campo="usuário"):
    return None if valor is None else usuario_id(valor, campo)


def solicitante_id(valor):
    """Devolve o id do solicitante (texto), ou levanta ValueError."""
    if isinstance(valor, str):
        valor = valor.strip()

        if valor and len(valor) <= TAMANHO_SOLICITANTE_ID:
            return valor

    raise ValueError("Informe um solicitante válido.")
