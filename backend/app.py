import logging
import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from routes.emprestimos import emprestimos_bp
from routes.equipamentos import equipamentos_bp
from routes.categorias import categorias_bp
from routes.solicitantes import solicitantes_bp
from routes.reservas import reservas_bp
from routes.manutencoes import manutencoes_bp
from routes.historico import historico_bp
from routes.auth import auth_bp
from routes.usuarios import usuarios_bp
from routes.painel import painel_bp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Origens autorizadas a chamar a API pelo navegador (frontend).
# Pode ser alterado pela variável de ambiente CORS_ORIGINS,
# com os endereços separados por vírgula.
ORIGENS_PERMITIDAS = {
    origem.strip().rstrip("/")
    for origem in os.getenv(
        "CORS_ORIGINS",
        "https://elocampus.com.br,"
        "https://www.elocampus.com.br,"
        "https://elocampus-frontend.a6ti6s.easypanel.host",
    ).split(",")
    if origem.strip()
}


app = Flask(__name__)

# Aceita as rotas com ou sem a barra final (/api/equipamentos e
# /api/equipamentos/). Sem isso, o Flask responde com redirecionamento,
# que o navegador não segue em requisições com CORS.
app.url_map.strict_slashes = False

# Limite do corpo das requisições: cobre uma imagem de 3 MB em base64.
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

app.register_blueprint(equipamentos_bp)
app.register_blueprint(categorias_bp)
app.register_blueprint(solicitantes_bp)
app.register_blueprint(emprestimos_bp)
app.register_blueprint(reservas_bp)
app.register_blueprint(manutencoes_bp)
app.register_blueprint(historico_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(painel_bp)


@app.after_request
def aplicar_cors(resposta):
    origem = request.headers.get("Origin", "").rstrip("/")

    if origem in ORIGENS_PERMITIDAS:
        resposta.headers["Access-Control-Allow-Origin"] = origem
        resposta.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type"
        )
        resposta.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        resposta.headers["Access-Control-Max-Age"] = "600"

    resposta.headers.add("Vary", "Origin")
    return resposta


@app.errorhandler(HTTPException)
def erro_http(erro):
    mensagens = {
        404: "Rota não encontrada.",
        405: "Método não permitido para esta rota.",
        413: "Os dados enviados são grandes demais. "
             "Reduza a imagem para no máximo 3 MB.",
    }

    return jsonify({
        "erro": mensagens.get(erro.code, erro.description)
    }), erro.code


@app.errorhandler(Exception)
def erro_inesperado(erro):
    logger.exception("Erro não tratado em %s %s", request.method, request.path)

    return jsonify({
        "erro": "Erro interno do servidor. Tente novamente mais tarde."
    }), 500


@app.route("/", methods=["GET"])
def inicio():
    return jsonify({
        "projeto": "ELO Campus",
        "mensagem": "Backend iniciado com sucesso!"
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "sistema": "ELO Campus"
    })


if __name__ == "__main__":
    app.run(debug=True)
