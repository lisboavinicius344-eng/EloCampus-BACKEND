from unittest.mock import patch

from tests.test_rotas import cliente  # noqa: F401


def test_lembretes_exigem_a_chave(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")

    assert cliente.post("/api/lembretes/processar").status_code == 401
    assert cliente.post(
        "/api/lembretes/processar", headers={"X-Monitor-Token": "outra"}
    ).status_code == 401


def test_sem_monitor_token_configurado(cliente, monkeypatch):
    monkeypatch.delenv("MONITOR_TOKEN", raising=False)

    resposta = cliente.post(
        "/api/lembretes/processar", headers={"X-Monitor-Token": "x"}
    )

    assert resposta.status_code == 503


def test_processa_e_simula(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")
    cabecalho = {"X-Monitor-Token": "chave-secreta"}

    with patch(
        "routes.lembretes.LembreteService.processar",
        return_value=[{"tipo": "atraso"}],
    ) as processar:
        normal = cliente.post("/api/lembretes/processar", headers=cabecalho)
        simulado = cliente.post(
            "/api/lembretes/processar?simular=true", headers=cabecalho
        )

    assert normal.get_json() == {
        "total": 1, "simulacao": False, "lembretes": [{"tipo": "atraso"}]
    }
    assert simulado.get_json()["simulacao"] is True
    assert [c.kwargs["simular"] for c in processar.call_args_list] == [
        False, True
    ]


def test_copia_do_atraso_nao_vai_para_admin():
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from services.lembrete_service import LembreteService

    prevista = datetime.now(timezone.utc) - timedelta(days=1)
    cursor = MagicMock()
    cursor.fetchone.return_value = (5, prevista, "Ana Lima", "ana@t.local", "Bia", "bia@t.local")
    cursor.fetchall.return_value = [("Notebook", "NB-1")]

    como_operadora = LembreteService._montar(cursor, 5, "atraso")
    como_admin = LembreteService._montar(cursor, 5, "atraso", ["bia@t.local"])

    assert como_operadora["copia"] == "bia@t.local"
    assert como_admin["copia"] is None
    assert como_admin["destinatarios"] == "ana@t.local"
