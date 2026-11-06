"""QR Code das etiquetas dos equipamentos.

O QR Code grava a URL da consulta pública com o código do equipamento:
a câmera do celular abre a página direto, e a leitura dentro do sistema
também entende a URL (painel_service._extrair_codigo).
"""
import io
import os
from urllib.parse import quote

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


def conteudo(equipamento):
    base = url_consulta()
    separador = "&" if "?" in base else "?"
    return f"{base}{separador}codigo={quote(codigo(equipamento), safe='')}"


def gerar(texto, formato="svg"):
    """Retorna (bytes, tipo) da imagem do QR Code."""
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(texto)
    qr.make(fit=True)

    if formato == "png":
        saida = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(saida, format="PNG")
        return saida.getvalue(), "image/png"

    imagem = qr.make_image(image_factory=qrcode.image.svg.SvgPathFillImage)
    return imagem.to_string(encoding="utf-8"), "image/svg+xml"
