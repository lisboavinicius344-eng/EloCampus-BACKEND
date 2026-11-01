import os

from flask import Blueprint, jsonify, request

from routes.monitor import _chave_valida
from services.lembrete_service import LembreteService

lembretes_bp = Blueprint("lembretes", __name__, url_prefix="/api/lembretes")


@lembretes_bp.route("/processar", methods=["POST"])
def processar_lembretes():
    """Chamado pelo n8n de hora em hora; devolve os e-mails a enviar.

    Exige a chave das automações (MONITOR_TOKEN) no cabeçalho
    X-Monitor-Token. Com ?simular=true, só mostra, sem marcar como
    enviados (para testar o workflow).
    """
    if not os.getenv("MONITOR_TOKEN", "").strip():
        return jsonify({
            "erro": "Configure a variável MONITOR_TOKEN no backend."
        }), 503

    if not _chave_valida():
        return jsonify({"erro": "Chave de automação inválida."}), 401

    simular = request.args.get("simular", "").lower() in ("1", "true", "sim")
    lembretes = LembreteService().processar(simular=simular)

    return jsonify({
        "total": len(lembretes),
        "simulacao": simular,
        "lembretes": lembretes,
    }), 200
