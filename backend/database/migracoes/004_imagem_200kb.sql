-- =====================================================================
-- MIGRAÇÃO 004 - Foto dos equipamentos com no máximo 200 KB
-- =====================================================================
--
-- O backend passou a comprimir as fotos para no máximo 200 KB. Esta
-- migração só aperta a regra do banco (era 3 MB). Requer a 003.
-- Bancos novos já recebem a regra pelo schema.sql.
--
--   psql -h <host> -U <usuario> -d <banco> -v ON_ERROR_STOP=1 \
--        -f 004_imagem_200kb.sql
--
-- É seguro rodar mais de uma vez. NOT VALID: a regra vale para fotos
-- gravadas daqui em diante, sem falhar por alguma foto antiga maior.
-- =====================================================================

BEGIN;

ALTER TABLE equipamentos
    DROP CONSTRAINT IF EXISTS equipamentos_imagem_tamanho;

ALTER TABLE equipamentos
    ADD CONSTRAINT equipamentos_imagem_tamanho
        CHECK (octet_length(imagem) <= 204800) NOT VALID;

COMMENT ON COLUMN equipamentos.imagem IS
    'Foto do equipamento, comprimida pelo backend para no máximo 200 KB. Servida publicamente em GET /api/equipamentos/<id>/imagem.';

COMMIT;
