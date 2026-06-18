# Relatório — Tigrão Moderador — Fase 07

## Pedido aplicado

O bot moderador foi ajustado para manter as funções reais do pacote ativas por padrão. A configuração funcional de autorização do painel passa a ser uma única variável: `TIGRAO_BOT_ACCESS_USER_IDS`.

## Alterações realizadas

- `app/config/settings.py`
  - Criada a variável principal `TIGRAO_BOT_ACCESS_USER_IDS`.
  - `CODE_OWNER_IDS`, `OWNER_IDS`, `TR3_CODE_OWNER_IDS`, `TIGRAO_FSM_MODERATOR_IDS`, `MODERATOR_IDS` e `TR3_TIGRAO_FSM_MODERATOR_IDS` permanecem apenas como aliases de compatibilidade para deploys antigos.
  - Removidas as flags públicas de moderação: `TIGRAO_FSM_ENABLED`, `TIGRAO_FSM_DESTRUCTIVE_ACTIONS_ENABLED`, `TIGRAO_FSM_DDX_HARD_ENABLED` e `TIGRAO_FSM_REACTIONS_ENABLED`.

- `app/main.py`
  - O plugin moderador é montado diretamente no startup quando há token configurado.
  - `/readyz` agora indica `moderator_active: true` em vez de depender de flag de ativação.

- `app/plugins/tigrao_fsm/routers/panel.py`
  - A autorização do `/tigrao` usa somente `TIGRAO_BOT_ACCESS_USER_IDS`.
  - O painel mostra ações destrutivas e DDX hard por padrão.
  - Foram removidos bloqueios de interface que pediam ativação por variável de ambiente.

- `app/plugins/tigrao_fsm/runtime/ddx_runtime.py`
  - O runtime DDX hard não depende mais de flag global.
  - Continua seguro por condição real: só apaga se houver filtro ativo cadastrado no grupo e o bot tiver permissão de apagar mensagens.

- `.env.example`
  - Removida a seção de flags de moderação.
  - Mantida apenas a variável funcional de acesso ao painel: `TIGRAO_BOT_ACCESS_USER_IDS`.

- `README.md`
  - Atualizado para documentar que as funções reais ficam ativas por padrão.
  - Documentado que `TIGRAO_BOT_ACCESS_USER_IDS` é a configuração nova para quem pode abrir e operar o bot.

- `tests/test_tigrao_moderador_phase7.py`
  - Adicionados testes para garantir a nova variável única de acesso.
  - Adicionados testes para garantir que as antigas flags não aparecem no `.env.example` nem comandam o runtime.
  - Adicionado teste estático para garantir que ações e DDX aparecem no painel sem guardas de flag.

## Funções que ficam ativas por padrão

- Painel `/tigrao`.
- Seleção de grupos registrados.
- Verificação de permissões do bot no grupo.
- Solicitações de entrada.
- Autoaceite por ID autorizado.
- Ações destrutivas com confirmação explícita.
- Apagar mensagem por `message_id` ou link `t.me`.
- DDX hard por filtro textual cadastrado.
- Logs de uso, entrada, moderação e erro.
- Healthcheck `/healthz`.

## Observação honesta

O módulo de reações continua sendo stub reservado e não foi exposto como função real nesta fase. Eu não marquei esse módulo como ativo porque ele ainda não executa uma ação efetiva; expor botão falso seria pior do que manter fora do painel.

## Validação executada

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
11 passed
```

## Limitação restante

A validação local garante compilação e testes de lógica estática/unitária. O comportamento final de permissões administrativas, DM aberta e chamadas reais da Bot API ainda precisa ser validado em Telegram/Railway com token real.
