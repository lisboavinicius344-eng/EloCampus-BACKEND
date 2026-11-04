"""Relatórios do acervo: consultas para a equipe e o e-mail semanal.

Os períodos são dias completos no horário de Brasília. O relatório
semanal cobre os 7 dias anteriores ao dia em que é gerado, sem contar
esse dia, que ainda não terminou.
"""
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from database.conexao import Conexao
from services import regras
from services.painel_service import PainelService


FUSO = ZoneInfo("America/Sao_Paulo")
PERIODO_MAXIMO_DIAS = 366
LIMITE_PADRAO = 10
LIMITE_MAXIMO = 100

# Empréstimos com item fora e prazo vencido, os mais antigos primeiro.
SQL_ATRASADOS = """
    SELECT
        e.id,
        s.nome,
        s.email,
        e.data_prevista_devolucao,
        STRING_AGG(
            eq.nome || COALESCE(' (' || eq.numero_patrimonio || ')', ''),
            ', ' ORDER BY ie.id
        )
    FROM emprestimos e
    JOIN solicitantes s ON s.id = e.solicitante_id
    JOIN itens_emprestimo ie
        ON ie.emprestimo_id = e.id AND ie.data_devolucao IS NULL
    JOIN equipamentos eq ON eq.id = ie.equipamento_id
    WHERE e.status = 'em_andamento'
      AND e.data_prevista_devolucao < NOW()
    GROUP BY e.id, s.nome, s.email, e.data_prevista_devolucao
    ORDER BY e.data_prevista_devolucao
"""

SQL_MAIS_EMPRESTADOS = """
    SELECT
        eq.id,
        eq.nome,
        eq.numero_patrimonio,
        COUNT(*) AS vezes
    FROM itens_emprestimo ie
    JOIN emprestimos e ON e.id = ie.emprestimo_id
    JOIN equipamentos eq ON eq.id = ie.equipamento_id
    WHERE e.data_emprestimo >= %s AND e.data_emprestimo < %s
    GROUP BY eq.id, eq.nome, eq.numero_patrimonio
    ORDER BY vezes DESC, eq.nome
    LIMIT %s
"""

SQL_MANUTENCOES_EM_ABERTO = """
    SELECT
        m.id,
        eq.nome,
        eq.numero_patrimonio,
        m.descricao_problema,
        m.data_abertura
    FROM manutencoes m
    JOIN equipamentos eq ON eq.id = m.equipamento_id
    WHERE m.status IN ('aberta', 'em_andamento')
    ORDER BY m.data_abertura
"""


def _ler_data(valor, campo):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(
            f"Informe {campo} no formato AAAA-MM-DD."
        ) from None


def _instante(dia):
    return datetime(dia.year, dia.month, dia.day, tzinfo=FUSO)


def periodo(inicio=None, fim=None):
    """Devolve (primeiro_dia, ultimo_dia), incluindo os dois.

    Sem datas, usa os últimos 7 dias, contando hoje.
    """
    hoje = datetime.now(FUSO).date()
    ultimo = _ler_data(fim, "a data final") if fim else hoje
    primeiro = (
        _ler_data(inicio, "a data inicial") if inicio
        else ultimo - timedelta(days=6)
    )

    if ultimo < primeiro:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")

    if (ultimo - primeiro).days >= PERIODO_MAXIMO_DIAS:
        raise ValueError(
            f"O período pode ter no máximo {PERIODO_MAXIMO_DIAS} dias."
        )

    return primeiro, ultimo


def periodo_semanal():
    """Os 7 dias completos anteriores a hoje."""
    hoje = datetime.now(FUSO).date()
    return hoje - timedelta(days=7), hoje - timedelta(days=1)


def limite(valor):
    if valor in (None, ""):
        return LIMITE_PADRAO

    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError("O limite deve ser um número inteiro.") from None

    if not 1 <= numero <= LIMITE_MAXIMO:
        raise ValueError(f"O limite deve estar entre 1 e {LIMITE_MAXIMO}.")

    return numero


def _dias_de_atraso(prevista):
    return max((datetime.now(timezone.utc) - prevista).days, 0)


class RelatorioService:

    def resumo(self, primeiro, ultimo):
        """Números do período e a situação atual do acervo."""
        inicio = _instante(primeiro)
        fim = _instante(ultimo + timedelta(days=1))

        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                regras.expirar_reservas(cursor)
                cursor.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM emprestimos
                         WHERE data_emprestimo >= %(i)s
                           AND data_emprestimo < %(f)s),
                        (SELECT COUNT(*) FROM itens_emprestimo ie
                         JOIN emprestimos e ON e.id = ie.emprestimo_id
                         WHERE e.data_emprestimo >= %(i)s
                           AND e.data_emprestimo < %(f)s),
                        (SELECT COUNT(*) FROM itens_emprestimo
                         WHERE data_devolucao >= %(i)s
                           AND data_devolucao < %(f)s),
                        (SELECT COUNT(*) FROM itens_emprestimo
                         WHERE data_devolucao >= %(i)s
                           AND data_devolucao < %(f)s
                           AND estado_na_devolucao = 'danificado'),
                        (SELECT COUNT(*) FROM manutencoes
                         WHERE data_abertura >= %(i)s
                           AND data_abertura < %(f)s),
                        (SELECT COUNT(*) FROM manutencoes
                         WHERE status = 'concluida'
                           AND data_conclusao >= %(i)s
                           AND data_conclusao < %(f)s),
                        (SELECT COUNT(*) FROM reservas
                         WHERE criado_em >= %(i)s AND criado_em < %(f)s),
                        (SELECT COUNT(*) FROM reservas
                         WHERE status = 'pendente'),
                        (SELECT COUNT(*) FROM manutencoes
                         WHERE status IN ('aberta', 'em_andamento')),
                        (SELECT COUNT(*) FROM solicitacoes_acesso
                         WHERE status = 'pendente')
                """, {"i": inicio, "f": fim})
                numeros = cursor.fetchone()

        return {
            "periodo": {
                "inicio": primeiro.isoformat(),
                "fim": ultimo.isoformat(),
            },
            "no_periodo": {
                "emprestimos": numeros[0],
                "itens_emprestados": numeros[1],
                "itens_devolvidos": numeros[2],
                "itens_devolvidos_danificados": numeros[3],
                "manutencoes_abertas": numeros[4],
                "manutencoes_concluidas": numeros[5],
                "reservas_criadas": numeros[6],
            },
            "agora": {
                "equipamentos": PainelService().resumo(),
                "reservas_pendentes": numeros[7],
                "manutencoes_em_aberto": numeros[8],
                "solicitacoes_acesso_pendentes": numeros[9],
            },
        }

    def atrasados(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(SQL_ATRASADOS)
                registros = cursor.fetchall()

        return [
            {
                "emprestimo_id": r[0],
                "solicitante": r[1],
                "email": r[2],
                "data_prevista_devolucao": r[3].isoformat(),
                "dias_atraso": _dias_de_atraso(r[3]),
                "itens": r[4],
            }
            for r in registros
        ]

    def mais_emprestados(self, primeiro, ultimo, quantidade=LIMITE_PADRAO):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(SQL_MAIS_EMPRESTADOS, (
                    _instante(primeiro),
                    _instante(ultimo + timedelta(days=1)),
                    quantidade,
                ))
                registros = cursor.fetchall()

        return [
            {
                "equipamento_id": r[0],
                "nome": r[1],
                "numero_patrimonio": r[2],
                "vezes": r[3],
            }
            for r in registros
        ]

    def manutencoes_em_aberto(self):
        with Conexao.conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(SQL_MANUTENCOES_EM_ABERTO)
                registros = cursor.fetchall()

        return [
            {
                "manutencao_id": r[0],
                "equipamento": r[1],
                "numero_patrimonio": r[2],
                "descricao_problema": r[3],
                "data_abertura": r[4].isoformat(),
            }
            for r in registros
        ]

    def semanal(self):
        """O relatório semanal, com o e-mail pronto para o n8n enviar."""
        primeiro, ultimo = periodo_semanal()
        resumo = self.resumo(primeiro, ultimo)
        atrasados = self.atrasados()
        mais_emprestados = self.mais_emprestados(primeiro, ultimo, 5)
        manutencoes = self.manutencoes_em_aberto()
        rotulo = f"{primeiro:%d/%m} a {ultimo:%d/%m/%Y}"

        return {
            **resumo,
            "atrasados": atrasados,
            "mais_emprestados": mais_emprestados,
            "manutencoes_em_aberto": manutencoes,
            "assunto": f"ELO Campus - relatório semanal ({rotulo})",
            "mensagem_html": _html(
                rotulo, resumo, atrasados, mais_emprestados, manutencoes
            ),
        }


def _linhas(pares):
    return "".join(
        '<tr><td style="padding:7px 0;border-bottom:1px solid #eee9fb">'
        f"{escape(rotulo)}</td>"
        '<td style="padding:7px 0;border-bottom:1px solid #eee9fb;'
        f'text-align:right;font-weight:bold">{valor}</td></tr>'
        for rotulo, valor in pares
    )


def _tabela(titulo, pares):
    return (
        f'<h3 style="margin:22px 0 8px;font-size:16px">{escape(titulo)}</h3>'
        '<table style="width:100%;border-collapse:collapse;font-size:14px">'
        f"{_linhas(pares)}</table>"
    )


def _lista(titulo, itens, vazio):
    corpo = (
        '<ul style="margin:0;padding-left:20px;font-size:14px">'
        + "".join(
            f'<li style="margin-bottom:6px">{item}</li>' for item in itens
        )
        + "</ul>"
        if itens
        else f'<p style="margin:0;font-size:14px;color:#5b5570">{escape(vazio)}</p>'
    )
    return (
        f'<h3 style="margin:22px 0 8px;font-size:16px">{escape(titulo)}</h3>'
        f"{corpo}"
    )


def _html(rotulo, resumo, atrasados, mais_emprestados, manutencoes):
    periodo_ = resumo["no_periodo"]
    agora = resumo["agora"]
    acervo = agora["equipamentos"]

    def com_patrimonio(nome, patrimonio):
        texto = escape(nome)
        return f"{texto} ({escape(patrimonio)})" if patrimonio else texto

    return f"""<div style="margin:0;padding:24px 12px;background:#f3f1fb;font-family:Arial,Helvetica,sans-serif;color:#1f1b2e">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e4def7">
    <div style="background:linear-gradient(135deg,#7c3aed,#c026d3);padding:22px 28px;color:#ffffff">
      <div style="font-size:13px;letter-spacing:2px;text-transform:uppercase;opacity:.85">ELO Campus</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px">Relatório semanal</div>
      <div style="font-size:14px;margin-top:4px">{escape(rotulo)}</div>
    </div>
    <div style="padding:6px 28px 26px;line-height:1.5">
      {_tabela("Na semana", [
          ("Empréstimos registrados", periodo_["emprestimos"]),
          ("Itens emprestados", periodo_["itens_emprestados"]),
          ("Itens devolvidos", periodo_["itens_devolvidos"]),
          ("Itens devolvidos danificados", periodo_["itens_devolvidos_danificados"]),
          ("Reservas criadas", periodo_["reservas_criadas"]),
          ("Manutenções abertas", periodo_["manutencoes_abertas"]),
          ("Manutenções concluídas", periodo_["manutencoes_concluidas"]),
      ])}
      {_tabela("Situação atual", [
          ("Equipamentos no acervo", acervo["total"]),
          ("Disponíveis", acervo["disponiveis"]),
          ("Emprestados", acervo["emprestados"]),
          ("Em atraso", acervo["atrasados"]),
          ("Em manutenção", acervo["manutencao"]),
          ("Inativos", acervo["inativos"]),
          ("Reservas aguardando análise", agora["reservas_pendentes"]),
          ("Solicitações de acesso pendentes", agora["solicitacoes_acesso_pendentes"]),
      ])}
      {_lista("Devoluções em atraso", [
          f"<strong>{escape(a['solicitante'])}</strong>: {escape(a['itens'])} "
          f"({a['dias_atraso']} dia(s) de atraso)"
          for a in atrasados
      ], "Nenhuma devolução em atraso.")}
      {_lista("Manutenções em aberto", [
          f"<strong>{com_patrimonio(m['equipamento'], m['numero_patrimonio'])}</strong>: "
          f"{escape(m['descricao_problema'])}"
          for m in manutencoes
      ], "Nenhuma manutenção em aberto.")}
      {_lista("Mais emprestados na semana", [
          f"{com_patrimonio(e['nome'], e['numero_patrimonio'])}: {e['vezes']} vez(es)"
          for e in mais_emprestados
      ], "Nenhum empréstimo na semana.")}
    </div>
    <div style="padding:14px 28px;background:#faf9fe;font-size:12px;color:#8a84a0;border-top:1px solid #eee9fb">
      Mensagem automática do ELO Campus. Não responda este e-mail.
    </div>
  </div>
</div>"""
