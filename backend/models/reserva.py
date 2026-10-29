from services import identificadores


class Reserva:
    STATUS_VALIDOS = (
        "pendente",
        "aprovada",
        "rejeitada",
        "cancelada",
        "concluida",
        "expirada"
    )

    def __init__(
        self,
        solicitante_id,
        data_inicio,
        data_fim,
        usuario_responsavel_id=None,
        observacoes=None
    ):
        solicitante_id = identificadores.solicitante_id(solicitante_id)

        if not data_inicio or not data_fim:
            raise ValueError("As datas de início e fim são obrigatórias.")

        if data_fim <= data_inicio:
            raise ValueError("A data final deve ser posterior à data inicial.")

        self.solicitante_id = solicitante_id
        self.usuario_responsavel_id = usuario_responsavel_id
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        self.observacoes = observacoes