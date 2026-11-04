# ELO Campus: backend

API do sistema de empréstimo e controle de equipamentos com QR Code do
Campus Lapa da UFOB. Feita em Python com Flask e PostgreSQL, publicada no
Easypanel e integrada ao n8n e ao Uptime Kuma.

A documentação de todas as rotas está em [docs/API.md](docs/API.md).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `backend/routes` | Rotas da API |
| `backend/services` | Regras de negócio e consultas ao banco |
| `backend/models` | Validação dos dados recebidos |
| `backend/database` | `schema.sql` e migrações |
| `backend/tests` | Testes automáticos |
| `n8n` | Workflows do n8n |
| `docs` | Documentação da API e da integração com o frontend |

Os limites de prazo e de itens por pessoa ficam em
`backend/services/regras.py`.

## Rodar no computador

Requer Python 3.13 ou superior e PostgreSQL 13 ou superior.

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # depois, preencha o .env
psql -h localhost -U <usuario> -d <banco> -v ON_ERROR_STOP=1 -f database/schema.sql
flask --app app run
```

Para subir a API e o banco com Docker, preencha `backend/.env` e rode, na
raiz do projeto, `docker compose --env-file backend/.env up --build`. A
API fica em `http://127.0.0.1:8000`.

## Testes

```bash
cd backend
pip install pytest
python -m pytest -q
```

Os testes automáticos não precisam de banco: o acesso a ele é simulado.

## Banco de dados

- **Banco novo:** rode `backend/database/schema.sql`.
- **Banco existente:** rode os arquivos de `backend/database/migracoes`
  que ainda não foram aplicados, em ordem. Eles podem rodar mais de uma
  vez.
- **Primeiro administrador:** siga a seção "Pós-instalação" no fim do
  `schema.sql`.
- **Senha de admin esquecida:** `python redefinir_senha_admin.py <e-mail>`.

## Publicar

O deploy no Easypanel é **manual, de propósito**: um push no GitHub não
muda o que está no ar.

1. Se a versão tiver migração, aplique-a no banco antes.
2. Faça o push para a `main`.
3. No Easypanel, abra o serviço do backend e clique em **Deploy**.
4. Confira `GET /api/monitor?formato=texto`. A resposta deve ser
   `SISTEMA OK`.

As variáveis de ambiente estão explicadas em `backend/.env.example` e
ficam na aba **Environment** do serviço. Senhas e chaves nunca vão para o
repositório.

## Automações

| O quê | Rota | Quem chama |
|---|---|---|
| Monitoramento | `GET /api/monitor` | Uptime Kuma |
| Lembretes de devolução | `POST /api/lembretes/processar` | n8n, de hora em hora |
| Relatório semanal | `GET /api/relatorios/semanal` | n8n, às segundas às 8h |
