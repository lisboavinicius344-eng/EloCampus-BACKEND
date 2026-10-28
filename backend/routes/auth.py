from flask import Blueprint, g, jsonify, request

from services.auth_service import AuthService
from services.auth_token import (
    gerar_token,
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


@auth_bp.route("/cadastro-aluno", methods=["POST"])
def cadastrar_aluno():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        usuario, email_enviado = AuthService.cadastrar_aluno(dados)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    mensagem = (
        "Conta criada. Enviamos uma senha provisória para o seu e-mail."
        if email_enviado
        else "Conta criada, mas não foi possível enviar o e-mail com a "
             "senha provisória. Procure a administração."
    )

    return jsonify({
        "mensagem": mensagem,
        "email_enviado": email_enviado,
        "usuario": usuario
    }), 201


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
