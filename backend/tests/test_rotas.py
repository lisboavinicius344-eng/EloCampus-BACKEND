from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import app
from services.auth_token import gerar_token
from services.emprestimo_service import EmprestimoService
from services.usuario_service import UsuarioService


USUARIOS = {
    1: (1, "Admin", "admin@teste.local", "admin", True, None),
    2: (2, "Operador", "operador@teste.local", "operador", True, None),
    3: (3, "Aluno", "aluno@teste.local", "aluno", True, 30),
    4: (4, "Professor", "prof@teste.local", "professor", True, 40),
}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "chave-de-teste")
    return app.test_client()


@pytest.fixture
def autenticado():
    """Simula a consulta do usuário do token no banco."""
    cursor = MagicMock()
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor

    def consultar(_sql, parametros):
        cursor.fetchone.return_value = USUARIOS.get(parametros[0])

    cursor.execute.side_effect = consultar

    with patch(
        "services.auth_token.Conexao.conectar",
        return_value=conexao,
    ):
        yield


def _cabecalho(usuario_id):
    return {"Authorization": f"Bearer {gerar_token(usuario_id)}"}


@pytest.mark.parametrize(
    ("metodo", "rota"),
    [
        ("get", "/api/manutencoes/"),
        ("post", "/api/manutencoes/"),
        ("patch", "/api/manutencoes/1/finalizar"),
        ("get", "/api/historico/"),
        ("post", "/api/historico/"),
        ("get", "/api/usuarios/"),
    ],
)
def test_rotas_restritas_exigem_login(cliente, metodo, rota):
    resposta = getattr(cliente, metodo)(rota, json={})

    assert resposta.status_code == 401


@pytest.mark.parametrize(
    ("metodo", "rota"),
    [
        ("post", "/api/emprestimos/"),
        ("get", "/api/manutencoes/"),
        ("get", "/api/historico/"),
        ("get", "/api/solicitantes/"),
        ("get", "/api/solicitantes/99"),
        ("get", "/api/usuarios/"),
    ],
)
def test_aluno_nao_acessa_rotas_da_equipe(
    cliente, autenticado, metodo, rota
):
    resposta = getattr(cliente, metodo)(
        rota, json={}, headers=_cabecalho(3)
    )

    assert resposta.status_code == 403


def test_professor_tem_as_mesmas_restricoes_do_aluno(cliente, autenticado):
    for metodo, rota in [
        ("post", "/api/emprestimos/"),
        ("get", "/api/solicitantes/"),
        ("get", "/api/solicitantes/30"),
        ("get", "/api/manutencoes/"),
    ]:
        resposta = getattr(cliente, metodo)(
            rota, json={}, headers=_cabecalho(4)
        )
        assert resposta.status_code == 403, rota


def test_operador_nao_gerencia_usuarios(cliente, autenticado):
    resposta = cliente.get("/api/usuarios/", headers=_cabecalho(2))

    assert resposta.status_code == 403


def test_aluno_consulta_o_proprio_solicitante(cliente, autenticado):
    with patch(
        "routes.solicitantes.solicitante_service.obter_por_id",
        return_value={"id": 30},
    ):
        resposta = cliente.get(
            "/api/solicitantes/30", headers=_cabecalho(3)
        )

    assert resposta.status_code == 200


def test_responsavel_do_emprestimo_vem_do_token(cliente, autenticado):
    with patch(
        "routes.emprestimos.emprestimo_service.cadastrar",
        return_value={"id": 1},
    ) as cadastrar:
        resposta = cliente.post(
            "/api/emprestimos/",
            json={"usuario_responsavel_id": 1, "solicitante_id": 30},
            headers=_cabecalho(2),
        )

    assert resposta.status_code == 201
    assert cadastrar.call_args.args[0]["usuario_responsavel_id"] == 2


def test_cors_libera_o_frontend(cliente):
    resposta = cliente.options(
        "/api/equipamentos",
        headers={
            "Origin": "https://elocampus.com.br",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert resposta.status_code == 200
    assert (
        resposta.headers["Access-Control-Allow-Origin"]
        == "https://elocampus.com.br"
    )
    assert "Authorization" in resposta.headers[
        "Access-Control-Allow-Headers"
    ]


def test_cors_bloqueia_outras_origens(cliente):
    resposta = cliente.options(
        "/api/equipamentos/",
        headers={"Origin": "https://site-qualquer.com"},
    )

    assert "Access-Control-Allow-Origin" not in resposta.headers


def test_rota_inexistente_responde_json(cliente):
    resposta = cliente.get("/api/nao-existe")

    assert resposta.status_code == 404
    assert resposta.get_json() == {"erro": "Rota não encontrada."}


def test_erro_inesperado_responde_json(cliente, autenticado):
    with patch(
        "routes.equipamentos.equipamento_service.listar",
        side_effect=RuntimeError("falha no banco"),
    ):
        resposta = cliente.get(
            "/api/equipamentos/", headers=_cabecalho(1)
        )

    assert resposta.status_code == 500
    assert "erro" in resposta.get_json()
    assert "falha no banco" not in resposta.get_data(as_text=True)


def test_emprestimo_recusa_devolucao_no_passado():
    ontem = datetime.now(timezone.utc) - timedelta(days=1)

    with pytest.raises(ValueError, match="no futuro"):
        EmprestimoService().cadastrar({
            "equipamentos": [1],
            "solicitante_id": 30,
            "usuario_responsavel_id": 2,
            "data_prevista_devolucao": ontem.isoformat(),
        })


def test_usuario_nao_desativa_a_propria_conta():
    with pytest.raises(ValueError, match="própria conta"):
        UsuarioService().desativar(1, usuario_logado_id=1)


def test_cadastro_de_usuario_recusa_papel_aluno():
    with pytest.raises(ValueError, match="admin ou operador"):
        UsuarioService().cadastrar({
            "nome": "X",
            "email": "x@teste.local",
            "senha": "12345678",
            "papel": "aluno",
        })


def test_dashboard_resumo_exige_login(cliente):
    assert cliente.get("/api/dashboard/resumo").status_code == 401


@pytest.mark.parametrize(
    ("usuario_id", "inclui_emprestimo"),
    [(None, False), (3, False), (2, True), (1, True)],
)
def test_consulta_qr_so_mostra_emprestimo_para_equipe(
    cliente, autenticado, usuario_id, inclui_emprestimo
):
    cabecalho = _cabecalho(usuario_id) if usuario_id else {}

    with patch(
        "routes.painel.painel_service.consultar_qr",
        return_value={"equipamento": {"id": 1}, "emprestimo": None},
    ) as consultar:
        resposta = cliente.get("/api/consulta-qr/PAT-1", headers=cabecalho)

    assert resposta.status_code == 200
    assert consultar.call_args.kwargs["incluir_emprestimo"] is inclui_emprestimo


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("  PAT-001 ", "PAT-001"),
        ("https://elocampus.com.br/pages/consulta-qr.html?codigo=PAT-9", "PAT-9"),
        ("https://elocampus.com.br/equipamentos/PAT-7", "PAT-7"),
        ("https://x.com/?id=15", "15"),
    ],
)
def test_extrai_codigo_do_qr(codigo, esperado):
    from services.painel_service import PainelService

    assert PainelService._extrair_codigo(codigo) == esperado


@pytest.mark.parametrize(
    ("tipo", "permitido"),
    [
        ("aluno", False),
        ("externo", False),
        ("professor", True),
        ("servidor", True),
        ("tecnico", True),
    ],
)
def test_elegibilidade_de_equipamento_restrito(tipo, permitido):
    from services.elegibilidade import verificar_elegibilidade

    cursor = MagicMock()
    cursor.fetchall.return_value = [(7,)]

    if permitido:
        verificar_elegibilidade(cursor, tipo, [7])
    else:
        with pytest.raises(ValueError, match="somente para professores"):
            verificar_elegibilidade(cursor, tipo, [7])


RESERVA_APROVADA = {
    "id": 8,
    "solicitante_id": 30,
    "data_fim": "2026-12-01T17:00:00+00:00",
    "observacoes": "TCC",
    "itens": [{"equipamento_id": 2}, {"equipamento_id": 5}],
}


def test_retirada_usa_os_dados_da_reserva(cliente, autenticado):
    with (
        patch(
            "routes.reservas.reserva_service.obter_por_id",
            return_value=RESERVA_APROVADA,
        ),
        patch(
            "routes.reservas.emprestimo_service.cadastrar",
            return_value={"id": 1},
        ) as cadastrar,
    ):
        resposta = cliente.post(
            "/api/reservas/8/retirar", headers=_cabecalho(2)
        )

    assert resposta.status_code == 201
    dados = cadastrar.call_args.args[0]
    assert cadastrar.call_args.kwargs["reserva_id"] == 8
    assert dados["solicitante_id"] == 30
    assert dados["equipamentos"] == [2, 5]
    assert dados["data_prevista_devolucao"] == RESERVA_APROVADA["data_fim"]
    assert dados["usuario_responsavel_id"] == 2


def test_retirada_aceita_outra_data_de_devolucao(cliente, autenticado):
    with (
        patch(
            "routes.reservas.reserva_service.obter_por_id",
            return_value=RESERVA_APROVADA,
        ),
        patch(
            "routes.reservas.emprestimo_service.cadastrar",
            return_value={"id": 1},
        ) as cadastrar,
    ):
        cliente.post(
            "/api/reservas/8/retirar",
            json={"data_prevista_devolucao": "2026-12-05T17:00:00+00:00"},
            headers=_cabecalho(1),
        )

    assert (
        cadastrar.call_args.args[0]["data_prevista_devolucao"]
        == "2026-12-05T17:00:00+00:00"
    )


@pytest.mark.parametrize("usuario_id", [3, 4])
def test_usuario_final_nao_registra_retirada(cliente, autenticado, usuario_id):
    resposta = cliente.post(
        "/api/reservas/8/retirar", headers=_cabecalho(usuario_id)
    )

    assert resposta.status_code == 403


def test_retirada_de_reserva_inexistente(cliente, autenticado):
    with patch(
        "routes.reservas.reserva_service.obter_por_id",
        return_value=None,
    ):
        resposta = cliente.post(
            "/api/reservas/99/retirar", headers=_cabecalho(2)
        )

    assert resposta.status_code == 404


@pytest.mark.parametrize(
    ("reserva", "itens_reservados", "mensagem"),
    [
        (None, [], "não encontrada"),
        (("pendente", 30), [(2,)], "aprovada"),
        (("aprovada", 99), [(2,)], "solicitante"),
        (("aprovada", 30), [(2,), (7,)], "equipamentos"),
    ],
)
def test_validacao_da_reserva_na_retirada(reserva, itens_reservados, mensagem):
    cursor = MagicMock()
    cursor.fetchone.return_value = reserva
    cursor.fetchall.return_value = itens_reservados

    with pytest.raises(ValueError, match=mensagem):
        EmprestimoService._validar_reserva(cursor, 8, 30, [2])
