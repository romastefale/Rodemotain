# Relatório — Tigrão Moderador — Fase 06

> Nota: este relatório é histórico. A Fase 07 substitui a regra de flags e deixa as funções reais do moderador ativas por padrão, usando `TIGRAO_BOT_ACCESS_USER_IDS` como variável funcional de acesso ao painel.

## Resumo

Apliquei uma fase de continuidade no ZIP isolado `tigrao-moderador-bot(1).zip`, sem reinserir módulos musicais do TR4. O foco foi tornar o bot moderador mais operacional fora do webhook e melhorar a ação de apagar mensagem.

## Alterações realizadas

- `app/bot/group_registry.py`
  - Normaliza `chat.type` quando vier como enum/objeto do aiogram.
  - Evita perder grupos em runtime por diferença entre string e enum.

- `app/plugins/tigrao_fsm/parsers.py`
  - Adiciona `ParsedMessageRef`.
  - Adiciona `parse_message_ref()` para aceitar `message_id` bruto e links Telegram `t.me`.
  - Valida links privados `/c/<chat>/<mensagem>` contra o grupo selecionado.

- `app/plugins/tigrao_fsm/routers/panel.py`
  - Registra grupo ao usar `/tigrao` em grupo.
  - Adiciona handler de `chat_join_request` para modo polling.
  - Adiciona handler silencioso de mensagem de grupo para registrar grupos e rodar DDX hard no modo polling.
  - A ação “Apagar mensagem” agora aceita link `t.me` além de `message_id`.

- `pytest.ini`
  - Adiciona `pythonpath = .` e `asyncio_mode = auto`, permitindo `pytest -q` diretamente.

- `tests/test_tigrao_moderador_phase6.py`
  - Cobre parser de links de mensagem.
  - Cobre rejeição de link de outro grupo.
  - Cobre presença dos handlers de polling.
  - Cobre normalização de `chat.type` no registro de grupos.
  - Cobre DDX hard com filtro e permissão.

## Ajuste de segurança

As flags `TIGRAO_FSM_DESTRUCTIVE_ACTIONS_ENABLED` e `TIGRAO_FSM_DDX_HARD_ENABLED` agora têm default seguro desligado no código. O `.env.example` continua mostrando `true` para uso intencional do bot moderador, mas a ativação em produção fica explícita por variável de ambiente.

## Garantia de isolamento musical

Não foram adicionados imports, serviços, modelos, rotas ou arquivos musicais. O teste `test_no_music.py` permanece ativo.

## Validações executadas

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
8 passed
```

## Limitações ainda existentes

- Reações reais continuam como placeholder seguro.
- O bot ainda depende de teste real no Telegram para validar permissões efetivas, entrega de DM e comportamento final de Bot API.
- A limpeza automática de mensagens futuras por DDX em polling foi conectada, mas o comportamento exato de propagação de handlers depende do aiogram em produção; o webhook continua sendo a superfície mais determinística porque executa `before_dispatch` antes do dispatcher.
