from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import senha_provisoria
from services.auth_service import AuthService
from tests.test_rotas import _cabecalho, autenticado, cliente  # noqa: F401


def test_senha_gerada_e_legivel_e_expira_em_24h(monkeypatch):
    monkeypatch.delenv("SENHA_PROVISORIA_HORAS", raising=False)

    senha, senha_hash, expira_em = senha_provisoria.gerar()

    assert len(senha) == senha_provisoria.TAMANHO
    assert set(senha) <= set(senha_provisoria.ALFABETO)
    assert senha not in senha_hash
    restante = expira_em - datetime.now(timezone.utc)
    assert timedelta(hours=23, minutes=59) < restante <= timedelta(hours=24)


def test_validade_configuravel(monkeypatch):
    monkeypatch.setenv("SENHA_PROVISORIA_HORAS", "2")
    _, _, expira_em = senha_provisoria.gerar()

    assert expira_em - datetime.now(timezone.utc) <= timedelta(hours=2)


def test_senhas_diferentes_a_cada_geracao():
    assert len({senha_provisoria.gerar()[0] for _ in range(10)}) == 10


def test_senha_pendente_bloqueia_as_demais_rotas(cliente, autenticado):
    resposta = cliente.get("/api/equipamentos/", headers=_cabecalho(5))

    assert resposta.status_code == 403
    assert resposta.get_json()["codigo"] == "TROCA_DE_SENHA_OBRIGATORIA"


def test_senha_pendente_permite_trocar_a_senha(cliente, autenticado):
    with patch("routes.auth.AuthService.trocar_senha") as trocar:
        resposta = cliente.post(
            "/api/auth/trocar-senha",
            json={"senha_atual": "Provisoria1", "nova_senha": "minhaNova123"},
            headers=_cabecalho(5),
        )

    assert resposta.status_code == 200
    assert trocar.call_args.args[0] == 5


def test_trocar_senha_exige_login(cliente):
    assert cliente.post("/api/auth/trocar-senha", json={}).status_code == 401


def test_senha_pendente_e_visitante_na_consulta_qr(cliente, autenticado):
    with patch(
        "routes.painel.painel_service.consultar_qr",
        return_value={"equipamento": {"id": 1}, "emprestimo": None},
    ) as consultar:
        cliente.get("/api/consulta-qr/X", headers=_cabecalho(5))

    assert consultar.call_args.kwargs["incluir_emprestimo"] is False


@pytest.mark.parametrize(
    ("dados", "mensagem"),
    [
        ({"nova_senha": "12345678"}, "senha atual"),
        ({"senha_atual": "x", "nova_senha": "curta"}, "pelo menos 8"),
        ({"senha_atual": "igual12345", "nova_senha": "igual12345"}, "diferente"),
    ],
)
def test_validacoes_da_troca_de_senha(dados, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        AuthService.trocar_senha(1, dados)


def test_login_avisa_primeiro_acesso(cliente):
    with patch(
        "routes.auth.AuthService.login",
        return_value={"id": 5, "deve_trocar_senha": True},
    ):
        resposta = cliente.post(
            "/api/auth/login", json={"email": "a@b.c", "senha": "x"}
        )

    corpo = resposta.get_json()
    assert resposta.status_code == 200
    assert corpo["usuario"]["deve_trocar_senha"] is True
    assert "crie sua senha" in corpo["mensagem"]


def test_autocadastro_nunca_devolve_a_senha(cliente):
    with patch(
        "routes.auth.AuthService.cadastrar_aluno",
        return_value=({"id": 9}, False),
    ):
        resposta = cliente.post("/api/auth/cadastro-aluno", json={})

    assert resposta.status_code == 201
    assert resposta.get_json()["email_enviado"] is False
    assert "senha_provisoria" not in resposta.get_json()


@pytest.mark.parametrize(
    ("enviado", "devolve_senha"), [(True, False), (False, True)]
)
def test_admin_so_recebe_a_senha_se_o_email_falhar(
    cliente, autenticado, enviado, devolve_senha
):
    with patch(
        "routes.usuarios.usuario_service.cadastrar",
        return_value=({"id": 9}, enviado, None if enviado else "Abc123xyzQ"),
    ):
        resposta = cliente.post(
            "/api/usuarios/",
            json={"nome": "N", "email": "n@t.local"},
            headers=_cabecalho(1),
        )

    assert resposta.status_code == 201
    assert ("senha_provisoria" in resposta.get_json()) is devolve_senha


def test_envio_inclui_senha_e_validade(monkeypatch):
    monkeypatch.setenv("N8N_CADASTRO_WEBHOOK_URL", "http://n8n.teste/w")
    expira_em = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)

    with patch("services.n8n_service.requests.post") as post:
        enviado = senha_provisoria.enviar(
            {"id": 1, "nome": "Ana", "email": "a@t.local", "papel": "aluno"},
            "Abc123xyzQ",
            expira_em,
            "cadastro_aluno",
        )

    corpo = post.call_args.kwargs["json"]
    assert enviado is True
    assert corpo["evento"] == "cadastro_aluno"
    assert corpo["usuario"]["email"] == "a@t.local"
    assert corpo["senha_provisoria"] == "Abc123xyzQ"
    assert corpo["senha_expira_em"] == "2026-10-24T12:00:00+00:00"


def test_falha_no_envio_nao_interrompe(monkeypatch):
    with patch(
        "services.senha_provisoria.notificar_senha_provisoria",
        side_effect=RuntimeError("n8n fora do ar"),
    ):
        assert senha_provisoria.enviar(
            {"id": 1}, "x", datetime.now(timezone.utc), "cadastro_aluno"
        ) is False
