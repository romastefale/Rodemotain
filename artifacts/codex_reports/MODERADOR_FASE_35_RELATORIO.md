# Rodemotain Moderador — Fase 35

## Escopo

Foi adicionado um modo de diagnóstico total real para grupos de teste.

## Novo comando

`/diagnostico_total`

O comando é restrito aos IDs definidos em `TIGRAO_BOT_ACCESS_USER_IDS` e exige confirmação explícita `CONFIRMO_TOTAL`.

Formatos aceitos:

- Em DM: `/diagnostico_total -1001234567890 CONFIRMO_TOTAL`
- Em DM com alvo: `/diagnostico_total -1001234567890 123456789 CONFIRMO_TOTAL`
- Dentro do grupo: `/diagnostico_total CONFIRMO_TOTAL`
- Dentro do grupo com alvo: `/diagnostico_total 123456789 CONFIRMO_TOTAL`

## O que testa

O modo total executa ações reais e registra resultado em relatório `.txt`:

- getMe
- getChat
- getChatMember do bot
- getChatAdministrators
- envio de mensagem de teste
- edição de mensagem de teste
- fixar e desfixar mensagem de teste
- criar e revogar link direto adicional
- criar e revogar link com solicitação
- gerar novo link principal do bot
- alterar e restaurar título do grupo
- alterar e restaurar descrição do grupo
- fechar grupo temporariamente e restaurar permissões
- criar/remover filtro DDX temporário
- ativar/desativar anti-flood, anti-raid e captcha
- apagar mensagem de teste

Com `target_user_id`, também testa:

- getChatMember do alvo
- warning e limpeza de warning
- mute e unmute
- promover temporariamente
- título customizado de admin
- rebaixar
- ban e unban

## Segurança

O comando não aparece no menu público do Telegram. Ele exige operador autorizado e confirmação textual explícita. O relatório informa falhas, pulos e ações executadas. Use somente em grupo de teste.

## Validação

Executado:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `112 passed`.
