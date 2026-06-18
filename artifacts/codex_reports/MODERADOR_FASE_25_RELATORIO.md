# MODERADOR FASE 25 — Navegação por categorias e emojis

Base usada: `tigrao-moderador-bot-fase24.zip`.

## Objetivo

Reorganizar o painel do Rodemotain para evitar uma lista longa de botões em sequência. A navegação foi dividida em categorias com emojis, preservando callbacks internos, confirmação obrigatória e segurança por `TIGRAO_BOT_ACCESS_USER_IDS`.

## Aplicado

### Painel do grupo

O painel principal do grupo agora apresenta categorias:

- 📥 Entrada
- 📊 Logs
- 👤 Usuários
- 💬 Mensagens
- 👑 Admins
- 🔗 Links
- 🧩 Tópicos
- 🎛️ Grupo
- 🛡️ Proteções
- 🧾 Auditoria
- 🧨 DDX hard

### Ações do grupo

O antigo menu longo `Ações do grupo` virou menu de categorias. Cada categoria abre somente suas funções relacionadas:

- 👤 Usuários: ban, mute, warn, tag de membro.
- 💬 Mensagens: apagar, purge, fixar/desfixar.
- 👑 Admins: auditar, promover, rebaixar, título customizado, sender chat/canal.
- 🔗 Links: exportar, criar, editar e revogar links.
- 🧩 Tópicos: criar, editar, fechar, reabrir, apagar e controlar tópico geral.
- 🎛️ Grupo: fechar/reabrir grupo, título, descrição e foto.
- 🛡️ Proteções: status, anti-flood, anti-raid, captcha e DDX.
- ⚛️ Reações: remover reação e limpar reações recentes.
- 🧾 Auditoria: admins/bots, proteções e logs.

### Navegação

- Botão `⬅️ Categorias` volta para o menu de categorias.
- Botão `⬅️ Grupo` volta para o painel do grupo.
- Botões comuns receberam emojis: confirmar, cancelar, voltar, fechar, logs, entradas e DDX.
- Quando uma função é aberta dentro de uma categoria, o botão `Voltar` retorna à categoria correta, não mais ao menu longo genérico.

## Segurança preservada

- Nenhuma ação destrutiva passou a executar diretamente.
- A confirmação explícita continua ativa para ações sensíveis.
- A autorização continua restrita à variável `TIGRAO_BOT_ACCESS_USER_IDS`.
- Callbacks continuam validados com limite de 64 bytes.

## Validação

Executado localmente:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
87 passed
```
