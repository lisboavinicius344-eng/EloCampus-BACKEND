"""Admin master, zerar dados, cobrança e justificativa das solicitações."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import administracao_service
from services.auth_token import eh_master
from services.cobranca_service import CobrancaService, EnvioIndisponivel
from services.solicitacao_acesso_service import SolicitacaoAcessoService
from tests.test_rotas import _cabecalho, autenticado, cliente, uid  # noqa: F401


def test_master_e_admin_com_email_na_lista(monkeypatch):
    monkeypatch.setenv("ADMIN_MASTER_EMAILS", "Chefe@Escola.br, outro@x.br")

    assert eh_master("admin", " chefe@escola.br ")
    assert not eh_master("operador", "chefe@escola.br")
    assert not eh_master("admin", "admin@escola.br")


def test_sem_variavel_ninguem_e_master(monkeypatch):
    monkeypatch.delenv("ADMIN_MASTER_EMAILS", raising=False)
    assert not eh_master("admin", "admin@teste.local")


def test_zerar_dados_so_para_o_master(cliente, autenticado, monkeypatch):
    monkeypatch.delenv("ADMIN_MASTER_EMAILS", raising=False)
    assert cliente.post("/api/administracao/zerar-dados", json={}, headers=_cabecalho(1)).status_code == 403
    assert cliente.post("/api/administracao/zerar-dados", json={}).status_code == 401

    monkeypatch.setenv("ADMIN_MASTER_EMAILS", "admin@teste.local")
    resposta = cliente.post("/api/administracao/zerar-dados", json={"confirmacao": "sim"}, headers=_cabecalho(1))
    assert resposta.status_code == 400
    assert "ZERAR DADOS" in resposta.get_json()["erro"]

    with patch("routes.administracao.administracao_service.zerar_dados", return_value={"equipamentos": 3}) as zerar:
        resposta = cliente.post("/api/administracao/zerar-dados", json={"confirmacao": "ZERAR DADOS"}, headers=_cabecalho(1))
    assert resposta.status_code == 200
    assert resposta.get_json()["apagados"] == {"equipamentos": 3}
    assert zerar.call_args.args[0] == "ZERAR DADOS"


def test_confirmacao_errada_nao_toca_no_banco():
    with patch("services.administracao_service.Conexao.conectar") as conectar:
        with pytest.raises(ValueError):
            administracao_service.zerar_dados("zerar", {"nome": "A", "email": "a@b"})
    assert not conectar.called


def test_admin_comum_nao_mexe_na_conta_master(cliente, autenticado, monkeypatch):
    monkeypatch.delenv("ADMIN_MASTER_EMAILS", raising=False)
    master = {"id": uid(9), "master": True}

    with patch("routes.usuarios.usuario_service.obter_por_id", return_value=master):
        assert cliente.patch(f"/api/usuarios/{uid(9)}/desativar", headers=_cabecalho(1)).status_code == 403
        assert cliente.patch(f"/api/usuarios/{uid(9)}/reenviar-senha", headers=_cabecalho(1)).status_code == 403


@pytest.mark.parametrize(
    ("efeito", "codigo"),
    [
        ({"return_value": None}, 404),
        ({"side_effect": ValueError("sem e-mail")}, 400),
        ({"side_effect": EnvioIndisponivel("fora do ar")}, 503),
        ({"return_value": {"para": "a@b.c", "assunto": "X"}}, 200),
    ],
)
def test_rota_de_cobranca(cliente, autenticado, efeito, codigo):
    with patch("routes.emprestimos.CobrancaService.cobrar", **efeito):
        resposta = cliente.post("/api/emprestimos/5/cobrar", headers=_cabecalho(2))

    assert resposta.status_code == codigo


def test_aluno_nao_cobra(cliente, autenticado):
    assert cliente.post("/api/emprestimos/5/cobrar", headers=_cabecalho(3)).status_code == 403


def test_texto_da_cobranca():
    agora = datetime.now(timezone.utc)
    itens = [(1, "Notebook", "NB-1"), (2, "Mouse", None)]

    atrasada = CobrancaService._mensagem("<b>Ana</b> Lima", "a@b.c", agora - timedelta(days=2, hours=1), itens, agora)
    no_prazo = CobrancaService._mensagem("Ana Lima", "a@b.c", agora + timedelta(days=1), itens, agora)

    assert atrasada["assunto"] == "ELO Campus - cobrança: devolução atrasada (há 2 dias)"
    assert "Notebook (NB-1), Mouse" in atrasada["mensagem_html"]
    assert "&lt;b&gt;Ana&lt;/b&gt;" in atrasada["mensagem_html"] and "<b>Ana" not in atrasada["mensagem_html"]
    assert "lembrete da equipe" in no_prazo["assunto"]
    assert atrasada["destinatarios"] == "a@b.c"


def test_recusa_exige_motivo():
    with pytest.raises(ValueError, match="motivo da recusa"):
        SolicitacaoAcessoService().recusar(uid(7), {}, uid(1))


def test_justificativa_da_aprovacao_tem_limite():
    with pytest.raises(ValueError, match="500"):
        SolicitacaoAcessoService().aprovar(uid(7), {"justificativa": "x" * 501}, uid(1))
