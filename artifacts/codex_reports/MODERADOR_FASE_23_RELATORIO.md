# MODERADOR FASE 23 — ajustes de acesso, start/help e mensagens temporárias

Base usada: `tigrao-moderador-bot-fase22.zip`.

## Alterações aplicadas

1. Criada mensagem curta única para usuário não autorizado/caminho incorreto de entrada:

```text
Acesso negado.
Use o botão para solucionar a entrada no grupo ou comando /captcha
```

2. `/captcha` foi removido da lista visual do `/start`.

3. O menu de comandos registrado no Telegram agora mostra apenas:

```text
/start
/help
/tigrao
```

O comando `/captcha` continua funcionando como fallback operacional, mas não fica exposto no menu principal.

4. `/start` e `/help` em grupos/supergrupos agora respondem normalmente, mas a resposta do bot é programada para apagamento automático em 5 minutos.

5. Usuário não autorizado em `/start` ou `/help` recebe apenas a mensagem curta de acesso negado.

## Observação de comportamento

A remoção automática é aplicada à mensagem enviada pelo bot em grupo. O comando enviado pelo usuário não é apagado automaticamente nesta fase.

## Validação

Executado:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local:

```text
79 passed
```
