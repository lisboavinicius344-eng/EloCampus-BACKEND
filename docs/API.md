# ELO Campus — Documentação da API para o frontend

Este documento descreve tudo o que o frontend precisa para trocar o modo
de demonstração pela API real: endereço, login, permissões, todas as
rotas com campos e exemplos, e o que muda em relação ao `api.js` atual.

---

## 1. Configuração

No `assets/js/runtime-config.js`:

```js
window.ELO_API_BASE_URL = "https://elocampus-backend.a6ti6s.easypanel.host/api";
window.ELO_DATA_MODE = "api";
```

Quando o domínio definitivo estiver acessível, troque por
`https://backend.elocampus.com.br/api`.

O backend já aceita chamadas (CORS) destes endereços:

- `https://elocampus.com.br`
- `https://www.elocampus.com.br`
- `https://elocampus-frontend.a6ti6s.easypanel.host`

Para liberar outro endereço (ex.: `http://localhost:5500` em testes),
peça para incluí-lo na variável `CORS_ORIGINS` do backend.

As rotas funcionam com ou sem a barra final
(`/equipamentos` e `/equipamentos/` são iguais).

---

## 2. Convenções

### Identificadores

| Recurso | Tipo do `id` | Exemplo |
|---|---|---|
| Usuários (contas) | **UUID** (texto) | `"3f6c1e2a-9b7d-4c1e-8a2f-0d9e5b7c4a11"` |
| Solicitantes | **texto** (até 250 caracteres; o banco gera um UUID) | `"8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f"` |
| Solicitações de acesso | **UUID** (texto) | |
| Equipamentos, empréstimos, reservas, categorias, manutenções, histórico | número inteiro | `12` |

- **Ids de pessoas não são números**: não use `Number(...)`,
  `parseInt` nem `<input type="number">` com eles; envie e compare
  como **texto**.
- Nas URLs, use `encodeURIComponent(id)`.

### Datas

- **Enviar:** formato ISO 8601 **com fuso horário**.
  Exemplo: `"2026-11-03T18:00:00-03:00"` ou `new Date(...).toISOString()`.
- **Receber:** ISO 8601 em UTC, ex.: `"2026-11-03T21:00:00+00:00"`.
  Use `new Date(valor)` para exibir no horário local.

### Respostas

As respostas de sucesso vêm "embrulhadas" em um objeto com o nome do
recurso, por exemplo `{ "equipamentos": [...] }` ou
`{ "mensagem": "...", "equipamento": {...} }`.

**Exceções:** `/historico`, `/dashboard/resumo` e `/consulta-qr`
devolvem os dados diretamente (veja cada rota).

### Erros

Todos os erros vêm em JSON, sempre no campo **`erro`**:

```json
{ "erro": "A data final deve ser posterior à data inicial." }
```

| Status | Quando acontece | O que o frontend deve fazer |
|---|---|---|
| `400` | Dados inválidos ou regra de negócio violada | **Mostrar o texto de `erro` ao usuário** — as mensagens já são escritas para isso |
| `401` | Sem login, token inválido ou **expirado** | Voltar para a tela de login |
| `403` | Usuário logado, mas sem permissão | Mostrar o texto de `erro` |
| `404` | Registro ou rota não encontrada | Mostrar o texto de `erro` |
| `500` | Erro interno | Mensagem genérica ("tente novamente") |

> ⚠️ **Ajuste necessário no `api.js`:** hoje a função `requisitar` só lê
> a mensagem nos status 409/422 e no campo `mensagem`. Ela precisa ler o
> campo **`erro`** e tratar o status **400**, senão o usuário só verá
> "O servidor não conseguiu atender à solicitação".

---

## 3. Login, primeiro acesso e sessão

### Como funciona o primeiro acesso

Ninguém escolhe senha ao criar a conta. O fluxo é:

1. A conta é criada: um **aluno ou professor** pede acesso em
   **"Solicitar acesso"** e o **admin aprova** (seção 13.1); ou o
   admin cria uma conta da **equipe** (seção 13).
2. A pessoa recebe por **e-mail**, automaticamente, uma **senha
   provisória**, válida por **24 horas**.
3. Ela entra com essa senha. O login responde
   `"deve_trocar_senha": true`.
4. **A senha provisória vale um único acesso**: nesse login ela é
   trocada no banco e não entra mais. O frontend leva direto para a
   tela **"Criar sua senha"**, que chama `POST /auth/trocar-senha`
   com o token desse login.
5. A partir daí, tudo funciona normalmente.

Se a pessoa sair antes de criar a senha, usa **"Esqueci minha
senha"** para receber outra (que também vale um único acesso).

Enquanto a senha não for trocada, **qualquer outra rota responde 403**
com `"codigo": "TROCA_DE_SENHA_OBRIGATORIA"` — use esse código para
redirecionar à tela de criação de senha.

### `POST /auth/login` — público

```json
{ "email": "ana@escola.edu.br", "senha": "minhasenha" }
```

**200**

```json
{
  "mensagem": "Login realizado com sucesso.",
  "token": "eyJ1c3VhcmlvX2lkIjozfQ.Z...",
  "usuario": {
    "id": "3f6c1e2a-9b7d-4c1e-8a2f-0d9e5b7c4a11",
    "nome": "Ana Beatriz Lima",
    "email": "ana@escola.edu.br",
    "papel": "aluno",
    "solicitante_id": "8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f",
    "deve_trocar_senha": false
  }
}
```

Se `usuario.deve_trocar_senha` for `true`, a mensagem é
"Crie sua nova senha para continuar." — **guarde o token**
e vá para a tela de criação de senha.

**401**

- `{ "erro": "E-mail ou senha inválidos." }`
- `{ "erro": "Sua senha provisória expirou. Use \"Esqueci minha senha\" para receber uma nova." }`

> ⚠️ O login responde **401** quando a senha está errada. Como o
> `requisitar` atual redireciona para o login em qualquer 401, faça a
> chamada de login **fora** dessa função (ou trate esse caso), para
> conseguir mostrar a mensagem de erro.

- O login é **por e-mail** (maiúsculas e minúsculas não importam).
- Envie o token em todas as outras chamadas:
  `Authorization: Bearer <token>`
- O token vale **1 hora**. Depois disso a API responde 401 e o usuário
  precisa entrar de novo.
- Contas desativadas não conseguem entrar, e tokens de contas
  desativadas param de funcionar imediatamente.

### `POST /auth/esqueci-senha` — público

Botão **"Esqueci minha senha"** (`recuperar-senha.html`).

```json
{ "email": "ana@escola.edu.br" }
```

**200**, sempre com a mesma resposta, exista o e-mail ou não (assim a
tela não revela quem tem conta):

```json
{ "mensagem": "Se o e-mail estiver cadastrado, você receberá em instantes uma senha provisória. Ela vale por pouco tempo; sua senha atual continua funcionando até você usá-la." }
```

**400** só quando o e-mail é inválido: `{ "erro": "Informe um e-mail válido." }`.

Como funciona:

1. Se o e-mail for de uma conta **ativa**, o backend gera uma senha
   provisória e a envia pelo n8n (evento `recuperacao_senha`).
2. Ela vale **60 minutos** (variável `SENHA_RECUPERACAO_MINUTOS`).
3. **A senha atual continua valendo.** Um pedido feito por outra pessoa
   não tira o acesso de ninguém.
4. Se a pessoa entrar com a **senha atual**, o pedido é cancelado.
5. Se entrar com a **senha provisória**, ela vira a senha da conta e o
   login responde `deve_trocar_senha: true`: o mesmo fluxo do primeiro
   acesso (tela "Criar sua senha").
6. Pedidos repetidos para a mesma conta em menos de **2 minutos** são
   ignorados (sem novo e-mail), com a mesma resposta 200.

### `POST /auth/trocar-senha` — logado (inclusive com senha provisória)

Usada no primeiro acesso e também para trocar a senha depois.

- **Criar a senha** (login com `deve_trocar_senha: true`): basta
  `{ "nova_senha": "..." }`. A senha provisória já foi consumida no
  login; `senha_atual`, se vier, é ignorada.
- **Trocar a senha** (conta já ativa): `senha_atual` é obrigatória.

```json
{ "senha_atual": "minhaSenhaAntiga", "nova_senha": "minhaSenhaNova" }
```

**200** — `{ "mensagem": "Senha alterada com sucesso." }`

O **mesmo token** passa a acessar todas as rotas — não é preciso
entrar de novo.

Erros (400): nova senha com menos de 8 caracteres; na troca comum,
senha atual ausente ou incorreta, ou nova senha igual à atual.

### `POST /auth/solicitar-acesso` — público

Tela **"Solicitar acesso"** (alunos e professores). O endereço antigo
`POST /auth/cadastro-aluno` continua funcionando igual.

```json
{
  "nome": "Ana Beatriz Lima",
  "email": "ana@escola.edu.br",
  "tipo": "aluno",
  "matricula": "2024001",
  "mensagem": "Sou do 3º semestre de Informática"
}
```

- Obrigatórios: `nome` e `email`.
- Opcionais: `tipo` (`aluno` ou `professor`; o admin confirma na
  aprovação), `matricula`, `mensagem` (até 500 caracteres).
- Se a variável `ACESSO_DOMINIOS_PERMITIDOS` estiver configurada no
  backend (ex.: `ufob.edu.br`), só e-mails desses domínios são aceitos.

**200**, sempre com a mesma resposta (pedido novo, pedido repetido ou
e-mail que já tem conta), para a tela não revelar quem tem acesso:

```json
{ "mensagem": "Solicitação enviada. Quando a administração aprovar, você receberá no e-mail uma senha provisória para o primeiro acesso. Se você já tem conta, use \"Esqueci minha senha\"." }
```

**400** quando faltam dados ou o e-mail é inválido. Nenhum e-mail é
enviado neste momento: ele só sai quando o admin aprova.

---

## 4. Papéis e permissões

| Papel na API | Nome no frontend hoje | Quem é |
|---|---|---|
| `admin` | `administrador` | Administração |
| `operador` | `operador` | Equipe de atendimento |
| `aluno` | `aluno` | Usuário final |
| `professor` | `professor` | Usuário final com acesso a equipamentos restritos |

> O perfil `servidor` do frontend não tem login na API. Servidores
> existem apenas como **solicitantes** (pessoas que recebem empréstimos
> registrados pela equipe).

| Funcionalidade | admin | operador | aluno / professor |
|---|:-:|:-:|:-:|
| Painel (resumo) | ✅ | ✅ | ✅ |
| Ver equipamentos e categorias | ✅ | ✅ | ✅ |
| Cadastrar/editar/baixar equipamentos e categorias | ✅ | ✅ | ❌ |
| Solicitantes | ✅ | ✅ | só o próprio cadastro |
| Ver empréstimos | todos | todos | só os próprios |
| Registrar empréstimo e devolução | ✅ | ✅ | ❌ |
| Criar reserva | ✅ | ✅ | ✅ (em nome próprio) |
| Aprovar/rejeitar reserva | ✅ | ✅ | ❌ |
| Cancelar reserva | ✅ | ✅ | só as próprias |
| Manutenções e histórico | ✅ | ✅ | ❌ |
| Gestão da equipe (`/usuarios`) | ✅ | ❌ | ❌ |
| Consulta por QR Code | ✅ | ✅ | ✅ (também sem login) |

**Regra de elegibilidade:** equipamentos com
`"elegibilidade": "somente_funcionarios"` só podem ser reservados ou
emprestados para professores, servidores e técnicos. Para alunos, a API
responde 400 com a explicação.

---

## 5. Painel e consulta por QR Code

### `GET /dashboard/resumo` — qualquer usuário logado

Devolve os números diretamente (sem embrulho), no mesmo formato do
`demoResumo`:

```json
{
  "total": 18,
  "disponiveis": 9,
  "emprestados": 4,
  "atrasados": 2,
  "manutencao": 2,
  "inativos": 1
}
```

### `GET /consulta-qr/<codigo>` — público

Aceita o **QR Code**, o **número de patrimônio** (sem diferenciar
maiúsculas) ou o **ID**. Também aceita a URL gravada no QR Code: usa os
parâmetros `codigo`, `patrimonio`, `qr` ou `id`, ou o último trecho do
caminho. Envie com `encodeURIComponent(codigo)`, como o `api.js` já faz.

**200**

```json
{
  "equipamento": {
    "id": 2,
    "nome": "Projetor Epson X49",
    "patrimonio": "PRJ-0017",
    "numero_patrimonio": "PRJ-0017",
    "categoria": "Projeção",
    "setor": "Audiovisual",
    "localizacao": "Sala 12",
    "estado_conservacao": "bom",
    "status": "emprestado",
    "situacao": "atrasado"
  },
  "emprestimo": {
    "id": 4,
    "solicitante": "Prof. Ricardo Alves",
    "data_emprestimo": "2026-10-20T13:20:00+00:00",
    "data_prevista_devolucao": "2026-10-23T21:00:00+00:00",
    "atrasado": true
  }
}
```

- `emprestimo` só é preenchido para **admin e operador**. Para
  visitantes, alunos e professores ele vem `null` (privacidade).
- **404** — `{ "erro": "Nenhum equipamento corresponde a esse código." }`

O `qr.js` atual já lê `nome`, `patrimonio`, `situacao` e `setor`, então
a tela funciona sem alterações.

---

## 6. Equipamentos

### Objeto equipamento

```json
{
  "id": 2,
  "nome": "Projetor Epson X49",
  "numero_patrimonio": "PRJ-0017",
  "categoria_id": 3,
  "categoria": "Projeção",
  "setor": "Audiovisual",
  "localizacao": "Sala 12",
  "estado_conservacao": "bom",
  "status": "disponivel",
  "situacao": "disponivel",
  "qr_code": "QR-PRJ-0017",
  "observacoes": null,
  "elegibilidade": "todos",
  "criado_em": "2026-10-01T12:00:00+00:00"
}
```

| Campo | Valores |
|---|---|
| `estado_conservacao` | `novo`, `bom`, `regular`, `danificado` (condição física) |
| `status` | `disponivel`, `emprestado`, `manutencao`, `baixado` (definido pelo backend) |
| `situacao` | `disponivel`, `emprestado`, `atrasado`, `manutencao`, `inativo` (para exibir; igual ao modo demo) |
| `elegibilidade` | `todos`, `somente_funcionarios` |

### Rotas

| Método e rota | Quem | Descrição |
|---|---|---|
| `GET /equipamentos` | logado | `{ "equipamentos": [...] }` |
| `GET /equipamentos/<id>` | logado | `{ "equipamento": {...} }` |
| `POST /equipamentos` | admin, operador | Cadastra → **201** `{ "mensagem", "equipamento" }` |
| `PUT /equipamentos/<id>` | admin, operador | Atualiza → `{ "mensagem", "equipamento" }` |
| `PATCH /equipamentos/<id>/inativar` | admin, operador | Dá baixa → `{ "mensagem", "equipamento" }` |

**Corpo de `POST` e `PUT`:**

```json
{
  "nome": "Projetor Epson X49",
  "categoria_id": 3,
  "numero_patrimonio": "PRJ-0017",
  "setor": "Audiovisual",
  "localizacao": "Sala 12",
  "estado_conservacao": "bom",
  "qr_code": "QR-PRJ-0017",
  "observacoes": "Acompanha controle remoto",
  "elegibilidade": "todos"
}
```

- Obrigatórios: `nome` e a categoria, de um destes dois jeitos:
  - `categoria_id`: uma categoria já cadastrada e ativa;
  - `categoria`: o **nome** da categoria. Se ainda não existir, ela é
    criada na hora (sem diferenciar maiúsculas nem espaços extras). Assim
    o formulário de equipamento funciona mesmo com o banco vazio.
    Categoria desativada é recusada (400).
  - Se vierem os dois, vale o `categoria_id`.
- **Foto (`imagem`)**, opcional, no mesmo corpo do `POST`/`PUT`:
  - uma data URL (`data:image/jpeg;base64,...`, como devolve o
    `FileReader.readAsDataURL`) grava ou troca a foto;
  - `null` remove a foto;
  - ausente (ou `""`) mantém a foto atual. **Na edição, só envie
    `imagem` se a pessoa escolheu outra foto ou clicou em remover.**
  - Formatos: JPG, PNG, WebP ou GIF (o tipo é conferido pelo conteúdo;
    SVG é recusado). Pode enviar a foto **original, de até 10 MB**:
    o backend comprime para **no máximo 200 KB** (até 1280 px no maior
    lado, JPEG; aplica a rotação do celular; fundo transparente vira
    branco). Fotos que já têm até 200 KB são guardadas como vieram.
    Corpo acima de 15 MB responde 413.
- A resposta traz `imagem_url` (ou `null`), **relativa à base da API**:
  `"/equipamentos/7/imagem?v=1793214215"`. No front:
  `img.src = API_BASE_URL + equipamento.imagem_url`.

### `GET /equipamentos/<id>/imagem` — público

Devolve a foto (o arquivo da imagem, não JSON), para usar direto em
`<img src>`; a tag `<img>` não envia o token, por isso a rota é pública,
como a consulta por QR. 404 se o equipamento não tiver foto. O `?v=` da
`imagem_url` muda a cada troca de foto, então o navegador pode guardar
a imagem em cache sem mostrar a antiga.
- O `PUT` substitui todos os campos — envie o objeto completo. A única
  exceção é `elegibilidade`: se não for enviada, o valor atual é mantido.
- **O `status` não é enviado pelo frontend**: o backend calcula
  (`danificado` → `manutencao`; equipamento emprestado ou baixado mantém
  o status).
- Patrimônio repetido → 400 "Já existe um equipamento com esse número de patrimônio."
- Não é possível mudar a conservação de um equipamento emprestado (isso
  é feito na devolução) nem dar baixa em equipamento emprestado.

> **Não existe `DELETE`.** Equipamentos nunca são apagados, para
> preservar o histórico: use `PATCH /equipamentos/<id>/inativar`.

---

## 7. Categorias

Objeto: `{ "id", "nome", "descricao", "ativo" }`

| Método e rota | Quem | Corpo / resposta |
|---|---|---|
| `GET /categorias` | logado | `{ "categorias": [...] }` |
| `GET /categorias/<id>` | logado | `{ "categoria": {...} }` |
| `POST /categorias` | admin, operador | `{ "nome", "descricao" }` → **201** |
| `PUT /categorias/<id>` | admin, operador | `{ "nome", "descricao" }` |
| `PATCH /categorias/<id>/desativar` | admin, operador | Recusa se houver equipamentos não baixados na categoria |

O nome é único sem diferenciar maiúsculas ("Notebook" = "notebook").

---

## 8. Solicitantes

Pessoas que recebem empréstimos e fazem reservas.

```json
{
  "id": "8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f",
  "nome": "Ana Beatriz Lima",
  "tipo": "aluno",
  "setor": "Curso de Informática",
  "email": "ana@escola.edu.br",
  "telefone": "(77) 99999-0000",
  "matricula": "2024001",
  "ativo": true,
  "criado_em": "2026-10-01T12:00:00+00:00",
  "tem_conta": false
}
```

- `tipo`: `aluno`, `servidor`, `professor`, `tecnico`, `externo`.
- `email`: **obrigatório para `aluno` e `professor`** (é por ele que a
  pessoa cria a conta) e único entre solicitantes ativos. Guardado em
  minúsculas.
- `matricula`: opcional (matrícula ou SIAPE), única.
- `tem_conta`: se a pessoa já criou a conta de acesso.

| Método e rota | Quem | Corpo / resposta |
|---|---|---|
| `GET /solicitantes` | admin, operador | `{ "solicitantes": [...] }` |
| `GET /solicitantes/<id>` | logado | `{ "solicitante": {...} }` — aluno/professor só o próprio |
| `POST /solicitantes` | admin, operador | `{ "nome", "tipo", "email", "matricula"?, "setor"?, "telefone"? }` → **201** |
| `PUT /solicitantes/<id>` | admin, operador | Mesmo corpo do `POST` |
| `PATCH /solicitantes/<id>/desativar` | admin, operador | 404 se não existir ou já estiver desativado |

- **Mudar o tipo** de quem tem conta: aluno ↔ professor atualiza a conta
  junto; virar servidor, técnico ou externo é recusado (400), porque
  esses tipos não têm conta.
- **Desativar** é recusado (400) enquanto a pessoa estiver com algum
  equipamento. Ao desativar, a **conta dela também é desativada** e as
  reservas pendentes ou aprovadas são canceladas.

---

## 9. Empréstimos

Um empréstimo tem **um ou mais itens** (equipamentos). A devolução é
registrada **por item**; quando o último item é devolvido, o empréstimo
passa para `concluido`.

> **Fluxo:** o aluno/professor **reserva** → a equipe **aprova** → na
> retirada, a equipe usa **`POST /reservas/<id>/retirar`** (seção 10),
> que cria o empréstimo a partir da reserva. O `POST /emprestimos` é
> para retiradas **sem** reserva (atendimento no balcão).

### Objeto empréstimo

```json
{
  "id": 5,
  "solicitante_id": "8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f",
  "solicitante": "Ana Beatriz Lima",
  "usuario_responsavel_id": "1b9e7d2c-5f4a-4e3b-9c8d-7e6f5a4b3c2d",
  "usuario_responsavel": "Operador",
  "data_emprestimo": "2026-10-21T12:00:00+00:00",
  "data_prevista_devolucao": "2026-10-24T21:00:00+00:00",
  "status": "em_andamento",
  "observacoes": null,
  "itens": [
    {
      "equipamento_id": 3,
      "equipamento": "Notebook Dell Latitude",
      "numero_patrimonio": "INF-0031",
      "estado_na_retirada": "bom",
      "data_devolucao": null,
      "estado_na_devolucao": null,
      "observacoes": null
    }
  ]
}
```

- `status`: `em_andamento`, `concluido`, `cancelado`.
- `itens` vem em todas as respostas, inclusive na listagem
  `GET /emprestimos`. `numero_patrimonio` é `null` quando o equipamento
  não tem patrimônio.
- Atraso: `status = "em_andamento"` e `data_prevista_devolucao` no passado.

### Rotas

| Método e rota | Quem | Descrição |
|---|---|---|
| `GET /emprestimos` | logado | Equipe vê todos; aluno/professor só os próprios → `{ "emprestimos": [...] }` |
| `GET /emprestimos/<id>` | logado | `{ "emprestimo": {...} }` (com `itens`) |
| `POST /emprestimos` | admin, operador | Registra a retirada → **201** |
| `PATCH /emprestimos/<id>/itens/<equipamento_id>/devolver` | admin, operador | Registra a devolução de um item |

**Corpo do `POST /emprestimos`:**

```json
{
  "solicitante_id": "8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f",
  "equipamentos": [3, 7],
  "data_prevista_devolucao": "2026-10-24T18:00:00-03:00",
  "observacoes": "Uso em aula prática"
}
```

- O responsável é **o usuário logado** (não é enviado).
- `data_prevista_devolucao` precisa estar no futuro e em **no máximo
  15 dias**.
- Quem tem **equipamento com devolução atrasada** não pega outro
  emprestado nem reserva (400), até a devolução.
- Todos os equipamentos precisam estar `disponivel` e não danificados.
- A API recusa (400) equipamentos que **outra pessoa** tem reservados
  (reserva aprovada) dentro do período do empréstimo. A mensagem informa
  quais são; ajuste a data de devolução ou escolha outro equipamento.

**Corpo da devolução:**

```json
{ "estado_na_devolucao": "bom", "observacoes": "Sem avarias" }
```

`estado_na_devolucao`: `bom`, `regular` ou `danificado` (um item não
volta `novo`). Devolvido `danificado`, o equipamento vai para manutenção
e **a manutenção é aberta automaticamente**, com as observações da
devolução; ela aparece em `GET /manutencoes`.

> **Diferença para o `api.js` atual:** o demo usa `POST /devolucoes`
> com vários itens de uma vez. Na API, chame a rota de devolução **uma
> vez para cada item**. Os campos `condicao`, `acessoriosConferidos`,
> `equipamentoConferido` e `assinaturaRecebida` do demo não existem na
> API — se forem necessários, inclua as informações em `observacoes`.

---

## 10. Reservas

### Objeto reserva

```json
{
  "id": 12,
  "solicitante_id": "8f38fcd1-2c4b-4e0a-9f1d-7a6b5c4d3e2f",
  "solicitante": "Ana Beatriz Lima",
  "usuario_responsavel_id": null,
  "usuario_responsavel": null,
  "data_inicio": "2026-11-03T13:00:00+00:00",
  "data_fim": "2026-11-03T17:00:00+00:00",
  "status": "pendente",
  "observacoes": "Apresentação do TCC",
  "criado_em": "2026-10-23T15:00:00+00:00",
  "itens": [
    { "equipamento_id": 2, "equipamento": "Projetor Epson X49", "status_equipamento": "disponivel" }
  ]
}
```

`status`: `pendente` → `aprovada` | `rejeitada` | `cancelada`;
`aprovada` → `cancelada` | `concluida` (quando a retirada é registrada).

**`expirada`** é aplicado automaticamente:
- reserva `pendente` cujo **início já passou** sem análise da equipe;
- reserva `aprovada` cujo **fim já passou** sem retirada.

Reserva expirada não pode ser aprovada, cancelada nem retirada.

### Rotas

| Método e rota | Quem | Descrição |
|---|---|---|
| `GET /reservas` | logado | Equipe vê todas; aluno/professor só as próprias → `{ "reservas": [...] }` |
| `GET /reservas/<id>` | logado | `{ "reserva": {...} }` (com `itens`) |
| `POST /reservas` | logado | Cria a reserva → **201** |
| `PATCH /reservas/<id>/aprovar` | admin, operador | Só reservas `pendente` |
| `PATCH /reservas/<id>/rejeitar` | admin, operador | Só reservas `pendente` |
| `PATCH /reservas/<id>/cancelar` | logado | `pendente` ou `aprovada`; aluno/professor só as próprias |
| `POST /reservas/<id>/retirar` | admin, operador | Registra a retirada: cria o empréstimo e conclui a reserva |

Os `PATCH` não precisam de corpo e respondem
`{ "mensagem", "reserva" }`.

### Registrar a retirada de uma reserva

`POST /reservas/<id>/retirar` — usado quando a pessoa vem buscar o que
reservou. Cria o empréstimo **com os mesmos equipamentos e o mesmo
solicitante** da reserva e muda a reserva para `concluida`, tudo de uma
vez (se algo falhar, nada é gravado).

O corpo é **opcional**:

```json
{
  "data_prevista_devolucao": "2026-11-05T18:00:00-03:00",
  "observacoes": "Retirado pela própria aluna"
}
```

- Sem `data_prevista_devolucao`, a devolução fica para o **fim do
  período reservado** (`data_fim`). Se esse horário já passou, a API pede
  uma data futura (400).
- Sem `observacoes`, usa as observações da reserva.
- O responsável é o usuário logado.
- **Quando:** a partir de **2 horas antes do início** até o **fim** do
  período reservado. Fora disso, 400 com a explicação.

**201**

```json
{ "mensagem": "Retirada registrada com sucesso.", "emprestimo": { "...": "objeto empréstimo da seção 9" } }
```

Erros (400): reserva que não está `aprovada` (inclusive já retirada),
equipamento que deixou de estar disponível ou foi danificado. 404 se a
reserva não existir.

Sugestão de tela: na lista de reservas aprovadas, um botão
**"Registrar retirada"** para a equipe.

**Corpo do `POST /reservas` (aluno/professor):**

```json
{
  "equipamentos": [2],
  "data_inicio": "2026-11-03T10:00:00-03:00",
  "data_fim": "2026-11-03T14:00:00-03:00",
  "observacoes": "Apresentação do TCC"
}
```

- Para aluno/professor, o solicitante vem do login.
- A equipe, ao reservar para alguém, envia também `"solicitante_id"`
  (e opcionalmente `"usuario_responsavel_id"`).
- As datas **precisam ter fuso horário** e `data_fim` deve ser depois de
  `data_inicio`.
- **Limites:** começar no **futuro**, com no máximo **30 dias** de
  antecedência, e durar no máximo **7 dias**.
- Quem tem **equipamento com devolução atrasada** não reserva (400).
- Equipamentos **emprestados** podem ser reservados, desde que a
  devolução prevista seja **antes** do início da reserva.
- A API recusa (400):
  - equipamentos em **manutenção** ou **baixados** (sem previsão de retorno);
  - períodos que conflitam com outras reservas pendentes/aprovadas;
  - períodos que conflitam com empréstimos em andamento — e, se o
    empréstimo estiver **atrasado**, qualquer período, até a devolução;
  - equipamentos restritos a funcionários (para alunos).
- As mesmas verificações (disponibilidade, conflitos, elegibilidade e
  atraso da pessoa) são refeitas na **aprovação**.

---

## 11. Manutenções (equipe)

```json
{
  "id": 4,
  "equipamento_id": 9,
  "equipamento": "Caixa de som Bose",
  "numero_patrimonio": "AUD-0044",
  "usuario_responsavel_id": "1b9e7d2c-5f4a-4e3b-9c8d-7e6f5a4b3c2d",
  "responsavel": "Operador",
  "descricao_problema": "Chiado no alto-falante",
  "data_abertura": "2026-10-20T13:15:00+00:00",
  "data_conclusao": null,
  "status": "aberta",
  "solucao": null,
  "observacoes": null
}
```

`status`: `aberta`, `em_andamento`, `concluida`, `cancelada`.

| Método e rota | Corpo / resposta |
|---|---|
| `GET /manutencoes` | `{ "manutencoes": [...] }` |
| `GET /manutencoes/<id>` | `{ "manutencao": {...} }` |
| `POST /manutencoes` | `{ "equipamento_id", "descricao_problema", "usuario_responsavel_id"?, "observacoes"? }` → **201** |
| `PATCH /manutencoes/<id>/finalizar` | `{ "solucao", "estado_conservacao"?, "observacoes"? }` |

- Abrir a manutenção coloca o equipamento em `manutencao`. Só pode haver
  uma manutenção aberta por equipamento.
- **Equipamento emprestado não recebe manutenção** (400): registre a
  devolução como `danificado`, que abre a manutenção automaticamente.
  Ela também é aberta sozinha quando um equipamento é cadastrado ou
  editado com conservação `danificado`.
- **Finalizar** devolve o equipamento a `disponivel` com a conservação
  informada em `estado_conservacao`: `novo`, `bom` (padrão) ou
  `regular`.
- Enquanto houver manutenção aberta, editar o equipamento não muda a
  conservação (400): ela é atualizada ao finalizar.

---

## 12. Histórico de movimentações (equipe)

> Responde **sem embrulho**: a listagem é um array e os demais, o
> próprio objeto.

```json
[
  {
    "id": 31,
    "equipamento_id": 3,
    "equipamento_nome": "Notebook Dell Latitude",
    "usuario_id": "1b9e7d2c-5f4a-4e3b-9c8d-7e6f5a4b3c2d",
    "usuario_nome": "Operador",
    "emprestimo_id": 5,
    "tipo_movimentacao": "emprestimo",
    "data_movimentacao": "2026-10-21T12:00:00+00:00",
    "descricao": "Equipamento emprestado."
  }
]
```

| Método e rota | Descrição |
|---|---|
| `GET /historico` | Lista, mais recentes primeiro |
| `GET /historico/<id>` | Um registro |
| `POST /historico` | `{ "equipamento_id", "tipo_movimentacao", "usuario_id"?, "emprestimo_id"?, "descricao"? }` → **201** |

O backend registra sozinho os tipos `emprestimo` e `devolucao`.

---

## 13.1 Solicitações de acesso (somente admin)

Objeto:

```json
{
  "id": "6d1f0c3e-2a4b-4c5d-8e9f-0a1b2c3d4e5f",
  "nome": "Ana Beatriz Lima",
  "email": "ana@escola.edu.br",
  "tipo": "aluno",
  "matricula": "2024001",
  "mensagem": "Sou do 3º semestre de Informática",
  "status": "pendente",
  "criado_em": "2026-10-29T12:00:00+00:00",
  "analisado_por": null,
  "analisado_por_nome": null,
  "analisado_em": null,
  "motivo_recusa": null,
  "usuario_id": null
}
```

`status`: `pendente` → `aprovada` | `recusada`.

| Método e rota | Corpo / resposta |
|---|---|
| `GET /solicitacoes-acesso?status=pendente` | `{ "solicitacoes": [...] }` (pendentes primeiro; `status` opcional: `pendente`, `aprovada`, `recusada`) |
| `GET /solicitacoes-acesso/<id>` | `{ "solicitacao": {...} }` |
| `POST /solicitacoes-acesso/<id>/aprovar` | corpo opcional (abaixo) → `{ "mensagem", "email_enviado", "solicitacao", "usuario" }` |
| `POST /solicitacoes-acesso/<id>/recusar` | `{ "motivo"? }` → `{ "mensagem", "solicitacao" }` |

**Aprovar** cria a conta e **envia o e-mail com a senha provisória
automaticamente**. O corpo é opcional e serve para o admin confirmar
ou corrigir os dados:

```json
{ "tipo": "aluno", "nome": "Ana Beatriz Lima", "matricula": "2024001", "setor": "Informática", "telefone": "(77) 99999-0000" }
```

- `tipo` é obrigatório se o pedido veio sem ele.
- Se já existir um **solicitante ativo com o mesmo e-mail** (cadastrado
  pela equipe), a conta é **vinculada** a ele. Para vincular a outro
  solicitante, envie `"solicitante_id"`.
- Se não existir, o solicitante é **criado** com os dados do pedido.
- Se o e-mail falhar (`"email_enviado": false`), a resposta traz
  `"senha_provisoria"` para o admin repassar pessoalmente.
- Erros (400): solicitação já analisada, e-mail que já tem conta,
  solicitante de tipo sem conta (servidor, técnico, externo).

**Recusar** não envia e-mail. Depois de recusada, a pessoa pode pedir
de novo.

---

## 13. Gestão da equipe (somente admin — tela a ser criada)

Objeto: `{ "id", "nome", "email", "papel", "ativo", "solicitante_id", "criado_em", "deve_trocar_senha" }`

`deve_trocar_senha: true` indica quem ainda não fez o primeiro acesso.

| Método e rota | Corpo / resposta |
|---|---|
| `GET /usuarios` | `{ "usuarios": [...] }` (todas as contas) |
| `GET /usuarios/<id>` | `{ "usuario": {...} }` |
| `POST /usuarios` | `{ "nome", "email", "papel": "admin" \| "operador" }` → **201** |
| `PATCH /usuarios/<id>/reenviar-senha` | Gera e envia uma **nova senha provisória** (24 h) |
| `PATCH /usuarios/<id>/desativar` | Não permite desativar a própria conta nem o último administrador |

O admin **não define a senha**: a pessoa recebe a senha provisória por
e-mail e cria a própria no primeiro acesso.

Resposta de `POST /usuarios` e `reenviar-senha`:

```json
{
  "mensagem": "Usuário cadastrado. A senha provisória foi enviada por e-mail.",
  "email_enviado": true,
  "usuario": { "...": "objeto usuário" }
}
```

Se o e-mail falhar (`"email_enviado": false`), a resposta inclui
`"senha_provisoria"` para o admin **repassar pessoalmente** — mostre-a
uma única vez, com destaque.

Use **reenviar-senha** quando a senha provisória expirar, o e-mail não
chegar ou alguém esquecer a senha: a senha anterior deixa de valer e a
pessoa precisará criar uma nova no próximo acesso.

---

## 14. De → para: `api.js` atual

| Função no `api.js` | Hoje chama | Na API |
|---|---|---|
| `resumoDashboard` | `/dashboard/resumo` | ✅ igual |
| `equipamentos` | `/equipamentos` | ✅ igual (ler `.equipamentos`) |
| `equipamento(id)` | `/equipamentos/<id>` | ✅ igual (ler `.equipamento`) |
| `consultaQr` | `/consulta-qr/<codigo>` | ✅ igual |
| `emprestimos` | `/emprestimos` | ✅ igual (ler `.emprestimos`; campos diferentes, ver seção 9) |
| `registrarEmprestimo` | `POST /emprestimos` | ✅ igual — enviar `solicitante_id`, `equipamentos`, `data_prevista_devolucao` |
| `movimentacoes` | `/movimentacoes` | ⚠️ **`/historico`** |
| `registrarDevolucao` | `POST /devolucoes` | ⚠️ **`PATCH /emprestimos/<id>/itens/<equipamento_id>/devolver`**, um por item |
| `salvarEquipamento` | `POST`/`PUT /equipamentos` | ✅ igual — campos da seção 6 |
| `removerEquipamento` | `DELETE /equipamentos/<id>` | ⚠️ **`PATCH /equipamentos/<id>/inativar`** |
| `perfil` / `salvarPerfil` | `/perfil` | ❌ não existe — usar o `usuario` devolvido pelo login |
| `autenticar` (auth.js) | contas fixas | ⚠️ **`POST /auth/login`** com `email` e `senha` |
| — | — | 🆕 tela **"Criar sua senha"** → `POST /auth/trocar-senha` (seção 3) |

**Nomes de campos que mudam** (demo → API):

| Demo | API |
|---|---|
| `patrimonio` | `numero_patrimonio` (na consulta QR vêm os dois) |
| `condicao` (`"Bom"`) | `estado_conservacao` (`"bom"`) |
| `categoria` (texto, ao salvar) | `categoria_id` (número) — listar com `GET /categorias` |
| `retirada` / `prevista` / `devolvida` | `data_emprestimo` / `data_prevista_devolucao` / `itens[].data_devolucao` |
| `perfil: "administrador"` | `papel: "admin"` |
| `login` (usuário/matrícula) | `email` |

---

## 15. Teste rápido

```bash
curl https://elocampus-backend.a6ti6s.easypanel.host/api/health
# {"sistema":"ELO Campus","status":"ok"}
```

Dúvidas ou rotas novas: falar com a equipe do backend.
