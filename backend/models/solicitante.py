class Solicitante:
    TIPOS_VALIDOS = (
        "aluno",
        "servidor",
        "professor",
        "tecnico",
        "externo"
    )

    def __init__(
        self,
        nome,
        tipo,
        setor=None,
        email=None,
        telefone=None
    ):
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("O nome do solicitante é obrigatório.")

        if not isinstance(tipo, str) or not tipo.strip():
            raise ValueError("O tipo do solicitante é obrigatório.")

        tipo = tipo.strip().lower()

        if tipo not in self.TIPOS_VALIDOS:
            raise ValueError(
                "Tipo de solicitante inválido. Use: "
                + ", ".join(self.TIPOS_VALIDOS) + "."
            )

        self.nome = nome.strip()
        self.tipo = tipo
        self.setor = setor
        self.email = email
        self.telefone = telefone