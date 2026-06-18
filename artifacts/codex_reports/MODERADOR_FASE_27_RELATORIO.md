# MODERADOR FASE 27 — Fluxo limpo de mensagens do painel

Base usada: `tigrao-moderador-bot-fase26.zip`.

## Objetivo

Ajustar os fluxos que precisam criar uma nova mensagem no privado, sem manter a mensagem antiga do fluxo parada na conversa, e oferecer uma saída clara depois de confirmar ou cancelar.

## Alterações aplicadas

- Adicionado callback `panel` para voltar diretamente ao painel principal do grupo selecionado.
- `confirm_cancel_keyboard` agora mostra:
  - `✅ Confirmar`
  - `↩️ Cancelar`
  - `⬅️ Painel principal`
  - `✖️ Fechar`
- Adicionado `post_action_keyboard` para resultado final:
  - `⬅️ Painel principal`
  - `✖️ Fechar`
- Quando um fluxo por DM precisa receber texto/foto, a mensagem editada que virou instrução é registrada como mensagem transitória.
- Quando o operador envia o texto/foto válido e o bot cria uma nova confirmação/resultado, o bot tenta apagar a instrução antiga do fluxo.
- Ao confirmar ação destrutiva/avançada, o resultado pergunta se o operador quer voltar ao painel principal ou fechar.
- Ao cancelar uma ação pendente, o resultado também pergunta se quer voltar ao painel principal ou fechar.
- Os fluxos de DDX, aceite/recusa de entrada, warnings consultivos e confirmações avançadas foram adaptados para esse padrão quando criam nova mensagem.

## Segurança preservada

- A ação real continua executando somente depois do botão `✅ Confirmar`.
- O botão `⬅️ Painel principal` cancela pendências antes de voltar.
- O botão `✖️ Fechar` encerra a sessão e apaga a mensagem atual quando possível.
- O acesso continua restrito a `TIGRAO_BOT_ACCESS_USER_IDS`.

## Validação

Executado:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `94 passed`.
