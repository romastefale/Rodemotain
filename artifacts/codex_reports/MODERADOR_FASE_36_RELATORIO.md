# Rodemotain Moderador — Fase 36

## Escopo

Conclusão da sessão de log/auditoria do diagnóstico total.

## Alterações

- Separação explícita entre registro de eventos e registro de erros no relatório final.
- Inclusão de raw data de erro com tipo de exceção, mensagem, repr, traceback e atributos úteis quando existirem.
- Inclusão de raw data de eventos em JSON seguro.
- Captura temporária de logs do processo Python durante `/diagnostico_total`.
- Classificação de falhas por tipo: permissão, alvo/chat, rede ou execução.
- Relatório informa que será apagado em 1 hora.
- Arquivo local do relatório é agendado para remoção após 1 hora.
- Mensagem/documento enviado na DM também é agendado para remoção após 1 hora quando o Telegram permitir.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `114 passed`.
