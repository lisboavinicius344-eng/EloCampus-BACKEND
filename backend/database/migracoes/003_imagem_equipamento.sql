-- =====================================================================
-- MIGRAÇÃO 003 - Foto dos equipamentos
-- =====================================================================
--
-- Para bancos criados ANTES desta mudança. Bancos novos já recebem
-- estas colunas pelo schema.sql e não precisam rodar este arquivo.
--
--   psql -h <host> -U <usuario> -d <banco> -v ON_ERROR_STOP=1 \
--        -f 003_imagem_equipamento.sql
--
-- É seguro rodar mais de uma vez. Não altera dados existentes.
-- =====================================================================

BEGIN;

ALTER TABLE equipamentos
    ADD COLUMN IF NOT EXISTS imagem BYTEA,
    ADD COLUMN IF NOT EXISTS imagem_tipo VARCHAR(20),
    ADD COLUMN IF NOT EXISTS imagem_atualizada_em TIMESTAMPTZ;

ALTER TABLE equipamentos
    DROP CONSTRAINT IF EXISTS equipamentos_imagem_completa,
    DROP CONSTRAINT IF EXISTS equipamentos_imagem_tipo_valido,
    DROP CONSTRAINT IF EXISTS equipamentos_imagem_tamanho;

ALTER TABLE equipamentos
    ADD CONSTRAINT equipamentos_imagem_completa
        CHECK ((imagem IS NULL) = (imagem_tipo IS NULL)),
    ADD CONSTRAINT equipamentos_imagem_tipo_valido
        CHECK (imagem_tipo IN ('image/png', 'image/jpeg', 'image/webp', 'image/gif')),
    ADD CONSTRAINT equipamentos_imagem_tamanho
        CHECK (octet_length(imagem) <= 3145728);

COMMENT ON COLUMN equipamentos.imagem IS
    'Foto do equipamento (até 3 MB). Servida publicamente em GET /api/equipamentos/<id>/imagem.';
COMMENT ON COLUMN equipamentos.imagem_atualizada_em IS
    'Muda a cada troca de imagem; entra na URL (?v=) para o navegador não usar a versão antiga em cache.';

COMMIT;
