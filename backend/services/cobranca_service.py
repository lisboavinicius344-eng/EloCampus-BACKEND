"""Cobrança de devolução por e-mail, disparada pela equipe.

O e-mail sai na hora pelo workflow "enviar-email" do n8n, que só recebe o
e-mail pronto e envia. Cada cobrança vai para o histórico dos itens.
"""
from datetime import datetime, timedelta, timezone
from html import escape

from database.conexao import Conexao
from services import historico_service
from services.lembrete_service import _data_local, _html
from services.n8n_service import _notificar, url_webhook


# Evita cobrar a mesma pessoa várias vezes seguidas por engano.
INTERVALO_MINIMO = timedelta(minutes=10)
WEBHOOK = "N8N_EMAIL_WEBHOOK_URL"


class EnvioIndisponivel(Exception):
    """O e-mail não saiu: n8n fora do ar ou webhook não configurado."""


class CobrancaService:

    def cobrar(self, emprestimo_id, usuario):
        """Envia a cobrança e retorna os dados do envio, ou None se não existe."""
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT e.status, e.data_prevista_devolucao,
                           s.nome, s.email
                    FROM emprestimos e
                    JOIN solicitantes s ON s.id = e.solicitante_id
                    WHERE e.id = %s
                """, (emprestimo_id,))
                registro = cursor.fetchone()

                if registro is None:
                    return None

                status, prevista, nome, email = registro

                if status != "em_andamento":
                    raise ValueError("Só é possível cobrar um empréstimo em andamento.")

                if not email:
                    raise ValueError(
                        "Esta pessoa não tem e-mail no cadastro. Atualize o "
                        "solicitante para poder enviar a cobrança."
                    )

                cursor.execute("""
                    SELECT eq.id, eq.nome, eq.numero_patrimonio
                    FROM itens_emprestimo ie
                    JOIN equipamentos eq ON eq.id = ie.equipamento_id
                    WHERE ie.emprestimo_id = %s AND ie.data_devolucao IS NULL
                    ORDER BY ie.id
                """, (emprestimo_id,))
                itens = cursor.fetchall()

                if not itens:
                    raise ValueError("Todos os itens deste empréstimo já foram devolvidos.")

                cursor.execute("""
                    SELECT MAX(data_movimentacao)
                    FROM historico_movimentacoes
                    WHERE emprestimo_id = %s AND tipo_movimentacao = 'cobranca'
                """, (emprestimo_id,))
                ultima = cursor.fetchone()[0]
                agora = datetime.now(timezone.utc)

                if ultima and agora - ultima < INTERVALO_MINIMO:
                    raise ValueError(
                        "Uma cobrança já foi enviada às "
                        f"{_data_local(ultima)[-5:]}. Aguarde alguns minutos "
                        "antes de enviar outra."
                    )

        mensagem = self._mensagem(nome, email, prevista, itens, agora)

        if not url_webhook(WEBHOOK):
            raise EnvioIndisponivel(
                "O envio de cobranças não está configurado no servidor."
            )

        if not _notificar(WEBHOOK, "email", mensagem):
            raise EnvioIndisponivel(
                "Não foi possível enviar o e-mail agora. Tente de novo em "
                "instantes."
            )

        # Só registra depois que o n8n aceitou o envio.
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                for equipamento_id, _, _ in itens:
                    historico_service.registrar(
                        cursor, equipamento_id, usuario["id"], "cobranca",
                        f"Cobrança de devolução enviada por e-mail para "
                        f"{email} por {usuario['nome']}.",
                        emprestimo_id,
                    )

        return {"para": email, "assunto": mensagem["assunto"]}

    @staticmethod
    def _mensagem(nome, email, prevista, itens, agora):
        itens_texto = ", ".join(
            f"{n} ({p})" if p else n for _, n, p in itens
        )
        data = _data_local(prevista)
        atrasado = prevista < agora

        if atrasado:
            dias = (agora - prevista).days
            quando = "desde hoje" if dias == 0 else f"há {dias} dia{'s' if dias > 1 else ''}"
            assunto = f"ELO Campus - cobrança: devolução atrasada ({quando})"
            texto = (
                f"A devolução de <strong>{escape(itens_texto)}</strong> estava "
                f"prevista para <strong>{data}</strong> e está atrasada "
                f"{quando}. Devolva o quanto antes à equipe do acervo."
            )
            aviso = (
                "Enquanto houver devolução atrasada, não é possível fazer "
                "novas reservas nem empréstimos."
            )
        else:
            assunto = "ELO Campus - lembrete da equipe: devolução de equipamento"
            texto = (
                f"A equipe do acervo lembra que a devolução de "
                f"<strong>{escape(itens_texto)}</strong> está prevista para "
                f"<strong>{data}</strong>."
            )
            aviso = "Precisa de mais tempo? Fale com a equipe antes do prazo."

        return {
            "para": email,
            "destinatarios": email,
            "assunto": assunto,
            "mensagem_html": _html(nome.split()[0], "Devolução de equipamento", texto, aviso),
        }
