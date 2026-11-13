from unittest.mock import patch

import pytest

from services import qr_equipamento
from tests.test_rotas import cliente  # noqa: F401

EQUIPAMENTO = {"id": 7, "nome": "Projetor", "numero_patrimonio": "PRJ-0017", "qr_code": None}


@pytest.mark.parametrize(
    ("dados", "esperado"),
    [
        ({"id": 7, "qr_code": "QR-7", "numero_patrimonio": "PRJ-0017"}, "QR-7"),
        ({"id": 7, "qr_code": " ", "numero_patrimonio": "PRJ-0017"}, "PRJ-0017"),
        ({"id": 7, "qr_code": None, "numero_patrimonio": None}, "7"),
    ],
)
def test_codigo_da_etiqueta(dados, esperado):
    assert qr_equipamento.codigo(dados) == esperado


def test_url_curta_com_o_id_no_site_da_consulta(monkeypatch):
    monkeypatch.delenv("QR_ITEM_URL", raising=False)
    monkeypatch.setenv("QR_CONSULTA_URL", "https://elocampus.com.br/pages/consulta-qr.html")
    url = qr_equipamento.conteudo({"id": 1, "numero_patrimonio": "LAB 01/A", "qr_code": None})

    assert url == "https://elocampus.com.br/q/1"


def test_url_propria_do_item(monkeypatch):
    monkeypatch.setenv("QR_ITEM_URL", "https://elo.ufob.edu.br/q/")

    assert qr_equipamento.conteudo(EQUIPAMENTO) == "https://elo.ufob.edu.br/q/7"


def test_url_padrao(monkeypatch):
    monkeypatch.delenv("QR_ITEM_URL", raising=False)
    monkeypatch.delenv("QR_CONSULTA_URL", raising=False)

    assert qr_equipamento.conteudo(EQUIPAMENTO) == "https://elocampus-frontend.a6ti6s.easypanel.host/q/7"


def test_qr_lido_de_volta_aponta_para_o_id():
    from services.painel_service import PainelService

    assert PainelService._extrair_codigo(qr_equipamento.conteudo(EQUIPAMENTO)) == ("7", True)


def test_qr_curto_fica_pequeno(monkeypatch):
    """Endereço curto cabe na versão 3 do QR (29 módulos): legível com 2,5 cm."""
    import qrcode

    monkeypatch.setenv("QR_CONSULTA_URL", "https://elocampus.com.br/pages/consulta-qr.html")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_equipamento.conteudo({"id": 99999}))
    qr.make(fit=True)

    assert qr.version <= 3


@pytest.mark.parametrize(("formato", "tipo", "inicio"), [("svg", "image/svg+xml", b"<svg"), ("png", "image/png", b"\x89PNG")])
def test_rota_publica_devolve_a_imagem(cliente, formato, tipo, inicio):
    with patch("routes.equipamentos.equipamento_service.obter_por_id", return_value=EQUIPAMENTO):
        resposta = cliente.get(f"/api/equipamentos/7/qrcode?formato={formato}")

    assert resposta.status_code == 200
    assert resposta.mimetype == tipo
    assert resposta.data.startswith(inicio)
    assert "inline" in resposta.headers["Content-Disposition"]


def test_rota_para_baixar(cliente):
    with patch("routes.equipamentos.equipamento_service.obter_por_id", return_value=EQUIPAMENTO):
        resposta = cliente.get("/api/equipamentos/7/qrcode?baixar=1")

    assert resposta.headers["Content-Disposition"] == 'attachment; filename="qrcode-PRJ-0017.svg"'


def test_rota_erros(cliente):
    assert cliente.get("/api/equipamentos/7/qrcode?formato=gif").status_code == 400
    with patch("routes.equipamentos.equipamento_service.obter_por_id", return_value=None):
        assert cliente.get("/api/equipamentos/7/qrcode").status_code == 404
