from flask import Blueprint, g, jsonify, request

from services.auth_token import requer_papeis
from services.historico_service import HistoricoService


historico_bp = Blueprint(
    "historico",
    __name__,
    url_prefix="/api/historico"
)

historico_service = HistoricoService()


@historico_bp.route("/", methods=["GET"])
@requer_papeis("admin", "operador")
def listar():
    valor = request.args.get("equipamento_id")

    if valor is None:
        return jsonify(historico_service.listar()), 200

    if not valor.isdecimal() or int(valor) <= 0:
        return jsonify({"erro": "Informe um equipamento_id válido."}), 400

    return jsonify(historico_service.listar(int(valor))), 200


@historico_bp.route("/<int:historico_id>", methods=["GET"])
@requer_papeis("admin", "operador")
def obter_por_id(historico_id):
    registro = historico_service.obter_por_id(historico_id)

    if registro is None:
        return jsonify({"erro": "Movimentação não encontrada."}), 404

    return jsonify(registro), 200


@historico_bp.route("/", methods=["POST"])
@requer_papeis("admin", "operador")
def cadastrar():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie um objeto JSON válido."}), 400

    # A movimentação é sempre de quem está logado.
    dados["usuario_id"] = g.usuario["id"]

    try:
        registro = historico_service.cadastrar(dados)
        return jsonify(registro), 201
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
