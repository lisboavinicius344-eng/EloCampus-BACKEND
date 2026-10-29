from flask import Blueprint, g, jsonify, request

from services.auth_service import AuthService
from services.perfil_service import PerfilService
from services.solicitacao_acesso_service import SolicitacaoAcessoService
from services.auth_token import (
    gerar_token,
    requer_autenticacao,
    requer_autenticacao_para_trocar_senha,
)

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


@auth_bp.route("/login", methods=["POST"])
def login():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        usuario = AuthService.login(dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 401

    mensagem = (
        "Crie sua nova senha para continuar."
        if usuario["deve_trocar_senha"]
        else "Login realizado com sucesso."
    )

    return jsonify({
        "mensagem": mensagem,
        "token": gerar_token(usuario["id"]),
        "usuario": usuario
    }), 200


@auth_bp.route("/solicitar-acesso", methods=["POST"])
# Endereço antigo da tela de cadastro, mantido para o frontend atual.
@auth_bp.route("/cadastro-aluno", methods=["POST"])
def solicitar_acesso():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        SolicitacaoAcessoService().solicitar(dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    # A mesma resposta em todos os casos (pedido novo, pedido repetido ou
    # e-mail que já tem conta): a tela não revela quem tem acesso.
    return jsonify({
        "mensagem": (
            "Solicitação enviada. Quando a administração aprovar, você "
            "receberá no e-mail uma senha provisória para o primeiro "
            "acesso. Se você já tem conta, use \"Esqueci minha senha\"."
        )
    }), 200


@auth_bp.route("/esqueci-senha", methods=["POST"])
def esqueci_senha():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        AuthService.esqueci_senha(dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    # A mesma resposta para e-mails cadastrados ou não: assim a tela não
    # serve para descobrir quem tem conta no sistema.
    return jsonify({
        "mensagem": (
            "Se o e-mail estiver cadastrado, você receberá em instantes "
            "uma senha provisória. Ela vale por pouco tempo; sua senha "
            "atual continua funcionando até você usá-la."
        )
    }), 200


@auth_bp.route("/trocar-senha", methods=["POST"])
@requer_autenticacao_para_trocar_senha
def trocar_senha():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        AuthService.trocar_senha(g.usuario["id"], dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify({"mensagem": "Senha alterada com sucesso."}), 200


@auth_bp.route("/perfil", methods=["GET"])
@requer_autenticacao
def obter_perfil():
    perfil = PerfilService().obter(g.usuario["id"])

    if perfil is None:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    return jsonify({"perfil": perfil}), 200


@auth_bp.route("/perfil", methods=["PUT"])
@requer_autenticacao
def atualizar_perfil():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        perfil = PerfilService().atualizar(g.usuario["id"], dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    if perfil is None:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    return jsonify({
        "mensagem": "Perfil atualizado com sucesso.",
        "perfil": perfil
    }), 200
