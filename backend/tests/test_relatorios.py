from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from services import relatorio_service
from services.relatorio_service import FUSO, periodo, periodo_semanal
from tests.test_rotas import _cabecalho, autenticado, cliente  # noqa: F401


HOJE = datetime.now(FUSO).date()


@pytest.mark.parametrize(
    "rota",
    [
        "/api/relatorios/resumo",
        "/api/relatorios/atrasados",
        "/api/relatorios/mais-emprestados",
        "/api/relatorios/manutencoes",
    ],
)
def test_relatorios_sao_da_equipe(cliente, autenticado, rota):
    assert cliente.get(rota).status_code == 401
    assert cliente.get(rota, headers=_cabecalho(3)).status_code == 403
    assert cliente.get(rota, headers=_cabecalho(4)).status_code == 403


def test_periodo_padrao_tem_7_dias_contando_hoje():
    assert periodo() == (HOJE - timedelta(days=6), HOJE)


def test_periodo_informado():
    assert periodo("2026-10-01", "2026-10-31") == (
        date(2026, 10, 1), date(2026, 10, 31)
    )


@pytest.mark.parametrize(
    ("inicio", "fim", "mensagem"),
    [
        ("01/10/2026", "2026-10-31", "AAAA-MM-DD"),
        ("2026-10-31", "2026-10-01", "igual ou posterior"),
        ("2024-01-01", "2026-01-01", "366"),
    ],
)
def test_periodo_invalido(inicio, fim, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        periodo(inicio, fim)


def test_rota_recusa_periodo_invalido(cliente, autenticado):
    resposta = cliente.get(
        "/api/relatorios/resumo?inicio=ontem", headers=_cabecalho(1)
    )

    assert resposta.status_code == 400
    assert "AAAA-MM-DD" in resposta.get_json()["erro"]


def test_semanal_nao_conta_hoje():
    primeiro, ultimo = periodo_semanal()

    assert ultimo == HOJE - timedelta(days=1)
    assert (ultimo - primeiro).days == 6


@pytest.mark.parametrize(
    ("valor", "esperado"), [(None, 10), ("", 10), ("5", 5), ("100", 100)]
)
def test_limite_valido(valor, esperado):
    assert relatorio_service.limite(valor) == esperado


@pytest.mark.parametrize("valor", ["0", "101", "abc"])
def test_limite_invalido(valor):
    with pytest.raises(ValueError):
        relatorio_service.limite(valor)


def test_semanal_exige_a_chave(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")

    assert cliente.get("/api/relatorios/semanal").status_code == 401
    assert cliente.get(
        "/api/relatorios/semanal", headers={"X-Monitor-Token": "outra"}
    ).status_code == 401


def test_semanal_sem_monitor_token_configurado(cliente, monkeypatch):
    monkeypatch.delenv("MONITOR_TOKEN", raising=False)

    assert cliente.get("/api/relatorios/semanal").status_code == 503


def test_semanal_com_a_chave(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")

    with patch(
        "routes.relatorios.relatorios.semanal",
        return_value={"assunto": "x", "mensagem_html": "<div></div>"},
    ):
        resposta = cliente.get(
            "/api/relatorios/semanal",
            headers={"X-Monitor-Token": "chave-secreta"},
        )

    assert resposta.status_code == 200
    assert resposta.get_json()["assunto"] == "x"


def test_historico_filtra_por_equipamento(cliente, autenticado):
    with patch(
        "routes.historico.historico_service.listar", return_value=[]
    ) as listar:
        resposta = cliente.get(
            "/api/historico?equipamento_id=7", headers=_cabecalho(2)
        )

    assert resposta.status_code == 200
    listar.assert_called_once_with(7)


@pytest.mark.parametrize("valor", ["abc", "0", "-1"])
def test_historico_recusa_filtro_invalido(cliente, autenticado, valor):
    resposta = cliente.get(
        f"/api/historico?equipamento_id={valor}", headers=_cabecalho(2)
    )

    assert resposta.status_code == 400
