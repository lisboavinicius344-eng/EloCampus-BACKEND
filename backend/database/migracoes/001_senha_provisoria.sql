-- =====================================================================
-- MIGRAÇÃO 001 - Senha provisória no primeiro acesso
-- =====================================================================
--
-- Para bancos criados ANTES desta mudança. Bancos novos já recebem
-- estas colunas pelo schema.sql e não precisam rodar este arquivo.
--
--   psql -h <host> -U <usuario> -d <banco> -v ON_ERROR_STOP=1 \
--        -f 001_senha_provisoria.sql
--
-- É seguro rodar mais de uma vez. Não altera dados existentes: as
-- contas atuais continuam entrando normalmente com a senha que já têm.
-- =====================================================================

BEGIN;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS senha_provisoria_expira_em TIMESTAMPTZ;

COMMENT ON COLUMN usuarios.deve_trocar_senha IS
    'TRUE enquanto a conta usa a senha provisória enviada por e-mail. O login funciona, mas a API só libera a troca de senha.';
COMMENT ON COLUMN usuarios.senha_provisoria_expira_em IS
    'Validade da senha provisória. Depois disso, o login é recusado até o admin reenviar uma nova.';

COMMIT;
