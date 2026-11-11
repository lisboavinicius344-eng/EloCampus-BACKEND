-- Justificativa da análise das solicitações de acesso (auditoria).
--
-- Guarda o "porquê" da aprovação (opcional) e da recusa (obrigatória).
-- As recusas antigas copiam o motivo_recusa para a coluna nova.
-- Rode ANTES do deploy do backend que usa a coluna. Pode rodar mais de
-- uma vez sem efeito colateral.

BEGIN;

ALTER TABLE solicitacoes_acesso
    ADD COLUMN IF NOT EXISTS justificativa TEXT;

UPDATE solicitacoes_acesso
SET justificativa = motivo_recusa
WHERE justificativa IS NULL AND motivo_recusa IS NOT NULL;

COMMENT ON COLUMN solicitacoes_acesso.justificativa IS
    'Por que a solicitação foi aprovada ou recusada (obrigatória na recusa).';

COMMIT;
