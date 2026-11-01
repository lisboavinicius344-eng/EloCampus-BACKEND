"""Lembretes de devolução, entregues ao n8n para envio por e-mail.

O n8n chama POST /api/lembretes/processar de hora em hora. O backend
escolhe quem precisa de lembrete, marca o empréstimo (para não repetir)
e devolve os e-mails prontos: o n8n só envia.

- Véspera: 24 h antes do prazo, uma vez, só em empréstimos de mais de
  1 dia (num empréstimo de horas, chegaria logo depois da retirada).
- Atraso: a cada 24 h até a devolução, com cópia para quem registrou o
  empréstimo.
"""
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from database.conexao import Conexao


FUSO = ZoneInfo("America/Sao_Paulo")
LINK_ACESSO = "https://elocampus.com.br/"

# Empréstimos em andamento com algum item ainda fora, de quem tem e-mail.
_PENDENTE = """
    e.status = 'em_andamento'
    AND s.email IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM itens_emprestimo ie
        WHERE ie.emprestimo_id = e.id AND ie.data_devolucao IS NULL
    )
"""

SQL_VESPERA = f"""
    SELECT e.id
    FROM emprestimos e
    JOIN solicitantes s ON s.id = e.solicitante_id
    WHERE {_PENDENTE}
      AND e.lembrete_vespera_em IS NULL
      AND e.data_prevista_devolucao > NOW()
      AND e.data_prevista_devolucao <= NOW() + INTERVAL '24 hours'
      AND e.data_prevista_devolucao - e.data_emprestimo > INTERVAL '24 hours'
    FOR UPDATE OF e SKIP LOCKED
"""

# 23 h, e não 24: o agendamento do n8n pode atrasar alguns minutos.
SQL_ATRASO = f"""
    SELECT e.id
    FROM emprestimos e
    JOIN solicitantes s ON s.id = e.solicitante_id
    WHERE {_PENDENTE}
      AND e.data_prevista_devolucao < NOW()
      AND (e.lembrete_atraso_em IS NULL
           OR e.lembrete_atraso_em < NOW() - INTERVAL '23 hours')
    FOR UPDATE OF e SKIP LOCKED
"""


def _data_local(valor):
    return valor.astimezone(FUSO).strftime("%d/%m/%Y às %H:%M")


class LembreteService:

    def processar(self, simular=False):
        """Devolve os lembretes a enviar agora.

        simular=True só mostra, sem marcar como enviados.
        """
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(SQL_VESPERA)
                vespera = [r[0] for r in cursor.fetchall()]
                cursor.execute(SQL_ATRASO)
                atraso = [r[0] for r in cursor.fetchall()]

                if not simular:
                    if vespera:
                        cursor.execute("""
                            UPDATE emprestimos
                            SET lembrete_vespera_em = NOW()
                            WHERE id = ANY(%s)
                        """, (vespera,))
                    if atraso:
                        cursor.execute("""
                            UPDATE emprestimos
                            SET lembrete_atraso_em = NOW()
                            WHERE id = ANY(%s)
                        """, (atraso,))

                lembretes = [
                    self._montar(cursor, emprestimo_id, "vespera")
                    for emprestimo_id in vespera
                ] + [
                    self._montar(cursor, emprestimo_id, "atraso")
                    for emprestimo_id in atraso
                ]

        return lembretes

    @staticmethod
    def _montar(cursor, emprestimo_id, tipo):
        cursor.execute("""
            SELECT e.id, e.data_prevista_devolucao, s.nome, s.email,
                   u.nome, u.email
            FROM emprestimos e
            JOIN solicitantes s ON s.id = e.solicitante_id
            JOIN usuarios u ON u.id = e.usuario_responsavel_id
            WHERE e.id = %s
        """, (emprestimo_id,))
        _, prevista, nome, email, responsavel, responsavel_email = (
            cursor.fetchone()
        )

        cursor.execute("""
            SELECT eq.nome, eq.numero_patrimonio
            FROM itens_emprestimo ie
            JOIN equipamentos eq ON eq.id = ie.equipamento_id
            WHERE ie.emprestimo_id = %s AND ie.data_devolucao IS NULL
            ORDER BY ie.id
        """, (emprestimo_id,))
        itens = [
            {"nome": r[0], "patrimonio": r[1]} for r in cursor.fetchall()
        ]

        agora = datetime.now(timezone.utc)
        dias_atraso = max((agora - prevista).days, 0) if tipo == "atraso" else 0
        itens_texto = ", ".join(
            f"{i['nome']} ({i['patrimonio']})" if i["patrimonio"] else i["nome"]
            for i in itens
        )
        primeiro_nome = nome.split()[0]
        data = _data_local(prevista)

        if tipo == "vespera":
            assunto = "ELO Campus - lembrete: devolução amanhã"
            titulo = "Lembrete de devolução"
            texto = (
                f"A devolução de <strong>{escape(itens_texto)}</strong> está "
                f"prevista para <strong>{data}</strong>. Leve o(s) "
                "equipamento(s) até a equipe do acervo dentro do prazo."
            )
            aviso = (
                "Precisa de mais tempo? Fale com a equipe antes do prazo."
            )
        else:
            quando = (
                "desde hoje" if dias_atraso == 0
                else f"há {dias_atraso} dia{'s' if dias_atraso > 1 else ''}"
            )
            assunto = f"ELO Campus - devolução atrasada ({quando})"
            titulo = "Devolução atrasada"
            texto = (
                f"A devolução de <strong>{escape(itens_texto)}</strong> "
                f"estava prevista para <strong>{data}</strong> e está "
                f"atrasada {quando}. Devolva o quanto antes à equipe do "
                "acervo."
            )
            aviso = (
                "Enquanto houver devolução atrasada, não é possível fazer "
                "novas reservas nem empréstimos."
            )

        # No atraso, quem registrou o empréstimo recebe uma cópia.
        copia = responsavel_email if tipo == "atraso" else None

        return {
            "tipo": tipo,
            "emprestimo_id": emprestimo_id,
            "para": email,
            "copia": copia,
            # Pronto para o campo "To" do Gmail no n8n.
            "destinatarios": ", ".join(filter(None, (email, copia))),
            "solicitante": {"nome": nome, "email": email},
            "responsavel": {"nome": responsavel, "email": responsavel_email},
            "itens": itens,
            "itens_texto": itens_texto,
            "data_prevista_devolucao": prevista.isoformat(),
            "data_prevista_formatada": data,
            "dias_atraso": dias_atraso,
            "assunto": assunto,
            "mensagem_html": _html(primeiro_nome, titulo, texto, aviso),
        }


def _html(primeiro_nome, titulo, texto, aviso):
    """O mesmo visual dos e-mails de senha do ELO Campus."""
    return f"""<div style="margin:0;padding:24px 12px;background:#f3f1fb;font-family:Arial,Helvetica,sans-serif;color:#1f1b2e">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e4def7">
    <div style="background:linear-gradient(135deg,#7c3aed,#c026d3);padding:22px 28px;color:#ffffff">
      <div style="font-size:13px;letter-spacing:2px;text-transform:uppercase;opacity:.85">ELO Campus</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px">{escape(titulo)}</div>
    </div>
    <div style="padding:26px 28px;font-size:15px;line-height:1.55">
      <p style="margin:0 0 14px">Olá, <strong>{escape(primeiro_nome)}</strong>!</p>
      <p style="margin:0 0 14px">{texto}</p>
      <p style="text-align:center;margin:22px 0">
        <a href="{LINK_ACESSO}" style="background:#7c3aed;color:#ffffff;text-decoration:none;padding:12px 26px;border-radius:999px;font-weight:bold;display:inline-block">Ver meus empréstimos</a>
      </p>
      <p style="margin:0;padding:12px 14px;background:#fff7ed;border-radius:10px;font-size:13px;color:#7c2d12">{escape(aviso)}</p>
    </div>
    <div style="padding:14px 28px;background:#faf9fe;font-size:12px;color:#8a84a0;border-top:1px solid #eee9fb">
      Mensagem automática do ELO Campus. Não responda este e-mail.
    </div>
  </div>
</div>"""
