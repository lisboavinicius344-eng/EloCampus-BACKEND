import hashlib
import hmac
import os
from functools import wraps

from flask import request, jsonify, g
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from database.conexao import Conexao
from services import identificadores


# Equipe que administra o sistema.
PAPEIS_EQUIPE = ("admin", "operador")

# Usuários finais: só acessam os próprios empréstimos e reservas.
PAPEIS_USUARIO_FINAL = ("aluno", "professor")


def _serializer():
    secret = os.getenv("FLASK_SECRET_KEY")
    if not secret:
        raise RuntimeError("FLASK_SECRET_KEY não configurada.")
    return URLSafeTimedSerializer(secret, salt="elocampus-auth")


def _versao_da_senha(senha_hash):
    """Impressão digital da senha, que muda sempre que a senha muda.

    Vai dentro do token: trocar a senha invalida os logins anteriores.
    O conteúdo do token é legível, por isso usa a chave secreta em vez
    do próprio hash.
    """
    chave = os.getenv("FLASK_SECRET_KEY", "").encode()
    return hmac.new(chave, senha_hash.encode(), hashlib.sha256).hexdigest()[:32]


def gerar_token(usuario_id, senha_hash=None):
    """Gera o token de login; sem senha_hash, lê a senha atual no banco."""
    if senha_hash is None:
        with Conexao.conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT senha_hash FROM usuarios WHERE id = %s",
                    (usuario_id,)
                )
                senha_hash = cur.fetchone()[0]

    # O id é UUID: vai no token como texto.
    return _serializer().dumps({
        "usuario_id": str(usuario_id),
        "senha": _versao_da_senha(senha_hash),
    })


def _usuario_do_token():
    """Retorna (usuario, erro). Exatamente um dos dois é None."""
    cabecalho = request.headers.get("Authorization", "")
    esquema, _, token = cabecalho.partition(" ")

    if esquema.lower() != "bearer" or not token:
        return None, "Autenticação necessária."

    try:
        dados = _serializer().loads(token, max_age=3600)
    except SignatureExpired:
        return None, "Token expirado. Faça login novamente."
    except BadSignature:
        return None, "Token inválido."

    try:
        usuario_id = identificadores.usuario_id(dados.get("usuario_id"))
    except ValueError:
        return None, "Token inválido."

    with Conexao.conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nome, email, papel, ativo, solicitante_id,
                       deve_trocar_senha, senha_hash
                FROM usuarios
                WHERE id = %s
                """,
                (usuario_id,)
            )
            usuario = cur.fetchone()

    if usuario is None or not usuario[4]:
        return None, "Usuário inativo ou inexistente."

    # Senha trocada depois deste login: é preciso entrar de novo. Tokens
    # sem a impressão digital também são recusados.
    if not hmac.compare_digest(
        str(dados.get("senha", "")), _versao_da_senha(usuario[7])
    ):
        return None, "Sua senha foi alterada. Faça login novamente."

    return {
        "id": str(usuario[0]),
        "nome": usuario[1],
        "email": usuario[2],
        "papel": usuario[3],
        "solicitante_id": usuario[5],
        "deve_trocar_senha": usuario[6],
        "master": eh_master(usuario[3], usuario[2]),
    }, None


def eh_master(papel, email):
    """Admin master: admin cujo e-mail está em ADMIN_MASTER_EMAILS.

    Só ele vê os IDs das pessoas no site e pode zerar os dados.
    """
    lista = os.getenv("ADMIN_MASTER_EMAILS", "")
    masters = {e.strip().lower() for e in lista.split(",") if e.strip()}
    return papel == "admin" and str(email or "").strip().lower() in masters


def requer_master(f):
    @wraps(f)
    @requer_autenticacao
    def decorada(*args, **kwargs):
        if not g.usuario.get("master"):
            return jsonify({
                "erro": "Somente o administrador master pode fazer isso."
            }), 403
        return f(*args, **kwargs)
    return decorada


def requer_autenticacao(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        usuario, erro = _usuario_do_token()

        if erro:
            return jsonify({"erro": erro}), 401

        # Com senha provisória, a única ação liberada é criar a senha.
        if usuario["deve_trocar_senha"]:
            return jsonify({
                "erro": "Crie sua senha antes de continuar.",
                "codigo": "TROCA_DE_SENHA_OBRIGATORIA"
            }), 403

        g.usuario = usuario
        return f(*args, **kwargs)

    return decorada


def requer_autenticacao_para_trocar_senha(f):
    """Exige login, mas aceita quem ainda está com a senha provisória."""
    @wraps(f)
    def decorada(*args, **kwargs):
        usuario, erro = _usuario_do_token()

        if erro:
            return jsonify({"erro": erro}), 401

        g.usuario = usuario
        return f(*args, **kwargs)

    return decorada


def autenticacao_opcional(f):
    """Identifica o usuário quando há token, sem exigir login.

    g.usuario fica None para visitantes. Um token enviado, mas inválido
    ou expirado, é recusado para não mascarar uma sessão vencida.
    """
    @wraps(f)
    def decorada(*args, **kwargs):
        g.usuario = None

        if request.headers.get("Authorization"):
            usuario, erro = _usuario_do_token()

            if erro:
                return jsonify({"erro": erro}), 401

            # Senha provisória pendente: tratado como visitante.
            if not usuario["deve_trocar_senha"]:
                g.usuario = usuario

        return f(*args, **kwargs)

    return decorada


def requer_papeis(*papeis):
    def decorador(f):
        @wraps(f)
        @requer_autenticacao
        def decorada(*args, **kwargs):
            if g.usuario["papel"] not in papeis:
                return jsonify({"erro": "Permissão insuficiente."}), 403
            return f(*args, **kwargs)
        return decorada
    return decorador
