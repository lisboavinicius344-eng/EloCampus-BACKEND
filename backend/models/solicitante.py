import re


EMAIL_VALIDO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _texto_opcional(valor, campo, tamanho):
    if valor is None:
        return None

    if not isinstance(valor, str):
        raise ValueError(f"O campo {campo} deve ser um texto.")

    valor = valor.strip()

    if len(valor) > tamanho:
        raise ValueError(
            f"O campo {campo} deve ter no máximo {tamanho} caracteres."
        )

    return valor or None


class Solicitante:
    TIPOS_VALIDOS = (
        "aluno",
        "servidor",
        "professor",
        "tecnico",
        "externo"
    )

    # Tipos que criam a própria conta pelo autocadastro: o e-mail é a
    # forma de a pessoa provar quem é, então é obrigatório.
    TIPOS_COM_CONTA = ("aluno", "professor")

    def __init__(
        self,
        nome,
        tipo,
        setor=None,
        email=None,
        telefone=None,
        matricula=None
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

        email = _texto_opcional(email, "e-mail", 150)

        if email is not None:
            if not EMAIL_VALIDO.match(email):
                raise ValueError("Informe um e-mail válido.")

            email = email.lower()

        elif tipo in self.TIPOS_COM_CONTA:
            raise ValueError(
                "O e-mail é obrigatório para alunos e professores: é por "
                "ele que a pessoa cria a conta de acesso."
            )

        self.nome = nome.strip()
        self.tipo = tipo
        self.setor = setor
        self.email = email
        self.telefone = telefone
        self.matricula = _texto_opcional(matricula, "matrícula", 40)
