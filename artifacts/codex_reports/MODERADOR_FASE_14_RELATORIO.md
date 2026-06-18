# Tigrão Moderador — Fase 14

Base usada: `tigrao-moderador-bot-fase12.zip`.

Escopo aplicado em duas etapas, conforme pedido:

## ETAPA01 — Administração pesada e links

Implementado:

- promover administrador com perfis `leve`, `moderador`, `admin`, `total` e flags customizadas;
- rebaixar administrador via `promote_chat_member` com permissões falsas;
- título customizado de administrador;
- banir e desbanir sender chat/canal;
- exportar link primário do bot;
- criar link completo com nome, duração, limite e modo de solicitação de entrada;
- editar link criado pelo bot;
- revogar link criado pelo bot.

Correções adicionais da ETAPA01:

- superfície de promoção ampliada para direitos atuais: stories, mensagens de canal, direct messages de canal e tags;
- todas as ações passam pelo fluxo padrão do painel: selecionar ação, enviar parâmetros por DM, revisar, confirmar/cancelar;
- ações sem texto também exigem confirmação.

## ETAPA02 — Mini App, foto, tópicos, tags, warnings e proteções automáticas

Implementado:

- envio de Mini App em `chat_join_request` quando o Telegram entrega `query_id` e `TIGRAO_JOIN_REQUEST_WEBAPP_URL` está configurada;
- endpoint seguro `/telegram/join-request-query` para o backend/Mini App resolver a query com `approve`, `decline` ou `queue`, exigindo `WEBHOOK_SECRET` quando configurado;
- alterar foto do grupo por envio de imagem/foto na DM do painel;
- remover foto do grupo;
- criar tópico com cor oficial permitida;
- editar tópico;
- fechar/reabrir tópico;
- apagar tópico;
- limpar fixados de tópico;
- fechar/reabrir/ocultar/reexibir tópico geral;
- renomear tópico geral;
- limpar fixados do tópico geral;
- tag real de membro via `set_chat_member_tag`;
- advertências e reincidência local por usuário/grupo;
- listagem e limpeza de advertências;
- configuração persistente de anti-flood;
- runtime anti-flood com exclusão opcional de mensagem e mute automático;
- configuração persistente de anti-raid;
- runtime anti-raid em solicitações de entrada com ações `queue`, `decline` ou `lock`;
- configuração persistente de captcha;
- captcha por DM com `/captcha código`, aprovação automática da solicitação quando correto.

## Segurança e navegação

- Todas as ações destrutivas ou administrativas relevantes mantêm confirmação antes da execução.
- `Voltar` e `Cancelar` preservam o padrão de limpar ação pendente.
- Permissões são revalidadas antes da execução real.
- Permissões de tópico foram ajustadas conforme método: `deleteForumTopic` usa `can_delete_messages`, limpar fixados usa `can_pin_messages`, e criar/editar/fechar/reabrir/ocultar usa `can_manage_topics`.
- A variável principal de acesso continua sendo `TIGRAO_BOT_ACCESS_USER_IDS`.

## Validação local

Executado no pacote final:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
49 passed
```

## Limites honestos

- Não houve teste com token real do Telegram nem em Railway.
- O Mini App de join request foi integrado no lado do bot e recebeu endpoint de resolução, mas o HTML/JS do Mini App externo não foi criado neste ZIP.
- Custom emoji de tópico não foi automatizado por catálogo; a criação/edição usa nome e cores oficiais permitidas.
