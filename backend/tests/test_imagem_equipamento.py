import base64
import io
import os
from unittest.mock import patch

import pytest
from PIL import Image

from services import imagem_equipamento
from tests.test_rotas import cliente  # noqa: F401


def gerar(formato="PNG", tamanho=(64, 48), modo="RGB", ruido=False, exif=None):
    if ruido:
        # Ruído não comprime: produz arquivos grandes como fotos reais.
        imagem = Image.frombytes(modo, tamanho, os.urandom(
            tamanho[0] * tamanho[1] * len(modo)
        ))
    else:
        imagem = Image.new(modo, tamanho, (30, 160, 120, 255)[:len(modo)])

    saida = io.BytesIO()
    opcoes = {"exif": exif} if exif is not None else {}
    imagem.save(saida, format=formato, **opcoes)
    return saida.getvalue()


def data_url(conteudo, tipo="image/png"):
    return f"data:{tipo};base64," + base64.b64encode(conteudo).decode()


def abrir(conteudo):
    return Image.open(io.BytesIO(conteudo))


@pytest.mark.parametrize(
    ("formato", "tipo"),
    [
        ("PNG", "image/png"),
        ("JPEG", "image/jpeg"),
        ("WEBP", "image/webp"),
        ("GIF", "image/gif"),
    ],
)
def test_imagem_pequena_e_guardada_como_veio(formato, tipo):
    original = gerar(formato)

    # O tipo declarado (png) é ignorado: vale o conteúdo do arquivo.
    acao, conteudo, tipo_lido = imagem_equipamento.ler(
        {"imagem": data_url(original, "image/png")}
    )

    assert (acao, conteudo, tipo_lido) == (
        imagem_equipamento.DEFINIR, original, tipo
    )


def test_foto_grande_e_comprimida_para_ate_200kb():
    original = gerar("PNG", (1900, 1300), ruido=True)
    assert len(original) > 3 * 1024 * 1024

    _, conteudo, tipo = imagem_equipamento.ler({"imagem": data_url(original)})

    assert tipo == "image/jpeg"
    assert len(conteudo) <= imagem_equipamento.TAMANHO_MAXIMO
    assert max(abrir(conteudo).size) <= imagem_equipamento.LADO_MAXIMO


def test_proporcao_e_mantida():
    original = gerar("PNG", (2400, 1200), ruido=True)

    _, conteudo, _ = imagem_equipamento.ler({"imagem": data_url(original)})
    largura, altura = abrir(conteudo).size

    assert abs(largura / altura - 2) < 0.02


def test_transparencia_vira_fundo_branco():
    original = gerar("PNG", (1600, 1200), modo="RGBA", ruido=True)

    _, conteudo, tipo = imagem_equipamento.ler({"imagem": data_url(original)})

    assert tipo == "image/jpeg"
    assert abrir(conteudo).mode == "RGB"


def test_foto_deitada_pelo_exif_e_girada():
    exif = Image.Exif()
    exif[0x0112] = 6  # câmera girada 90°: a foto deve ficar em pé
    original = gerar("JPEG", (80, 40), exif=exif.tobytes())

    _, conteudo, _ = imagem_equipamento.ler({"imagem": data_url(original)})

    assert abrir(conteudo).size == (40, 80)


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
        (data_url(gerar("BMP")), "não suportado"),
    ],
)
def test_recusa_conteudo_invalido(valor, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        imagem_equipamento.ler({"imagem": valor})


def test_recusa_envio_acima_de_10mb(monkeypatch):
    monkeypatch.setattr(imagem_equipamento, "TAMANHO_MAXIMO_ENVIO", 100)

    with pytest.raises(ValueError, match="10 MB"):
        imagem_equipamento.ler({"imagem": data_url(b"\x00" * 200)})


def test_recusa_resolucao_absurda(monkeypatch):
    monkeypatch.setattr(imagem_equipamento, "PIXELS_MAXIMOS", 1000)

    with pytest.raises(ValueError, match="resolução"):
        imagem_equipamento.ler({"imagem": data_url(gerar("PNG", (100, 100)))})


def test_rota_da_imagem_e_publica(cliente):
    png = gerar("PNG")

    with patch(
        "routes.equipamentos.equipamento_service.obter_imagem",
        return_value=(png, "image/png"),
    ):
        resposta = cliente.get("/api/equipamentos/7/imagem?v=1")

    assert resposta.status_code == 200
    assert resposta.mimetype == "image/png"
    assert resposta.data == png
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"


def test_rota_da_imagem_sem_imagem(cliente):
    with patch(
        "routes.equipamentos.equipamento_service.obter_imagem",
        return_value=None,
    ):
        resposta = cliente.get("/api/equipamentos/7/imagem")

    assert resposta.status_code == 404
    assert "erro" in resposta.get_json()
