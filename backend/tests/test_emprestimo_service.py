import pytest
from unittest.mock import MagicMock, patch

from services.emprestimo_service import EmprestimoService


@pytest.mark.parametrize(
    ("estado", "status_esperado"),
    [
        ("bom", "disponivel"),
        ("regular", "disponivel"),
        ("danificado", "manutencao"),
    ],
)
def test_devolucao_define_status_do_equipamento(
    estado, status_esperado
):
    servico = EmprestimoService()

    conexao = MagicMock()
    cursor = MagicMock()

    conexao.__enter__.return_value = conexao
    conexao.__exit__.return_value = False
    conexao.cursor.return_value.__enter__.return_value = cursor
    conexao.cursor.return_value.__exit__.return_value = False

    # Empréstimo em andamento, usuário ativo, item não devolvido
    # e nenhum item pendente depois da devolução.
    cursor.fetchone.side_effect = [
        ("em_andamento",),
        (1,),
        (10, "emprestado"),
        (0,),
    ]

    with (
        patch(
            "services.emprestimo_service.Conexao.conectar",
            return_value=conexao,
        ),
        patch.object(
            servico,
            "obter_por_id",
            return_value={"id": 5, "status": "concluido"},
        ),
        patch(
            "services.emprestimo_service.abrir_automatica"
        ) as abrir_manutencao,
    ):
        resultado = servico.devolver_equipamento(
            emprestimo_id=5,
            equipamento_id=10,
            estado_na_devolucao=estado,
            usuario_id="00000000-0000-4000-8000-000000000002",
        )

    assert resultado["status"] == "concluido"

    # Devolvido danificado abre a manutenção na mesma transação.
    assert abrir_manutencao.called == (estado == "danificado")

    atualizacoes = [
        chamada
        for chamada in cursor.execute.call_args_list
        if "UPDATE equipamentos" in chamada.args[0]
    ]

    assert len(atualizacoes) == 1
    parametros = atualizacoes[0].args[1]

    assert parametros == (status_esperado, estado, 10)


@pytest.mark.parametrize("estado", ["quebrado", "novo"])
def test_devolucao_rejeita_estado_de_conservacao_invalido(estado):
    servico = EmprestimoService()

    with pytest.raises(
        ValueError, match="Estado na devolução inválido"
    ):
        servico.devolver_equipamento(
            emprestimo_id=5,
            equipamento_id=10,
            estado_na_devolucao=estado,
            usuario_id="00000000-0000-4000-8000-000000000002",
        )


def test_devolucao_rejeita_usuario_responsavel_invalido():
    servico = EmprestimoService()

    with pytest.raises(
        ValueError, match="usuário responsável válido"
    ):
        servico.devolver_equipamento(
            emprestimo_id=5,
            equipamento_id=10,
            estado_na_devolucao="bom",
            usuario_id=True,
        )


def test_devolucao_rejeita_emprestimo_inexistente():
    servico = EmprestimoService()

    conexao = MagicMock()
    cursor = MagicMock()

    conexao.__enter__.return_value = conexao
    conexao.__exit__.return_value = False
    conexao.cursor.return_value.__enter__.return_value = cursor

    cursor.fetchone.return_value = None

    with patch(
        "services.emprestimo_service.Conexao.conectar",
        return_value=conexao,
    ):
        with pytest.raises(
            ValueError, match="Empréstimo não encontrado"
        ):
            servico.devolver_equipamento(
                emprestimo_id=5,
                equipamento_id=10,
                estado_na_devolucao="bom",
                usuario_id="00000000-0000-4000-8000-000000000002",
            )
