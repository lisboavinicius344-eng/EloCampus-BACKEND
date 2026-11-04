"""E-mail em segundo plano, logins antigos invalidados e reativação."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services import senha_provisoria
from services.auth_token import gerar_token
from services.categoria_service import CategoriaService
from services.solicitante_service import SolicitanteService
from services.usuario_service import UsuarioService
from tests.test_rotas import (  # noqa: F401
    SENHA_HASH,
    _cabecalho,
    autenticado,
    cliente,
    uid,
)


def test_envio_em_segundo_plano_nao_trava_nem_derruba():
    usuario = {"id": uid(1)}
    agora = datetime.now(timezone.utc)

    with patch(
        "services.senha_provisoria.notificar_senha_provisoria",
        side_effect=RuntimeError("n8n fora do ar"),
    ) as notificar:
        senha_provisoria.enviar_em_segundo_plano(
            usuario, "x", agora, "recuperacao_senha"
        )
        senha_provisoria.aguardar_envios()

    assert notificar.called


def test_token_vale_com_a_senha_atual(cliente, autenticado):
    with patch("routes.usuarios.usuario_service.listar", return_value=[]):
        resposta = cliente.get("/api/usuarios/", headers=_cabecalho(1))

    assert resposta.status_code == 200


def test_token_de_senha_anterior_e_recusado(cliente, autenticado):
    token = gerar_token(uid(1), "hash-da-senha-antiga")
    resposta = cliente.get(
        "/api/usuarios/", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 401
    assert "senha foi alterada" in resposta.get_json()["erro"]


def test_token_sem_impressao_digital_e_recusado(cliente, autenticado):
    from services.auth_token import _serializer

    token = _serializer().dumps({"usuario_id": uid(1)})
    resposta = cliente.get(
        "/api/usuarios/", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 401


def test_trocar_senha_devolve_um_token_novo(cliente, autenticado):
    with (
        patch("routes.auth.AuthService.trocar_senha"),
        patch("routes.auth.gerar_token", return_value="token-novo"),
    ):
        resposta = cliente.post(
            "/api/auth/trocar-senha",
            json={"nova_senha": "minhaNova123"},
            headers=_cabecalho(5),
        )

    assert resposta.get_json()["token"] == "token-novo"


@pytest.mark.parametrize(
    "rota",
    [
        f"/api/usuarios/{uid(3)}/reativar",
        "/api/solicitantes/30/reativar",
        "/api/categorias/1/reativar",
    ],
)
def test_reativar_e_da_equipe(cliente, autenticado, rota):
    assert cliente.patch(rota).status_code == 401
    assert cliente.patch(rota, headers=_cabecalho(3)).status_code == 403


def test_operador_nao_reativa_usuario(cliente, autenticado):
    resposta = cliente.patch(
        f"/api/usuarios/{uid(3)}/reativar", headers=_cabecalho(2)
    )

    assert resposta.status_code == 403


@pytest.mark.parametrize(
    ("rota", "servico"),
    [
        ("/api/solicitantes/30/reativar",
         "routes.solicitantes.solicitante_service.reativar"),
        ("/api/categorias/1/reativar",
         "routes.categorias.categoria_service.reativar"),
        (f"/api/usuarios/{uid(3)}/reativar",
         "routes.usuarios.usuario_service.reativar"),
    ],
)
def test_reativar_respostas(cliente, autenticado, rota, servico):
    with patch(servico, return_value=None):
        assert cliente.patch(rota, headers=_cabecalho(1)).status_code == 404

    with patch(servico, side_effect=ValueError("já está ativo")):
        resposta = cliente.patch(rota, headers=_cabecalho(1))
        assert resposta.status_code == 400
        assert resposta.get_json()["erro"] == "já está ativo"

    with patch(servico, return_value={"id": 1}):
        assert cliente.patch(rota, headers=_cabecalho(1)).status_code == 200


def _banco(modulo, registro):
    cursor = MagicMock()
    cursor.fetchone.return_value = registro
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return patch(f"services.{modulo}.Conexao.conectar", return_value=conexao)


def test_conta_com_solicitante_desativado_nao_reativa():
    with _banco("usuario_service", (False, False)):
        with pytest.raises(ValueError, match="Reative o solicitante"):
            UsuarioService().reativar(uid(3))


@pytest.mark.parametrize(
    ("servico", "modulo", "registro", "identificador"),
    [
        (UsuarioService, "usuario_service", (True, None), uid(1)),
        (SolicitanteService, "solicitante_service", (True,), "30"),
        (CategoriaService, "categoria_service", (True,), 1),
    ],
)
def test_ja_ativo_e_recusado(servico, modulo, registro, identificador):
    with _banco(modulo, registro):
        with pytest.raises(ValueError, match="já está ativ"):
            servico().reativar(identificador)
