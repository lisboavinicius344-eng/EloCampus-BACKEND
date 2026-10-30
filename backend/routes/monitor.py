import hmac
import os

from flask import Blueprint, Response, jsonify, request

from services import monitor_service

monitor_bp = Blueprint("monitor", __name__, url_prefix="/api")


def _chave_valida():
    """Confere a chave do monitoramento (variável MONITOR_TOKEN).

    Aceita o cabeçalho X-Monitor-Token ou o parâmetro ?token=.
    """
    esperado = os.getenv("MONITOR_TOKEN", "").strip()
    enviado = (
        request.headers.get("X-Monitor-Token")
        or request.args.get("token")
        or ""
    ).strip()

    return bool(esperado) and hmac.compare_digest(enviado, esperado)


def _responder(parte=None):
    status, verificacoes = monitor_service.verificar(parte)
    detalhado = _chave_valida()
    codigo = 503 if status == "falha" else 200

    # ?formato=texto: uma linha só ("FALHA: banco"), para o Uptime Kuma
    # copiar na mensagem do alerta.
    if request.args.get("formato") == "texto":
        resposta = Response(
            monitor_service.resumo(status, verificacoes, detalhado),
            status=codigo,
            mimetype="text/plain",
        )
    else:
        corpo = {
            "status": status,
            "sistema": "ELO Campus",
            "resumo": monitor_service.resumo(status, verificacoes, detalhado),
            "verificado_em": monitor_service.agora_iso(),
        }

        if parte is not None:
            corpo["parte"] = parte

        # Os detalhes (erros de banco, variáveis) só com a chave.
        if detalhado:
            corpo["verificacoes"] = verificacoes

        resposta = jsonify(corpo)
        resposta.status_code = codigo

    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@monitor_bp.route("/monitor", methods=["GET"])
def monitor():
    return _responder()


@monitor_bp.route("/monitor/<parte>", methods=["GET"])
def monitor_parte(parte):
    if parte not in monitor_service.PARTES:
        return jsonify({
            "erro": "Parte inválida. Use: "
                    + ", ".join(monitor_service.PARTES) + "."
        }), 404

    return _responder(parte)
