-- =====================================================================
-- MIGRAÇÃO 001 - Lembretes de devolução
-- =====================================================================
--
-- Para o banco criado com o schema.sql ANTES desta mudança (o banco em
-- produção hoje). Bancos novos já recebem as colunas pelo schema.sql.
-- RODE ANTES DO DEPLOY: o backend novo lê estas colunas.
--
--   psql -h <host> -U <usuario> -d <banco> -v ON_ERROR_STOP=1 \
--        -f 001_lembretes_devolucao.sql
--
-- É seguro rodar mais de uma vez e não altera dados.
-- =====================================================================

BEGIN;

ALTER TABLE emprestimos
    ADD COLUMN IF NOT EXISTS lembrete_vespera_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lembrete_atraso_em TIMESTAMPTZ;

COMMENT ON COLUMN emprestimos.lembrete_vespera_em IS
    'Quando o lembrete de véspera (24 h antes do prazo) foi entregue ao n8n. Evita enviar duas vezes.';
COMMENT ON COLUMN emprestimos.lembrete_atraso_em IS
    'Último aviso de atraso entregue ao n8n. O aviso se repete a cada 24 h até a devolução.';

COMMIT;
