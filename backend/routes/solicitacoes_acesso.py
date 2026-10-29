from flask import Blueprint, g, jsonify, request

from services.auth_token import requer_papeis
from services.solicitacao_acesso_service import SolicitacaoAcessoService

solicitacoes_acesso_bp = Blueprint(
    "solicitacoes_acesso",
    __name__,
    url_prefix="/api/solicitacoes-acesso"
)

solicitacao_service = SolicitacaoAcessoService()


@solicitacoes_acesso_bp.route("/", methods=["GET"])
@requer_papeis("admin")
def listar_solicitacoes():
    try:
        solicitacoes = solicitacao_service.listar(request.args.get("status"))
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify({"solicitacoes": solicitacoes}), 200


@solicitacoes_acesso_bp.route("/<uuid:solicitacao_id>", methods=["GET"])
@requer_papeis("admin")
def obter_solicitacao(solicitacao_id):
    solicitacao = solicitacao_service.obter_por_id(str(solicitacao_id))

    if solicitacao is None:
        return jsonify({"erro": "Solicitação não encontrada."}), 404

    return jsonify({"solicitacao": solicitacao}), 200


@solicitacoes_acesso_bp.route(
    "/<uuid:solicitacao_id>/aprovar", methods=["POST"]
)
@requer_papeis("admin")
def aprovar_solicitacao(solicitacao_id):
    dados = request.get_json(silent=True) or {}

    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie os dados em formato JSON."}), 400

    try:
        resultado = solicitacao_service.aprovar(
            str(solicitacao_id), dados, g.usuario["id"]
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    if resultado is None:
        return jsonify({"erro": "Solicitação não encontrada."}), 404

    solicitacao, usuario, enviado, senha = resultado
    resposta = {
        "mensagem": (
            "Acesso aprovado. A senha provisória foi enviada por e-mail."
            if enviado
            else "Acesso aprovado, mas o e-mail não foi enviado. Repasse "
                 "a senha provisória pessoalmente."
        ),
        "email_enviado": enviado,
        "solicitacao": solicitacao,
        "usuario": usuario,
    }

    if senha is not None:
        resposta["senha_provisoria"] = senha

    return jsonify(resposta), 200


@solicitacoes_acesso_bp.route(
    "/<uuid:solicitacao_id>/recusar", methods=["POST"]
)
@requer_papeis("admin")
def recusar_solicitacao(solicitacao_id):
    dados = request.get_json(silent=True) or {}

    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie os dados em formato JSON."}), 400

    try:
        solicitacao = solicitacao_service.recusar(
            str(solicitacao_id), dados, g.usuario["id"]
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    if solicitacao is None:
        return jsonify({"erro": "Solicitação não encontrada."}), 404

    return jsonify({
        "mensagem": "Solicitação recusada.",
        "solicitacao": solicitacao
    }), 200
