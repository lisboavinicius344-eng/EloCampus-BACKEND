from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from models.solicitante import Solicitante
from services import regras


AGORA = regras.agora()


@pytest.mark.parametrize(
    ("inicio", "fim", "mensagem"),
    [
        (AGORA - timedelta(hours=1), AGORA + timedelta(hours=1), "futuro"),
        (AGORA + timedelta(days=31), AGORA + timedelta(days=32), "30 dias"),
        (AGORA + timedelta(days=1), AGORA + timedelta(days=9), "7 dias"),
    ],
)
def test_periodo_de_reserva_fora_dos_limites(inicio, fim, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        regras.validar_periodo_reserva(inicio, fim)


def test_periodo_de_reserva_no_limite_e_aceito():
    inicio = AGORA + timedelta(days=29)
    regras.validar_periodo_reserva(inicio, inicio + timedelta(days=7))


def test_prazo_maximo_do_emprestimo():
    regras.validar_prazo_emprestimo(AGORA + timedelta(days=14))

    with pytest.raises(ValueError, match="15 dias"):
        regras.validar_prazo_emprestimo(AGORA + timedelta(days=16))


@pytest.mark.parametrize(
    ("inicio", "fim", "permitido"),
    [
        (AGORA + timedelta(hours=1), AGORA + timedelta(hours=5), True),
        (AGORA - timedelta(hours=1), AGORA + timedelta(hours=1), True),
        (AGORA + timedelta(hours=3), AGORA + timedelta(hours=5), False),
        (AGORA - timedelta(hours=3), AGORA - timedelta(hours=1), False),
    ],
)
def test_janela_de_retirada(inicio, fim, permitido):
    if permitido:
        regras.validar_janela_retirada(inicio, fim)
    else:
        with pytest.raises(ValueError):
            regras.validar_janela_retirada(inicio, fim)


def test_pendencia_bloqueia():
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)

    with pytest.raises(ValueError, match="atrasada"):
        regras.verificar_pendencias(cursor, 7)

    cursor.fetchone.return_value = None
    regras.verificar_pendencias(cursor, 7)


@pytest.mark.parametrize("tipo", ["aluno", "professor"])
def test_aluno_e_professor_precisam_de_email(tipo):
    with pytest.raises(ValueError, match="obrigatório"):
        Solicitante(nome="Ana", tipo=tipo)


def test_servidor_pode_nao_ter_email_e_email_e_normalizado():
    assert Solicitante(nome="Rui", tipo="servidor").email is None

    ana = Solicitante(
        nome="Ana", tipo="aluno", email=" Ana@UFOB.edu.br ",
        matricula=" 2024001 ",
    )
    assert ana.email == "ana@ufob.edu.br"
    assert ana.matricula == "2024001"


def test_email_invalido_e_recusado():
    with pytest.raises(ValueError, match="e-mail válido"):
        Solicitante(nome="Ana", tipo="aluno", email="ana@")


@pytest.mark.parametrize(
    ("em_uso", "reservados", "novos", "permitido"),
    [(0, 0, 3, True), (1, 1, 1, True), (2, 1, 1, False), (0, 0, 4, False)],
)
def test_limite_de_itens_por_pessoa(em_uso, reservados, novos, permitido):
    cursor = MagicMock()
    cursor.fetchone.return_value = (em_uso, reservados)

    if permitido:
        regras.verificar_limite_itens(cursor, "sol-1", novos)
    else:
        with pytest.raises(ValueError, match="até 3 equipamentos"):
            regras.verificar_limite_itens(cursor, "sol-1", novos)
