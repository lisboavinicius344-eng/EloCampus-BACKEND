"""Correções da revisão: tentativas, reenvio de senha e responsáveis."""
from unittest.mock import patch

import pytest

from services import limite_tentativas
from tests.test_rotas import _cabecalho, autenticado, cliente, uid  # noqa: F401


def test_limite_libera_depois_da_janela(monkeypatch):
    relogio = [1000.0]
    monkeypatch.setattr(limite_tentativas.time, "monotonic", lambda: relogio[0])
    limite = limite_tentativas.Limite(2, 60)

    limite.registrar("x")
    limite.registrar("x")
    assert limite.espera("x") > 0

    relogio[0] += 61
    assert limite.espera("x") == 0


def _login(cliente, email="ana@x.com", ip="10.0.0.1"):
    return cliente.post(
        "/api/auth/login",
        json={"email": email, "senha": "errada"},
        headers={"X-Forwarded-For": ip},
    )


def test_login_bloqueia_a_conta_depois_de_5_erros(cliente):
    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        codigos = [_login(cliente).status_code for _ in range(6)]
        outra_conta = _login(cliente, email="rui@x.com").status_code

    assert codigos == [401] * 5 + [429]
    assert outra_conta == 401  # o bloqueio é da conta, não de todos


def test_bloqueio_informa_quanto_esperar(cliente):
    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        for _ in range(5):
            _login(cliente)
        resposta = _login(cliente)

    assert resposta.status_code == 429
    assert int(resposta.headers["Retry-After"]) > 0
    assert "Aguarde" in resposta.get_json()["erro"]


def test_login_bloqueia_o_endereco_que_testa_muitas_contas(cliente):
    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        codigos = [
            _login(cliente, email=f"conta{i}@x.com").status_code
            for i in range(21)
        ]
        outro_endereco = _login(
            cliente, email="nova@x.com", ip="10.0.0.2"
        ).status_code

    assert codigos[-1] == 429 and codigos[:20] == [401] * 20
    assert outro_endereco == 401


def test_login_certo_zera_os_erros_da_conta(cliente):
    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        for _ in range(4):
            _login(cliente)

    with patch("routes.auth.AuthService.login", return_value={
        "id": uid(3), "deve_trocar_senha": False,
    }):
        assert _login(cliente).status_code == 200

    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        assert [_login(cliente).status_code for _ in range(5)] == [401] * 5


def test_ip_vem_do_ultimo_valor_do_proxy(cliente):
    # O começo do X-Forwarded-For pode ser forjado pelo cliente; o
    # proxy acrescenta o endereço real no fim.
    with patch("routes.auth.AuthService.login",
               side_effect=ValueError("E-mail ou senha inválidos.")):
        for i in range(20):
            _login(cliente, email=f"c{i}@x.com", ip=f"1.1.1.{i}, 10.0.0.9")
        resposta = _login(cliente, email="z@x.com", ip="9.9.9.9, 10.0.0.9")

    assert resposta.status_code == 429


@pytest.mark.parametrize(
    ("rota", "servico", "limite"),
    [
        ("/api/auth/esqueci-senha", "routes.auth.AuthService.esqueci_senha", 10),
        ("/api/auth/solicitar-acesso",
         "routes.auth.SolicitacaoAcessoService.solicitar", 5),
    ],
)
def test_formularios_publicos_tem_limite(cliente, rota, servico, limite):
    with patch(servico, return_value=True):
        codigos = [
            cliente.post(rota, json={"email": "a@b.c", "nome": "A"},
                         headers={"X-Forwarded-For": "10.0.0.5"}).status_code
            for _ in range(limite + 1)
        ]

    assert codigos == [200] * limite + [429]


def test_erro_de_digitacao_nao_gasta_tentativa(cliente):
    with patch("routes.auth.SolicitacaoAcessoService.solicitar",
               side_effect=ValueError("Informe um e-mail válido.")):
        for _ in range(8):
            cliente.post("/api/auth/solicitar-acesso", json={},
                         headers={"X-Forwarded-For": "10.0.0.6"})

    with patch("routes.auth.SolicitacaoAcessoService.solicitar",
               return_value=True):
        resposta = cliente.post(
            "/api/auth/solicitar-acesso", json={"nome": "A", "email": "a@b.c"},
            headers={"X-Forwarded-For": "10.0.0.6"},
        )

    assert resposta.status_code == 200


def test_admin_nao_reenvia_a_propria_senha(cliente, autenticado):
    with patch("routes.usuarios.usuario_service.reenviar_senha") as reenviar:
        resposta = cliente.patch(
            f"/api/usuarios/{uid(1)}/reenviar-senha", headers=_cabecalho(1)
        )

    assert resposta.status_code == 400
    assert "Esqueci minha senha" in resposta.get_json()["erro"]
    assert not reenviar.called


def test_historico_manual_e_de_quem_esta_logado(cliente, autenticado):
    with patch("routes.historico.historico_service.cadastrar",
               return_value={"id": 1}) as cadastrar:
        cliente.post(
            "/api/historico/",
            json={"equipamento_id": 1, "tipo_movimentacao": "x",
                  "usuario_id": uid(1)},
            headers=_cabecalho(2),
        )

    assert cadastrar.call_args.args[0]["usuario_id"] == uid(2)


def test_manutencao_e_de_quem_esta_logado(cliente, autenticado):
    with patch("routes.manutencoes.manutencao_service.cadastrar",
               return_value={"id": 1}) as cadastrar:
        cliente.post(
            "/api/manutencoes/",
            json={"equipamento_id": 1, "descricao_problema": "x",
                  "usuario_responsavel_id": uid(1)},
            headers=_cabecalho(2),
        )

    assert cadastrar.call_args.args[0]["usuario_responsavel_id"] == uid(2)


def test_reserva_da_equipe_e_de_quem_esta_logado(cliente, autenticado):
    with patch("routes.reservas.reserva_service.cadastrar",
               return_value={"id": 1}) as cadastrar:
        cliente.post(
            "/api/reservas/",
            json={"solicitante_id": "30", "usuario_responsavel_id": uid(1)},
            headers=_cabecalho(2),
        )

    assert cadastrar.call_args.args[0]["usuario_responsavel_id"] == uid(2)
