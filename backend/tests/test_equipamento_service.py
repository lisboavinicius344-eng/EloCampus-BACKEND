import pytest

from services.equipamento_service import EquipamentoService


@pytest.mark.parametrize(
    ("estado", "status_esperado"),
    [
        ("novo", "disponivel"),
        ("bom", "disponivel"),
        ("regular", "disponivel"),
        ("danificado", "manutencao"),
    ],
)
def test_status_automatico_por_estado(estado, status_esperado):
    dados = {
        "nome": "Equipamento de teste",
        "categoria_id": 1,
        "estado_conservacao": estado,
    }

    resultado = EquipamentoService._validar_dados(dados)

    assert resultado["status"] == status_esperado


def test_cliente_nao_define_status_operacional():
    dados = {
        "nome": "Equipamento de teste",
        "categoria_id": 1,
        "estado_conservacao": "bom",
        "status": "emprestado",
    }

    resultado = EquipamentoService._validar_dados(dados)

    assert resultado["status"] == "disponivel"


def test_equipamento_danificado_nao_fica_disponivel():
    dados = {
        "nome": "Equipamento de teste",
        "categoria_id": 1,
        "estado_conservacao": "danificado",
        "status": "disponivel",
    }

    resultado = EquipamentoService._validar_dados(dados)

    assert resultado["status"] == "manutencao"


from unittest.mock import MagicMock, patch


@pytest.mark.parametrize(
    ("status_atual", "estado_atual", "novo_estado", "status_esperado"),
    [
        ("disponivel", "bom", "danificado", "manutencao"),
        ("manutencao", "danificado", "bom", "disponivel"),
        ("manutencao", "danificado", "regular", "disponivel"),
        ("manutencao", "danificado", "novo", "disponivel"),
        ("baixado", "danificado", "bom", "baixado"),
    ],
)
def test_atualizar_define_status_automaticamente(
    status_atual, estado_atual, novo_estado, status_esperado
):
    servico = EquipamentoService()

    conexao = MagicMock()
    cursor = MagicMock()

    conexao.__enter__.return_value = conexao
    conexao.__exit__.return_value = False
    conexao.cursor.return_value.__enter__.return_value = cursor
    conexao.cursor.return_value.__exit__.return_value = False

    cursor.fetchone.side_effect = [
        (1, status_atual, estado_atual),
        (1,),
    ]

    with (
        patch(
            "services.equipamento_service.Conexao.conectar",
            return_value=conexao,
        ),
        patch.object(
            servico,
            "_validar_dados",
            return_value={
                "nome": "Equipamento teste",
                "numero_patrimonio": "PAT-TESTE",
                "categoria_id": 1,
                "setor": "Teste",
                "localizacao": "Sala teste",
                "estado_conservacao": novo_estado,
                "qr_code": None,
                "observacoes": None,
                "status": "disponivel",
            },
        ),
        patch.object(
            servico,
            "obter_por_id",
            return_value={"id": 1, "status": status_esperado},
        ),
    ):
        resultado = servico.atualizar(1, {})

    assert resultado["status"] == status_esperado

    chamadas_update = [
        chamada
        for chamada in cursor.execute.call_args_list
        if "UPDATE equipamentos" in chamada.args[0]
    ]

    assert len(chamadas_update) == 1
    parametros_update = chamadas_update[0].args[1]
    assert parametros_update[6] == status_esperado


def test_atualizar_bloqueia_mudanca_de_conservacao_em_emprestado():
    servico = EquipamentoService()

    conexao = MagicMock()
    cursor = MagicMock()

    conexao.__enter__.return_value = conexao
    conexao.__exit__.return_value = False
    conexao.cursor.return_value.__enter__.return_value = cursor
    conexao.cursor.return_value.__exit__.return_value = False

    cursor.fetchone.return_value = (1, "emprestado", "bom")

    with (
        patch(
            "services.equipamento_service.Conexao.conectar",
            return_value=conexao,
        ),
        patch.object(
            servico,
            "_validar_dados",
            return_value={
                "nome": "Equipamento teste",
                "numero_patrimonio": "PAT-TESTE",
                "categoria_id": 1,
                "setor": "Teste",
                "localizacao": "Sala teste",
                "estado_conservacao": "danificado",
                "qr_code": None,
                "observacoes": None,
                "status": "manutencao",
            },
        ),
    ):
        with pytest.raises(ValueError, match="equipamento emprestado"):
            servico.atualizar(1, {})

    assert not any(
        "UPDATE equipamentos" in chamada.args[0]
        for chamada in cursor.execute.call_args_list
    )


def test_categoria_pode_vir_pelo_nome():
    resultado = EquipamentoService._validar_dados({
        "nome": "Projetor",
        "categoria": "  Projetores   multimídia ",
    })

    assert resultado["categoria_id"] is None
    assert resultado["categoria_nome"] == "Projetores multimídia"


def test_categoria_id_tem_prioridade_sobre_o_nome():
    resultado = EquipamentoService._validar_dados({
        "nome": "Projetor",
        "categoria_id": "3",
        "categoria": "Outra",
    })

    assert resultado["categoria_id"] == 3
    assert resultado["categoria_nome"] is None


@pytest.mark.parametrize("dados", [{}, {"categoria": "   "}, {"categoria": 5}])
def test_categoria_obrigatoria(dados):
    with pytest.raises(ValueError, match="categoria"):
        EquipamentoService._validar_dados({"nome": "Projetor", **dados})


def test_resolver_categoria_desativada_e_recusada():
    cursor = MagicMock()
    cursor.fetchone.return_value = (4, "Projetores", False)

    with pytest.raises(ValueError, match="desativada"):
        EquipamentoService._resolver_categoria(
            cursor, {"categoria_id": None, "categoria_nome": "projetores"}
        )
