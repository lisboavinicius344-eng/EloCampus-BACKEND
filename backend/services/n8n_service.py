
import logging
import os

import requests

logger = logging.getLogger(__name__)


def _notificar(webhook_env, evento, payload):
    webhook_url = os.getenv(webhook_env, "").strip()

    if not webhook_url:
        logger.warning(
            "Evento %s não enviado ao n8n: variável %s não configurada.",
            evento,
            webhook_env,
        )
        return False

    secret = os.getenv("N8N_WEBHOOK_SECRET", "").strip()

    headers = {"Content-Type": "application/json"}

    if secret:
        headers["X-EloCampus-Webhook-Secret"] = secret

    try:
        resposta = requests.post(
            webhook_url,
            json={
                "evento": evento,
                **payload,
            },
            headers=headers,
            timeout=5,
        )
        resposta.raise_for_status()
        return True

    except requests.RequestException:
        logger.exception(
            "Falha ao notificar o n8n sobre o evento %s.",
            evento,
        )
        return False


def notificar_senha_provisoria(usuario, senha, expira_em, evento):
    """Envia ao n8n a senha provisória de primeiro acesso.

    Eventos: cadastro_aluno (autocadastro), cadastro_usuario (conta
    criada pelo admin), senha_provisoria (nova senha reenviada pelo
    admin) e recuperacao_senha (pedida em "Esqueci minha senha").
    """
    return _notificar(
        "N8N_CADASTRO_WEBHOOK_URL",
        evento,
        {
            "usuario": {
                "id": usuario["id"],
                "nome": usuario["nome"],
                "email": usuario["email"],
                "papel": usuario["papel"],
                "solicitante_id": usuario.get("solicitante_id"),
            },
            "senha_provisoria": senha,
            "senha_expira_em": expira_em.isoformat(),
        },
    )


def notificar_novo_emprestimo(emprestimo):
    return _notificar(
        "N8N_EMPRESTIMO_WEBHOOK_URL",
        "novo_emprestimo",
        {
            "emprestimo": {
                "id": emprestimo["id"],
                "solicitante_id": emprestimo["solicitante_id"],
                "solicitante": emprestimo["solicitante"],
                "usuario_responsavel_id": (
                    emprestimo["usuario_responsavel_id"]
                ),
                "data_prevista_devolucao": (
                    emprestimo["data_prevista_devolucao"]
                ),
                "status": emprestimo["status"],
                "itens": [
                    {
                        "equipamento_id": item["equipamento_id"],
                        "equipamento": item["equipamento"],
                    }
                    for item in emprestimo.get("itens", [])
                ],
            }
        },
    )


def notificar_devolucao_equipamento(
    emprestimo,
    equipamento_id,
    estado_na_devolucao,
    usuario_id,
):
    return _notificar(
        "N8N_DEVOLUCAO_WEBHOOK_URL",
        "devolucao_equipamento",
        {
            "emprestimo_id": emprestimo["id"],
            "solicitante_id": emprestimo.get("solicitante_id"),
            "equipamento_id": equipamento_id,
            "estado_na_devolucao": estado_na_devolucao,
            "usuario_responsavel_id": usuario_id,
            "status_emprestimo": emprestimo["status"],
        },
    )

def notificar_reserva(reserva, evento):
    return _notificar(
        "N8N_RESERVA_WEBHOOK_URL",
        evento,
        {
            "reserva": {
                "id": reserva["id"],
                "solicitante_id": reserva["solicitante_id"],
                "solicitante": reserva["solicitante"],
                "usuario_responsavel_id": (
                    reserva["usuario_responsavel_id"]
                ),
                "usuario_responsavel": (
                    reserva["usuario_responsavel"]
                ),
                "data_inicio": reserva["data_inicio"],
                "data_fim": reserva["data_fim"],
                "status": reserva["status"],
                "observacoes": reserva["observacoes"],
                "itens": [
                    {
                        "equipamento_id": item["equipamento_id"],
                        "equipamento": item["equipamento"],
                        "status_equipamento": item[
                            "status_equipamento"
                        ],
                    }
                    for item in reserva.get("itens", [])
                ],
            }
        },
    )

def notificar_equipamento(equipamento, evento):
    return _notificar(
        "N8N_EQUIPAMENTO_WEBHOOK_URL",
        evento,
        {"equipamento": equipamento},
    )

def notificar_manutencao(manutencao, evento):
    return _notificar(
        "N8N_MANUTENCAO_WEBHOOK_URL",
        evento,
        {"manutencao": manutencao},
    )

