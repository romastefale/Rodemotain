# Tigrão Moderador — Fase 08

## Objetivo

Atualizar o bot moderador para trabalhar com aiogram 3.28.x, considerar a superfície de permissões do Bot API 10.1 e permitir DDX hard com tempo definido pelo operador.

## Alterações aplicadas

1. Dependência principal fixada em `aiogram>=3.28,<3.29`.
2. DDX hard agora aceita filtro com duração customizada no painel:
   - `spam | 30m`
   - `link proibido | 2h`
   - `palavra proibida | 7d`
   - `golpe | permanente`
   - se o operador enviar apenas o texto, o filtro fica permanente.
3. Foram adicionados parsers para duração em segundos, minutos, horas, dias, semanas, meses aproximados e anos aproximados.
4. A tabela `tigrao_ddx_filters` ganhou `expires_at` com migração idempotente para bancos existentes.
5. O runtime do DDX ignora automaticamente filtros expirados.
6. A listagem do painel passa a exibir se o filtro é permanente ou quando expira.

## Limite técnico

O “tempo qualquer” do DDX aqui é tempo interno de validade do filtro. Não é a regra de `restrictChatMember` do Telegram. Como o DDX hard apaga mensagens futuras que batem no filtro, o bot só precisa manter o filtro ativo até `expires_at`.

## Permissões ainda relevantes para próximas fases

- `can_restrict_members`: ban, unban, mute, unmute, permissões padrão do grupo.
- `can_delete_messages`: apagar mensagem, purge, apagar tópico inteiro.
- `can_pin_messages`: fixar/desfixar/limpar fixados em grupos.
- `can_change_info`: alterar título, descrição, foto e configurações.
- `can_invite_users`: links, aprovação de entrada, convite.
- `can_manage_topics`: criar, editar, fechar, reabrir, ocultar e apagar tópicos.
- `can_promote_members`: promover/rebaixar administradores.
- `can_manage_tags`: tags de membros regulares.
- `can_manage_chat`: leitura operacional como log de eventos, boosts, membros ocultos e anti-spam/slow mode.

## Validação local

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `15 passed`.
