from unittest.mock import patch

import pytest

from services.perfil_service import PerfilService
from tests.test_rotas import _cabecalho, autenticado, cliente, uid  # noqa: F401


def test_perfil_exige_login(cliente):
    assert cliente.get("/api/auth/perfil").status_code == 401
    assert cliente.put("/api/auth/perfil", json={}).status_code == 401


def test_perfil_usa_o_usuario_do_token(cliente, autenticado):
    with patch(
        "routes.auth.PerfilService.atualizar",
        return_value={"id": uid(3), "nome": "Novo Nome"},
    ) as atualizar:
        resposta = cliente.put(
            "/api/auth/perfil", json={"nome": "Novo Nome"},
            headers=_cabecalho(3),
        )

    assert resposta.status_code == 200
    assert resposta.get_json()["perfil"]["nome"] == "Novo Nome"
    # Só edita a própria conta: o id vem do token, nunca do corpo.
    assert atualizar.call_args.args[0] == uid(3)


def test_senha_pendente_nao_edita_perfil(cliente, autenticado):
    resposta = cliente.put(
        "/api/auth/perfil", json={"nome": "X"}, headers=_cabecalho(5)
    )

    assert resposta.status_code == 403


@pytest.mark.parametrize(
    ("dados", "mensagem"),
    [
        ({}, "nome ou o telefone"),
        ({"email": "outro@x.com"}, "e-mail não pode"),
        ({"nome": "   "}, "Informe o nome"),
        ({"nome": "A" * 121}, "120"),
        ({"telefone": "abc"}, "telefone válido"),
    ],
)
def test_validacoes_do_perfil(dados, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        PerfilService().atualizar(uid(3), dados)
