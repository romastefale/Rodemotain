# Tigrão Moderador — Fase 16

Base real usada: `tigrao-moderador-bot-fase15.zip`.

## Objetivo
Corrigir o ponto que impedia confirmação total da Fase15: o fluxo de Join Request Query/Mini App usava chamadas de método no objeto `Bot` do aiogram (`send_chat_join_request_web_app` e `answer_chat_join_request_query`) que podem não existir em `aiogram>=3.28,<3.29`, embora existam na Telegram Bot API 10.1.

## Correções aplicadas

1. Criado `app/bot/api_compat.py`.
   - Prefere método nativo do `Bot` quando a versão do aiogram expuser o wrapper.
   - Se o wrapper não existir, chama a Telegram Bot API diretamente por HTTPS JSON.
   - Métodos cobertos:
     - `sendChatJoinRequestWebApp`
     - `answerChatJoinRequestQuery`
   - Erros são sanitizados e não expõem token em logs/mensagens.

2. Atualizado `app/plugins/tigrao_fsm/runtime/join_request_runtime.py`.
   - O envio do Mini App de join request agora usa `send_chat_join_request_web_app_compat`.

3. Atualizado `app/main.py`.
   - O endpoint `/telegram/join-request-query` agora usa `answer_chat_join_request_query_compat`.
   - Mantido o contrato: `approve`, `decline` ou `queue`.
   - Mantida proteção por `WEBHOOK_SECRET` quando configurado.

4. Correção de usabilidade do menu de reações.
   - Removido texto morto “Reações ainda não implementadas”.
   - O menu agora oferece os botões reais:
     - Remover reação de mensagem.
     - Remover reações recentes.

## Testes adicionados
Arquivo: `tests/test_tigrao_moderador_phase16_compat.py`.

Cobertura nova:
- Fallback HTTP para `answerChatJoinRequestQuery`.
- Fallback HTTP para `sendChatJoinRequestWebApp`.
- Preferência pelo método nativo do aiogram quando existir.
- Endpoint de join request query ligado ao helper compatível.
- Verificação estática de que não restam chamadas diretas aos métodos ausentes no `Bot`.
- Verificação de que o botão de reações não leva mais para texto indisponível.

## Validação local

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
60 passed
```

## Limites
- Ainda não houve teste real com token Telegram/Railway.
- O front-end HTML/JS do Mini App externo ainda não foi criado.
- A correção desta fase resolve o backend e a compatibilidade de chamada com Bot API 10.1 mantendo `aiogram>=3.28,<3.29`.
