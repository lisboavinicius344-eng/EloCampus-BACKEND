from unittest.mock import MagicMock, patch

import pytest
import requests

import app  # noqa: F401  Garante que a aplicação inteira importa.
from services import n8n_service
from services.equipamento_service import EquipamentoService
from services.manutencao_service import ManutencaoService
from services.reserva_service import ReservaService


def _conexao_simulada(cursor):
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.__exit__.return_value = False
    conexao.cursor.return_value.__enter__.return_value = cursor
    conexao.cursor.return_value.__exit__.return_value = False
    return conexao


def test_notificar_sem_url_configurada_nao_envia(monkeypatch):
    monkeypatch.delenv("N8N_MANUTENCAO_WEBHOOK_URL", raising=False)

    with patch("services.n8n_service.requests.post") as post:
        resultado = n8n_service.notificar_manutencao(
            {"id": 1},
            "manutencao_aberta",
        )

    assert resultado is False
    post.assert_not_called()


def test_notificar_manutencao_envia_evento_e_segredo(monkeypatch):
    monkeypatch.setenv(
        "N8N_MANUTENCAO_WEBHOOK_URL",
        "http://n8n.teste/webhook/manutencao",
    )
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-teste")

    with patch("services.n8n_service.requests.post") as post:
        resultado = n8n_service.notificar_manutencao(
            {"id": 7, "status": "aberta"},
            "manutencao_aberta",
        )

    assert resultado is True
    argumentos = post.call_args
    assert argumentos.args[0] == "http://n8n.teste/webhook/manutencao"
    assert argumentos.kwargs["json"] == {
        "evento": "manutencao_aberta",
        "manutencao": {"id": 7, "status": "aberta"},
    }
    assert (
        argumentos.kwargs["headers"]["X-EloCampus-Webhook-Secret"]
        == "segredo-teste"
    )


def test_falha_http_retorna_false(monkeypatch):
    monkeypatch.setenv(
        "N8N_EQUIPAMENTO_WEBHOOK_URL",
        "http://n8n.teste/webhook/equipamento",
    )

    with patch(
        "services.n8n_service.requests.post",
        side_effect=requests.ConnectionError,
    ):
        resultado = n8n_service.notificar_equipamento(
            {"id": 1},
            "equipamento_baixado",
        )

    assert resultado is False


@pytest.mark.parametrize(
    "servico",
    [EquipamentoService, ManutencaoService, ReservaService],
)
def test_erro_na_notificacao_nao_propaga(servico):
    alvo = {
        EquipamentoService: "notificar_equipamento",
        ManutencaoService: "notificar_manutencao",
        ReservaService: "notificar_reserva",
    }[servico]

    with patch(
        f"{servico.__module__}.{alvo}",
        side_effect=RuntimeError("falha inesperada"),
    ):
        servico._notificar_com_seguranca({"id": 1}, "evento_teste")


def test_inativar_equipamento_notifica_baixa():
    servico = EquipamentoService()
    cursor = MagicMock()
    cursor.fetchone.return_value = ("disponivel",)

    with (
        patch(
            "services.equipamento_service.Conexao.conectar",
            return_value=_conexao_simulada(cursor),
        ),
        patch.object(
            servico,
            "obter_por_id",
            return_value={"id": 3, "status": "baixado"},
        ),
        patch(
            "services.equipamento_service.notificar_equipamento"
        ) as notificar,
    ):
        resultado = servico.inativar(3)

    assert resultado["status"] == "baixado"
    notificar.assert_called_once_with(
        {"id": 3, "status": "baixado"},
        "equipamento_baixado",
    )


@pytest.mark.parametrize(
    ("operacao", "status_atual", "evento"),
    [
        ("rejeitar", "pendente", "reserva_rejeitada"),
        ("cancelar", "aprovada", "reserva_cancelada"),
    ],
)
def test_alterar_status_da_reserva_notifica(
    operacao, status_atual, evento
):
    servico = ReservaService()
    cursor = MagicMock()
    cursor.fetchone.return_value = (status_atual, None, None, 9)

    with (
        patch(
            "services.reserva_service.Conexao.conectar",
            return_value=_conexao_simulada(cursor),
        ),
        patch.object(
            servico,
            "obter_por_id",
            return_value={"id": 4},
        ),
        patch("services.reserva_service.notificar_reserva") as notificar,
    ):
        servico.alterar_status(4, operacao)

    notificar.assert_called_once_with({"id": 4}, evento)
