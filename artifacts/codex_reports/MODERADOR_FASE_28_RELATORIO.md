# Rodemotain Moderador — Fase 28

## Objetivo

Ajustar a geração de link de entrada para permitir link direto e preservar o link gerado em mensagem individual separada, fora do fluxo editável/apagável do painel.

## Alterações aplicadas

- Adicionado botão `✅ Criar link direto` no menu de solicitações de entrada.
- Mantido botão `🔗 Criar link com solicitação` para fluxo com aprovação/fila.
- Link direto usa `create_chat_invite_link(..., creates_join_request=False)`.
- Link com solicitação continua usando `creates_join_request=True` e preserva opção de autoaceite por IDs.
- Todo link criado pelo menu de entrada agora é enviado em mensagem individual separada.
- Link gerado por `Exportar link primário` e `Criar link direto/completo` também é enviado em mensagem individual separada quando a ação confirmar com sucesso.
- O painel continua editável e mostra apenas status/orientação, sem depender do link ficar dentro da mensagem do fluxo.
- Prompt de link completo atualizado para explicar link direto, link permanente direto e link com aprovação.

## Validação

Executado localmente:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `98 passed`.
