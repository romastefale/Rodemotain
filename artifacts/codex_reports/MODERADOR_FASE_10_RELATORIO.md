# MODERADOR FASE 10 — FUNÇÕES NOVAS

Base real usada: pacote `tigrao-moderador-bot-fase09.zip`.

## Recursos aplicados

1. Ban temporário com tempo livre pelo painel.
   - Entrada: `user_id | tempo`.
   - Exemplos: `123456 | 30m`, `123456 | 7d`, `123456 | permanente`.
   - Método Bot API: `banChatMember`.
   - Revalidação: `can_restrict_members`.

2. Mute temporário com tempo livre pelo painel.
   - Entrada: `user_id | tempo`.
   - Exemplos: `123456 | 10m`, `123456 | 1h30m`, `123456 | permanente`.
   - Método Bot API: `restrictChatMember`.
   - Revalidação: `can_restrict_members`.

3. Purge em lote.
   - Entrada: lista de IDs, links `t.me` ou intervalo `10-25`.
   - Limite: 1 a 100 mensagens por chamada.
   - Método Bot API: `deleteMessages`; fallback defensivo para `deleteMessage` se o wrapper não expuser `delete_messages`.
   - Revalidação: `can_delete_messages`.

4. Lockdown/unlock do grupo.
   - Fechamento/reabertura das permissões padrão de envio de membros comuns.
   - Método Bot API: `setChatPermissions`.
   - Revalidação: `can_restrict_members`.

5. Fixados.
   - Fixar mensagem por ID/link.
   - Desfixar mensagem por ID/link ou mais recente.
   - Limpar todos os fixados.
   - Métodos Bot API: `pinChatMessage`, `unpinChatMessage`, `unpinAllChatMessages`.
   - Revalidação: `can_pin_messages`.

6. Alteração de dados do grupo.
   - Alterar título: 1 a 128 caracteres.
   - Alterar descrição: até 255 caracteres; `-` limpa.
   - Métodos Bot API: `setChatTitle`, `setChatDescription`.
   - Revalidação: `can_change_info`.

7. Reações.
   - Remover reação específica de uma mensagem: `message_id/link | user_id` ou `message_id/link | chat:<actor_chat_id>`.
   - Remover reações recentes de um ator: `user_id` ou `chat:<actor_chat_id>`.
   - Métodos Bot API: `deleteMessageReaction`, `deleteAllMessageReactions`.
   - Revalidação: `can_delete_messages`.

8. Auditoria de administradores e bots.
   - Consulta `getChatAdministrators(return_bots=True)` quando disponível.
   - Fallback defensivo para wrapper que ainda não aceite `return_bots`.

## Arquivos principais alterados

- `app/plugins/tigrao_fsm/advanced_actions.py`
- `app/plugins/tigrao_fsm/parsers.py`
- `app/plugins/tigrao_fsm/keyboards.py`
- `app/plugins/tigrao_fsm/routers/panel.py`
- `tests/test_tigrao_moderador_phase10.py`

## Validação local

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `27 passed`.

## Limites honestos

A validação foi local, sem token real. As chamadas dependem do bot estar como administrador no Telegram com as permissões específicas concedidas no grupo/supergrupo. Algumas funções podem falhar por limites próprios do Telegram, como idade da mensagem, restrições de cargo do alvo, grupo que não é fórum ou método ainda não exposto pelo wrapper instalado.
