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
