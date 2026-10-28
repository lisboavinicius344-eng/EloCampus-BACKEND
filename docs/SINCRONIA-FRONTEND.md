# Sincronia entre frontend e backend do ELO Campus

Levantamento de 26/10/2026, comparando o frontend publicado
(`elocampus-frontend.a6ti6s.easypanel.host`) com o backend da `main`.
Detalhes de cada rota (corpos, respostas e erros) estão em
[API.md](API.md).

**Resumo:** login, primeiro acesso, painel, QR Code, equipamentos,
empréstimos (equipe) e a tela de equipe já falam com a API. O que falta
é sobretudo **tela**: as rotas de solicitantes, categorias, reservas e
manutenções já existem no backend e várias já estão no `api.js`, mas
nenhuma página as usa. Há ainda **dois fluxos do aluno que chamam rotas
da equipe** e recebem 403.

---

## 1. Situação atual, por área

| Área | Situação no front | O que falta |
|---|---|---|
| Login e sessão | ✅ Integrado | — |
| Primeiro acesso (`trocar-senha.html`) | ✅ Integrado, inclusive o redirecionamento no 403 | — |
| Esqueci minha senha (`recuperar-senha.html`) | ✅ Integrado (`POST /auth/esqueci-senha`) | — |
| Autocadastro (`cadastro.html`) | ✅ Integrado | Depende de existir solicitante (ver 2.1) |
| Painel (`dashboard.html`) | ✅ Resumo vem da API | — |
| Consulta por QR Code | ✅ Integrado | — |
| Equipamentos: listar, ver | ✅ Integrado | — |
| Equipamentos: cadastrar, editar | ⚠️ Integrado, mas falha sem categoria cadastrada | Tela de categorias + campo de elegibilidade (ver 2.3) |
| Equipamentos: retirar de uso | ❌ Só no navegador (mensagem "salvo localmente") | Chamar `PATCH /equipamentos/<id>/inativar` |
| Empréstimos (equipe) | ⚠️ Integrado, mas escolhe o solicitante pelo **nome** | Escolher pelo `id` (ver 2.1) |
| Devoluções (equipe) | ✅ Integrado | — |
| Histórico de movimentações | ✅ Integrado | — |
| Equipe do sistema (`usuarios.html`) | ✅ Listar, criar, reenviar senha | Botão "Desativar" |
| **Solicitantes** | ❌ Não existe tela no modo API | Tela completa (ver 2.1) |
| **Categorias** | ❌ Não existe tela | Tela completa (ver 2.3) |
| **Reservas** | ❌ Funções no `api.js`, sem tela | Telas do aluno e da equipe (ver 2.2) |
| **Manutenções** | ❌ Funções no `api.js`, sem tela | Tela da equipe (ver 2.4) |
| Aluno: "Pedir empréstimo" | ❌ Chama `POST /emprestimos` (só equipe) → **403** | Virar reserva (ver 2.2) |
| Aluno: "Devolver equipamentos" | ❌ Chama a devolução (só equipe) → **403** | Tirar do menu do aluno (ver 2.5) |
| Perfil: salvar alterações | ❌ Sem rota no backend | Esconder o botão ou pedir a rota (ver 2.6) |
| Relatórios, Servidor (menu do admin) | ❌ Páginas não existem (404) | Esconder do menu por enquanto |

---

## 2. Mudanças prioritárias no front

### 2.1 Tela de Solicitantes (urgente)

Sem solicitantes, **nenhum aluno consegue se cadastrar** e **nenhum
empréstimo pode ser registrado**. O banco de produção começa vazio.

- Onde: pode ser uma aba nova em `usuarios.html`, aproveitando as abas
  "Alunos / Professores / Servidores" que hoje só existem no modo
  demonstração. Acesso: admin e operador.
- Listar: `ELO.solicitantes()` → `GET /solicitantes`.
- Cadastrar: `POST /solicitantes` com
  `{ nome, tipo, setor, email, telefone }`. `tipo` é um de `aluno`,
  `professor`, `servidor`, `tecnico`, `externo`.
- **Mostrar o `id` com destaque** depois de cadastrar: é o "Código do
  solicitante" que o aluno digita no autocadastro.
- Editar: `PUT /solicitantes/<id>` (mesmo corpo).
- Desativar: `PATCH /solicitantes/<id>/desativar`.
- No **Novo empréstimo** (equipe), trocar o campo de texto do
  solicitante por uma lista (`<select>` ou busca) alimentada por
  `GET /solicitantes`, e enviar o `solicitante_id`. Hoje o
  `registrarEmprestimo` procura o solicitante pelo nome exato, o que
  falha com acentos ou nomes repetidos.

Funções novas no `api.js`:

```js
criarSolicitante: d => requisitar("/solicitantes", { metodo: "POST", corpo: d }),
editarSolicitante: (id, d) => requisitar(`/solicitantes/${id}`, { metodo: "PUT", corpo: d }),
desativarSolicitante: id => requisitar(`/solicitantes/${id}/desativar`, { metodo: "PATCH" }),
```

### 2.2 Reservas: o aluno reserva, a equipe aprova e registra a retirada

Regra de negócio: **o aluno não registra empréstimo, ele reserva**. A
equipe aprova e, quando a pessoa vem buscar, registra a retirada, que
cria o empréstimo.

**Aluno e professor** (o item de menu "Pedir empréstimo" vira
"Reservar equipamento", na mesma `novo-emprestimo.html` ou numa página
nova):

- Criar: `ELO.criarReserva(...)` → `POST /reservas` com
  `{ equipamentos: [ids], data_inicio, data_fim, observacoes }`.
  As datas precisam de fuso horário: use `new Date(...).toISOString()`.
  O solicitante vem do login, não precisa enviar.
- "Minhas reservas": `ELO.reservas()` → `GET /reservas` (a API já
  devolve só as da pessoa), mostrando o `status`.
- Cancelar: `ELO.cancelarReserva(id)`, para status `pendente` ou
  `aprovada`.
- Mensagens de recusa (400) chegam prontas no campo `erro`: conflito de
  horário, equipamento em manutenção, equipamento só para professores,
  empréstimo atrasado. Basta exibir.

**Equipe** (página nova "Reservas", admin e operador):

- Lista com filtro por status: `GET /reservas`.
- Pendentes: botões **Aprovar** e **Rejeitar** (`ELO.aprovarReserva`,
  `ELO.rejeitarReserva`).
- Aprovadas: botão **Registrar retirada** → `POST /reservas/<id>/retirar`
  com corpo opcional `{ data_prevista_devolucao, observacoes }`. A
  resposta traz o empréstimo criado; depois disso, ele aparece em
  Empréstimos e a devolução segue o fluxo normal.

Função nova no `api.js`:

```js
retirarReserva: (id, d = {}) => requisitar(`/reservas/${id}/retirar`, { metodo: "POST", corpo: d }),
```

### 2.3 Categorias e campos do equipamento

O formulário de equipamento aceita digitar uma categoria nova, mas a API
**exige uma categoria já cadastrada** (`categoria_id`). Com o banco
vazio, todo cadastro de equipamento falha.

- Tela "Categorias" (admin e operador), ou um botão "Nova categoria" no
  próprio formulário:
  - listar: `GET /categorias`;
  - criar: `POST /categorias` com `{ nome, descricao }`;
  - editar: `PUT /categorias/<id>`;
  - desativar: `PATCH /categorias/<id>/desativar` (a API recusa se
    houver equipamentos ativos na categoria).
- No formulário de equipamento:
  - trocar o campo livre de categoria por uma lista das categorias
    cadastradas;
  - acrescentar o campo **Quem pode usar** → `elegibilidade`:
    `todos` (padrão) ou `somente_funcionarios` (alunos não conseguem
    reservar nem receber emprestado);
  - **foto**: enviar no campo `imagem` do `salvarEquipamento` (ver 2.8).
- Na lista de equipamentos, o "Retirar de uso" deve chamar
  `ELO.removerEquipamento(id)` → `PATCH /equipamentos/<id>/inativar`. A
  mensagem "salvo localmente… não foi enviada a um servidor" deve sair no
  modo API.

### 2.4 Manutenções (equipe)

As funções já estão no `api.js` (`manutencoes`, `abrirManutencao`,
`finalizarManutencao`); falta a página.

- Lista: `GET /manutencoes`, com filtro por status.
- Abrir: `POST /manutencoes` com `{ equipamento_id, descricao_problema }`.
  O equipamento passa a "Em manutenção" e sai das reservas.
- Finalizar: `PATCH /manutencoes/<id>/finalizar` com `{ solucao }`
  (obrigatória). O equipamento volta a "Disponível".
- Sugestão: botão "Enviar para manutenção" na tela do equipamento.

Devolver um item como `danificado` já abre a manutenção sozinho.

### 2.5 Menu do aluno e do professor

- **Tirar "Devolver equipamentos"**. A devolução é registrada pela
  equipe no balcão; para o aluno a API responde 403.
- "Meus empréstimos" continua: `GET /emprestimos` já devolve só os da
  pessoa.
- Acrescentar "Minhas reservas" (ver 2.2).
- O perfil `servidor` não existe como conta no backend. Só existem as
  contas `admin`, `operador`, `aluno` e `professor`; servidores são
  apenas solicitantes cadastrados pela equipe.

### 2.6 Perfil

`ELO.salvarPerfil` lança erro no modo API porque o backend não tem rota
de edição de perfil. Por enquanto: mostrar os dados só para leitura e
usar `trocar-senha.html` para "Alterar minha senha" (a mesma rota serve
para quem já tem senha). Se a edição do nome ou telefone for necessária,
pedir a rota ao backend.

### 2.7 Pequenos ajustes

- **Equipe → Desativar usuário**: botão na tabela da equipe chamando
  `ELO.desativarUsuario(id)`. A API recusa desativar a própria conta e o
  último admin, e a mensagem vem pronta.
- **Menu do admin**: esconder "Relatórios" e "Servidor" até as páginas
  existirem.
- **Cache do `runtime-config.js`**: hoje o servidor deixa o navegador
  guardar esse arquivo por 1 hora, e quem abriu o site antes continua no
  modo demonstração. Servir esse arquivo com `Cache-Control: no-cache`
  (ou carregá-lo com `?v=<versão>`).

### 2.8 Foto do equipamento

A API guarda a foto. Três ajustes no front:

1. **Enviar** no `salvarEquipamento` (`api.js`), só quando a foto mudou:

   ```js
   if (dados.imagemAlterada) corpo.imagem = dados.imagem || null; // null remove
   ```

   No `equipamento-form.js`, marcar `imagemAlterada = true` quando a
   pessoa escolhe um arquivo ou clica em "Remover foto", e passar
   `imagemAlterada` junto com `imagem` nos dados do formulário. Sem isso,
   editar um equipamento apagaria a foto.

2. **Reduzir antes de enviar** (limite de 3 MB; foto de celular costuma
   passar disso). No lugar do `readAsDataURL`:

   ```js
   async function reduzirImagem(arquivo, lado = 1280, qualidade = 0.85) {
     const bitmap = await createImageBitmap(arquivo);
     const escala = Math.min(1, lado / Math.max(bitmap.width, bitmap.height));
     const canvas = document.createElement("canvas");
     canvas.width = Math.round(bitmap.width * escala);
     canvas.height = Math.round(bitmap.height * escala);
     canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
     return canvas.toDataURL("image/jpeg", qualidade);
   }
   // foto.addEventListener("change", async () => { imagem = await reduzirImagem(foto.files[0]); imagemAlterada = true; ... });
   ```

3. **Mostrar**: equipamentos (lista, detalhe, formulário) e a consulta
   por QR trazem `imagem_url`. Usar
   `API_BASE_URL + equipamento.imagem_url` no `<img src>`; quando for
   `null`, manter a silhueta atual. No `normalizarEquipamento`:
   `imagem: e.imagem_url ? API_BASE_URL + e.imagem_url : ""`.

---

## 3. Mapa completo: rota → tela

Todas as rotas começam com `/api`. "Equipe" = admin e operador.
"Final" = aluno e professor.

| Rota | Quem | Tela do front | `api.js` |
|---|---|---|---|
| `POST /auth/login` | público | Login | `autenticar` (auth.js) ✅ |
| `POST /auth/cadastro-aluno` | público | Cadastro | `cadastroAluno` ✅ |
| `POST /auth/trocar-senha` | logado | Criar sua senha / Alterar senha | `trocarSenha` ✅ |
| `POST /auth/esqueci-senha` | público | Recuperar senha | `solicitarRecuperacaoSenha` ✅ |
| `GET /dashboard/resumo` | logado | Painel | `resumoDashboard` ✅ |
| `GET /consulta-qr/<código>` | público (equipe vê quem está com o item) | Consulta por QR | `consultaQr` ✅ |
| `GET /equipamentos` | logado | Equipamentos, Ver equipamentos | `equipamentos` ✅ |
| `GET /equipamentos/<id>` | logado | Formulário de equipamento | `equipamento` ✅ |
| `POST /equipamentos` | equipe | Cadastrar equipamento | `salvarEquipamento` ⚠️ 2.3 |
| `PUT /equipamentos/<id>` | equipe | Editar equipamento | `salvarEquipamento` ⚠️ 2.3 |
| `PATCH /equipamentos/<id>/inativar` | equipe | Equipamentos → Retirar de uso | `removerEquipamento` ❌ não usado |
| `GET /equipamentos/<id>/imagem` | público | `<img src>` da foto | via `imagem_url` ❌ 2.8 |
| `GET /categorias` | logado | Formulário de equipamento | `categorias` ✅ |
| `POST /categorias` | equipe | Categorias | ❌ criar |
| `PUT /categorias/<id>` | equipe | Categorias | ❌ criar |
| `PATCH /categorias/<id>/desativar` | equipe | Categorias | ❌ criar |
| `GET /solicitantes` | equipe | Solicitantes, Novo empréstimo | `solicitantes` ⚠️ sem tela |
| `GET /solicitantes/<id>` | logado (final: só o próprio) | Perfil | ❌ opcional |
| `POST /solicitantes` | equipe | Solicitantes | ❌ criar |
| `PUT /solicitantes/<id>` | equipe | Solicitantes | ❌ criar |
| `PATCH /solicitantes/<id>/desativar` | equipe | Solicitantes | ❌ criar |
| `GET /emprestimos` | logado (final: só os próprios) | Empréstimos, Painel | `emprestimos` ✅ |
| `GET /emprestimos/<id>` | logado | Devoluções | usado em `registrarDevolucao` ✅ |
| `POST /emprestimos` | equipe | Novo empréstimo (equipe) | `registrarEmprestimo` ⚠️ 2.1 |
| `PATCH /emprestimos/<id>/itens/<eq>/devolver` | equipe | Devoluções | `registrarDevolucao` ✅ |
| `GET /reservas` | logado (final: só as próprias) | Reservas, Minhas reservas | `reservas` ❌ sem tela |
| `GET /reservas/<id>` | logado | Detalhe da reserva | ❌ opcional |
| `POST /reservas` | logado | Reservar equipamento | `criarReserva` ❌ sem tela |
| `PATCH /reservas/<id>/aprovar` | equipe | Reservas | `aprovarReserva` ❌ sem tela |
| `PATCH /reservas/<id>/rejeitar` | equipe | Reservas | `rejeitarReserva` ❌ sem tela |
| `PATCH /reservas/<id>/cancelar` | logado (final: só as próprias) | Reservas, Minhas reservas | `cancelarReserva` ❌ sem tela |
| `POST /reservas/<id>/retirar` | equipe | Reservas → Registrar retirada | ❌ criar |
| `GET /manutencoes` | equipe | Manutenções | `manutencoes` ❌ sem tela |
| `POST /manutencoes` | equipe | Manutenções, Equipamento | `abrirManutencao` ❌ sem tela |
| `PATCH /manutencoes/<id>/finalizar` | equipe | Manutenções | `finalizarManutencao` ❌ sem tela |
| `GET /historico` | equipe | Histórico de movimentações | `movimentacoes` ✅ |
| `GET /usuarios` | admin | Equipe | `usuarios` ✅ |
| `POST /usuarios` | admin | Equipe → Novo usuário | `criarUsuario` ✅ |
| `PATCH /usuarios/<id>/reenviar-senha` | admin | Equipe → Reenviar senha | `reenviarSenha` ✅ |
| `PATCH /usuarios/<id>/desativar` | admin | Equipe → Desativar | `desativarUsuario` ❌ não usado |

`POST /historico` existe, mas o front não precisa dela: o backend já
registra as movimentações sozinho em cada empréstimo, devolução e
manutenção.

---

## 4. Fluxos principais

### Do cadastro ao primeiro acesso

1. A equipe cadastra a pessoa em **Solicitantes** e passa o código (`id`).
2. A pessoa abre **Cadastro**, informa nome, e-mail e código.
3. Chega por e-mail uma senha provisória, válida por 24 horas.
4. No login, a API devolve `deve_trocar_senha: true` e o front leva para
   **Criar sua senha**.
5. Depois da troca, o mesmo token passa a valer em todas as telas.

Contas da equipe pulam os passos 1 e 2: o admin cria em **Equipe**.

### Da reserva à devolução

```
Aluno reserva ──► pendente ──► Equipe aprova ──► aprovada ──► Equipe registra a retirada
                     │                              │                    │
                     ├─► Equipe rejeita: rejeitada  └─► Cancelada        ▼
                     └─► Aluno cancela: cancelada              empréstimo em andamento
                                                                         │
                                                        Equipe registra a devolução
                                                                         │
                                          ┌──────────────────────────────┴──────┐
                                    bom/regular                              danificado
                                 item disponível                    item vai para manutenção
```

A equipe também pode registrar um empréstimo direto no balcão, sem
reserva (**Novo empréstimo**).

---

## 5. Regras técnicas comuns

- **Token**: `Authorization: Bearer <token>` em toda chamada. Ele vale
  1 hora; depois disso a API responde 401 e o `requisitar` já manda para
  o login.
- **Erros**: toda resposta de erro tem `{ "erro": "mensagem pronta" }`.
  Basta exibir `erro`; não é preciso traduzir.
- **403 com `codigo: "TROCA_DE_SENHA_OBRIGATORIA"`**: já tratado no
  `requisitar`.
- **403 sem código**: a conta não tem permissão para aquela ação. Se
  aparecer, a tela está chamando uma rota que não é do perfil (como nos
  itens 2.2 e 2.5).
- **Papéis**: o login devolve `papel` = `admin`, `operador`, `aluno` ou
  `professor`. Admin e operador têm as mesmas telas, exceto **Equipe**,
  que é só do admin. Professor é igual ao aluno, mas pode reservar
  equipamentos marcados como `somente_funcionarios`.
- **Datas**: a API devolve ISO 8601 em UTC. Para enviar, use
  `toISOString()`; datas sem fuso são recusadas.
- **Empréstimos**: `GET /emprestimos` traz os `itens` de cada empréstimo
  (nome do equipamento e `numero_patrimonio`), no mesmo formato do
  detalhe. O `normalizarEmprestimo` do `api.js` já usa esses campos.

---

## 6. Ordem de entrega sugerida

- [ ] Tela de Solicitantes, com o código em destaque (2.1)
- [ ] Novo empréstimo da equipe escolhendo o solicitante por `id` (2.1)
- [ ] Categorias e lista de categorias no formulário de equipamento (2.3)
- [ ] Campo "Quem pode usar" (`elegibilidade`) no equipamento (2.3)
- [ ] "Retirar de uso" chamando a API (2.3)
- [ ] Aluno: "Pedir empréstimo" vira "Reservar equipamento" + "Minhas reservas" (2.2)
- [ ] Aluno: tirar "Devolver equipamentos" do menu (2.5)
- [ ] Equipe: tela de Reservas com aprovar, rejeitar e registrar retirada (2.2)
- [ ] Equipe: tela de Manutenções (2.4)
- [ ] Equipe: botão Desativar usuário (2.7)
- [ ] Perfil só leitura + link para alterar senha (2.6)
- [ ] Esconder Relatórios e Servidor; `runtime-config.js` sem cache (2.7)
