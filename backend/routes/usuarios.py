from flask import Blueprint, g, jsonify, request

from services.auth_token import requer_papeis
from services.usuario_service import UsuarioService


usuarios_bp = Blueprint(
    "usuarios",
    __name__,
    url_prefix="/api/usuarios"
)

usuario_service = UsuarioService()


@usuarios_bp.route("/", methods=["GET"])
@requer_papeis("admin")
def listar_usuarios():
    return jsonify({"usuarios": usuario_service.listar()}), 200


@usuarios_bp.route("/<int:usuario_id>", methods=["GET"])
@requer_papeis("admin")
def obter_usuario(usuario_id):
    usuario = usuario_service.obter_por_id(usuario_id)

    if usuario is None:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    return jsonify({"usuario": usuario}), 200


@usuarios_bp.route("/", methods=["POST"])
@requer_papeis("admin")
def cadastrar_usuario():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie os dados em formato JSON."}), 400

    try:
        usuario = usuario_service.cadastrar(dados)
        return jsonify({
            "mensagem": "Usuário cadastrado com sucesso.",
            "usuario": usuario
        }), 201
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400


@usuarios_bp.route("/<int:usuario_id>/desativar", methods=["PATCH"])
@requer_papeis("admin")
def desativar_usuario(usuario_id):
    try:
        usuario = usuario_service.desativar(usuario_id, g.usuario["id"])

        if usuario is None:
            return jsonify({"erro": "Usuário não encontrado."}), 404

        return jsonify({
            "mensagem": "Usuário desativado com sucesso.",
            "usuario": usuario
        }), 200
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
