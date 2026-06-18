# Tigrão Moderador — Fase 09

Base factual usada: `tigrao-moderador-bot-fase08.zip` extraído e alterado localmente. Não foi usada memória residual como fonte de código.

## Escopo desta fase

Fase 1 do plano de quatro fases: correção dos erros e melhoria de usabilidade.

## Correções aplicadas

1. `unban` seguro:
   - `bot.unban_chat_member(...)` agora usa `only_if_banned=True`.
   - Isso impede que a ação “desbanir” acabe removendo do grupo um usuário que ainda era membro.

2. Mute mais completo:
   - `_mute_permissions()` agora bloqueia texto, mídia, polls, previews, reações e edição de tag.
   - `restrict_chat_member` agora usa `use_independent_chat_permissions=True`.

3. Modelo de permissões atualizado:
   - `TigraoBotPermissions` passou a refletir a superfície administrativa atual: `can_manage_video_chats`, `can_promote_members`, stories, canais, DMs de canal, tags e tópicos.
   - O painel mostra melhor o diagnóstico do que o bot possui ou não possui no grupo.

4. `ALLOWED_UPDATES` ampliado:
   - Incluídos `edited_message`, `channel_post`, `edited_channel_post`, `message_reaction`, `message_reaction_count`, `chat_boost` e `removed_chat_boost`.
   - Reações exigem inscrição explícita pela Bot API.

5. DDX temporizado mais flexível:
   - O parser agora aceita duração composta: `1h30m`, `2d 4h`, `1 semana`.
   - Também aceita data absoluta ISO-8601: `até 2026-07-01T12:00:00Z`.

6. Usabilidade de solicitações de entrada:
   - O menu agora separa “Ver pendentes”, “Aceitar ID pendente” e “Recusar ID pendente”.
   - A função de recusar solicitação já existia em `services.py`, mas não estava ligada ao painel; agora está conectada.

7. Usabilidade de logs:
   - Removido botão duplicado “Uso”.

8. Registro/extração de updates:
   - `main._extract_user_id` e `group_registry.remember_chat_from_update` passaram a considerar as novas superfícies de update inscritas.
   - `ddx_runtime` também aceita `edited_message`.

## Arquivos alterados

- `app/config/settings.py`
- `app/main.py`
- `app/bot/group_registry.py`
- `app/plugins/tigrao_fsm/permissions.py`
- `app/plugins/tigrao_fsm/parsers.py`
- `app/plugins/tigrao_fsm/destructive_actions.py`
- `app/plugins/tigrao_fsm/keyboards.py`
- `app/plugins/tigrao_fsm/routers/panel.py`
- `app/plugins/tigrao_fsm/runtime/ddx_runtime.py`
- `tests/test_tigrao_moderador_phase09.py`

## Validação local

Comandos executados:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
21 passed
```

## Limites honestos

Esta fase ainda não implementa as funções novas grandes, como purge em lote, ban/mute com duração customizada no painel, lockdown, pin/unpin, alteração de título/descrição/foto, tags reais, tópicos reais, reações reais e channel-only. Essas ficam para a Fase 2.

Também não houve teste com token real no Telegram; a confirmação empírica em grupo real fica para a Fase 4.
