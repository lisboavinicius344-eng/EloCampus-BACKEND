import base64
from unittest.mock import patch

import pytest

from services import imagem_equipamento
from tests.test_rotas import cliente  # noqa: F401


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20


def data_url(conteudo, tipo="image/png"):
    return f"data:{tipo};base64," + base64.b64encode(conteudo).decode()


@pytest.mark.parametrize(
    ("conteudo", "tipo"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_aceita_imagens_e_usa_o_tipo_real(conteudo, tipo):
    # O tipo declarado (png) é ignorado: vale o conteúdo do arquivo.
    acao, lido, tipo_lido = imagem_equipamento.ler(
        {"imagem": data_url(conteudo, "image/png")}
    )

    assert (acao, lido, tipo_lido) == (imagem_equipamento.DEFINIR, conteudo, tipo)


@pytest.mark.parametrize(
    ("dados", "acao"),
    [
        ({}, imagem_equipamento.MANTER),
        ({"imagem": ""}, imagem_equipamento.MANTER),
        ({"imagem": None}, imagem_equipamento.REMOVER),
    ],
)
def test_manter_ou_remover(dados, acao):
    assert imagem_equipamento.ler(dados)[0] == acao


@pytest.mark.parametrize(
    ("valor", "mensagem"),
    [
        (123, "data URL"),
        ("https://exemplo.com/foto.png", "data URL"),
        ("data:image/png;base64,@@@", "corrompida"),
        (data_url(b"<svg onload=alert(1)>", "image/svg+xml"), "não suportado"),
        (data_url(b"MZ executavel"), "não suportado"),
    ],
)
def test_recusa_conteudo_invalido(valor, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        imagem_equipamento.ler({"imagem": valor})


def test_recusa_imagem_grande(monkeypatch):
    monkeypatch.setattr(imagem_equipamento, "TAMANHO_MAXIMO", 100)

    with pytest.raises(ValueError, match="3 MB"):
        imagem_equipamento.ler({"imagem": data_url(PNG + b"\x00" * 200)})


def test_rota_da_imagem_e_publica(cliente):
    with patch(
        "routes.equipamentos.equipamento_service.obter_imagem",
        return_value=(PNG, "image/png"),
    ):
        resposta = cliente.get("/api/equipamentos/7/imagem?v=1")

    assert resposta.status_code == 200
    assert resposta.mimetype == "image/png"
    assert resposta.data == PNG
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"


def test_rota_da_imagem_sem_imagem(cliente):
    with patch(
        "routes.equipamentos.equipamento_service.obter_imagem",
        return_value=None,
    ):
        resposta = cliente.get("/api/equipamentos/7/imagem")

    assert resposta.status_code == 404
    assert "erro" in resposta.get_json()
