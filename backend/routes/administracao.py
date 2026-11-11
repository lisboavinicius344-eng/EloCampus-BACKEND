from flask import Blueprint, g, jsonify, request

from services import administracao_service
from services.auth_token import requer_master


administracao_bp = Blueprint(
    "administracao",
    __name__,
    url_prefix="/api/administracao"
)


@administracao_bp.route("/zerar-dados", methods=["POST"])
@requer_master
def zerar_dados():
    dados = request.get_json(silent=True) or {}

    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie os dados em formato JSON."}), 400

    try:
        apagados = administracao_service.zerar_dados(
            dados.get("confirmacao"), g.usuario
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify({
        "mensagem": "Dados zerados. Equipamentos, reservas, empréstimos, "
                    "manutenções e histórico foram apagados.",
        "apagados": apagados,
    }), 200
