"""Limite de tentativas: protege o login e os formulários públicos.

Conta as tentativas em memória, numa janela de tempo. Cada processo do
servidor (gunicorn) tem a sua contagem, e um reinício zera tudo: é uma
barreira contra quem tenta milhares de senhas, não uma contabilidade
exata.
"""
import threading
import time
from collections import defaultdict, deque

from flask import request


class Limite:
    def __init__(self, maximo, janela_segundos):
        self.maximo = maximo
        self.janela = janela_segundos
        self._registros = defaultdict(deque)
        self._trava = threading.Lock()

    def _limpar_antigos(self, fila, agora):
        while fila and fila[0] <= agora - self.janela:
            fila.popleft()

    def espera(self, chave):
        """Segundos até liberar a chave (0 = liberada)."""
        agora = time.monotonic()

        with self._trava:
            fila = self._registros.get(chave)

            if not fila:
                return 0

            self._limpar_antigos(fila, agora)

            if len(fila) < self.maximo:
                return 0

            return max(1, int(fila[0] + self.janela - agora) + 1)

    def registrar(self, chave):
        agora = time.monotonic()

        with self._trava:
            fila = self._registros[chave]
            self._limpar_antigos(fila, agora)
            fila.append(agora)

    def zerar(self, chave):
        with self._trava:
            self._registros.pop(chave, None)

    def zerar_tudo(self):
        with self._trava:
            self._registros.clear()


# Login: 5 senhas erradas por conta ou 20 por endereço, em 15 minutos.
LOGIN_POR_EMAIL = Limite(5, 15 * 60)
LOGIN_POR_IP = Limite(20, 15 * 60)

# Formulários públicos que enviam e-mail ou geram trabalho para o admin.
ESQUECI_SENHA_POR_IP = Limite(10, 15 * 60)
SOLICITAR_ACESSO_POR_IP = Limite(5, 60 * 60)

TODOS = (
    LOGIN_POR_EMAIL, LOGIN_POR_IP, ESQUECI_SENHA_POR_IP,
    SOLICITAR_ACESSO_POR_IP,
)


def ip_do_cliente():
    """Endereço de quem fez a requisição.

    No Easypanel há um proxy (Traefik) na frente: ele acrescenta o
    endereço real ao FINAL do X-Forwarded-For. O começo pode ter sido
    escrito pelo próprio cliente, então vale o último valor.
    """
    encaminhado = request.headers.get("X-Forwarded-For", "")

    if encaminhado:
        return encaminhado.split(",")[-1].strip()

    return request.remote_addr or "desconhecido"


def mensagem_de_espera(segundos):
    minutos = max(1, round(segundos / 60))
    return (
        "Muitas tentativas. Aguarde "
        f"{minutos} minuto{'s' if minutos > 1 else ''} e tente novamente."
    )
