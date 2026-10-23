import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from services.n8n_service import notificar_senha_provisoria


logger = logging.getLogger(__name__)

# Sem caracteres que se confundem ao digitar (0/O, 1/l/I).
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
TAMANHO = 10


def validade_em_horas():
    try:
        horas = int(os.getenv("SENHA_PROVISORIA_HORAS", "24"))
    except ValueError:
        horas = 24

    return max(horas, 1)


def gerar():
    """Retorna (senha, senha_hash, expira_em) de uma senha provisória."""
    senha = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
    expira_em = datetime.now(timezone.utc) + timedelta(
        hours=validade_em_horas()
    )

    return senha, generate_password_hash(senha), expira_em


def enviar(usuario, senha, expira_em, evento):
    """Envia a senha provisória por e-mail (n8n). Retorna True se enviou.

    Nunca interrompe a operação: a conta já foi gravada e, se o e-mail
    falhar, o administrador pode reenviar uma nova senha.
    """
    try:
        return notificar_senha_provisoria(usuario, senha, expira_em, evento)
    except Exception:
        logger.exception(
            "Falha ao enviar a senha provisória do usuário %s.",
            usuario.get("id"),
        )
        return False
