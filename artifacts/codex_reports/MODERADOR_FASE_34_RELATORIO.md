# MODERADOR FASE 34 — Diagnóstico real com relatório .txt

Base: Fase33.

## Implementado

- Novo comando `/diagnostico`, restrito a usuários em `TIGRAO_BOT_ACCESS_USER_IDS`.
- O comando executa testes reais e não destrutivos:
  - configuração do deploy;
  - escrita/leitura em DATA_DIR;
  - escrita/leitura no banco de logs;
  - getMe;
  - getWebhookInfo;
  - getMyCommands;
  - getChat, getChatMember do bot e getChatAdministrators em grupos conhecidos;
  - resumo de permissões do bot por grupo;
  - logs recentes formatados.
- O relatório é salvo em `DATA_DIR/audit_reports/`.
- O relatório final é enviado em `.txt` por DM ao operador autorizado.
- O comando também aceita `/diagnostico -100...` para auditar um grupo específico.
- O comando não foi colocado no menu público de comandos para manter a interface principal limpa.

## Segurança

- Não executa ban, mute, purge, link, promoção, alteração de grupo nem ação destrutiva.
- Somente consulta a Bot API e grava logs internos de auditoria.
- Usuário não autorizado recebe a mensagem curta de acesso negado.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `110 passed`.
