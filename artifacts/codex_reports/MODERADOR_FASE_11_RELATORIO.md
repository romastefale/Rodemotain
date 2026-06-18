# MODERADOR FASE 11 — Auditoria e revisão de erros

Base auditada: `tigrao-moderador-bot-fase10.zip`.

## Objetivo
Auditar navegação, botões, confirmação, edição/apagamento de mensagens do painel e aderência das funções novas ao padrão de segurança/usabilidade do código.

## Correções aplicadas

1. Ações avançadas não executam mais imediatamente após o texto enviado por DM.
   - `bantime`, `mutetime`, `purge`, `pin`, `unpin`, `settitle`, `setdesc`, `react1` e `reactall` agora apenas preparam `pending_advanced_action`.
   - A execução real ocorre somente no callback `confirm`.

2. Ações sem texto que alteram o grupo também passaram a exigir confirmação.
   - `lock`, `unlock` e `unpinall` agora exibem tela de confirmação antes de executar.

3. Proteção de alvo reforçada para ban/mute com tempo livre.
   - Antes de executar `bantime` ou `mutetime`, o fluxo revalida o bot, o alvo e bloqueia dono/autorizado, administrador/criador ou o próprio bot.

4. Navegação padronizada.
   - Criado `_go_back` para limpar pendências e voltar ao menu correto.
   - Prompts guardam `nav_back` para retornar a `act`, `join`, `ddx` ou `logs` conforme a superfície de origem.

5. Consulta de pendentes separada de ação.
   - `Ver pendentes 2h` deixou de ativar automaticamente `join_pending_id`.
   - Agora é apenas consulta. Aceitar/recusar dependem dos botões próprios.

6. Edição do painel ficou mais robusta.
   - `_safe_edit` agora trata falha de `edit_text` em mensagem antiga, apagada ou já modificada e cai para `callback.answer()` sem derrubar o fluxo.

7. Purge ficou mais tolerante para entrada humana.
   - Além de `10-12`, agora aceita `10 - 12`.

## Auditoria do escopo implementado

### Implementado e revisado nesta fase
- Confirmação por botão para ações destrutivas antigas.
- Confirmação por botão para ações avançadas novas.
- Confirmação por botão para alteração de dados do grupo.
- Confirmação por botão para remoção de reações.
- Confirmação por botão para purge em lote.
- Navegação com Voltar/Fechar preservada.
- Consulta de pendentes sem efeito colateral.
- Proteção de alvo em ban/mute customizado.
- Fallback de edição do painel.

### Ainda fora do escopo implementado
- Promover/rebaixar administradores e definir título customizado de admin.
- Banir/desbanir sender chat/canal.
- Gerenciamento completo de links: exportar primário, editar link, revogar link, subscription invite link.
- Fluxo de join request query com Mini App (`answerChatJoinRequestQuery` / `sendChatJoinRequestWebApp`).
- Alterar/remover foto do grupo por upload.
- Gerenciamento completo de tópicos/fórum: criar, editar, fechar, reabrir, apagar tópico, limpar fixados de tópico.
- Tags de membros regulares (`setChatMemberTag`).
- Rotinas automáticas anti-flood, anti-raid, captcha, advertências e reincidência.
- Teste empírico com token real no Telegram/Railway.

## Validação executada

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
34 passed
```
