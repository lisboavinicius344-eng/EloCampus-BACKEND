from unittest.mock import patch

import pytest

from services import monitor_service
from tests.test_rotas import cliente  # noqa: F401


OK = {"ok": True, "ms": 1}
FALHOU = {"ok": False, "ms": 1, "detalhe": "OperationalError: sem conexão"}


def _verificacoes(**trocas):
    base = {"api": OK, "banco": OK, "tabelas": {"ok": True, "falhas": {}},
            "configuracao": OK, "n8n": OK}
    base.update(trocas)
    return base


@pytest.mark.parametrize(
    ("status", "http"), [("ok", 200), ("degradado", 200), ("falha", 503)]
)
def test_codigo_http_segue_o_status(cliente, status, http):
    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=(status, _verificacoes()),
    ):
        resposta = cliente.get("/api/monitor")

    assert resposta.status_code == http
    assert resposta.get_json()["status"] == status
    assert resposta.headers["Cache-Control"] == "no-store"


def test_detalhes_so_com_a_chave(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")

    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=("falha", _verificacoes(banco=FALHOU)),
    ):
        sem_chave = cliente.get("/api/monitor").get_json()
        chave_errada = cliente.get(
            "/api/monitor", headers={"X-Monitor-Token": "outra"}
        ).get_json()
        cabecalho = cliente.get(
            "/api/monitor", headers={"X-Monitor-Token": "chave-secreta"}
        ).get_json()
        parametro = cliente.get("/api/monitor?token=chave-secreta").get_json()

    assert "verificacoes" not in sem_chave
    assert "verificacoes" not in chave_errada
    assert cabecalho["verificacoes"]["banco"]["detalhe"].startswith("Operational")
    assert "verificacoes" in parametro


def test_sem_monitor_token_configurado_nunca_mostra_detalhes(
    cliente, monkeypatch
):
    monkeypatch.delenv("MONITOR_TOKEN", raising=False)

    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=("ok", _verificacoes()),
    ):
        resposta = cliente.get("/api/monitor?token=")

    assert "verificacoes" not in resposta.get_json()


@pytest.mark.parametrize(
    ("falhas", "esperado"),
    [
        ({}, "ok"),
        ({"_n8n": RuntimeError("fora do ar")}, "degradado"),
        ({"_configuracao": RuntimeError("faltou")}, "falha"),
        ({"_banco_e_tabelas": OSError("sem banco")}, "falha"),
    ],
)
def test_status_geral(monkeypatch, falhas, esperado):
    monkeypatch.setattr(monitor_service, "_banco_e_tabelas", lambda: {
        t: {"ok": True, "ms": 1} for t in monitor_service.TABELAS
    })
    monkeypatch.setattr(monitor_service, "_configuracao", lambda: None)
    monkeypatch.setattr(monitor_service, "_n8n", lambda: None)

    for nome, erro in falhas.items():
        def falhar(erro=erro):
            raise erro
        monkeypatch.setattr(monitor_service, nome, falhar)

    status, verificacoes = monitor_service.verificar()

    assert status == esperado
    assert set(verificacoes) == {"api", "banco", "tabelas", "configuracao", "n8n"}


def test_tabela_com_problema_derruba_o_status(monkeypatch):
    tabelas = {t: {"ok": True, "ms": 1} for t in monitor_service.TABELAS}
    tabelas["reservas"] = {"ok": False, "ms": 1, "detalhe": "UndefinedTable"}
    monkeypatch.setattr(monitor_service, "_banco_e_tabelas", lambda: tabelas)
    monkeypatch.setattr(monitor_service, "_configuracao", lambda: None)
    monkeypatch.setattr(monitor_service, "_n8n", lambda: None)

    status, verificacoes = monitor_service.verificar()

    assert status == "falha"
    assert verificacoes["tabelas"]["falhas"] == {"reservas": "UndefinedTable"}


@pytest.mark.parametrize(
    ("status", "trocas", "detalhado", "esperado"),
    [
        ("ok", {}, True, "SISTEMA OK"),
        ("falha", {"banco": FALHOU,
                   "tabelas": {"ok": False, "falhas": {}}}, True,
         "FALHA: banco (OperationalError)"),
        ("falha", {"banco": FALHOU,
                   "tabelas": {"ok": False, "falhas": {}}}, False,
         "FALHA: banco"),
        ("falha", {"tabelas": {"ok": False,
                               "falhas": {"reservas": "x", "categorias": "y"}}},
         True, "FALHA: tabela categorias, reservas"),
        ("degradado", {"n8n": {"ok": False, "ms": 1,
                               "detalhe": "ConnectionError: recusada"}}, True,
         "DEGRADADO: n8n (ConnectionError)"),
        ("falha", {"configuracao": {"ok": False, "ms": 0,
                                    "detalhe": "RuntimeError: faltou"},
                   "n8n": {"ok": False, "ms": 1, "detalhe": "Timeout: x"}},
         True, "FALHA: configuracao (RuntimeError) | n8n (Timeout)"),
    ],
)
def test_resumo_diz_o_que_falhou(status, trocas, detalhado, esperado):
    texto = monitor_service.resumo(status, _verificacoes(**trocas), detalhado)

    assert texto == esperado
    # A palavra-chave do Uptime Kuma nunca aparece numa falha.
    assert ("SISTEMA OK" in texto) == (status == "ok")


def test_formato_texto(cliente, monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", "chave-secreta")
    falha = _verificacoes(banco=FALHOU, tabelas={"ok": False, "falhas": {}})

    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=("falha", falha),
    ):
        publico = cliente.get("/api/monitor?formato=texto")
        com_chave = cliente.get(
            "/api/monitor?formato=texto",
            headers={"X-Monitor-Token": "chave-secreta"},
        )

    assert publico.status_code == 503
    assert publico.mimetype == "text/plain"
    assert publico.get_data(as_text=True) == "FALHA: banco"
    assert com_chave.get_data(as_text=True) == "FALHA: banco (OperationalError)"


def test_json_traz_o_resumo(cliente):
    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=("ok", _verificacoes()),
    ):
        corpo = cliente.get("/api/monitor").get_json()

    assert corpo["resumo"] == "SISTEMA OK"


def test_monitor_por_parte(cliente):
    with patch(
        "routes.monitor.monitor_service.verificar",
        return_value=("falha", _verificacoes(n8n=FALHOU)),
    ) as verificar:
        resposta = cliente.get("/api/monitor/n8n")

    assert verificar.call_args.args == ("n8n",)
    assert resposta.status_code == 503
    assert resposta.get_json()["parte"] == "n8n"
    assert cliente.get("/api/monitor/qualquer").status_code == 404


@pytest.mark.parametrize("parte", ["banco", "tabelas", "configuracao", "n8n"])
def test_parte_isolada_so_confere_ela(monkeypatch, parte):
    chamadas = []
    monkeypatch.setattr(monitor_service, "_banco_e_tabelas",
                        lambda: chamadas.append("banco") or {})
    monkeypatch.setattr(monitor_service, "_configuracao",
                        lambda: chamadas.append("configuracao"))

    def n8n_fora():
        chamadas.append("n8n")
        raise RuntimeError("fora do ar")

    monkeypatch.setattr(monitor_service, "_n8n", n8n_fora)

    status, verificacoes = monitor_service.verificar(parte)

    esperado = {"banco": ["banco"], "tabelas": ["banco"],
                "configuracao": ["configuracao"], "n8n": ["n8n"]}[parte]
    assert chamadas == esperado
    # Monitor só do n8n: o n8n fora é falha (503), não "degradado".
    assert status == ("falha" if parte == "n8n" else "ok")
