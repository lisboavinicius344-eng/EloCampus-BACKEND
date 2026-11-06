from flask import Blueprint, Response, g, jsonify, request
from services import qr_equipamento
from services.equipamento_service import EquipamentoService
from services.auth_token import requer_autenticacao, requer_papeis

equipamentos_bp = Blueprint(
    "equipamentos",
    __name__,
    url_prefix="/api/equipamentos"
)

equipamento_service = EquipamentoService()


@equipamentos_bp.route("/", methods=["GET"])
@requer_autenticacao
def listar_equipamentos():
    return jsonify({
        "equipamentos": equipamento_service.listar()
    }), 200


@equipamentos_bp.route("/", methods=["POST"])
@requer_papeis("admin", "operador")
def cadastrar_equipamento():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        equipamento = equipamento_service.cadastrar(dados)
        return jsonify({
            "mensagem": "Equipamento cadastrado com sucesso.",
            "equipamento": equipamento
        }), 201
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400


@equipamentos_bp.route("/<int:equipamento_id>", methods=["GET"])
@requer_autenticacao
def obter_equipamento(equipamento_id):
    equipamento = equipamento_service.obter_por_id(equipamento_id)

    if equipamento is None:
        return jsonify({
            "erro": "Equipamento não encontrado."
        }), 404

    return jsonify({"equipamento": equipamento}), 200


@equipamentos_bp.route("/<int:equipamento_id>/imagem", methods=["GET"])
def obter_imagem_equipamento(equipamento_id):
    # Pública, como a consulta por QR Code: a tag <img> do navegador não
    # envia o token de login.
    imagem = equipamento_service.obter_imagem(equipamento_id)

    if imagem is None:
        return jsonify({
            "erro": "Equipamento sem imagem."
        }), 404

    conteudo, tipo = imagem
    resposta = Response(conteudo, mimetype=tipo)
    resposta.headers["Cache-Control"] = "public, max-age=604800"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Content-Disposition"] = "inline"
    return resposta


@equipamentos_bp.route("/<int:equipamento_id>/qrcode", methods=["GET"])
def obter_qrcode_equipamento(equipamento_id):
    # Pública pelo mesmo motivo da imagem; o QR só grava a URL da
    # consulta pública, que já mostra esses dados sem login.
    formato = request.args.get("formato", "svg").strip().lower()

    if formato not in qr_equipamento.FORMATOS:
        return jsonify({"erro": "Formato inválido. Use svg ou png."}), 400

    equipamento = equipamento_service.obter_por_id(equipamento_id)

    if equipamento is None:
        return jsonify({"erro": "Equipamento não encontrado."}), 404

    conteudo, tipo = qr_equipamento.gerar(
        qr_equipamento.conteudo(equipamento), formato
    )
    resposta = Response(conteudo, mimetype=tipo)
    # Curto: o código muda se o patrimônio ou o QR forem editados.
    resposta.headers["Cache-Control"] = "public, max-age=3600"
    resposta.headers["X-Content-Type-Options"] = "nosniff"

    nome = f"qrcode-{qr_equipamento.codigo(equipamento)}.{formato}"
    nome = "".join(c if c.isalnum() or c in "-_." else "-" for c in nome)
    modo = "attachment" if request.args.get("baixar") else "inline"
    resposta.headers["Content-Disposition"] = f'{modo}; filename="{nome}"'
    return resposta


@equipamentos_bp.route("/<int:equipamento_id>", methods=["PUT"])
@requer_papeis("admin", "operador")
def atualizar_equipamento(equipamento_id):
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "erro": "Envie os dados em formato JSON."
        }), 400

    try:
        equipamento = equipamento_service.atualizar(
            equipamento_id, dados
        )

        if equipamento is None:
            return jsonify({
                "erro": "Equipamento não encontrado."
            }), 404

        return jsonify({
            "mensagem": "Equipamento atualizado com sucesso.",
            "equipamento": equipamento
        }), 200
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400


@equipamentos_bp.route(
    "/<int:equipamento_id>/inativar",
    methods=["PATCH"]
)
@requer_papeis("admin", "operador")
def inativar_equipamento(equipamento_id):
    dados = request.get_json(silent=True) or {}
    observacoes = dados.get("observacoes") if isinstance(dados, dict) else None

    try:
        equipamento = equipamento_service.inativar(
            equipamento_id, g.usuario["id"], observacoes
        )

        if equipamento is None:
            return jsonify({
                "erro": "Equipamento não encontrado."
            }), 404

        return jsonify({
            "mensagem": "Equipamento baixado com sucesso.",
            "equipamento": equipamento
        }), 200
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
