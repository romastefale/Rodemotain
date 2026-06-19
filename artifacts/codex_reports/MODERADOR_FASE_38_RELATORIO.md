# Fase 38 — Diagnóstico total realmente total

## Correção aplicada

O comando `/diagnostico_total` não roda mais uma versão parcial quando `target_user_id` está ausente. Se o alvo não for informado, o bot recusa a execução e orienta o uso correto.

## Uso correto

Em DM:

```text
/diagnostico_total -1001234567890 123456789 CONFIRMO_TOTAL
```

Dentro do grupo:

```text
/diagnostico_total 123456789 CONFIRMO_TOTAL
```

O `target_user_id` precisa ser um membro comum de grupo de teste. Não pode ser owner, admin, usuário protegido/autorizado nem o próprio bot.

## Cobertura ampliada

Além dos testes já existentes de bot, grupo, mensagens, fixados, links, DDX e proteções, a Fase 38 adiciona cobertura real para:

- Auditoria formatada de administradores.
- Criação de mensagens de teste e purge em lote.
- Criação de mensagem e exclusão via ação `delmsg`.
- Edição de link de convite criado antes da revogação.
- Warning: adicionar, listar e limpar.
- Tag de membro: definir e limpar.
- Mutes destrutivos: `mute1h`, `mute24h`, `muteforever`, com desmute depois de cada etapa.
- Mute custom temporário e desmute.
- Promoção temporária, título customizado de admin e rebaixamento.
- Ban custom temporário e desbanimento.

## Validação

```text
117 passed
```
