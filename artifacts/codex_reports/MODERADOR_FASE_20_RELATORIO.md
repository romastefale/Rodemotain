# MODERADOR FASE 20 — Branding da interface

Base aplicada: `tigrao-moderador-bot-fase19.zip`.

## Objetivo

Trocar o nome visível da interface de `Tigrão/Tigrao Moderador` para `Rodemotain`, preservando nomes internos técnicos quando a alteração poderia quebrar callbacks, rotas, pacotes, tabelas, variáveis de ambiente ou compatibilidade de deploy.

## Alterações aplicadas

- Painel principal: `HOME_TEXT = "Rodemotain"`.
- `/start`: cabeçalho visível alterado para `🐯 Rodemotain`.
- `/help`: cabeçalho visível alterado para `🐯 Rodemotain — comandos`.
- Logs do painel: `Logs do Rodemotain`.
- Mensagem de permissão/admin do grupo: `usar o Rodemotain aqui`.
- Nome do link de solicitação de entrada criado pelo painel: `Rodemotain`.
- FastAPI title: `Rodemotain`.
- Mini App `/join-request`: `<title>` e `<h1>` alterados para `Rodemotain`.
- `PANEL_TITLE` alterado para `Rodemotain`.
- README principal ajustado para `Rodemotain Bot Moderador`.

## Preservado de propósito

- Comando `/tigrao`, porque já está implementado e citado como comando operacional.
- Variáveis `TIGRAO_*`, especialmente `TIGRAO_BOT_ACCESS_USER_IDS` e `TIGRAO_JOIN_REQUEST_WEBAPP_URL`, para não quebrar Railway/deploy existente.
- Pacote/pasta `app/plugins/tigrao_fsm`, callbacks, tabelas SQLite e nomes de classes, por compatibilidade técnica.

## Validação

Comandos executados:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
74 passed
```
