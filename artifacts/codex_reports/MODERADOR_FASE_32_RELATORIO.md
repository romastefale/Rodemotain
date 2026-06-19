# Rodemotain Moderador — Fase 32

Base: `tigrao-moderador-bot-fase31.zip`.

## Aplicações

- Auditoria de administradores/bots reescrita em linguagem compreensível.
- Promoção/rebaixamento com pré-validação real: verifica se o alvo está no grupo, bloqueia criador/administrador não editável e ajusta direitos para não tentar conceder privilégios que o bot não possui.
- Menu de solicitações de entrada dividido em subcategorias: pedidos pendentes, criação de links e autorização automática.
- Reações movidas para a categoria Mensagens.
- Prompt de reações e apagamento/purge passa a mostrar as últimas 5 mensagens registradas em formato de quote simples, com message_id e autor.
- Logs formatados de forma mais operacional, com ação humanizada, resultado, autor, alvo, grupo, superfície, detecção, detalhe e metadados úteis.
- DDX hard agora aceita formato por quebra de linha: primeira linha filtro, segunda linha tempo. O formato legado com `|` continua aceito para compatibilidade.
- Cache local de últimas mensagens do grupo para auxiliar ações por message_id/link.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `107 passed`.
