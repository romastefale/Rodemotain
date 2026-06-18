# MODERADOR FASE 24 — X9 inline

Base: `tigrao-moderador-bot-fase23.zip`.

## Objetivo

Adicionar superfície inline X9 para acionar funções rápidas do painel pelo formato:

- `@rodemotainbot ...` para abrir funções de grupo;
- `@rodemotainbot user_id` para abrir ações direcionadas ao usuário no grupo onde o botão for pressionado;
- `@rodemotainbot user_id chat_id` para aplicar ações em grupo explícito a partir de qualquer conversa.

## Segurança aplicada

- As respostas funcionais do X9 só são entregues para usuários definidos em `TIGRAO_BOT_ACCESS_USER_IDS`.
- Todo callback X9 revalida o usuário que apertou o botão.
- O grupo é resolvido no callback quando o `chat_id` não foi informado, porque a InlineQuery só informa `chat_type`, não o `chat_id` real do grupo.
- Ações destrutivas/mutantes passam por confirmação: `Confirmar` / `Cancelar`.
- Alvos protegidos, bot e administradores são bloqueados para ações destrutivas.
- Permissões reais do bot no grupo são revalidadas no momento da execução.

## Funções X9 adicionadas

Com alvo `user_id`:

- banir;
- mutar 1h;
- mutar 24h;
- mutar indefinido;
- desmutar;
- desbanir;
- advertir;
- auditar administradores/bots.

Sem alvo:

- fechar grupo;
- reabrir grupo;
- auditar administradores/bots;
- consultar status das proteções.

## Saída temporária

Após execução ou consulta, a mensagem inline é editada com o resultado e o bot agenda remoção em 60 segundos. A remoção depende das permissões do bot no chat onde a mensagem inline foi enviada.

## Arquivos alterados

- `app/plugins/tigrao_fsm/routers/inline_x9.py`
- `app/plugins/tigrao_fsm/plugin.py`
- `app/config/settings.py`
- `app/main.py`
- `tests/test_tigrao_moderador_phase24_x9_inline.py`

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `84 passed`.
