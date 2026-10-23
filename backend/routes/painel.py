from flask import Blueprint, g, jsonify

from services.auth_token import (
    PAPEIS_EQUIPE,
    autenticacao_opcional,
    requer_autenticacao,
)
from services.painel_service import PainelService


painel_bp = Blueprint(
    "painel",
    __name__,
    url_prefix="/api"
)

painel_service = PainelService()


@painel_bp.route("/dashboard/resumo", methods=["GET"])
@requer_autenticacao
def resumo_dashboard():
    return jsonify(painel_service.resumo()), 200


# Pública: a página de consulta por QR Code abre sem login.
# Quem está com o equipamento só é informado para a equipe.
@painel_bp.route("/consulta-qr/<path:codigo>", methods=["GET"])
@autenticacao_opcional
def consulta_qr(codigo):
    equipe = bool(g.usuario) and g.usuario["papel"] in PAPEIS_EQUIPE

    try:
        resultado = painel_service.consultar_qr(
            codigo, incluir_emprestimo=equipe
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    if resultado is None:
        return jsonify({
            "erro": "Nenhum equipamento corresponde a esse código."
        }), 404

    return jsonify(resultado), 200
