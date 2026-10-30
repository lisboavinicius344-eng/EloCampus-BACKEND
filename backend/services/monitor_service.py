"""Verificação de saúde para o monitoramento (n8n, Uptime Kuma).

Status geral:
- "ok":        tudo funcionando (HTTP 200);
- "degradado": o sistema funciona, mas algo auxiliar falhou, como o n8n
               (os e-mails não saem) (HTTP 200);
- "falha":     banco, tabelas ou configuração obrigatória com problema
               (HTTP 503).
"""
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from database.conexao import Conexao


TABELAS = (
    "solicitantes", "usuarios", "solicitacoes_acesso", "categorias",
    "equipamentos", "emprestimos", "itens_emprestimo", "manutencoes",
    "historico_movimentacoes", "reservas", "itens_reserva",
)


def _medir(funcao):
    """Roda uma verificação e devolve {"ok", "ms", "detalhe"?}."""
    inicio = time.perf_counter()

    try:
        detalhe = funcao()
        resultado = {"ok": True}
    except Exception as erro:  # o monitor precisa relatar, não cair
        detalhe = f"{type(erro).__name__}: {erro}".strip()[:300]
        resultado = {"ok": False}

    resultado["ms"] = round((time.perf_counter() - inicio) * 1000)

    if detalhe:
        resultado["detalhe"] = detalhe

    return resultado


def _banco_e_tabelas():
    """Uma conexão para o banco e outra leitura por tabela."""
    tabelas = {}

    with Conexao.conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT 1")

            for tabela in TABELAS:
                def ler(tabela=tabela):
                    # Nome fixo da lista acima, nunca vindo do cliente.
                    cursor.execute(f"SELECT 1 FROM {tabela} LIMIT 1")
                    cursor.fetchall()

                tabelas[tabela] = _medir(ler)

                if not tabelas[tabela]["ok"]:
                    # Uma consulta com erro invalida a transação.
                    conexao.rollback()

    return tabelas


def _configuracao():
    faltando = [
        nome for nome in ("FLASK_SECRET_KEY", "DB_HOST", "DB_NAME")
        if not os.getenv(nome)
    ]

    if faltando:
        raise RuntimeError("Variáveis ausentes: " + ", ".join(faltando))


def _n8n():
    url = os.getenv("N8N_CADASTRO_WEBHOOK_URL", "").strip()

    if not url:
        raise RuntimeError("N8N_CADASTRO_WEBHOOK_URL não configurada.")

    partes = urlsplit(url)
    # /healthz é o endpoint de saúde do próprio n8n: não dispara workflow.
    resposta = requests.get(
        f"{partes.scheme}://{partes.netloc}/healthz", timeout=5
    )
    resposta.raise_for_status()


PARTES = ("banco", "tabelas", "configuracao", "n8n")


def verificar(parte=None):
    """Devolve (status, verificacoes).

    parte=None confere tudo. Com uma parte ("banco", "tabelas",
    "configuracao" ou "n8n"), confere só ela: é o que permite um monitor
    por parte no Uptime Kuma, e o nome do monitor diz o que caiu. Nesse
    caso, a falha da parte é sempre "falha" (HTTP 503), inclusive o n8n.
    """
    if parte is not None and parte not in PARTES:
        raise ValueError(
            "Parte inválida. Use: " + ", ".join(PARTES) + "."
        )

    verificacoes = {"api": {"ok": True, "ms": 0}}

    if parte in (None, "banco", "tabelas"):
        tabelas = {}

        def banco():
            nonlocal tabelas
            tabelas = _banco_e_tabelas()

        verificacoes["banco"] = _medir(banco)
        verificacoes["tabelas"] = {
            "ok": verificacoes["banco"]["ok"]
            and all(t["ok"] for t in tabelas.values()),
            "falhas": {
                nome: t.get("detalhe", "falhou")
                for nome, t in tabelas.items() if not t["ok"]
            },
        }

    if parte in (None, "configuracao"):
        verificacoes["configuracao"] = _medir(_configuracao)

    if parte in (None, "n8n"):
        verificacoes["n8n"] = _medir(_n8n)

    if parte is not None:
        status = "ok" if verificacoes[parte]["ok"] else "falha"
    elif not all(
        verificacoes[nome]["ok"] for nome in ("banco", "tabelas", "configuracao")
    ):
        status = "falha"
    elif not verificacoes["n8n"]["ok"]:
        status = "degradado"
    else:
        status = "ok"

    return status, verificacoes


def _tipo_do_erro(verificacao):
    """'OperationalError: ...' -> 'OperationalError'."""
    detalhe = verificacao.get("detalhe", "")
    return detalhe.split(":", 1)[0].strip() if detalhe else ""


def resumo(status, verificacoes, detalhado=False):
    """Uma linha para o alerta, com o que falhou primeiro.

    Ex.: "FALHA: banco (ConnectionTimeout)" ou
    "DEGRADADO: n8n (ConnectionError)". O Uptime Kuma mostra só o
    começo da resposta na mensagem do alerta, por isso a ordem importa.
    O tipo do erro só aparece com a chave do monitoramento.
    """
    if status == "ok":
        return "SISTEMA OK"

    falhas = []

    for nome in PARTES:
        verificacao = verificacoes.get(nome)

        if verificacao is None or verificacao["ok"]:
            continue

        if nome == "tabelas":
            if not verificacoes["banco"]["ok"]:
                continue  # sem banco, as tabelas não foram lidas
            texto = "tabela " + ", ".join(sorted(verificacao["falhas"]))
        else:
            texto = nome

            if detalhado and _tipo_do_erro(verificacao):
                texto += f" ({_tipo_do_erro(verificacao)})"

        falhas.append(texto)

    return f"{status.upper()}: " + " | ".join(falhas)


def agora_iso():
    return datetime.now(timezone.utc).isoformat()
