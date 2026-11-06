"""Lembretes de devolução, entregues ao n8n para envio por e-mail.

O n8n chama POST /api/lembretes/processar de hora em hora. O backend
escolhe quem precisa de lembrete, marca o empréstimo (para não repetir)
e devolve os e-mails prontos: o n8n só envia.

- Véspera: 24 h antes do prazo, uma vez, só em empréstimos de mais de
  1 dia (num empréstimo de horas, chegaria logo depois da retirada).
- Atraso: a cada 24 h até a devolução, com cópia para quem registrou o
  empréstimo.
- Alerta de atraso para a administração: junto com cada aviso de atraso,
  um e-mail para os administradores ativos, com os itens e os dados de
  contato da pessoa.
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

                admins = self._emails_dos_admins(cursor) if atraso else []

                lembretes = [
                    self._montar(cursor, emprestimo_id, "vespera")
                    for emprestimo_id in vespera
                ] + [
                    self._montar(cursor, emprestimo_id, "atraso", admins)
                    for emprestimo_id in atraso
                ]

                if admins:
                    lembretes += [
                        self._montar_alerta_admin(cursor, emprestimo_id, admins)
                        for emprestimo_id in atraso
                    ]

        return lembretes

    @staticmethod
    def _emails_dos_admins(cursor):
        cursor.execute("""
            SELECT email
            FROM usuarios
            WHERE papel = 'admin' AND ativo = TRUE AND email IS NOT NULL
            ORDER BY email
        """)
        return [r[0] for r in cursor.fetchall()]

    @staticmethod
    def _montar_alerta_admin(cursor, emprestimo_id, admins):
        """E-mail para a administração: o que está atrasado e com quem."""
        cursor.execute("""
            SELECT e.data_prevista_devolucao, e.data_emprestimo,
                   s.nome, s.email, s.telefone, s.matricula, s.tipo,
                   u.nome
            FROM emprestimos e
            JOIN solicitantes s ON s.id = e.solicitante_id
            JOIN usuarios u ON u.id = e.usuario_responsavel_id
            WHERE e.id = %s
        """, (emprestimo_id,))
        (prevista, retirada, nome, email, telefone, matricula, tipo,
         responsavel) = cursor.fetchone()

        cursor.execute("""
            SELECT eq.nome, eq.numero_patrimonio
            FROM itens_emprestimo ie
            JOIN equipamentos eq ON eq.id = ie.equipamento_id
            WHERE ie.emprestimo_id = %s AND ie.data_devolucao IS NULL
            ORDER BY ie.id
        """, (emprestimo_id,))
        itens = [{"nome": r[0], "patrimonio": r[1]} for r in cursor.fetchall()]

        dias_atraso = max((datetime.now(timezone.utc) - prevista).days, 0)
        quando = (
            "desde hoje" if dias_atraso == 0
            else f"há {dias_atraso} dia{'s' if dias_atraso > 1 else ''}"
        )
        itens_texto = ", ".join(
            f"{i['nome']} ({i['patrimonio']})" if i["patrimonio"] else i["nome"]
            for i in itens
        )
        linhas = [
            ("Equipamento(s)", itens_texto),
            ("Pessoa", f"{nome} ({tipo})"),
            ("E-mail", email or "não informado"),
            ("Telefone", telefone or "não informado"),
            ("Matrícula", matricula or "não informada"),
            ("Retirada", _data_local(retirada)),
            ("Devolução prevista", _data_local(prevista)),
            ("Atraso", quando),
            ("Registrado por", responsavel),
        ]
        tabela = "".join(
            '<tr><td style="padding:6px 12px 6px 0;color:#5b5570;white-space:nowrap">'
            f"{escape(rotulo)}</td><td style=\"padding:6px 0\"><strong>"
            f"{escape(str(valor))}</strong></td></tr>"
            for rotulo, valor in linhas
        )
        texto = (
            "Há um empréstimo com devolução atrasada. Entre em contato com "
            "a pessoa ou registre a devolução no sistema."
            f'<table style="margin:16px 0 0;font-size:14px;border-collapse:collapse">{tabela}</table>'
        )

        return {
            "tipo": "atraso_admin",
            "emprestimo_id": emprestimo_id,
            "para": admins[0],
            "copia": None,
            "destinatarios": ", ".join(admins),
            "solicitante": {"nome": nome, "email": email},
            "itens": itens,
            "itens_texto": itens_texto,
            "data_prevista_devolucao": prevista.isoformat(),
            "data_prevista_formatada": _data_local(prevista),
            "dias_atraso": dias_atraso,
            "assunto": f"ELO Campus - atraso: {itens_texto} com {nome} ({quando})",
            "mensagem_html": _html(
                "equipe", "Devolução atrasada", texto,
                "Este aviso se repete a cada 24 horas até a devolução.",
                botao="Abrir o ELO Campus",
            ),
        }

    @staticmethod
    def _montar(cursor, emprestimo_id, tipo, admins=()):
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

        # No atraso, quem registrou o empréstimo recebe uma cópia, exceto
        # se for admin: os admins já recebem o alerta próprio.
        copia = (
            responsavel_email
            if tipo == "atraso" and responsavel_email not in admins
            else None
        )

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


def _html(primeiro_nome, titulo, texto, aviso, botao="Ver meus empréstimos"):
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
        <a href="{LINK_ACESSO}" style="background:#7c3aed;color:#ffffff;text-decoration:none;padding:12px 26px;border-radius:999px;font-weight:bold;display:inline-block">{escape(botao)}</a>
      </p>
      <p style="margin:0;padding:12px 14px;background:#fff7ed;border-radius:10px;font-size:13px;color:#7c2d12">{escape(aviso)}</p>
    </div>
    <div style="padding:14px 28px;background:#faf9fe;font-size:12px;color:#8a84a0;border-top:1px solid #eee9fb">
      Mensagem automática do ELO Campus. Não responda este e-mail.
    </div>
  </div>
</div>"""
