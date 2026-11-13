"""QR Code das etiquetas dos equipamentos.

O QR Code grava um endereço curto com o ID do equipamento
(ex.: https://elocampus.com.br/q/36). O site leva a pessoa ao item dentro
do sistema, e a leitura dentro do sistema também entende o endereço
(painel_service._extrair_codigo). Endereço curto = QR com menos
quadradinhos, que continua legível impresso pequeno.
"""
import io
import os
from urllib.parse import urlsplit

import qrcode
import qrcode.image.svg
from qrcode.constants import ERROR_CORRECT_M


URL_CONSULTA_PADRAO = (
    "https://elocampus-frontend.a6ti6s.easypanel.host/pages/consulta-qr.html"
)
FORMATOS = ("svg", "png")


def url_consulta():
    """Página de consulta gravada nas etiquetas (variável QR_CONSULTA_URL).

    Etiqueta impressa não muda depois: defina o endereço definitivo antes
    de imprimir.
    """
    return os.getenv("QR_CONSULTA_URL", "").strip() or URL_CONSULTA_PADRAO


def codigo(equipamento):
    """O que identifica o equipamento na etiqueta: QR, patrimônio ou ID."""
    for campo in ("qr_code", "numero_patrimonio"):
        valor = str(equipamento.get(campo) or "").strip()
        if valor:
            return valor
    return str(equipamento["id"])


def url_item():
    """Início do endereço gravado no QR (variável QR_ITEM_URL).

    Sem valor, usa o mesmo site de QR_CONSULTA_URL com o caminho /q.
    """
    propria = os.getenv("QR_ITEM_URL", "").strip()

    if propria:
        return propria.rstrip("/")

    partes = urlsplit(url_consulta())
    return f"{partes.scheme}://{partes.netloc}/q"


def conteudo(equipamento):
    """Endereço gravado no QR: url_item() + "/" + ID do equipamento."""
    return f"{url_item()}/{int(equipamento['id'])}"


def gerar(texto, formato="svg"):
    """Retorna (bytes, tipo) da imagem do QR Code."""
    # Margem de 2 módulos: suficiente para a câmera do celular e deixa a
    # etiqueta pequena (a página de etiquetas ainda dá espaço em volta).
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(texto)
    qr.make(fit=True)

    if formato == "png":
        saida = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(saida, format="PNG")
        return saida.getvalue(), "image/png"

    imagem = qr.make_image(image_factory=qrcode.image.svg.SvgPathFillImage)
    return imagem.to_string(encoding="utf-8"), "image/svg+xml"
