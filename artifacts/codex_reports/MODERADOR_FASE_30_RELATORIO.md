# Rodemotain Moderador — Fase 30

## Escopo aplicado

Aplicada atualização solicitada após leitura dos logs Railway e revisão da navegação do painel.

### Remoção de tópicos da interface

A categoria `🧩 Tópicos` foi removida da navegação principal e do menu de ações. Os callbacks de tópicos também foram retirados da lista pública de callbacks aceitos pelo painel, impedindo uso normal por botões antigos de interface.

O código baixo nível de ações de fórum/tópicos foi preservado como compatibilidade interna e histórico técnico, mas não fica exposto no painel operacional.

### Links de convite

A nomenclatura de `Exportar link primário` foi substituída na interface por `Gerar novo link principal` / `Gerar novo link principal do bot`.

O texto de confirmação foi reforçado para explicar que esta ação gera um novo link principal do bot e pode fazer o link principal anterior gerado pelo bot deixar de funcionar. Links criados por outros administradores não são reaproveitados pelo bot.

A criação de link adicional permanece separada e o link gerado continua sendo enviado em mensagem individual separada, fora do fluxo editável/apagável do painel.

### Logs e acabamento web

Adicionada rota `/favicon.ico`, usando o mesmo ícone público/cacheado do bot utilizado pelo Mini App. Isso evita o 404 visto em navegador comum.

Adicionado detector de resultado não tratado do dispatcher. Quando o `feed_update` retornar resultado compatível com `UNHANDLED`, o backend registra `telegram_update_unhandled` com `update_id` e tipo do update, sem gravar payload sensível.

## Validação local

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local: `100 passed`.
