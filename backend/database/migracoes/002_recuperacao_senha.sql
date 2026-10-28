-- =====================================================================
-- MIGRAÇÃO 002 - "Esqueci minha senha"
-- =====================================================================
--
-- Para bancos criados ANTES desta mudança. Bancos novos já recebem
-- estas colunas pelo schema.sql e não precisam rodar este arquivo.
-- Requer a migração 001 (senha provisória) já aplicada.
--
--   psql -h <host> -U <usuario> -d <banco> -v ON_ERROR_STOP=1 \
--        -f 002_recuperacao_senha.sql
--
-- É seguro rodar mais de uma vez. Não altera dados existentes.
-- =====================================================================

BEGIN;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS reset_senha_hash VARCHAR(255),
    ADD COLUMN IF NOT EXISTS reset_senha_expira_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reset_senha_solicitado_em TIMESTAMPTZ;

COMMENT ON COLUMN usuarios.reset_senha_hash IS
    'Senha enviada por "Esqueci minha senha". Convive com a senha atual: só substitui senha_hash quando é usada no login.';
COMMENT ON COLUMN usuarios.reset_senha_expira_em IS
    'Validade da senha de recuperação (SENHA_RECUPERACAO_MINUTOS, padrão 60).';
COMMENT ON COLUMN usuarios.reset_senha_solicitado_em IS
    'Último pedido de recuperação. Pedidos repetidos em menos de 2 minutos são ignorados.';

COMMIT;
