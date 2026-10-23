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
        usuario, enviado, senha = usuario_service.cadastrar(dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify(
        _resposta_senha_provisoria("Usuário cadastrado.", usuario, enviado, senha)
    ), 201


@usuarios_bp.route("/<int:usuario_id>/reenviar-senha", methods=["PATCH"])
@requer_papeis("admin")
def reenviar_senha(usuario_id):
    resultado = usuario_service.reenviar_senha(usuario_id)

    if resultado is None:
        return jsonify({
            "erro": "Usuário não encontrado ou desativado."
        }), 404

    usuario, enviado, senha = resultado

    return jsonify(
        _resposta_senha_provisoria(
            "Nova senha provisória gerada.", usuario, enviado, senha
        )
    ), 200


def _resposta_senha_provisoria(mensagem, usuario, enviado, senha):
    resposta = {
        "mensagem": mensagem + (
            " A senha provisória foi enviada por e-mail."
            if enviado
            else " Não foi possível enviar o e-mail: repasse a senha "
                 "provisória pessoalmente."
        ),
        "email_enviado": enviado,
        "usuario": usuario,
    }

    # Só quando o e-mail falhou, para o admin não ficar sem saída.
    if not enviado:
        resposta["senha_provisoria"] = senha

    return resposta


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
