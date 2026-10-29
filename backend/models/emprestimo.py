from datetime import datetime

from services import identificadores


class Emprestimo:
    STATUS_VALIDOS = ("em_andamento", "concluido", "cancelado")

    def __init__(
        self,
        solicitante_id,
        usuario_responsavel_id,
        data_prevista_devolucao,
        observacoes=None
    ):
        solicitante_id = identificadores.solicitante_id(solicitante_id)
        usuario_responsavel_id = identificadores.usuario_id(
            usuario_responsavel_id, "usuário responsável"
        )

        if not data_prevista_devolucao:
            raise ValueError("A data prevista para devolução é obrigatória.")

        self.solicitante_id = solicitante_id
        self.usuario_responsavel_id = usuario_responsavel_id
        self.data_prevista_devolucao = data_prevista_devolucao
        self.observacoes = observacoes