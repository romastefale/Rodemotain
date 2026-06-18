# MODERADOR FASE 18 — /start, /help e diagnóstico Railway

Base usada: `tigrao-moderador-bot-fase17.zip`.

## Diagnóstico do log Railway

O deploy está subindo corretamente:

- volume montado;
- container iniciado;
- aplicação FastAPI/Uvicorn iniciada;
- webhook registrado em `https://rodemotain.up.railway.app/telegram/webhook`;
- `/healthz` respondeu `200 OK`.

O ponto funcional observado foi:

- `Update ... is not handled`.

Isso indica que o update chegou ao webhook e foi entregue ao aiogram, mas não havia handler para aquele tipo/comando. Como o pacote só tinha `/tigrao` e `/captcha`, `/start` e `/help` não respondiam.

## Correções aplicadas

### 1. Handler `/start`

Adicionado em `app/plugins/tigrao_fsm/routers/panel.py`.

Comportamento:

- usuário autorizado recebe tutorial rápido;
- usuário não autorizado recebe aviso de bot privado e instrução para incluir o ID em `TIGRAO_BOT_ACCESS_USER_IDS`;
- não abre painel para usuário não autorizado.

### 2. Handler `/help`

Adicionado em `app/plugins/tigrao_fsm/routers/panel.py`.

Comportamento:

- usuário autorizado recebe lista de comandos e recursos do painel;
- usuário não autorizado recebe lista mínima e aviso de acesso privado.

### 3. Menu de comandos do Telegram

Adicionado `_set_bot_commands_safe()` em `app/main.py`.

No startup, o bot tenta registrar:

- `/start` — tutorial rápido do moderador;
- `/help` — lista comandos e recursos;
- `/tigrao` — abrir painel de moderação;
- `/captcha` — responder captcha de entrada.

Falha ao registrar comandos não impede startup.

## Validação

Executado:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
67 passed
```

## Observação

O log não indica falha de Railway, webhook ou healthcheck. O problema confirmado era falta de handler para update/comando recebido.
