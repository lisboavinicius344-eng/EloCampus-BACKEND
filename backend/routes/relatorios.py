import os

from flask import Blueprint, jsonify, request

from routes.monitor import _chave_valida
from services import relatorio_service
from services.auth_token import requer_papeis
from services.relatorio_service import RelatorioService

relatorios_bp = Blueprint(
    "relatorios",
    __name__,
    url_prefix="/api/relatorios"
)

relatorios = RelatorioService()


@relatorios_bp.route("/resumo", methods=["GET"])
@requer_papeis("admin", "operador")
def resumo():
    try:
        primeiro, ultimo = relatorio_service.periodo(
            request.args.get("inicio"), request.args.get("fim")
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify(relatorios.resumo(primeiro, ultimo)), 200


@relatorios_bp.route("/atrasados", methods=["GET"])
@requer_papeis("admin", "operador")
def atrasados():
    return jsonify({"atrasados": relatorios.atrasados()}), 200


@relatorios_bp.route("/mais-emprestados", methods=["GET"])
@requer_papeis("admin", "operador")
def mais_emprestados():
    try:
        primeiro, ultimo = relatorio_service.periodo(
            request.args.get("inicio"), request.args.get("fim")
        )
        quantidade = relatorio_service.limite(request.args.get("limite"))
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    return jsonify({
        "periodo": {
            "inicio": primeiro.isoformat(),
            "fim": ultimo.isoformat(),
        },
        "equipamentos": relatorios.mais_emprestados(
            primeiro, ultimo, quantidade
        ),
    }), 200


@relatorios_bp.route("/manutencoes", methods=["GET"])
@requer_papeis("admin", "operador")
def manutencoes():
    return jsonify({
        "manutencoes": relatorios.manutencoes_em_aberto()
    }), 200


@relatorios_bp.route("/semanal", methods=["GET"])
def semanal():
    """Chamado pelo n8n toda segunda-feira; devolve o e-mail pronto.

    Exige a chave das automações (MONITOR_TOKEN) no cabeçalho
    X-Monitor-Token, como os lembretes de devolução.
    """
    if not os.getenv("MONITOR_TOKEN", "").strip():
        return jsonify({
            "erro": "Configure a variável MONITOR_TOKEN no backend."
        }), 503

    if not _chave_valida():
        return jsonify({"erro": "Chave de automação inválida."}), 401

    return jsonify(relatorios.semanal()), 200
